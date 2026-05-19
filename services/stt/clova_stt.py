import json
import os
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from enum import Enum

import websockets
from fastapi import HTTPException

CLOVA_SPEECH_WS_URL = "wss://clovaspeech-gw.ncloud.com/external-wss/v1/streaming"


class ResultType(str, Enum):
    PARTIAL = "partial"
    FINAL = "final"


@dataclass
class SttResult:
    type: ResultType
    text: str


def get_clova_secret_key() -> str:
    key = os.getenv("CLOVA_SPEECH_SECRET_KEY")
    if not key:
        raise HTTPException(
            status_code=500,
            detail="CLOVA_SPEECH_SECRET_KEY 환경 변수가 설정되어 있지 않습니다.",
        )
    return key


async def stream_clova_stt(
    audio_chunks: AsyncGenerator[bytes, None],
    sample_rate: int = 16000,
    language: str = "ko-KR",
) -> AsyncGenerator[SttResult, None]:
    """
    Clova Speech Streaming API에 음성 청크를 전달하고 STT 결과를 yield합니다.

    Clova Speech WebSocket 프로토콜:
    1. 연결 후 최초 메시지로 config JSON 전송
    2. 이후 binary 음성 데이터 전송
    3. 서버에서 partial/final 결과 JSON 수신
    4. 종료 시 빈 binary 프레임 전송
    """
    secret_key = get_clova_secret_key()

    headers = {"x-clovaspeech-api-key": secret_key}

    config = {
        "transcription": {
            "language": language,
        },
        "audioFormat": {
            "sampleRate": sample_rate,
            "encoding": "PCM",
            "channels": 1,
        },
    }

    async with websockets.connect(CLOVA_SPEECH_WS_URL, extra_headers=headers) as ws:
        await ws.send(json.dumps(config))

        async def _send_audio():
            async for chunk in audio_chunks:
                await ws.send(chunk)
            await ws.send(b"")  # 종료 신호

        import asyncio

        send_task = asyncio.create_task(_send_audio())

        try:
            async for raw_message in ws:
                if isinstance(raw_message, bytes):
                    continue

                message = json.loads(raw_message)
                result_type = message.get("type")
                text = message.get("text", "").strip()

                if not text:
                    continue

                if result_type == "partial":
                    yield SttResult(type=ResultType.PARTIAL, text=text)
                elif result_type == "final":
                    yield SttResult(type=ResultType.FINAL, text=text)
        finally:
            send_task.cancel()
