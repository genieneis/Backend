from fastapi import HTTPException
import json
import os
from dataclasses import dataclass, field
from openai import AsyncOpenAI, RateLimitError, APIStatusError
from services.db.supabase import get_supabase


async def get_user_transcripts(*, user_id: str, token: str) -> list[dict]:
    client = get_supabase()
    client.postgrest.auth(token)

    try:
        t_resp = (
            client.table("lesson_stt_transcripts")
            .select("id, subject, subject_name, filename, content, created_at")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .execute()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"노트 조회 실패: {str(e)}") from e

    rows = t_resp.data
    if not rows:
        return []

    transcript_ids = [r["id"] for r in rows]

    # AI 보정 내용 조회: transcript_id → ai_content
    ai_content_map: dict[str, str] = {}
    try:
        ai_resp = (
            client.table("lesson_stt_ai_transcripts")
            .select("transcript_id, content")
            .in_("transcript_id", transcript_ids)
            .execute()
        )
        for a in ai_resp.data:
            ai_content_map[a["transcript_id"]] = a["content"]
    except Exception:
        pass

    # 요약 조회: lesson_stt_summaries.transcript_id = raw_transcript_id
    summary_map: dict[str, str | None] = {}  # transcript_id → topic
    try:
        s_resp = (
            client.table("lesson_stt_summaries")
            .select("transcript_id, content")
            .in_("transcript_id", transcript_ids)
            .execute()
        )
        for s in s_resp.data:
            try:
                topic = json.loads(s["content"]).get("topic")
            except (json.JSONDecodeError, TypeError):
                topic = None
            summary_map[s["transcript_id"]] = topic
    except Exception:
        pass

    return [
        {
            "id": row["id"],
            "subject": row.get("subject"),
            "subject_name": row.get("subject_name"),
            "filename": row.get("filename"),
            "content": row["content"],
            "ai_content": ai_content_map.get(row["id"]),
            "created_at": row["created_at"],
            "summary": {
                "exists": row["id"] in summary_map,
                "topic": summary_map.get(row["id"]),
            },
        }
        for row in rows
    ]


async def get_transcript_summary(*, transcript_id: str, token: str) -> dict | None:
    client = get_supabase()
    client.postgrest.auth(token)

    try:
        response = (
            client.table("lesson_stt_summaries")
            .select("id, content, created_at")
            .eq("transcript_id", transcript_id)
            .maybe_single()
            .execute()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"요약 조회 실패: {str(e)}") from e

    if not response.data:
        return None

    try:
        content = json.loads(response.data["content"])
    except (json.JSONDecodeError, KeyError):
        return None

    return content


async def save_lesson_summary(*, transcript_id: str, summary: "LessonSummary", token: str) -> dict:
    client = get_supabase()
    client.postgrest.auth(token)

    content = json.dumps({
        "topic": summary.topic,
        "summary": summary.summary,
        "key_concepts": summary.key_concepts,
        "important_points": summary.important_points,
        "homework": summary.homework,
        "test_info": summary.test_info,
    }, ensure_ascii=False)

    try:
        response = (
            client.table("lesson_stt_summaries")
            .insert({"transcript_id": transcript_id, "content": content})
            .execute()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"요약 저장 실패: {str(e)}") from e

    record = response.data[0] if response.data else None
    if not record:
        raise HTTPException(status_code=500, detail="요약 저장 실패: 저장된 데이터가 없습니다.")

    return record


async def save_lecture_stt_transcript(
    *,
    user_id: str,
    filename: str,
    content: str,
    subject: str | None = None,
    subject_name: str | None = None,
    ai_content: str | None = None,
    token: str,
) -> dict:
    client = get_supabase()
    client.postgrest.auth(token)

    row: dict = {"user_id": user_id, "filename": filename, "content": content}
    if subject:
        row["subject"] = subject
    if subject_name:
        row["subject_name"] = subject_name

    try:
        response = (
            client.table("lesson_stt_transcripts")
            .insert(row)
            .execute()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"강의 STT 저장 실패: {str(e)}") from e

    record = response.data[0] if response.data else None
    if not record:
        raise HTTPException(status_code=500, detail="강의 STT 저장 실패: 저장된 데이터가 없습니다.")

    transcript_id = record["id"]

    # 후보정 텍스트가 있으면 별도 테이블에 저장
    ai_transcript_id: str | None = None
    if ai_content and ai_content.strip():
        ai_row: dict = {
            "transcript_id": transcript_id,
            "user_id": user_id,
            "content": ai_content,
        }
        if subject:
            ai_row["subject"] = subject
        if subject_name:
            ai_row["subject_name"] = subject_name
        try:
            ai_resp = client.table("lesson_stt_ai_transcripts").insert(ai_row).execute()
            ai_transcript_id = ai_resp.data[0]["id"] if ai_resp.data else None
        except Exception as e:
            # AI 보정 저장 실패는 원문 저장 성공을 방해하지 않음
            raise HTTPException(status_code=500, detail=f"AI 보정 STT 저장 실패: {str(e)}") from e

    return {
        "id": transcript_id,
        "ai_transcript_id": ai_transcript_id,
        "filename": record["filename"],
        "created_at": record["created_at"],
    }



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
    homework: str | None = None
    test_info: str | None = None


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
