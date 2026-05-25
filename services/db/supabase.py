import os

from fastapi import HTTPException
from supabase import Client, create_client

_client: Client | None = None
_admin_client: Client | None = None


def get_supabase() -> Client:
    global _client

    if _client is not None:
        return _client

    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")

    if not url or not key:
        raise HTTPException(
            status_code=500,
            detail="SUPABASE_URL 또는 SUPABASE_KEY 환경 변수가 설정되어 있지 않습니다.",
        )

    _client = create_client(url, key)
    return _client


def get_supabase_admin() -> Client:
    global _admin_client

    if _admin_client is not None:
        return _admin_client

    url = os.getenv("SUPABASE_URL")
    service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

    if not url or not service_role_key:
        raise HTTPException(
            status_code=500,
            detail="SUPABASE_URL 또는 SUPABASE_SERVICE_ROLE_KEY 환경 변수가 설정되어 있지 않습니다.",
        )

    _admin_client = create_client(url, service_role_key)
    return _admin_client
