import json
import os
from dataclasses import dataclass, field
from typing import Optional

from fastapi import HTTPException
from openai import AsyncOpenAI, RateLimitError, APIStatusError


SYSTEM_PROMPT = """\
당신은 청각장애 학생을 위한 수업 내용 요약 도우미.
수업 중 STT로 변환된 텍스트를 입력받아 학생이 복습하기 쉬운 형태로 요약.

다음 항목을 분석하여 반드시 아래 JSON 형식으로만 응답하세요. 설명이나 마크다운 없이 JSON만 출력.

{
  "topic": "수업 주제 (한 문장)",
  "summary": "전체 수업 내용 요약 (요약 분량은 전체적으로 800~1000자.)",
  "key_concepts": ["핵심 개념 또는 키워드 목록"],
  "important_points": ["중요 포인트 목록 (교사가 강조한 내용)"],
  "homework": "숙제/과제 안내 (없으면 null)",
  "test_info": "시험/평가 관련 안내 (없으면 null)"
}
"""


@dataclass
class LessonSummary:
    topic: str
    summary: str
    key_concepts: list[str] = field(default_factory=list)
    important_points: list[str] = field(default_factory=list)
    homework: Optional[str] = None
    test_info: Optional[str] = None


def get_gpt_client() -> AsyncOpenAI:
    api_key = os.getenv("GPT_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="GPT_API_KEY 환경 변수가 설정되어 있지 않습니다.",
        )
    return AsyncOpenAI(api_key=api_key)


async def summarize_lesson(stt_text: str) -> LessonSummary:
    client = get_gpt_client()

    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"STT 텍스트:\n{stt_text}"},
            ],
            temperature=0.3,
        )
    except RateLimitError as e:
        raise HTTPException(
            status_code=429,
            detail="GPT API 크레딧이 부족합니다. OpenAI 플랜 및 결제 정보를 확인하세요.",
        ) from e
    except APIStatusError as e:
        raise HTTPException(
            status_code=502,
            detail=f"GPT API 오류: {e.message}",
        ) from e

    raw = response.choices[0].message.content.strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=502,
            detail="GPT 응답을 파싱할 수 없습니다.",
        )

    return LessonSummary(
        topic=data.get("topic", ""),
        summary=data.get("summary", ""),
        key_concepts=data.get("key_concepts", []),
        important_points=data.get("important_points", []),
        homework=data.get("homework"),
        test_info=data.get("test_info"),
    )
