import json
import os
from typing import Optional

import anthropic
from fastapi import HTTPException

from dataclasses import dataclass, field


TAG_TYPES = {
    "핵심개념": "핵심 개념 또는 정의",
    "시험": "시험·평가 관련 언급",
    "과제": "숙제·제출 관련 안내",
    "강조": "교사의 강조 표현",
}

SYSTEM_PROMPT = """\
당신은 청각장애 학생을 위한 수업 내용 분석 도우미입니다.
교사가 말한 STT 텍스트를 입력받아 두 가지 작업을 수행합니다.

1. **텍스트 보정**: STT 오인식을 현재 수업 과목 맥락에 맞게 교정합니다.
   - 과목 전문 용어의 오인식을 수정합니다 (예: "미분계수", "광합성" 등).
   - 문장 흐름이 자연스럽도록 최소한으로 수정합니다. 내용을 추가하거나 생략하지 마세요.

2. **중요도 태깅**: 텍스트에서 아래 태그에 해당하는 내용을 추출합니다.
   - 핵심개념: 핵심 개념 정의 또는 중요 내용
   - 시험: 시험·평가 관련 언급
   - 과제: 숙제·과제·제출 안내
   - 강조: "중요해요", "다시 말하면", "시험에 나올 수 있어요" 등 교사 강조 표현

반드시 아래 JSON 형식으로만 응답하세요. 설명이나 마크다운 없이 JSON만 출력하세요.

{
  "corrected_text": "보정된 텍스트",
  "tags": [
    {"type": "핵심개념", "content": "추출된 내용"},
    {"type": "시험", "content": "추출된 내용"}
  ]
}

태그가 없으면 "tags"는 빈 배열로 반환하세요.\
"""


@dataclass
class Tag:
    type: str
    content: str


@dataclass
class LlmProcessResult:
    corrected_text: str
    tags: list[Tag] = field(default_factory=list)


def get_anthropic_client() -> anthropic.Anthropic:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="ANTHROPIC_API_KEY 환경 변수가 설정되어 있지 않습니다.",
        )
    return anthropic.Anthropic(api_key=api_key)


async def process_stt_text(
    text: str,
    subject: Optional[str] = None,
) -> LlmProcessResult:
    """
    STT final 텍스트를 LLM으로 보정하고 중요도 태그를 추출합니다.
    과목명이 있으면 해당 과목 맥락으로 보정합니다.
    """
    client = get_anthropic_client()

    subject_context = f"현재 수업 과목: {subject}\n\n" if subject else ""
    user_message = f"{subject_context}STT 텍스트:\n{text}"

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    raw = response.content[0].text.strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # LLM이 JSON을 잘못 반환한 경우 원문 그대로 반환
        return LlmProcessResult(corrected_text=text)

    tags = [
        Tag(type=t["type"], content=t["content"])
        for t in data.get("tags", [])
        if t.get("type") in TAG_TYPES and t.get("content")
    ]

    return LlmProcessResult(
        corrected_text=data.get("corrected_text", text),
        tags=tags,
    )
