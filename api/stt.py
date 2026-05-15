"""
STT endpoints.

POST  /stt/transcribe   — 오디오 파일 업로드 → 텍스트 변환 (REST)
WS    /ws/stt/live      — 실시간 스트리밍 STT (WebSocket)
POST  /stt/correct      — STT 결과 교과 특화 보정 (REST)
WS    /ws/stt           — 실시간 보정 (WebSocket)
"""

import asyncio
import json

from fastapi import APIRouter, File, UploadFile, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from services.stt import clova_ws_connect, transcribe_file
from services.stt_correction import correct_stt, correct_stt_stream

router = APIRouter()


# ── REST: 파일 업로드 STT ────────────────────────────────────────────────────

@router.post("/stt/transcribe")
async def stt_transcribe(file: UploadFile = File(...)):
    """오디오 파일(PCM/WAV 권장)을 업로드하면 한국어 텍스트로 변환합니다."""
    audio_bytes = await file.read()
    text = await transcribe_file(audio_bytes)
    return {"text": text}


# ── WebSocket: 실시간 스트리밍 STT ───────────────────────────────────────────

@router.websocket("/ws/stt/live")
async def stt_live(ws: WebSocket):
    """
    실시간 STT WebSocket (Clova Speech Recognition).

    오디오 포맷: PCM 16kHz, 16-bit, mono (Little Endian)

    클라이언트 → 서버: binary 오디오 청크
                       또는 text "end" (스트림 종료)
    서버 → 클라이언트: {"text": "인식 결과", "is_final": bool}
                       {"error": "에러 메시지"}
    """
    await ws.accept()
    try:
        async with clova_ws_connect() as clova_ws:
            async def client_to_clova():
                try:
                    while True:
                        data = await ws.receive()
                        if "bytes" in data:
                            await clova_ws.send(data["bytes"])
                        elif data.get("text") == "end":
                            await clova_ws.close()
                            break
                except Exception:
                    await clova_ws.close()

            async def clova_to_client():
                try:
                    async for message in clova_ws:
                        result = json.loads(message)
                        transcription = result.get("transcription", {})
                        text = transcription.get("text", "").strip()
                        if text:
                            await ws.send_json({
                                "text": text,
                                "is_final": transcription.get("type") == "FINAL",
                            })
                except Exception:
                    pass

            await asyncio.gather(client_to_clova(), clova_to_client())

    except WebSocketDisconnect:
        pass
    except Exception as e:
        await ws.send_json({"error": str(e)})
        await ws.close()


# ── REST: 교과 특화 보정 ──────────────────────────────────────────────────────

class CorrectionRequest(BaseModel):
    text: str
    subject: str
    grade: str
    school: str
    top_k: int = 5


@router.post("/stt/correct")
async def stt_correct(req: CorrectionRequest):
    corrected = await correct_stt(req.text, req.subject, req.grade, req.school, req.top_k)
    return {"corrected": corrected}


# ── WebSocket: 실시간 교과 특화 보정 ─────────────────────────────────────────

@router.websocket("/ws/stt")
async def stt_correction_ws(ws: WebSocket):
    """
    STT 보정 WebSocket.

    1. 첫 메시지: JSON 세션 컨텍스트
       {"subject": "사회", "grade": "1학년", "school": "중학교", "top_k": 5}
    2. 이후 메시지: 보정할 텍스트 (plain string)
    3. 서버 응답: 보정 토큰 스트리밍 → {"done": true}
    """
    await ws.accept()
    try:
        context = json.loads(await ws.receive_text())

        while True:
            stt_chunk = await ws.receive_text()
            if not stt_chunk.strip():
                continue

            async for token in correct_stt_stream(
                stt_chunk,
                subject=context.get("subject", ""),
                grade=context.get("grade", ""),
                school=context.get("school", ""),
                top_k=context.get("top_k", 5),
            ):
                await ws.send_text(token)

            await ws.send_json({"done": True})

    except WebSocketDisconnect:
        pass
    except Exception as e:
        await ws.send_json({"error": str(e)})
        await ws.close()
