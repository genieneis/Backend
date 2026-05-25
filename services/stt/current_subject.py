from datetime import time
from zoneinfo import ZoneInfo
from datetime import datetime
from services.neis.neis_timetable import get_school_timetable

# 일반적인 중·고등학교 교시별 시간 (시작, 종료)
# 학교마다 다를 수 있으므로 추후 NEIS 학교 일과시간 API로 교체 가능
DEFAULT_PERIODS: list[tuple[time, time]] = [
    (time(9, 0),  time(9, 45)),   # 1교시
    (time(9, 55), time(10, 40)),  # 2교시
    (time(10, 50), time(11, 35)), # 3교시
    (time(11, 45), time(12, 30)), # 4교시
    (time(13, 20), time(14, 5)),  # 5교시 (점심 후)
    (time(14, 15), time(15, 0)),  # 6교시
    (time(15, 10), time(15, 55)), # 7교시
]


def get_current_period(now: datetime | None = None) -> int | None:
    """현재 시각 기준 교시(1~7) 반환. 수업 중이 아니면 None."""
    if now is None:
        now = datetime.now(ZoneInfo("Asia/Seoul"))

    current_time = now.time()

    for index, (start, end) in enumerate(DEFAULT_PERIODS):
        if start <= current_time <= end:
            return index + 1

    return None


async def get_current_subject(
    *,
    school_kind: str,
    education_office_code: str,
    school_code: str,
    grade: str,
    class_nm: str,
    now: datetime | None = None,
) -> str | None:
    """현재 교시에 해당하는 과목명 반환. 수업 중이 아니거나 시간표 없으면 None."""
    period = get_current_period(now)
    if period is None:
        return None

    timetable_response = await get_school_timetable(
        school_kind=school_kind,
        education_office_code=education_office_code,
        school_code=school_code,
        grade=grade,
        class_nm=class_nm,
    )

    for item in timetable_response.get("timetable", []):
        if item.get("period") == str(period):
            return item.get("subject")

    return None
