import json
import os
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from enum import Enum

import grpc
from fastapi import HTTPException

from . import nest_pb2, nest_pb2_grpc

CLOVA_SPEECH_HOST = "clovaspeech-gw.ncloud.com:50051"


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


async def _build_requests(
    audio_chunks: AsyncGenerator[bytes, None],
    language: str,
) -> AsyncGenerator[nest_pb2.NestRequest, None]:
    yield nest_pb2.NestRequest(
        type=nest_pb2.RequestType.CONFIG,
        config=nest_pb2.NestConfig(
            config=json.dumps({"transcription": {"language": language}})
        ),
    )

    async for chunk in audio_chunks:
        yield nest_pb2.NestRequest(
            type=nest_pb2.RequestType.DATA,
            data=nest_pb2.NestData(
                chunk=chunk,
                extra_contents=json.dumps({"seqId": 0, "epFlag": False}),
            ),
        )


async def stream_clova_stt(
    audio_chunks: AsyncGenerator[bytes, None],
    language: str = "ko",
) -> AsyncGenerator[SttResult, None]:
    secret_key = get_clova_secret_key()
    metadata = (("authorization", f"Bearer {secret_key}"),)

    async with grpc.aio.secure_channel(
        CLOVA_SPEECH_HOST,
        grpc.ssl_channel_credentials(),
    ) as channel:
        stub = nest_pb2_grpc.NestServiceStub(channel)

        async for response in stub.recognize(
            _build_requests(audio_chunks, language),
            metadata=metadata,
        ):
            try:
                data = json.loads(response.contents)
            except (json.JSONDecodeError, ValueError):
                continue

            response_types = data.get("responseType", [])

            if "transcription" in response_types:
                transcription = data.get("transcription", {})
                text = transcription.get("text", "").strip()
                if text:
                    yield SttResult(type=ResultType.FINAL, text=text)
