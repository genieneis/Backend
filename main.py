from fastapi import FastAPI

from api.stt import router as stt_router

app = FastAPI(title="Genie NEIS Backend")

app.include_router(stt_router)


@app.get("/")
def read_root():
    return {"message": "Hello FastAPI"}
