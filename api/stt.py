import json
from collections.abc import AsyncGenerator

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from services.stt.clova_stt import ResultType, stream_clova_stt
from services.stt.current_subject import get_current_subject
from services.stt.llm_processor import process_stt_text

router = APIRouter(
    prefix="/ws",
    tags=["STT"],
)


async def _audio_chunks_from_ws(ws: WebSocket) -> AsyncGenerator[bytes, None]:
    """WebSocket에서 binary 음성 청크를 yield합니다.
    {"type": "end"} 텍스트 메시지를 받으면 정상 종료합니다 (연결은 유지).
    """
    while True:
        message = await ws.receive()
        if message["type"] == "websocket.disconnect":
            return
        if "text" in message and message["text"]:
            try:
                data = json.loads(message["text"])
                if data.get("type") == "end":
                    return
            except (json.JSONDecodeError, ValueError):
                pass
        if "bytes" in message and message["bytes"]:
            yield message["bytes"]


# @router.websocket("/stt")
# async def stt_websocket(
#     ws: WebSocket,
#     school_kind: str,
#     education_office_code: str,
#     school_code: str,
#     grade: str,
#     class_nm: str,
# ):
#     """
#     실시간 STT WebSocket 엔드포인트.

#     연결 파라미터 (query string):
#       school_kind, education_office_code, school_code, grade, class_nm

#     클라이언트 → 서버: binary 음성 청크 (PCM 16kHz mono)
#     서버 → 클라이언트: JSON 문자열
#       partial: {"type": "partial", "text": "...", "subject": "수학", "tags": []}
#       final:   {"type": "final",   "text": "...", "subject": "수학", "tags": [...]}
#     """
#     await ws.accept()

#     subject = await get_current_subject(
#         school_kind=school_kind,
#         education_office_code=education_office_code,
#         school_code=school_code,
#         grade=grade,
#         class_nm=class_nm,
#     )

#     try:
#         audio_gen = _audio_chunks_from_ws(ws)

#         async for stt_result in stream_clova_stt(audio_gen):
#             if stt_result.type == ResultType.PARTIAL:
#                 await ws.send_text(json.dumps({
#                     "type": "partial",
#                     "text": stt_result.text,
#                     "subject": subject,
#                     "tags": [],
#                 }, ensure_ascii=False))

#             elif stt_result.type == ResultType.FINAL:
#                 llm_result = await process_stt_text(
#                     text=stt_result.text,
#                     subject=subject,
#                 )

#                 await ws.send_text(json.dumps({
#                     "type": "final",
#                     "text": llm_result.corrected_text,
#                     "subject": subject,
#                     "tags": [
#                         {"type": tag.type, "content": tag.content}
#                         for tag in llm_result.tags
#                     ],
#                 }, ensure_ascii=False))

#     except WebSocketDisconnect:
#         pass


@router.websocket("/stt")
async def stt_raw_websocket(ws: WebSocket):
    """
    과목 보정 없이 STT 결과만 실시간으로 전송하는 WebSocket 엔드포인트.

    클라이언트 → 서버: binary 음성 청크 (PCM 16kHz mono)
    서버 → 클라이언트: JSON 문자열
      {"type": "final", "text": "..."}
    """
    await ws.accept()

    try:
        async for stt_result in stream_clova_stt(_audio_chunks_from_ws(ws)):
            await ws.send_text(json.dumps({
                "type": stt_result.type.value,
                "text": stt_result.text,
            }, ensure_ascii=False))

    except WebSocketDisconnect:
        pass
