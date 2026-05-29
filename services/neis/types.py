from enum import Enum


class SchoolKind(str, Enum):
    elementary = "elementary"
    middle = "middle"
    high = "high"
    special = "special"
    etc = "etc"


SCHOOL_KIND_CATEGORY: dict[str, SchoolKind] = {
    "초등학교":            SchoolKind.elementary,
    "각종학교(초)":         SchoolKind.elementary,
    "재외한국학교(초)":      SchoolKind.elementary,
    "평생학교(초)-3년6학기": SchoolKind.elementary,
    "평생학교(초)-4년12학기": SchoolKind.elementary,

    "중학교":             SchoolKind.middle,
    "각종학교(중)":         SchoolKind.middle,
    "방송통신중학교":        SchoolKind.middle,
    "평생학교(중)-2년6학기": SchoolKind.middle,
    "평생학교(중)-3년6학기": SchoolKind.middle,

    "고등학교":            SchoolKind.high,
    "각종학교(고)":         SchoolKind.high,
    "고등기술학교":         SchoolKind.high,
    "방송통신고등학교":       SchoolKind.high,
    "평생학교(고)-2년6학기": SchoolKind.high,
    "평생학교(고)-3년6학기": SchoolKind.high,

    "특수학교":            SchoolKind.special,
}


def get_school_kind_category(school_kind: str | None) -> SchoolKind:
    return SCHOOL_KIND_CATEGORY.get(school_kind or "", SchoolKind.etc)
