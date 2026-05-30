from fastapi import APIRouter, Query

from services.neis.types import SchoolKind
from services.neis.neis_school import (
    save_all_schools_to_temp_db,
    search_schools_from_temp_db,
)
from services.neis.neis_timetable import (
    get_class_list,
    get_school_regular_timetable,
    get_school_timetable,
    get_school_weekly_timetable,
)

router = APIRouter(
    prefix="/api/neis",
    tags=["NEIS"],
)


@router.post("/schools/save-temp")
async def save_schools(
    page_size: int = Query(1000, ge=1, le=1000),
):
    return await save_all_schools_to_temp_db(page_size=page_size)


@router.get("/schools/search")
async def search_local_schools(
    keyword: str = Query(..., min_length=1, description="학교명 검색어"),
):
    """
    학교명 검색 API
    """
    return search_schools_from_temp_db(keyword=keyword)


@router.get("/classes")
async def get_classes(
    school_kind: SchoolKind = Query(..., description="학교급 (elementary/middle/high/special)"),
    education_office_code: str = Query(..., description="시도교육청코드, 예: B10"),
    school_code: str = Query(..., description="행정표준코드, 예: 7010227"),
    grade: str = Query(..., description="학년, 예: 1"),
    special_school_course: str | None = Query(
        None,
        description="특수학교 학교급 (school_kind=special일 때 필수). 예: 초등학교, 중학교, 고등학교",
    ),
    date: str | None = Query(None, description="기준 날짜 YYYYMMDD. 생략하면 오늘 날짜 기준"),
):
    """
    학교/학년에 해당하는 반 목록 조회 API.
    특수학교(school_kind=special)는 special_school_course도 함께 전달해야 합니다.
    """
    return await get_class_list(
        school_kind=school_kind,
        education_office_code=education_office_code,
        school_code=school_code,
        grade=grade,
        date=date,
        special_school_course=special_school_course,
    )


@router.get("/timetable/weekly/regular")
async def get_user_regular_timetable(
    school_kind: SchoolKind = Query(..., description="학교급 (elementary/middle/high/special)"),
    education_office_code: str = Query(..., description="시도교육청코드, 예: B10"),
    school_code: str = Query(..., description="행정표준코드, 예: 7130165"),
    grade: str = Query(..., description="학년, 예: 1"),
    class_nm: str = Query(..., description="학급명, 예: 3"),
    special_school_course: str | None = Query(
        None,
        description="특수학교 학교급 (school_kind=special일 때 필수). 예: 초등학교, 중학교, 고등학교",
    ),
):
    """
    반별 정규 시간표 조회 API.
    해당 학년도 초반 2달치(3/2~4/30) 데이터를 기반으로 요일/교시별 최빈 과목을 반환합니다.
    """
    return await get_school_regular_timetable(
        school_kind=school_kind,
        education_office_code=education_office_code,
        school_code=school_code,
        grade=grade,
        class_nm=class_nm,
        special_school_course=special_school_course,
    )


@router.get("/timetable/weekly")
async def get_user_weekly_timetable(
    school_kind: SchoolKind = Query(..., description="학교급 (elementary/middle/high/special)"),
    education_office_code: str = Query(..., description="시도교육청코드, 예: B10"),
    school_code: str = Query(..., description="행정표준코드, 예: 7130165"),
    grade: str = Query(..., description="학년, 예: 1"),
    class_nm: str = Query(..., description="학급명, 예: 3"),
    special_school_course: str | None = Query(
        None,
        description="특수학교 학교급 (school_kind=special일 때 필수). 예: 초등학교, 중학교, 고등학교",
    ),
    date: str | None = Query(
        None,
        description="기준 날짜 YYYYMMDD. 생략하면 오늘 날짜 기준으로 해당 주 월~금 반환",
    ),
):
    """
    반별 주간(월~금) 시간표 조회 API.
    """
    return await get_school_weekly_timetable(
        school_kind=school_kind,
        education_office_code=education_office_code,
        school_code=school_code,
        grade=grade,
        class_nm=class_nm,
        date=date,
        special_school_course=special_school_course,
    )


@router.get("/timetable")
async def get_user_timetable(
    school_kind: SchoolKind = Query(..., description="학교급 (elementary/middle/high/special)"),
    education_office_code: str = Query(..., description="시도교육청코드, 예: B10"),
    school_code: str = Query(..., description="행정표준코드, 예: 7130165"),
    grade: str = Query(..., description="학년, 예: 1"),
    class_nm: str = Query(..., description="학급명, 예: 3"),
    special_school_course: str | None = Query(
        None,
        description="특수학교 학교급 (school_kind=special일 때 필수). 예: 초등학교, 중학교, 고등학교",
    ),
    date: str | None = Query(None, description="시간표 일자 YYYYMMDD. 생략하면 오늘 날짜 기준"),
):
    """
    반별 특정 일자 시간표 조회 API.
    """
    return await get_school_timetable(
        school_kind=school_kind,
        education_office_code=education_office_code,
        school_code=school_code,
        grade=grade,
        class_nm=class_nm,
        date=date,
        special_school_course=special_school_course,
    )
