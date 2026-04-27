from datetime import datetime, timezone

from fastapi import APIRouter, Query

from services.user_service import compute_user_suggestions

router = APIRouter(tags=["Suggestions"])


@router.get("/suggest/{user_id}")
def suggest(
    user_id: str,
    limit: int = Query(10, ge=1, le=50, description="Number of user suggestions to return"),
):
    suggestions = compute_user_suggestions(user_id, limit)
    return {
        "user_id":      user_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total":        len(suggestions),
        "suggestions":  suggestions,
    }
