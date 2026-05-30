import json
import logging
import os

from openai import AsyncOpenAI

from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

from services.stt.stt_session import PendingSentence


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
  "ai_text": "AI 보정 텍스트",
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
    ai_text: str
    tags: list[Tag] = field(default_factory=list)


def get_openai_client() -> AsyncOpenAI:
    api_key = os.getenv("GPT_API_KEY")
    if not api_key:
        raise ValueError("GPT_API_KEY 환경 변수가 설정되어 있지 않습니다.")
    return AsyncOpenAI(api_key=api_key)


@dataclass
class CorrectedSentence:
    id: int
    ai_text: str
    tags: list[Tag] = field(default_factory=list)


_BATCH_SYSTEM_PROMPT = """\
당신은 청각장애 학생을 위한 수업 STT 보정 전문가입니다.
교사가 말한 문장들의 STT 오인식을 교과 용어에 맞게 교정하고 중요도 태그를 추출합니다.

교정 원칙:
- 제공된 교과 용어를 참고해 발음 혼동·오인식을 수정합니다.
- 문장의 의미와 흐름은 바꾸지 마세요. 내용을 추가하거나 생략하지 마세요.

태그 종류:
- 핵심개념: 핵심 개념 정의 또는 중요 내용
- 시험: 시험·평가 관련 언급
- 과제: 숙제·과제·제출 안내
- 강조: "중요해요", "다시 말하면", "시험에 나올 수 있어요" 등 교사 강조 표현

반드시 아래 JSON 형식으로만 응답하세요. 설명이나 마크다운 없이 JSON만 출력하세요.

{
  "sentences": [
    {"id": <id>, "ai_text": "AI 보정 문장", "tags": [{"type": "핵심개념", "content": "내용"}]},
    ...
  ]
}

태그가 없는 문장은 "tags"를 빈 배열로 반환하세요.\
"""


def _build_batch_user_message(
    sentences: list[PendingSentence],
    subject_name: str,
    domain: str | None,
    priority_terms: list[str],
    source_terms: list[str],
    matched: bool,
) -> str:
    lines: list[str] = []

    lines.append(f"[현재 수업 과목] {subject_name}")

    if matched:
        if domain:
            lines.append(f"[현재 영역] {domain}")
        if priority_terms:
            lines.append(f"[우선 교정 용어] {', '.join(priority_terms)}")
        if source_terms:
            lines.append(f"[참고 원문 용어] {', '.join(source_terms)}")

    lines.append("")
    lines.append("[보정할 문장들]")
    for s in sentences:
        lines.append(f'{s.id}: "{s.text}"')

    return "\n".join(lines)


async def process_stt_batch(
    sentences: list[PendingSentence],
    subject_name: str,
    domain: str | None,
    priority_terms: list[str],
    source_terms: list[str],
    matched: bool,
) -> list[CorrectedSentence]:
    """
    3~5문장 배치를 LLM으로 보정. 문장 id별 결과 반환.
    LLM 파싱 실패 시 원문 그대로 반환.
    """
    client = get_openai_client()
    user_message = _build_batch_user_message(
        sentences, subject_name, domain, priority_terms, source_terms, matched
    )

    logger.info("[LLM 프롬프트]\n%s", user_message)

    response = await client.chat.completions.create(
        model="gpt-4.1-mini",
        max_tokens=2048,
        messages=[
            {"role": "system", "content": _BATCH_SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
    )

    raw = response.choices[0].message.content.strip()

    id_to_text = {s.id: s.text for s in sentences}

    try:
        data = json.loads(raw)
        results = []
        for item in data.get("sentences", []):
            sid = item.get("id")
            if sid not in id_to_text:
                continue
            tags = [
                Tag(type=t["type"], content=t["content"])
                for t in item.get("tags", [])
                if t.get("type") in TAG_TYPES and t.get("content")
            ]
            results.append(CorrectedSentence(
                id=sid,
                ai_text=item.get("ai_text", id_to_text[sid]),
                tags=tags,
            ))
        # LLM이 일부 문장을 누락했을 경우 원문으로 채움
        returned_ids = {r.id for r in results}
        for s in sentences:
            if s.id not in returned_ids:
                results.append(CorrectedSentence(id=s.id, ai_text=s.text))
        return sorted(results, key=lambda r: r.id)

    except (json.JSONDecodeError, KeyError, TypeError):
        return [CorrectedSentence(id=s.id, ai_text=s.text) for s in sentences]


async def process_stt_text(
    text: str,
    subject: str | None = None,
) -> LlmProcessResult:
    """
    STT final 텍스트를 LLM으로 보정하고 중요도 태그를 추출합니다.
    과목명이 있으면 해당 과목 맥락으로 보정합니다.
    """
    client = get_openai_client()

    subject_context = f"현재 수업 과목: {subject}\n\n" if subject else ""
    user_message = f"{subject_context}STT 텍스트:\n{text}"

    response = await client.chat.completions.create(
        model="gpt-4.1-mini",
        max_tokens=1024,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
    )

    raw = response.choices[0].message.content.strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # LLM이 JSON을 잘못 반환한 경우 원문 그대로 반환
        return LlmProcessResult(ai_text=text)

    tags = [
        Tag(type=t["type"], content=t["content"])
        for t in data.get("tags", [])
        if t.get("type") in TAG_TYPES and t.get("content")
    ]

    return LlmProcessResult(
        ai_text=data.get("ai_text", text),
        tags=tags,
    )
