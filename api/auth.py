from fastapi import APIRouter
from pydantic import BaseModel, EmailStr

from services.auth.auth_service import sign_in, sign_up
from services.neis.types import SchoolKind

router = APIRouter(
    prefix="/api/auth",
    tags=["Auth"],
)


class SignUpRequest(BaseModel):
    email: EmailStr
    password: str
    name: str
    school_kind: SchoolKind
    education_office_code: str
    school_code: str
    school_name: str | None = None
    grade: str
    class_nm: str


@router.post("/signup", status_code=201)
async def signup(body: SignUpRequest):
    """
    회원가입 API.
    Supabase Auth로 계정 생성 후 profiles 테이블에 학교 정보 저장.
    """
    return await sign_up(
        email=body.email,
        password=body.password,
        name=body.name,
        school_kind=body.school_kind,
        education_office_code=body.education_office_code,
        school_code=body.school_code,
        school_name=body.school_name,
        grade=body.grade,
        class_nm=body.class_nm,
    )
