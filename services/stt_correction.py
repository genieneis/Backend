import os
from typing import AsyncGenerator
from typing import Optional

import anthropic

from .vector_search import search_curriculum

CLAUDE_MODEL = "claude-sonnet-4-6"

_client: Optional[anthropic.AsyncAnthropic] = None


def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    return _client


SYSTEM_PROMPT = (
    "당신은 한국 교과 수업 음성인식(STT) 결과를 교정하는 전문가입니다. "
    "교과서 내용을 참고하여 STT 오인식된 전문 용어, 교과 개념어, 고유명사를 정확하게 교정하십시오. "
    "원문의 의미와 문장 구조는 최대한 유지하고, 교정된 텍스트만 출력하십시오."
)


def _build_user_message(stt_text: str, subject: str, grade: str, school: str, context_texts: list[str]) -> str:
    context_block = "\n".join(f"- {t}" for t in context_texts) if context_texts else "참고 자료 없음"
    return (
        f"[수업 정보]\n학교: {school}  학년: {grade}  교과: {subject}\n\n"
        f"[교과서 참고 내용]\n{context_block}\n\n"
        f"[STT 원문]\n{stt_text}\n\n"
        f"[교정 결과]"
    )


async def correct_stt_stream(
    stt_text: str,
    subject: str,
    grade: str,
    school: str,
    top_k: int = 5,
) -> AsyncGenerator[str, None]:
    """Yield corrected text tokens as they stream from Claude."""
    context_texts = search_curriculum(stt_text, subject, grade, school, top_k=top_k)

    async with _get_client().messages.stream(
        model=CLAUDE_MODEL,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": _build_user_message(stt_text, subject, grade, school, context_texts),
            }
        ],
    ) as stream:
        async for text in stream.text_stream:
            yield text


async def correct_stt(
    stt_text: str,
    subject: str,
    grade: str,
    school: str,
    top_k: int = 5,
) -> str:
    """Return fully corrected text (non-streaming, for REST endpoint)."""
    chunks = []
    async for chunk in correct_stt_stream(stt_text, subject, grade, school, top_k):
        chunks.append(chunk)
    return "".join(chunks)
