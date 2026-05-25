import asyncio
import os
from datetime import datetime, timedelta
from typing import Any, Optional
from zoneinfo import ZoneInfo

import httpx
from fastapi import HTTPException

NEIS_BASE_URL = "https://open.neis.go.kr"

TIMETABLE_CONFIG = {
    "elementary": {
        "endpoint": "/hub/elsTimetable",
        "response_key": "elsTimetable",
    },
    "middle": {
        "endpoint": "/hub/misTimetable",
        "response_key": "misTimetable",
    },
    "high": {
        "endpoint": "/hub/hisTimetable",
        "response_key": "hisTimetable",
    },
    
}

def get_neis_api_key() -> str:
    api_key = os.getenv("NEIS_API_KEY")

    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="NEIS_API_KEY 환경 변수가 설정되어 있지 않습니다.",
        )

    return api_key


def get_today_yyyymmdd() -> str:
    return datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y%m%d")


def get_week_dates(date_yyyymmdd: str) -> list[str]:
    """주어진 날짜가 속한 주의 월~금 날짜 목록 반환 (YYYYMMDD 형식)"""
    dt = datetime.strptime(date_yyyymmdd, "%Y%m%d")
    monday = dt - timedelta(days=dt.weekday())
    return [(monday + timedelta(days=i)).strftime("%Y%m%d") for i in range(5)]


def get_school_year(date_yyyymmdd: str) -> str:
    """
    NEIS 학년도 계산.
    보통 3월부터 새 학년도이므로,
    1~2월은 전년도 학년도로 봅니다.

    예:
    20260215 -> 2025
    20260515 -> 2026
    """
    year = int(date_yyyymmdd[:4])
    month = int(date_yyyymmdd[4:6])

    if month < 3:
        return str(year - 1)

    return str(year)


def extract_timetable_rows(
    data: dict[str, Any],
    response_key: str,
) -> tuple[list[dict[str, Any]], int]:
    """
    NEIS 시간표 응답에서 row와 전체 개수를 추출합니다.

    elementary -> elsTimetable
    middle     -> misTimetable
    high       -> hisTimetable
    """
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

    timetable = data.get(response_key)

    if not timetable or not isinstance(timetable, list):
        raise HTTPException(
            status_code=502,
            detail={
                "message": "NEIS 시간표 API 응답 형식이 예상과 다릅니다.",
                "expected_key": response_key,
                "received_keys": list(data.keys()),
                "raw_response": data,
            },
        )

    total_count = 0
    rows: list[dict[str, Any]] = []

    for item in timetable:
        if "head" in item:
            for head_item in item["head"]:
                if "list_total_count" in head_item:
                    total_count = int(head_item["list_total_count"])

                if "RESULT" in head_item:
                    result = head_item["RESULT"]
                    code = result.get("CODE")
                    message = result.get("MESSAGE", "")

                    if code == "INFO-200":
                        return [], 0

                    if code != "INFO-000":
                        raise HTTPException(
                            status_code=502,
                            detail=f"NEIS API 오류: {code} - {message}",
                        )

        if "row" in item:
            rows = item["row"]

    return rows, total_count

def to_timetable_item(row: dict[str, Any]) -> dict[str, Any]:
    """
    프론트 시간표 리스트에 필요한 최소 정보만 반환합니다.
    """
    return {
        "period": row.get("PERIO"),
        "subject": row.get("ITRT_CNTNT"),
    }

async def fetch_timetable_page(
    *,
    client: httpx.AsyncClient,
    api_key: str,
    school_kind: str,
    education_office_code: str,
    school_code: str,
    school_year: str,
    grade: str,
    date: str,
    page_index: int,
    page_size: int,
    class_nm: Optional[str] = None,
) -> tuple[list[dict[str, Any]], int]:
    params: dict[str, Any] = {
        "KEY": api_key,
        "Type": "json",
        "pIndex": page_index,
        "pSize": page_size,
        "ATPT_OFCDC_SC_CODE": education_office_code,
        "SD_SCHUL_CODE": school_code,
        "AY": school_year,
        "ALL_TI_YMD": date,
        "GRADE": grade,
    }

    if class_nm is not None:
        params["CLASS_NM"] = class_nm


    try:
        config = TIMETABLE_CONFIG.get(school_kind)

        if not config:
            raise HTTPException(
                status_code=400,
                detail="school_kind는 elementary, middle, high 중 하나여야 합니다.",
            )

        url = NEIS_BASE_URL + config["endpoint"]
        response_key = config["response_key"]
        debug_params = {k: v for k, v in params.items() if k != "KEY"}
        debug_request = client.build_request("GET", url, params=debug_params)
        print(f"[NEIS] request url: {debug_request.url}")
        response = await client.get(url, params=params)
        response.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=502,
            detail=f"NEIS 시간표 API HTTP 오류: {e.response.status_code}",
        ) from e
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=502,
            detail=f"NEIS 시간표 API 요청 실패: {str(e)}",
        ) from e

    return extract_timetable_rows(
    response.json(),
    response_key=response_key,
)


