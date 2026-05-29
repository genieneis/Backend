from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr

from dependencies import get_current_user_id
from services.auth.auth import delete_user, sign_in, sign_up
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
    first_period_start_time: str | None = None
    fifth_period_start_time: str | None = None


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
        first_period_start_time=body.first_period_start_time,
        fifth_period_start_time=body.fifth_period_start_time,
    )

class LoginRequest(BaseModel):
    email: str
    password: str


@router.post("/login")
async def login(body: LoginRequest):
    """
    로그인 API.
    성공 시 access_token, refresh_token 반환.
    """
    return await sign_in(email=body.email, password=body.password)


@router.delete("/me", status_code=200)
async def withdraw(user_id: str = Depends(get_current_user_id)):
    """
    회원 탈퇴 API.
    Authorization 헤더의 JWT에서 user_id를 추출하여 계정 삭제.
    """
    return await delete_user(user_id=user_id)