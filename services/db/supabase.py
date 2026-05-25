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
