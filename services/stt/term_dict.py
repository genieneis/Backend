import json
from dataclasses import dataclass

from services.db.supabase import get_supabase_admin

TABLE = "subject_term_sets"


@dataclass
class TermSet:
    """DB subject_term_sets 한 행에 해당하는 domain 용어 묶음."""
    domain: str          # 교과 영역명 (예: "운동과 에너지", "물질")
    core_keywords: list[str]   # 도메인 감지용 핵심 키워드 — LLM에는 보내지 않음
    source_terms: list[str]    # PDF 원문 용어 — LLM 참고용
    priority_terms: list[str]  # STT 오인식 빈도 높은 용어 — LLM 보정 우선 대상


def _normalize(name: str) -> str:
    """과목명 공백 제거 (DB subject_name이 공백 없는 형식으로 저장됨)."""
    return name.replace(" ", "").strip()


def _parse_array(value) -> list[str]:
    """DB에서 TEXT[] 또는 JSON 문자열로 온 배열 필드를 파이썬 리스트로 변환."""
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, ValueError):
            return []
    return []


async def load_term_sets(
    school_level: str,
    grade_band: str | None,
    subject_name: str,
) -> list[TermSet]:
    """과목에 해당하는 모든 domain term_sets 조회.

    grade_band: 초등만 "1~2학년"|"3~4학년"|"5~6학년", 중·고등은 None (DB에서 NULL)
    반환값이 비어있으면 해당 과목의 용어사전 데이터가 없는 것.
    """
    normalized = _normalize(subject_name)

    client = get_supabase_admin()
    query = (
        client.table(TABLE)
        .select("domain,core_keywords,source_terms,priority_terms")
        .eq("school_level", school_level)
        .eq("subject_name", normalized)
    )

    # 초등: grade_band로 학년군 필터, 중·고등: grade_band가 NULL인 행만 조회
    if grade_band:
        query = query.eq("grade_band", grade_band)
    else:
        query = query.is_("grade_band", "null")

    res = query.execute()

    return [
        TermSet(
            domain=row["domain"],
            core_keywords=_parse_array(row["core_keywords"]),
            source_terms=_parse_array(row["source_terms"]),
            priority_terms=_parse_array(row["priority_terms"]),
        )
        for row in res.data
    ]
