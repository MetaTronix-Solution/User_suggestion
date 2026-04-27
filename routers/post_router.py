import psycopg2

from fastapi import APIRouter, HTTPException, Query

from db.queries import validate_user_in_db
from models.schemas import RecommendationResponse
from services.post_service import TOP_N, compute_post_recommendations

router = APIRouter(tags=["Recommendations"])


@router.get(
    "/suggestions/{user_id}",
    response_model=RecommendationResponse,
    summary="Get post/reel recommendations for a user",
)
def suggestions(
    user_id: str,
    top_n: int = Query(default=TOP_N, ge=1, le=100, description="Number of posts to return"),
):
    try:
        validate_user_in_db(user_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except psycopg2.errors.InvalidTextRepresentation:
        raise HTTPException(status_code=400, detail=f"Invalid UUID: '{user_id}'")
    except psycopg2.OperationalError as e:
        raise HTTPException(status_code=503, detail=f"DB connection error: {e}")

    try:
        return compute_post_recommendations(user_id, top_n=top_n)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=f"Data file not found: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")
