from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def read_root():
    return {"message": "Hello FastAPI"}

@app.get("/jesseo")
def read_jesseo():
    return {"hi Jesseo"}