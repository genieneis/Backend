import json
import os
from pathlib import Path
from typing import Any, Optional

import httpx
from fastapi import HTTPException

NEIS_SCHOOL_INFO_URL = "https://open.neis.go.kr/hub/schoolInfo"

TEMP_DB_PATH = Path("temp_db.txt")


def get_neis_api_key() -> str:
    api_key = os.getenv("NEIS_API_KEY")

    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="NEIS_API_KEY 환경 변수가 설정되어 있지 않습니다.",
        )

    return api_key


def extract_rows(data: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
    if "RESULT" in data:
        result = data["RESULT"]
        code = result.get("CODE")
        message = result.get("MESSAGE", "")

        if code == "INFO-200":
            return [], 0

        raise HTTPException(
            status_code=502,
            detail=f"NEIS API 오류: {code} - {message}",
        )

    school_info = data.get("schoolInfo")

    if not school_info or not isinstance(school_info, list):
        raise HTTPException(
            status_code=502,
            detail="NEIS API 응답 형식이 예상과 다릅니다.",
        )

    total_count = 0
    rows: list[dict[str, Any]] = []

    for item in school_info:
        if "head" in item:
            for head_item in item["head"]:
                if "list_total_count" in head_item:
                    total_count = int(head_item["list_total_count"])

        if "row" in item:
            rows = item["row"]

    return rows, total_count


def to_school_item(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "education_office_code": row.get("ATPT_OFCDC_SC_CODE"),
        "school_code": row.get("SD_SCHUL_CODE"),
        "school_name": row.get("SCHUL_NM"),
        "school_kind": row.get("SCHUL_KND_SC_NM"),
        "sido": row.get("LCTN_SC_NM"),
        "address": row.get("ORG_RDNMA"),
    }


async def fetch_school_page(
    *,
    client: httpx.AsyncClient,
    api_key: str,
    page_index: int,
    page_size: int,
) -> tuple[list[dict[str, Any]], int]:
    params = {
        "KEY": api_key,
        "Type": "json",
        "pIndex": page_index,
        "pSize": page_size,
    }

    try:
        response = await client.get(NEIS_SCHOOL_INFO_URL, params=params)
        response.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=502,
            detail=f"NEIS API HTTP 오류: {e.response.status_code}",
        ) from e
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=502,
            detail=f"NEIS API 요청 실패: {str(e)}",
        ) from e

    return extract_rows(response.json())


async def save_all_schools_to_temp_db(page_size: int = 1000):
    api_key = get_neis_api_key()

    schools_by_code: dict[str, dict[str, Any]] = {}
    page_index = 1
    total_count = 0

    async with httpx.AsyncClient(timeout=20.0) as client:
        while True:
            rows, total_count = await fetch_school_page(
                client=client,
                api_key=api_key,
                page_index=page_index,
                page_size=page_size,
            )

            if not rows:
                break

            for row in rows:
                school_item = to_school_item(row)
                school_code = school_item.get("school_code")

                if not school_code:
                    continue

                schools_by_code[school_code] = school_item

            if len(schools_by_code) >= total_count:
                break

            page_index += 1

    all_schools = list(schools_by_code.values())

    all_schools.sort(
        key=lambda school: (
            school.get("sido") or "",
            school.get("school_kind") or "",
            school.get("school_name") or "",
        )
    )

    payload = {
        "total_count": total_count,
        "saved_count": len(all_schools),
        "schools": all_schools,
    }

    TEMP_DB_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return {
        "message": "학교 핵심 정보 임시 저장 완료",
        "file_path": str(TEMP_DB_PATH),
        "total_count": total_count,
        "saved_count": len(all_schools),
    }


def load_temp_db() -> dict[str, Any]:
    if not TEMP_DB_PATH.exists():
        raise HTTPException(
            status_code=404,
            detail="temp_db.txt가 없습니다. 먼저 /api/neis/schools/save-temp를 호출하세요.",
        )

    return json.loads(TEMP_DB_PATH.read_text(encoding="utf-8"))


def search_schools_from_temp_db(*, keyword: str):
    data = load_temp_db()
    schools = data.get("schools", [])

    keyword = keyword.strip()

    results = []

    for school in schools:
        school_name = school.get("school_name") or ""

        if keyword in school_name:
            results.append(school)

    return {
        "keyword": keyword,
        "count": len(results),
        "schools": results,
    }