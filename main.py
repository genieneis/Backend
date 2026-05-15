from dotenv import load_dotenv
from fastapi import FastAPI

load_dotenv()

from api.stt import router as stt_router
from api.neis import router as neis_router

app = FastAPI()

app.include_router(stt_router)
app.include_router(neis_router)


@app.get("/")
def read_root():
    return {"message": "Hello FastAPI"}


