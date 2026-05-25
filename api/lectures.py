from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from supabase_auth.errors import AuthApiError

from services.db.supabase import get_supabase
from services.lectures.lectures import save_lecture_stt_transcript, summarize_lesson


router = APIRouter(
    prefix="/api/lectures",
    tags=["Lectures"],
)

_bearer = HTTPBearer()

MAX_FILE_SIZE = 3 * 1024 * 1024  # 3MB


@router.post("/stt-transcript", status_code=201)
async def upload_lecture_stt_transcript(
    file: UploadFile = File(..., description="STT 변환 텍스트 파일 (.txt)"),
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
):
    """
    강의 STT 변환 텍스트 파일을 업로드하여 DB에 저장.

    - Authorization 헤더에 Bearer 토큰 필요
    - .txt 파일만 허용, 최대 3MB
    """
    client = get_supabase()

    try:
        user_response = client.auth.get_user(credentials.credentials)
    except AuthApiError as e:
        raise HTTPException(status_code=401, detail=str(e.message)) from e

    user = user_response.user
    if not user:
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")

    if not file.filename or not file.filename.endswith(".txt"):
        raise HTTPException(status_code=400, detail=".txt 파일만 업로드할 수 있습니다.")

    contents = await file.read()

    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="파일 크기는 3MB를 초과할 수 없습니다.")

    try:
        content = contents.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="파일 인코딩이 UTF-8이어야 합니다.")

    if not content.strip():
        raise HTTPException(status_code=400, detail="파일 내용이 비어 있습니다.")

    return await save_lecture_stt_transcript(
        user_id=user.id,
        filename=file.filename,
        content=content,
        token=credentials.credentials,
    )

MAX_FILE_SIZE = 3 * 1024 * 1024  # 3MB


@router.post("/summary")
async def create_lesson_summary(
    file: UploadFile = File(..., description="STT 변환 텍스트 파일 (.txt)"),
):
    """
    STT 변환 텍스트 파일을 받아 GPT로 수업 요약본을 생성합니다.
    """
    if not file.filename or not file.filename.endswith(".txt"):
        raise HTTPException(status_code=400, detail=".txt 파일만 업로드할 수 있습니다.")

    contents = await file.read()

    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="파일 크기는 3MB를 초과할 수 없습니다.")

    try:
        stt_text = contents.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="파일 인코딩이 UTF-8이어야 합니다.")

    if not stt_text.strip():
        raise HTTPException(status_code=400, detail="파일 내용이 비어 있습니다.")

    result = await summarize_lesson(stt_text)

    return {
        "topic": result.topic,
        "summary": result.summary,
        "key_concepts": result.key_concepts,
        "important_points": result.important_points,
        "homework": result.homework,
        "test_info": result.test_info,
    }
