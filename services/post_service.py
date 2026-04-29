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

TOP_N      = 20
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
    from db.queries import get_db_connection
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    p.id::text AS post_id,
                    p.views_count AS views,
                    COUNT(DISTINCT c.id) AS comment_count,
                    COUNT(DISTINCT r.id) AS total_reactions,
                    p.views_count + (COUNT(DISTINCT r.id) * 3) + (COUNT(DISTINCT c.id) * 5) AS trending_score
                FROM social_media_post p
                LEFT JOIN social_media_comment  c ON c.post_id = p.id
                LEFT JOIN social_media_reaction r ON r.post_id = p.id
                GROUP BY p.id, p.views_count
            """)
            rows = cur.fetchall()
    finally:
        conn.close()

    return pd.DataFrame(rows, columns=["post_id", "views", "comment_count", "total_reactions", "trending_score"])


# ──────────────────────────────────────────────────────────────────────────────
# POST SCORE PIPELINE
# ──────────────────────────────────────────────────────────────────────────────

def _build_score_df(user_id: str, top_n: int, save_csv: bool = False) -> pd.DataFrame:
    """Merge all four scoring signals and return a ranked DataFrame."""
    print(f"\n  Scoring posts for user_id: {user_id}")

    df = pd.merge(_load_random_scores(), _load_trending_scores(), on="post_id", how="left")
    df["trending_score"] = df["trending_score"].fillna(0.0)
    print(f"   CSV dataset: {len(df)} posts")

    df_content = _get_content_scores(user_id)
    print(f"   Content model: {len(df_content)} posts scored")

    df_collab = _get_collaborative_scores(user_id)
    print(f"   Collaborative model: {len(df_collab)} posts scored")

    df = pd.merge(df, df_content, on="post_id", how="left")
    df["content_score"] = df["content_score"].fillna(0.0)

    df = pd.merge(df, df_collab, on="post_id", how="left")
    df["collaborative_score"] = df["collaborative_score"].fillna(0.0).infer_objects()

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

def compute_post_recommendations(
    user_id: str, top_n: int = TOP_N
) -> RecommendationResponse:
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

    existing_post_ids = list(set(filter_posts_existing_in_db(list(score_map.keys()))))

    # 2. Score reels
    reel_df = _build_reel_score_df(top_n=top_n)

    reel_score_map = {
        row["reel_id"]: {
            "final_score":    float(row["final_score"]),
            "content_score":  0.0,
            "trending_score": float(row["trending_score"]),
            "random_score":   float(row["random_score"]),
        }
        for _, row in reel_df.iterrows()
    }

    existing_reel_ids = list(set(filter_reels_existing_in_db(list(reel_score_map.keys()))))

    # ─────────────────────────────────────────────
    # 🔥 GLOBAL DEDUPE (CRITICAL FIX)
    # ─────────────────────────────────────────────

    # Remove cross-over BEFORE pool creation
    existing_post_ids = [
        pid for pid in existing_post_ids
        if pid not in set(existing_reel_ids)
    ]

    existing_reel_ids = [
        rid for rid in existing_reel_ids
        if rid not in set(existing_post_ids)
    ]

    # 3. Shuffle for randomness
    random.shuffle(existing_post_ids)
    random.shuffle(existing_reel_ids)

    post_pool = list(dict.fromkeys(existing_post_ids))[:top_n * 2]
    reel_pool = list(dict.fromkeys(existing_reel_ids))[:top_n]

    # 4. Target calculations (40% reels, 60% posts)
    target_reels = int(top_n * 0.4)
    target_posts = top_n - target_reels

    # adjust if we don't have enough in pool
    if len(reel_pool) < target_reels:
        target_reels = len(reel_pool)
        target_posts = top_n - target_reels

    if len(post_pool) < target_posts:
        target_posts = len(post_pool)
        # if we have extra reels, use them to fill up top_n
        target_reels = min(len(reel_pool), top_n - target_posts)

    final_post_ids = post_pool[:target_posts]
    final_reel_ids = reel_pool[:target_reels]

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

    # 6. FINAL ASSEMBLY (FULL DEDUPE PROTECTION)
    posts: List[PostDetail] = []
    seen_ids = set()
    pi = ri = 0

    total_items = len(final_post_ids) + len(final_reel_ids)
    for i in range(total_items):
        ratio_r = ri / target_reels if target_reels > 0 else 1.0
        ratio_p = pi / target_posts if target_posts > 0 else 1.0

        if ratio_r < ratio_p and ri < len(final_reel_ids):
            rid = final_reel_ids[ri]
            ri += 1
            if str(rid) not in seen_ids:
                detail = reel_details_map.get(rid)
                if detail:
                    seen_ids.add(str(rid))
                    posts.append(PostDetail(**detail, **reel_score_map[rid]))
        elif pi < len(final_post_ids):
            pid = final_post_ids[pi]
            pi += 1
            if str(pid) not in seen_ids:
                detail = details_map.get(pid)
                if detail:
                    seen_ids.add(str(pid))
                    posts.append(PostDetail(**detail, **score_map[pid]))

    return RecommendationResponse(
        user_id=user_id,
        total_posts=len(posts),
        top_n=top_n,
        posts=posts
    )