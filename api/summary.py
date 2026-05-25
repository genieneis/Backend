from fastapi import APIRouter, HTTPException, UploadFile, File

from services.summary.gpt_summarizer import summarize_lesson

router = APIRouter(
    prefix="/api/summary",
    tags=["Summary"],
)

MAX_FILE_SIZE = 3 * 1024 * 1024  # 3MB


@router.post("/lesson")
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