async def _get_single_day_timetable(
    *,
    client: httpx.AsyncClient,
    api_key: str,
    school_kind: str,
    education_office_code: str,
    school_code: str,
    grade: str,
    class_nm: str,
    date: str,
) -> dict[str, Any]:
    school_year = get_school_year(date)

    page_index = 1
    page_size = 100
    all_rows: list[dict[str, Any]] = []

    while True:
        rows, total_count = await fetch_timetable_page(
            client=client,
            api_key=api_key,
            school_kind=school_kind,
            education_office_code=education_office_code,
            school_code=school_code,
            school_year=school_year,
            grade=grade,
            class_nm=class_nm,
            date=date,
            page_index=page_index,
            page_size=page_size,
        )

        if not rows:
            break

        all_rows.extend(rows)

        if len(all_rows) >= total_count:
            break

        page_index += 1

    timetable = [to_timetable_item(row) for row in all_rows]
    timetable.sort(key=lambda item: int(item["period"]) if item.get("period") else 0)

    return {
        "school_name": all_rows[0].get("SCHUL_NM") if all_rows else None,
        "school_year": school_year,
        "semester": all_rows[0].get("SEM") if all_rows else None,
        "count": len(timetable),
        "timetable": timetable,
    }


async def get_school_timetable(
    *,
    school_kind: str,
    education_office_code: str,
    school_code: str,
    grade: str,
    class_nm: str,
    date: Optional[str] = None,
):
    api_key = get_neis_api_key()
    target_date = date or get_today_yyyymmdd()

    async with httpx.AsyncClient(timeout=10.0) as client:
        result = await _get_single_day_timetable(
            client=client,
            api_key=api_key,
            school_kind=school_kind,
            education_office_code=education_office_code,
            school_code=school_code,
            grade=grade,
            class_nm=class_nm,
            date=target_date,
        )

    return {
        **result,
        "date": target_date,
        "grade": grade,
        "class_nm": class_nm,
    }


DAY_NAMES = ["월", "화", "수", "목", "금"]


async def get_school_weekly_timetable(
    *,
    school_kind: str,
    education_office_code: str,
    school_code: str,
    grade: str,
    class_nm: str,
    date: Optional[str] = None,
):
    api_key = get_neis_api_key()
    base_date = date or get_today_yyyymmdd()
    week_dates = get_week_dates(base_date)

    async with httpx.AsyncClient(timeout=30.0) as client:
        results = await asyncio.gather(
            *[
                _get_single_day_timetable(
                    client=client,
                    api_key=api_key,
                    school_kind=school_kind,
                    education_office_code=education_office_code,
                    school_code=school_code,
                    grade=grade,
                    class_nm=class_nm,
                    date=d,
                )
                for d in week_dates
            ],
            return_exceptions=True,
        )

    school_name = None
    school_year = None
    semester = None
    weekly_timetable = []

    for day_name, day_date, result in zip(DAY_NAMES, week_dates, results):
        if isinstance(result, Exception):
            weekly_timetable.append({
                "day": day_name,
                "date": day_date,
                "count": 0,
                "timetable": [],
            })
        else:
            if school_name is None:
                school_name = result["school_name"]
                school_year = result["school_year"]
                semester = result["semester"]
            weekly_timetable.append({
                "day": day_name,
                "date": day_date,
                "count": result["count"],
                "timetable": result["timetable"],
            })

    return {
        "school_name": school_name,
        "school_year": school_year,
        "semester": semester,
        "grade": grade,
        "class_nm": class_nm,
        "week_start": week_dates[0],
        "week_end": week_dates[4],
        "weekly_timetable": weekly_timetable,
    }


async def get_class_list(
    *,
    school_kind: str,
    education_office_code: str,
    school_code: str,
    grade: str,
):
    api_key = get_neis_api_key()
    target_date = date or get_today_yyyymmdd()
    school_year = get_school_year(target_date)

    page_index = 1
    page_size = 1000
    all_rows: list[dict[str, Any]] = []

    async with httpx.AsyncClient(timeout=10.0) as client:
        while True:
            rows, total_count = await fetch_timetable_page(
                client=client,
                api_key=api_key,
                school_kind=school_kind,
                education_office_code=education_office_code,
                school_code=school_code,
                school_year=school_year,
                grade=grade,
                date=target_date,
                page_index=page_index,
                page_size=page_size,
            )

            if not rows:
                break

            all_rows.extend(rows)

            if len(all_rows) >= total_count:
                break

            page_index += 1

    school_name = all_rows[0].get("SCHUL_NM") if all_rows else None
    classes = sorted({row["CLASS_NM"] for row in all_rows if row.get("CLASS_NM")})

    return {
        "school_name": school_name,
        "school_year": school_year,
        "grade": grade,
        "count": len(classes),
        "classes": classes,
    }