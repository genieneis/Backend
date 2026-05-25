from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from api.auth import router as auth_router
from api.lectures import router as lectures_router
from api.neis import router as neis_router
from api.stt import router as stt_router

app = FastAPI()

app.include_router(auth_router)
app.include_router(lectures_router)
app.include_router(neis_router)
app.include_router(stt_router)

# 임시 CORS 설정 - 실제 배포 시에는 배포된 프론트엔드 도메인만 허용으로 변경해야함
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def read_root():
    return {"message": "Hello FastAPI"}


