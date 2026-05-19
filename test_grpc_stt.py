import asyncio
import os
import sys
import wave


# - WAV 파일 → Clova Speech gRPC 직접 호출
# - STT 자체가 정상 작동하는지 확인

sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()

from services.stt.clova_stt import stream_clova_stt

WAV_PATH = "reference/korean_speaking.wav"
CHUNK_FRAMES = 1600  # 100ms @ 16kHz


async def audio_from_wav(path: str):
    with wave.open(path, "rb") as wav:
        while True:
            chunk = wav.readframes(CHUNK_FRAMES)
            if not chunk:
                break
            yield chunk
            await asyncio.sleep(0.1)


async def main():
    print(f"파일: {WAV_PATH}")
    print("STT 스트리밍 시작...\n")

    async for result in stream_clova_stt(audio_from_wav(WAV_PATH)):
        print(f"[{result.type.value}] {result.text}")

    print("\n완료")


asyncio.run(main())
