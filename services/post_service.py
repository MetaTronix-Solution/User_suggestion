from typing import List

import numpy as np
import pandas as pd

from db.queries import (
    fetch_post_details,
    filter_posts_existing_in_db,
    validate_user_in_db,
)
from models.schemas import PostDetail, RecommendationResponse
from score.random_score import generate_random_scores as refresh_random_scores
from score.content_score import search_posts_for_user
from score.collaborative_score import collaborative_filter_response
from utils.helpers import REC_WEIGHTS, TRENDING_CSV, _min_max_normalize

TOP_N      = 10
OUTPUT_CSV = False


# ─────────────────────────────────────────────────────────────────────────────
# SCORE LOADERS
# ─────────────────────────────────────────────────────────────────────────────

def _get_content_scores(user_id: str) -> pd.DataFrame:
    try:
        results = search_posts_for_user(user_id)
    except ValueError as e:
        raise RuntimeError(f"Content scorer failed for user '{user_id}': {e}")
    df = pd.DataFrame(results).rename(columns={"similarity": "content_score"})
    df["post_id"] = df["post_id"].astype(str)
    return df


def _get_collaborative_scores(user_id: str) -> pd.DataFrame:
    try:
        results = collaborative_filter_response(user_id)
    except ValueError as e:
        raise RuntimeError(f"Collaborative scorer failed for user '{user_id}': {e}")
    if not results:
        return pd.DataFrame(columns=["post_id", "collaborative_score"])
    df = pd.DataFrame(results)
    if "post_id" not in df.columns or "similarity" not in df.columns:
        return pd.DataFrame(columns=["post_id", "collaborative_score"])
    df = df.rename(columns={"similarity": "collaborative_score"})
    df["post_id"] = df["post_id"].astype(str)
    return df


def _load_random_scores() -> pd.DataFrame:
    data = refresh_random_scores()
    df   = pd.DataFrame(data) if isinstance(data, list) else data
    df["post_id"] = df["post_id"].astype(str)
    return df


def _load_trending_scores() -> pd.DataFrame:
    cols = [
        "post_id", "trending_score", "views", "total_reactions",
        "like_count", "love_count", "haha_count", "wow_count",
        "sad_count", "angry_count", "comment_count", "created_at",
    ]
    df = pd.read_csv(TRENDING_CSV)
    df = df[[c for c in cols if c in df.columns]].drop_duplicates("post_id")
    df["post_id"] = df["post_id"].astype(str)
    return df


# ─────────────────────────────────────────────────────────────────────────────
# SCORE PIPELINE
# ─────────────────────────────────────────────────────────────────────────────

def _build_score_df(user_id: str, top_n: int, save_csv: bool = False) -> pd.DataFrame:
    """Merge all four scoring signals and return a ranked DataFrame."""
    print(f"\n🔍 Scoring for user_id: {user_id}")

    df = pd.merge(_load_random_scores(), _load_trending_scores(), on="post_id", how="inner")
    print(f"  → CSV dataset: {len(df)} posts")

    df_content = _get_content_scores(user_id)
    print(f"  → Content model: {len(df_content)} posts scored")

    df_collab = _get_collaborative_scores(user_id)
    print(f"  → Collaborative model: {len(df_collab)} posts scored")

    df = pd.merge(df, df_content, on="post_id", how="left")
    df["content_score"] = df["content_score"].fillna(0.0)

    df = pd.merge(df, df_collab, on="post_id", how="left")
    df["collaborative_score"] = df["collaborative_score"].fillna(0.0)

    df["random_score_norm"]        = _min_max_normalize(df["random_score"])
    df["trending_score_norm"]      = _min_max_normalize(df["trending_score"])
    df["content_score_norm"]       = _min_max_normalize(df["content_score"])
    df["collaborative_score_norm"] = _min_max_normalize(df["collaborative_score"])

    df["final_score"] = (
        REC_WEIGHTS["content_score"]       * df["content_score_norm"]       +
        REC_WEIGHTS["trending_score"]      * df["trending_score_norm"]      +
        REC_WEIGHTS["random_score"]        * df["random_score_norm"]        +
        REC_WEIGHTS["collaborative_score"] * df["collaborative_score_norm"]
    )

    df = df.sort_values("final_score", ascending=False).reset_index(drop=True)
    df.index += 1

    base_cols  = ["post_id", "final_score", "content_score", "trending_score", "random_score"]
    extra_cols = ["views", "total_reactions", "comment_count", "created_at"]
    result     = df[base_cols + [c for c in extra_cols if c in df.columns]].head(top_n * 3)

    for col in ["final_score", "content_score", "trending_score", "random_score"]:
        if col in result.columns:
            result[col] = result[col].round(4)

    if save_csv:
        out = f"recommended_posts_{user_id}.csv"
        result.to_csv(out)
        print(f"  ✅ Saved → {out}")

    return result


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────────────────────

def compute_post_recommendations(
    user_id: str, top_n: int = TOP_N
) -> RecommendationResponse:
    """
    Full pipeline: validate → score → DB filter → enrich → assemble.
    Shared by the API endpoint and the CLI.
    """
    validate_user_in_db(user_id)

    df        = _build_score_df(user_id, top_n=top_n)
    score_map = {
        str(row["post_id"]): {
            "final_score":    float(row["final_score"]),
            "content_score":  float(row["content_score"]),
            "trending_score": float(row["trending_score"]),
            "random_score":   float(row["random_score"]),
        }
        for _, row in df.iterrows()
    }

    existing_ids = filter_posts_existing_in_db(list(score_map.keys()))
    print(f"  → {len(score_map)} scored | {len(existing_ids)} in DB | top {top_n} returned")

    final_ids = existing_ids[:top_n]
    if not final_ids:
        return RecommendationResponse(user_id=user_id, total_posts=0, top_n=top_n, posts=[])

    details_map = fetch_post_details(final_ids, requesting_user_id=user_id)

    posts: List[PostDetail] = []
    for pid in final_ids:
        detail = details_map.get(pid)
        if not detail:
            continue
        posts.append(PostDetail(**detail, **score_map[pid]))

    return RecommendationResponse(user_id=user_id, total_posts=len(posts), top_n=top_n, posts=posts)