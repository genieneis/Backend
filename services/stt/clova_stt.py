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
            config=json.dumps({
                "transcription": {"language": language},
                "semanticEpd": {
                    "skipEmptyText": True,
                    "useWordEpd": True,
                    "usePeriodEpd": True,
                    "gapThreshold": 700,      # 700ms 묵음 → FINAL
                    "durationThreshold": 1500, # 1.5초마다 PARTIAL → 실시간 자막
                },
            })
        ),
    )

    # 마지막 청크에 epFlag: True를 설정해야 Clova가 발화 종료를 인식하고 FINAL 결과를 반환함
    prev_chunk: bytes | None = None
    async for chunk in audio_chunks:
        if prev_chunk is not None:
            yield nest_pb2.NestRequest(
                type=nest_pb2.RequestType.DATA,
                data=nest_pb2.NestData(
                    chunk=prev_chunk,
                    extra_contents=json.dumps({"seqId": 0, "epFlag": False}),
                ),
            )
        prev_chunk = chunk

    if prev_chunk is not None:
        yield nest_pb2.NestRequest(
            type=nest_pb2.RequestType.DATA,
            data=nest_pb2.NestData(
                chunk=prev_chunk,
                extra_contents=json.dumps({"seqId": 0, "epFlag": True}),
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

            if "transcription" not in response_types:
                continue

            transcription = data.get("transcription", {})
            delta = transcription.get("text", "")
            ep_flag = transcription.get("epFlag", False)
            epd_type = transcription.get("epdType", "")

            if not delta and not ep_flag:
                continue

            # gap: 묵음 감지, endPoint: epFlag=true 전송, period: 구두점
            is_final = ep_flag or epd_type in ("gap", "endPoint", "period")

            if is_final:
                yield SttResult(type=ResultType.FINAL, text=delta)
            else:
                yield SttResult(type=ResultType.PARTIAL, text=delta)
