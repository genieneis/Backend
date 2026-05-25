from fastapi import HTTPException

from services.db.supabase import get_supabase


async def save_lecture_stt_transcript(*, user_id: str, filename: str, content: str, token: str) -> dict:
    client = get_supabase()
    client.postgrest.auth(token)

    try:
        response = (
            client.table("lesson_stt_transcripts")
            .insert({
                "user_id": user_id,
                "filename": filename,
                "content": content,
            })
            .execute()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"강의 STT 저장 실패: {str(e)}") from e

    record = response.data[0] if response.data else None
    if not record:
        raise HTTPException(status_code=500, detail="강의 STT 저장 실패: 저장된 데이터가 없습니다.")

    return {
        "id": record["id"],
        "filename": record["filename"],
        "created_at": record["created_at"],
    }
