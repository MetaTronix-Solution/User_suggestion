from typing import List
import random

import numpy as np
import pandas as pd

from db.queries import (
    fetch_post_details,
    fetch_reel_details,
    filter_posts_existing_in_db,
    filter_reels_existing_in_db,
    validate_user_in_db,
)
from models.schemas import PostDetail, RecommendationResponse
from score.random_score import generate_random_scores as refresh_random_scores
from score.content_score import search_posts_for_user
from score.collaborative_score import collaborative_filter_response
from utils.helpers import REC_WEIGHTS, TRENDING_CSV, _min_max_normalize

TOP_N      = 10
OUTPUT_CSV = False


# ──────────────────────────────────────────────────────────────────────────────
# SCORE LOADERS
# ──────────────────────────────────────────────────────────────────────────────

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


# ──────────────────────────────────────────────────────────────────────────────
# POST SCORE PIPELINE
# ──────────────────────────────────────────────────────────────────────────────

def _build_score_df(user_id: str, top_n: int, save_csv: bool = False) -> pd.DataFrame:
    """Merge all four scoring signals and return a ranked DataFrame."""
    print(f"\n  Scoring posts for user_id: {user_id}")

    df = pd.merge(_load_random_scores(), _load_trending_scores(), on="post_id", how="inner")
    print(f"   CSV dataset: {len(df)} posts")

    df_content = _get_content_scores(user_id)
    print(f"   Content model: {len(df_content)} posts scored")

    df_collab = _get_collaborative_scores(user_id)
    print(f"   Collaborative model: {len(df_collab)} posts scored")

    df = pd.merge(df, df_content, on="post_id", how="left")
    df["content_score"] = df["content_score"].fillna(0.0)

    df = pd.merge(df, df_collab, on="post_id", how="left")
    df["collaborative_score"] = df["collaborative_score"].fillna(0.0).infer_objects(copy=False)

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

    df = df.sort_values("final_score", ascending=False)

    # 🚨 REMOVE DUPLICATES HERE
    df = df.drop_duplicates(subset=["post_id"], keep="first")

    df = df.reset_index(drop=True)
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
        print(f"  Saved -> {out}")

    return result


# ──────────────────────────────────────────────────────────────────────────────
# REEL SCORE PIPELINE
# ──────────────────────────────────────────────────────────────────────────────

def _build_reel_score_df(top_n: int) -> pd.DataFrame:
    """
    Score reels using views_count as trending proxy + random noise.
    Pulls directly from DB — no CSV needed.
    """
    from db.queries import get_db_connection
    import psycopg2.extras

    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id::text AS reel_id, views_count
                FROM   social_media_reel
                WHERE  video IS NOT NULL
                ORDER  BY created_at DESC
                LIMIT  %s
                """,
                (top_n * 10,),
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    if not rows:
        return pd.DataFrame(columns=["reel_id", "final_score", "trending_score", "random_score"])

    df = pd.DataFrame(rows)
    df["reel_id"]        = df["reel_id"].astype(str)
    df["random_score"]   = np.random.rand(len(df))
    df["trending_score"] = df["views_count"].astype(float)

    df["trending_score_norm"] = _min_max_normalize(df["trending_score"])
    df["random_score_norm"]   = _min_max_normalize(df["random_score"])

    df["final_score"] = (
        0.6 * df["trending_score_norm"] +
        0.4 * df["random_score_norm"]
    )

    return (
        df[["reel_id", "final_score", "trending_score", "random_score"]]
        .sort_values("final_score", ascending=False)
        .reset_index(drop=True)
    )


# ──────────────────────────────────────────────────────────────────────────────
# PUBLIC API
# ──────────────────────────────────────────────────────────────────────────────

def compute_post_recommendations(user_id: str, top_n: int = TOP_N) -> RecommendationResponse:
    validate_user_in_db(user_id)

    # 1. Score posts
    df = _build_score_df(user_id, top_n=top_n)

    score_map = {}

    for _, row in df.iterrows():
        pid = str(row["post_id"])

        if pid not in score_map:
            score_map[pid] = {
                "final_score": float(row["final_score"]),
                "content_score": float(row["content_score"]),
                "trending_score": float(row["trending_score"]),
                "random_score": float(row["random_score"]),
            }

    # filter valid posts from DB (ONLY ONCE)
    existing_post_ids = list(set(filter_posts_existing_in_db(list(score_map.keys()))))

    # 2. Score reels
    reel_df = _build_reel_score_df(top_n=top_n)

    reel_score_map = {}

    for _, row in reel_df.iterrows():
        rid = str(row["reel_id"])

        reel_score_map[rid] = {
            "final_score": float(row["final_score"]),
            "content_score": 0.0,
            "trending_score": float(row["trending_score"]),
            "random_score": float(row["random_score"]),
        }

    existing_reel_ids = list(set(filter_reels_existing_in_db(list(reel_score_map.keys()))))

    # ─────────────────────────────────────────────
    # CROSS DEDUPE FIX
    # ─────────────────────────────────────────────
    existing_post_ids = [pid for pid in existing_post_ids if pid not in existing_reel_ids]
    existing_reel_ids = [rid for rid in existing_reel_ids if rid not in existing_post_ids]

    random.shuffle(existing_post_ids)
    random.shuffle(existing_reel_ids)

    post_pool = existing_post_ids[:top_n * 2]
    reel_pool = existing_reel_ids[:top_n]

    # 3. Interleave selection
    final_post_ids = []
    final_reel_ids = []

    pi = ri = 0

    for i in range(top_n):
        if ri < len(reel_pool) and (i + 1) % 4 == 0:
            final_reel_ids.append(reel_pool[ri])
            ri += 1
        elif pi < len(post_pool):
            final_post_ids.append(post_pool[pi])
            pi += 1

    # 4. If empty fallback
    if not final_post_ids and not final_reel_ids:
        return RecommendationResponse(
            user_id=user_id,
            total_posts=0,
            top_n=top_n,
            posts=[]
        )

    # 5. Fetch details
    details_map = fetch_post_details(final_post_ids, requesting_user_id=user_id)
    reel_details_map = fetch_reel_details(final_reel_ids, requesting_user_id=user_id)

    # 6. Build final response
    posts: List[PostDetail] = []
    seen_ids = set()

    pi = ri = 0
    i = 0

    while len(posts) < top_n and (pi < len(final_post_ids) or ri < len(final_reel_ids)):

        use_reel = (i + 1) % 4 == 0

        if use_reel and ri < len(final_reel_ids):
            rid = final_reel_ids[ri]
            ri += 1

            if rid in seen_ids:
                continue

            detail = reel_details_map.get(rid)
            if detail:
                seen_ids.add(rid)
                posts.append(PostDetail(**detail, **reel_score_map[rid]))

        elif pi < len(final_post_ids):
            pid = final_post_ids[pi]
            pi += 1

            if pid in seen_ids:
                continue

            detail = details_map.get(pid)
            if detail:
                seen_ids.add(pid)
                posts.append(PostDetail(**detail, **score_map[pid]))

        i += 1

    return RecommendationResponse(
        user_id=user_id,
        total_posts=len(posts),
        top_n=top_n,
        posts=posts
    )