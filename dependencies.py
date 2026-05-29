import base64
import json
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_bearer = HTTPBearer()


def _decode_jwt_payload(token: str) -> dict:
    try:
        payload_part = token.split('.')[1]
        payload_part += '=' * (4 - len(payload_part) % 4)
        return json.loads(base64.urlsafe_b64decode(payload_part))
    except Exception:
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")


async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> str:
    """JWT sub 클레임에서 user_id를 추출하는 FastAPI 의존성."""
    payload = _decode_jwt_payload(credentials.credentials)
    user_id = payload.get('sub')
    if not user_id:
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")
    return user_id


async def get_current_token(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> str:
    """raw Bearer 토큰을 반환하는 FastAPI 의존성."""
    return credentials.credentials
