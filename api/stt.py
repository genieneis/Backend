import asyncio
import json
import logging
from collections.abc import AsyncGenerator

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

from services.stt.clova_stt import ResultType, stream_clova_stt
from services.stt.current_subject import get_current_subject
from services.stt.llm_processor import process_stt_batch, process_stt_text
from services.stt.stt_session import STTSession

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


@router.websocket("/stt/ai")
async def stt_ai_websocket(
    ws: WebSocket,
    school_level: str,
    subject_name: str,
    grade_band: str | None = None,
):
    """
    과목 맞춤 STT 보정 WebSocket 엔드포인트.

    연결 파라미터 (query string):
      school_level: "elementary" | "middle" | "high"
      subject_name: 과목명 (예: 과학, 물리학, 공통수학1)
      grade_band:   초등만 필요. 프론트에서 변환해서 전달 ("1~2학년"|"3~4학년"|"5~6학년")

    클라이언트 → 서버: binary 음성 청크 (PCM 16kHz mono)
                       또는 {"type": "end"} 텍스트로 종료 신호

    서버 → 클라이언트:
      {"type": "session_ready", "matched": bool, "subject_name": str, "domain_count": int}
      {"type": "partial", "text": str}
      {"type": "final_raw", "id": int, "text": str}
      {"type": "ai_corrected", "domain": str|null, "sentences": [{"id", "ai_text", "tags"}]}
      {"type": "done"}
    """
    await ws.accept()

    logger.info(
        "[STT 세션 시작] school_level=%s | subject_name=%s | grade_band=%s",
        school_level, subject_name, grade_band,
    )

    session = await STTSession.create(
        school_level=school_level,
        grade_band=grade_band,
        subject_name=subject_name,
    )

    if session.matched:
        for ts in session.term_sets:
            logger.info(
                "[용어사전 로드] domain=%s | core_keywords=%s | priority_terms=%s",
                ts.domain, ts.core_keywords, ts.priority_terms,
            )
    else:
        logger.info("[용어사전 로드] 매칭된 과목 없음 (subject_name=%s)", session.subject_name)

    await ws.send_text(json.dumps({
        "type": "session_ready",
        "matched": session.matched,
        "subject_name": session.subject_name,
        "domain_count": len(session.term_sets),
    }, ensure_ascii=False))

    flush_lock = asyncio.Lock()

    async def do_flush():
        async with flush_lock:
            if not session._pending:
                return
            prev_domain = session.detector.current_domain
            batch, domain, priority_terms, source_terms = session.flush()

            logger.info(
                "[도메인 체크] domain=%s | batch_ids=%s",
                domain, [s.id for s in batch],
            )
            if domain and domain != prev_domain:
                logger.info(
                    "[도메인 확정] %s → %s",
                    prev_domain or "미확정", domain,
                )

            try:
                results = await process_stt_batch(
                    sentences=batch,
                    subject_name=session.subject_name,
                    domain=domain,
                    priority_terms=priority_terms,
                    source_terms=source_terms,
                    matched=session.matched,
                    domain_names=[ts.domain for ts in session.term_sets] or None,
                )
            except Exception as e:
                logger.error("[LLM 보정 실패] %s", e)
                return

            payload = {
                "type": "ai_corrected",
                "domain": domain,
                "sentences": [
                    {"id": r.id, "ai_text": r.ai_text}
                    for r in results
                ],
            }
            
            await ws.send_text(json.dumps(payload, ensure_ascii=False))

    async def timer_task():
        while True:
            await asyncio.sleep(1)
            if session.should_flush():
                await do_flush()

    timer = asyncio.create_task(timer_task())

    # partial delta를 누적해 완성 문장을 만드는 버퍼
    partial_buffer = ""

    try:
        async for stt_result in stream_clova_stt(_audio_chunks_from_ws(ws)):
            if stt_result.type == ResultType.PARTIAL:
                partial_buffer += stt_result.text
                await ws.send_text(json.dumps({
                    "type": "partial",
                    "text": stt_result.text,
                }, ensure_ascii=False))

            elif stt_result.type == ResultType.FINAL:
                # 완성 문장 = 누적된 partial + 마지막 final delta
                full_sentence = (partial_buffer + stt_result.text).strip()
                partial_buffer = ""

                sid = session.add_final(full_sentence)
                await ws.send_text(json.dumps({
                    "type": "final_raw",
                    "id": sid,
                    "text": stt_result.text,  # 프론트는 자체 partial 누적하므로 delta만 전달
                }, ensure_ascii=False))
                if session.should_flush():
                    await do_flush()

        # 스트림 종료 후 잔여 문장 처리
        if session._pending:
            await do_flush()

        await ws.send_text(json.dumps({"type": "done"}, ensure_ascii=False))

    except WebSocketDisconnect:
        pass
    finally:
        timer.cancel()


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

        await ws.send_text(json.dumps({"type": "done"}, ensure_ascii=False))

    except WebSocketDisconnect:
        pass
