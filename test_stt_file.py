"""
WAV 파일을 WebSocket STT 엔드포인트에 전송하고 결과를 출력합니다.

사용법:
    python test_stt_file.py <wav_file>
    python test_stt_file.py reference/korean_speaking.wav

WAV 조건: PCM, 16kHz, mono
    다른 형식이면 ffmpeg로 변환:
    ffmpeg -i input.wav -ar 16000 -ac 1 output.wav
"""

import asyncio
import json
import sys
import wave

import websockets

WS_URL = "ws://localhost:8000/ws/stt"
CHUNK_FRAMES = 1600  # 100ms @ 16kHz


def open_wav(path: str) -> wave.Wave_read:
    try:
        wav = wave.open(path, "rb")
    except FileNotFoundError:
        print(f"파일을 찾을 수 없습니다: {path}")
        sys.exit(1)
    except wave.Error as e:
        print(f"WAV 파일 오류: {e}")
        sys.exit(1)

    ch = wav.getnchannels()
    sr = wav.getframerate()
    sw = wav.getsampwidth()

    print(f"파일: {path}")
    print(f"채널: {ch} | 샘플레이트: {sr}Hz | 비트: {sw * 8}bit")

    errors = []
    if ch != 1:
        errors.append(f"채널이 {ch}개입니다 (mono=1 필요)")
    if sr != 16000:
        errors.append(f"샘플레이트가 {sr}Hz입니다 (16000Hz 필요)")

    if errors:
        print("\n형식 오류:")
        for e in errors:
            print(f"  - {e}")
        print(f"\nffmpeg 변환 명령:")
        print(f"  ffmpeg -i {path} -ar 16000 -ac 1 converted.wav")
        wav.close()
        sys.exit(1)

    duration = wav.getnframes() / sr
    print(f"길이: {duration:.1f}초")
    print()

    return wav


async def stream_wav(wav: wave.Wave_read, websocket):
    total = wav.getnframes()
    sent = 0

    while True:
        chunk = wav.readframes(CHUNK_FRAMES)
        if not chunk:
            break
        await websocket.send(chunk)
        sent += CHUNK_FRAMES
        progress = min(sent / total * 100, 100)
        print(f"\r전송 중... {progress:.0f}%", end="", flush=True)
        await asyncio.sleep(0.1)

    print("\r전송 완료        ")


async def main(wav_path: str):
    wav = open_wav(wav_path)

    print(f"서버 연결 중: {WS_URL}")
    try:
        async with websockets.connect(WS_URL) as ws:
            print("연결됨. STT 결과:\n" + "-" * 40)

            receive_done = asyncio.Event()

            async def receive():
                try:
                    async for raw in ws:
                        data = json.loads(raw)
                        kind = data.get("type", "")
                        text = data.get("text", "")
                        label = "PARTIAL" if kind == "partial" else "FINAL  "
                        print(f"[{label}] {text}")
                except websockets.ConnectionClosed:
                    pass
                finally:
                    receive_done.set()

            recv_task = asyncio.create_task(receive())

            await stream_wav(wav, ws)
            wav.close()

            # 서버가 남은 결과를 보낼 시간 대기
            try:
                await asyncio.wait_for(receive_done.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                pass

            recv_task.cancel()
            print("-" * 40 + "\n완료")

    except OSError:
        print(f"서버에 연결할 수 없습니다. 서버가 실행 중인지 확인하세요: {WS_URL}")
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("사용법: python test_stt_file.py <wav_file>")
        sys.exit(1)

    asyncio.run(main(sys.argv[1]))
