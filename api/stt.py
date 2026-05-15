"""
STT correction endpoints.

WebSocket  /ws/stt  — real-time streaming correction
POST       /stt/correct — single-shot REST correction
"""

import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from services.stt_correction import correct_stt, correct_stt_stream

router = APIRouter()


class STTRequest(BaseModel):
    text: str
    subject: str
    grade: str
    school: str
    top_k: int = 5


class STTResponse(BaseModel):
    corrected: str


@router.post("/stt/correct", response_model=STTResponse)
async def stt_correct(req: STTRequest):
    corrected = await correct_stt(req.text, req.subject, req.grade, req.school, req.top_k)
    return STTResponse(corrected=corrected)


@router.websocket("/ws/stt")
async def stt_websocket(ws: WebSocket):
    """
    WebSocket protocol:
      1. Client sends JSON context once:
         {"subject": "사회", "grade": "1학년", "school": "중학교", "top_k": 5}
      2. Client sends STT text chunks as plain strings repeatedly.
      3. Server streams corrected tokens back as plain strings per chunk.
      4. Server sends {"done": true} when each chunk correction finishes.
    """
    await ws.accept()
    context: dict | None = None

    try:
        # First message must be the session context
        raw = await ws.receive_text()
        context = json.loads(raw)

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
