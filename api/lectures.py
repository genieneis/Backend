from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from dependencies import get_current_token, get_current_user_id
from services.db.supabase import get_supabase
from services.lectures.lectures import get_transcript_summary, get_user_transcripts, save_lecture_stt_transcript, save_lesson_summary, summarize_lesson

router = APIRouter(
    prefix="/api/lectures",
    tags=["Lectures"],
)

MAX_FILE_SIZE = 3 * 1024 * 1024  # 3MB


@router.get("/stt-transcripts")
async def list_user_transcripts(
    user_id: str = Depends(get_current_user_id),
    token: str = Depends(get_current_token),
):
    """
    로그인한 사용자의 STT 노트 목록을 AI 요약 포함하여 반환합니다.
    """
    transcripts = await get_user_transcripts(user_id=user_id, token=token)
    return {"transcripts": transcripts}


@router.post("/stt-transcript", status_code=201)
async def upload_lecture_stt_transcript(
    file: UploadFile = File(..., description="STT 변환 텍스트 파일 (.txt)"),
    subject: str | None = Form(None, description="과목 대범주 (예: 과학탐구, 수학)"),
    subject_name: str | None = Form(None, description="실제 과목명 (예: 물리학, 공통수학1)"),
    ai_content: str | None = Form(None, description="AI 보정 STT 텍스트"),
    user_id: str = Depends(get_current_user_id),
    token: str = Depends(get_current_token),
):
    """
    강의 STT 변환 텍스트 파일을 업로드하여 DB에 저장.
    - .txt 파일만 허용, 최대 3MB
    """
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
        user_id=user_id,
        filename=file.filename,
        content=content,
        subject=subject,
        subject_name=subject_name,
        ai_content=ai_content,
        token=token,
    )


@router.get("/stt-transcript/{transcript_id}/summary")
async def get_lesson_summary(
    transcript_id: str,
    token: str = Depends(get_current_token),
):
    """
    저장된 AI 요약을 반환합니다. 요약이 없으면 404를 반환합니다.
    """
    summary = await get_transcript_summary(transcript_id=transcript_id, token=token)
    if summary is None:
        raise HTTPException(status_code=404, detail="요약이 없습니다.")
    return summary


@router.post("/stt-transcript/{transcript_id}/summary", status_code=201)
async def create_lesson_summary(
    transcript_id: str,
    token: str = Depends(get_current_token),
):
    """
    저장된 STT 트랜스크립트를 기반으로 AI 요약을 생성하고 lesson_stt_summaries에 저장합니다.
    """
    supabase = get_supabase()
    supabase.postgrest.auth(token)

    # AI 보정본 우선 조회 (lesson_stt_ai_transcripts.transcript_id = raw_transcript_id)
    stt_text = ""
    try:
        ai_row = (
            supabase.table("lesson_stt_ai_transcripts")
            .select("content")
            .eq("transcript_id", transcript_id)
            .maybe_single()
            .execute()
        )
        if ai_row.data:
            stt_text = ai_row.data.get("content", "")
    except Exception:
        pass

    # AI 보정본 없으면 원문으로 fallback
    if not stt_text.strip():
        try:
            raw_row = (
                supabase.table("lesson_stt_transcripts")
                .select("content")
                .eq("id", transcript_id)
                .single()
                .execute()
            )
            stt_text = raw_row.data.get("content", "")
        except Exception as e:
            raise HTTPException(status_code=404, detail="트랜스크립트를 찾을 수 없습니다.") from e
    if not stt_text.strip():
        raise HTTPException(status_code=400, detail="트랜스크립트 내용이 비어 있습니다.")

    result = await summarize_lesson(stt_text)
    await save_lesson_summary(transcript_id=transcript_id, summary=result, token=token)

    return {
        "topic": result.topic,
        "summary": result.summary,
        "key_concepts": result.key_concepts,
        "important_points": result.important_points,
        "homework": result.homework,
        "test_info": result.test_info,
    }
