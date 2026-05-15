import contextlib
import json
import os

import httpx
import websockets

# NCP Clova Speech 서비스 생성 시 발급되는 값
# CLOVA_SPEECH_INVOKE_URL: 예) https://clovaspeech-gw.naver.com/external-api/v1/...
# CLOVA_SPEECH_SECRET_KEY: Clova Speech Secret Key


def _invoke_url() -> str:
    return os.getenv("CLOVA_SPEECH_INVOKE_URL", "").rstrip("/")


def _auth_headers() -> dict:
    return {"X-CLOVASPEECH-API-KEY": os.getenv("CLOVA_SPEECH_SECRET_KEY", "")}


# 스트리밍 세션 시작 시 첫 번째로 보내는 설정 메시지
_STREAM_CONFIG = json.dumps({
    "transcription": {"language": "ko-KR"},
})


async def transcribe_file(audio_bytes: bytes) -> str:
    """오디오 파일 전체를 Clova Speech REST API로 변환."""
    url = f"{_invoke_url()}/recognizer/upload"
    headers = {**_auth_headers(), "Content-Type": "application/octet-stream"}
    async with httpx.AsyncClient(timeout=120) as client:
        res = await client.post(url, content=audio_bytes, headers=headers)
        res.raise_for_status()
        # 응답: {"result": "COMPLETED", "text": "..."}
        return res.json().get("text", "")


@contextlib.asynccontextmanager
async def clova_ws_connect():
    """
    Clova Speech Streaming Recognition WebSocket 연결.

    오디오 포맷: PCM 16kHz, 16-bit, mono (Little Endian)
    연결 직후 JSON 설정 메시지를 먼저 전송하고 yield.

    응답 JSON 구조:
      {"transcription": {"text": "...", "type": "PARTIAL" | "FINAL"}}
    """
    url = f"{_invoke_url()}/recognizer/streaming"
    async with websockets.connect(url, extra_headers=_auth_headers()) as ws:
        await ws.send(_STREAM_CONFIG)
        yield ws
