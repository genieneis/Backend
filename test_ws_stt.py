import asyncio
import wave
import websockets

WS_URL = (
    "ws://localhost:8000/ws/stt"
    "?school_kind=high"
    "&education_office_code=B10"
    "&school_code=7010057"
    "&grade=2"
    "&class_nm=1"
)

WAV_PATH = "reference/korean_speaking.wav"


async def send_audio():
    async with websockets.connect(WS_URL) as websocket:
        print("WebSocket connected")

        async def receive_messages():
            try:
                async for message in websocket:
                    print("서버 응답:", message)
            except websockets.ConnectionClosed:
                print("WebSocket closed")

        receive_task = asyncio.create_task(receive_messages())

        with wave.open(WAV_PATH, "rb") as wav:
            print("channels:", wav.getnchannels())
            print("sample rate:", wav.getframerate())
            print("sample width:", wav.getsampwidth())

            # PCM 16kHz mono인지 확인
            if wav.getnchannels() != 1:
                raise ValueError("mono 음성 파일이어야 합니다.")
            if wav.getframerate() != 16000:
                raise ValueError("sample rate가 16000Hz여야 합니다.")

            chunk_size = 3200  # 약 100ms 분량: 16000 samples/sec * 2 bytes * 0.1 sec

            while True:
                chunk = wav.readframes(chunk_size // 2)

                if not chunk:
                    break

                await websocket.send(chunk)
                await asyncio.sleep(0.1)

        print("음성 전송 완료")
        await asyncio.sleep(3)

        receive_task.cancel()


asyncio.run(send_audio())