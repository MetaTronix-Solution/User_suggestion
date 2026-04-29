import psycopg2
import traceback

from fastapi import APIRouter, HTTPException, Query

from db.queries import validate_user_in_db
from models.schemas import RecommendationResponse
from services.post_service import TOP_N, compute_post_recommendations

router = APIRouter(tags=["Recommendations"])


@router.get("/suggestions/debug/{user_id}")
def debug_recommendations(user_id: str):
    from services.post_service import _build_score_df, _build_reel_score_df, _load_random_scores, _load_trending_scores, _get_content_scores
    from db.queries import filter_posts_existing_in_db, filter_reels_existing_in_db

    random_df   = _load_random_scores()
    trending_df = _load_trending_scores()
    content_df  = _get_content_scores(user_id)
    score_df    = _build_score_df(user_id, top_n=10)
    reel_df     = _build_reel_score_df(top_n=10)

    post_ids_in_db = filter_posts_existing_in_db(score_df["post_id"].tolist())
    reel_ids_in_db = filter_reels_existing_in_db(reel_df["reel_id"].tolist())

    return {
        "random_csv_count":   len(random_df),
        "trending_csv_count": len(trending_df),
        "content_scored":     len(content_df),
        "after_merge":        len(score_df),
        "posts_found_in_db":  len(post_ids_in_db),
        "reels_scored":       len(reel_df),
        "reels_found_in_db":  len(reel_ids_in_db),
    }


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
        print("FULL TRACEBACK:")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")