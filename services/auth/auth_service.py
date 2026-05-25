from fastapi import HTTPException
from supabase_auth.errors import AuthApiError, AuthWeakPasswordError

from services.db.supabase import get_supabase, get_supabase_admin


async def sign_up(
    *,
    email: str,
    password: str,
    name: str,
    school_kind: str,
    education_office_code: str,
    school_code: str,
    school_name: str | None,
    grade: str,
    class_nm: str,
) -> dict:
    client = get_supabase()
    client_admin = get_supabase_admin()

    try:
        auth_response = client.auth.sign_up({
            "email": email,
            "password": password,
        })
    except AuthWeakPasswordError as e:
        raise HTTPException(status_code=400, detail=str(e.message)) from e
    except AuthApiError as e:
        raise HTTPException(status_code=400, detail=str(e.message)) from e

    user = auth_response.user
    if not user:
        raise HTTPException(status_code=400, detail="회원가입에 실패했습니다.")

    try:
        client_admin.table("profiles").insert({
            "id": user.id,
            "name": name,
            "school_kind": school_kind,
            "education_office_code": education_office_code,
            "school_code": school_code,
            "school_name": school_name,
            "grade": grade,
            "class_nm": class_nm,
        }).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"회원정보 저장 실패: {str(e)}") from e

    return {
        "user_id": user.id,
        "email": user.email,
    }

async def sign_in(*, email: str, password: str) -> dict:
    client = get_supabase()

    try:
        auth_response = client.auth.sign_in_with_password({
            "email": email,
            "password": password,
        })
    except AuthApiError as e:
        raise HTTPException(status_code=401, detail=str(e.message)) from e

    session = auth_response.session
    user = auth_response.user

    profile_response = client.table("profiles").select("*").eq("id", user.id).maybe_single().execute()
    profile = profile_response.data if profile_response else None

    if not profile:
        raise HTTPException(status_code=404, detail="유저 정보를 찾을 수 없습니다.")

    return {
        "access_token": session.access_token,
        "refresh_token": session.refresh_token,
        "token_type": "bearer",
        "user": {
            "user_id": user.id,
            "email": user.email,
            "name": profile.get("name"),
            "school_kind": profile.get("school_kind"),
            "education_office_code": profile.get("education_office_code"),
            "school_code": profile.get("school_code"),
            "school_name": profile.get("school_name"),
            "grade": profile.get("grade"),
            "class_nm": profile.get("class_nm"),
        },
    }