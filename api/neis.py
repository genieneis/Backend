from typing import Optional

from fastapi import APIRouter, Query

from services.neis_school import (
    save_all_schools_to_temp_db,
    search_schools_from_temp_db,
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
    return search_schools_from_temp_db(
        keyword=keyword,
    )