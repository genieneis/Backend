from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from supabase_auth.errors import AuthApiError

from services.db.supabase import get_supabase
from services.lectures.lectures import save_lecture_stt_transcript, save_lesson_summary, summarize_lesson


router = APIRouter(
    prefix="/api/lectures",
    tags=["Lectures"],
)

_bearer = HTTPBearer()

MAX_FILE_SIZE = 3 * 1024 * 1024  # 3MB


@router.post("/stt-transcript", status_code=201)
async def upload_lecture_stt_transcript(
    file: UploadFile = File(..., description="STT 변환 텍스트 파일 (.txt)"),
    subject: str | None = Form(None, description="과목명"),
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
        subject=subject,
        token=credentials.credentials,
    )

@router.post("/stt-transcript/{transcript_id}/summary", status_code=201)
async def create_lesson_summary(
    transcript_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
):
    """
    저장된 STT 트랜스크립트를 기반으로 AI 요약을 생성하고 lesson_stt_summaries에 저장합니다.
    """
    supabase = get_supabase()

    try:
        user_response = supabase.auth.get_user(credentials.credentials)
    except AuthApiError as e:
        raise HTTPException(status_code=401, detail=str(e.message)) from e

    if not user_response.user:
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")

    supabase.postgrest.auth(credentials.credentials)
    try:
        row = (
            supabase.table("lesson_stt_transcripts")
            .select("content")
            .eq("id", transcript_id)
            .single()
            .execute()
        )
    except Exception as e:
        raise HTTPException(status_code=404, detail="트랜스크립트를 찾을 수 없습니다.") from e

    stt_text = row.data.get("content", "")
    if not stt_text.strip():
        raise HTTPException(status_code=400, detail="트랜스크립트 내용이 비어 있습니다.")

    result = await summarize_lesson(stt_text)
    await save_lesson_summary(
        transcript_id=transcript_id,
        summary=result,
        token=credentials.credentials,
    )

    return {
        "topic": result.topic,
        "summary": result.summary,
        "key_concepts": result.key_concepts,
        "important_points": result.important_points,
        "homework": result.homework,
        "test_info": result.test_info,
    }
