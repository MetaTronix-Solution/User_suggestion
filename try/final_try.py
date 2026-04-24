"""
main.py — Post Recommendation Score Generator + FastAPI
--------------------------------------------------------
Inputs:
  - data/post_random_scores.csv
  - data/post_trending_scores.csv
  - score/content_score.py  (FAISS-based, run as subprocess)

Run API server:
  uvicorn main:app --host 0.0.0.0 --port 8000 --reload

Run CLI:
  python main.py <user_id>

API Endpoints:
  GET  /recommend/{user_id}
  GET  /recommend/{user_id}?top_n=10
  GET  /health
"""

import sys
import os
import subprocess
import json
import pandas as pd
import numpy as np
from typing import List, Optional, Any

import psycopg2
import psycopg2.extras

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ──────────────────────────────────────────────
# DB CONFIG
# ──────────────────────────────────────────────
DB_CONFIG = dict(
    host="36.253.137.34",
    port=5436,
    dbname="social_db",
    user="innovator_user",
    password="Nep@tronix9335%",
)


def get_db_connection():
    """Return a new psycopg2 connection using DB_CONFIG."""
    return psycopg2.connect(**DB_CONFIG)


# ──────────────────────────────────────────────
# CONFIG
# ──────────────────────────────────────────────
RANDOM_SCORES_CSV   = "data/post_random_scores.csv"
TRENDING_SCORES_CSV = "data/post_trending_scores.csv"
CONTENT_SCORER_FILE = "score/content_score.py"
PYTHON_BIN          = "vnev/bin/python"

CONTENT_SCORER_TOP_K = 200

WEIGHTS = {
    "content_score":  0.50,
    "trending_score": 0.40,
    "random_score":   0.10,
}

TOP_N      = 20
OUTPUT_CSV = False   # disabled by default for API; CLI still saves

MEDIA_BASE_URL = "http://36.253.137.34:8005"


# ──────────────────────────────────────────────
# FASTAPI APP
# ──────────────────────────────────────────────
app = FastAPI(
    title="Social Media Recommendation API",
    description="Returns ranked post recommendations for a given user based on content, trending, and random scores.",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ──────────────────────────────────────────────
# RESPONSE MODELS
# ──────────────────────────────────────────────
class MediaItem(BaseModel):
    id:         str
    file:       str
    media_type: str


class CommentItem(BaseModel):
    id:         str
    username:   str
    avatar:     Optional[str]
    post:       str
    parent:     Optional[str]
    content:    str
    created_at: str


class SharedPostDetails(BaseModel):
    id:         str
    username:   str
    full_name:  Optional[str]
    avatar:     Optional[str]
    content:    Optional[str]
    created_at: str
    media:      List[MediaItem]


class PostDetail(BaseModel):
    id:                   str
    user_id:              str
    username:             str
    avatar:               Optional[str]
    content:              Optional[str]
    media:                List[MediaItem]
    categories_detail:    List[Any]
    shared_post:          Optional[str]
    shared_post_details:  Optional[SharedPostDetails]
    reactions_count:      int
    like_count:           int
    reaction_types:       List[str]
    current_user_reaction: Optional[str]
    is_followed:          bool
    comments_count:       int
    comments:             List[CommentItem]
    views_count:          int
    created_at:           str
    updated_at:           str
    # Scoring fields
    final_score:          float
    content_score:        float
    trending_score:       float
    random_score:         float


class RecommendationResponse(BaseModel):
    user_id:     str
    total_posts: int
    top_n:       int
    posts:       List[PostDetail]


# Lightweight model kept for the CLI / internal pipeline
class PostRecommendation(BaseModel):
    rank:            int
    post_id:         str
    final_score:     float
    content_score:   float
    trending_score:  float
    random_score:    float
    views:           Optional[float] = None
    total_reactions: Optional[float] = None
    comment_count:   Optional[float] = None
    created_at:      Optional[str]   = None


# ──────────────────────────────────────────────
# DB HELPERS — fetch enriched post details
# ──────────────────────────────────────────────

def _fetch_post_media(cur, post_ids: List[str]) -> dict:
    """Return {post_id: [MediaItem, ...]} for all given post IDs."""
    if not post_ids:
        return {}
    cur.execute(
        """
        SELECT pm.id::text, pm.post_id::text, pm.file, pm.media_type
        FROM   social_media_postmedia pm
        WHERE  pm.post_id = ANY(%s)
        ORDER BY pm.created_at ASC
        """,
        (post_ids,),
    )
    result: dict = {pid: [] for pid in post_ids}
    for row in cur.fetchall():
        result[row["post_id"]].append(
            MediaItem(id=row["id"], file=row["file"], media_type=row["media_type"])
        )
    return result


def _fetch_post_categories(cur, post_ids: List[str]) -> dict:
    """Return {post_id: [category_detail, ...]}."""
    if not post_ids:
        return {}
    cur.execute(
        """
        SELECT pc.post_id::text,
               c.id::text  AS cat_id,
               c.name       AS cat_name,
               c.slug       AS cat_slug
        FROM   social_media_postcategory pc
        JOIN   social_media_category     c  ON c.id = pc.category_id
        WHERE  pc.post_id = ANY(%s)
        """,
        (post_ids,),
    )
    result: dict = {pid: [] for pid in post_ids}
    for row in cur.fetchall():
        result[row["post_id"]].append(
            {"id": row["cat_id"], "name": row["cat_name"], "slug": row["cat_slug"]}
        )
    return result


def _fetch_reactions(cur, post_ids: List[str]) -> dict:
    """
    Return {post_id: {
        reactions_count, like_count, reaction_types: [str]
    }}
    """
    if not post_ids:
        return {}
    cur.execute(
        """
        SELECT r.post_id::text,
               r.reaction_type,
               COUNT(*) AS cnt
        FROM   social_media_reaction r
        WHERE  r.post_id = ANY(%s)
        GROUP  BY r.post_id, r.reaction_type
        """,
        (post_ids,),
    )
    result: dict = {pid: {"reactions_count": 0, "like_count": 0, "reaction_types": []} for pid in post_ids}
    for row in cur.fetchall():
        pid   = row["post_id"]
        rtype = row["reaction_type"]
        cnt   = row["cnt"]
        result[pid]["reactions_count"] += cnt
        if rtype not in result[pid]["reaction_types"]:
            result[pid]["reaction_types"].append(rtype)
        if rtype == "like":
            result[pid]["like_count"] += cnt
    return result


def _fetch_comments(cur, post_ids: List[str]) -> dict:
    """Return {post_id: [CommentItem, ...]}  (max 10 per post, newest first)."""
    if not post_ids:
        return {}
    cur.execute(
        """
        SELECT c.id::text,
               c.post_id::text,
               c.parent_id::text  AS parent,
               c.content,
               c.created_at::text,
               u.username,
               p.avatar
        FROM   social_media_comment  c
        JOIN   social_media_user     u ON u.id = c.user_id
        LEFT   JOIN social_media_profile p ON p.user_id = c.user_id
        WHERE  c.post_id = ANY(%s)
        ORDER  BY c.created_at DESC
        """,
        (post_ids,),
    )
    result: dict = {pid: [] for pid in post_ids}
    counts: dict = {pid: 0 for pid in post_ids}
    for row in cur.fetchall():
        pid = row["post_id"]
        if counts[pid] >= 10:
            continue
        result[pid].append(
            CommentItem(
                id         = row["id"],
                username   = row["username"],
                avatar     = row["avatar"],
                post       = row["post_id"],
                parent     = row["parent"],
                content    = row["content"],
                created_at = row["created_at"],
            )
        )
        counts[pid] += 1
    return result


def _fetch_comments_count(cur, post_ids: List[str]) -> dict:
    if not post_ids:
        return {}
    cur.execute(
        """
        SELECT post_id::text, COUNT(*) AS cnt
        FROM   social_media_comment
        WHERE  post_id = ANY(%s)
        GROUP  BY post_id
        """,
        (post_ids,),
    )
    result = {pid: 0 for pid in post_ids}
    for row in cur.fetchall():
        result[row["post_id"]] = row["cnt"]
    return result


def _fetch_views_count(cur, post_ids: List[str]) -> dict:
    """
    Try social_media_postview table; fall back to 0 if table doesn't exist
    or views column already on the post row.
    """
    if not post_ids:
        return {}
    try:
        cur.execute(
            """
            SELECT post_id::text, COUNT(*) AS cnt
            FROM   social_media_postview
            WHERE  post_id = ANY(%s)
            GROUP  BY post_id
            """,
            (post_ids,),
        )
        result = {pid: 0 for pid in post_ids}
        for row in cur.fetchall():
            result[row["post_id"]] = row["cnt"]
        return result
    except psycopg2.Error:
        return {pid: 0 for pid in post_ids}


def _fetch_shared_post_details(cur, shared_post_ids: List[str]) -> dict:
    """Return {post_id: SharedPostDetails} for shared posts."""
    ids = [pid for pid in shared_post_ids if pid]
    if not ids:
        return {}

    cur.execute(
        """
        SELECT p.id::text,
               p.content,
               p.created_at::text,
               u.username,
               u.id::text AS uid,
               COALESCE(pr.full_name, '') AS full_name,
               pr.avatar
        FROM   social_media_post    p
        JOIN   social_media_user    u  ON u.id = p.user_id
        LEFT   JOIN social_media_profile pr ON pr.user_id = p.user_id
        WHERE  p.id = ANY(%s)
        """,
        (ids,),
    )
    rows   = {row["id"]: row for row in cur.fetchall()}
    media  = _fetch_post_media(cur, ids)

    result = {}
    for pid, row in rows.items():
        result[pid] = SharedPostDetails(
            id         = pid,
            username   = row["username"],
            full_name  = row["full_name"] or None,
            avatar     = row["avatar"],
            content    = row["content"],
            created_at = row["created_at"],
            media      = media.get(pid, []),
        )
    return result


def _is_followed(cur, follower_id: str, followee_ids: List[str]) -> dict:
    """Return {post_owner_id: bool} — whether follower_id follows each owner."""
    if not followee_ids or not follower_id:
        return {fid: False for fid in followee_ids}
    cur.execute(
        """
        SELECT following_id::text
        FROM   social_media_follow
        WHERE  follower_id  = %s
          AND  following_id = ANY(%s)
        """,
        (follower_id, followee_ids),
    )
    followed = {row["following_id"] for row in cur.fetchall()}
    return {fid: (fid in followed) for fid in followee_ids}


def _current_user_reaction(cur, user_id: str, post_ids: List[str]) -> dict:
    """Return {post_id: reaction_type | None} for the requesting user."""
    if not post_ids or not user_id:
        return {pid: None for pid in post_ids}
    cur.execute(
        """
        SELECT post_id::text, reaction_type
        FROM   social_media_reaction
        WHERE  user_id = %s
          AND  post_id = ANY(%s)
        """,
        (user_id, post_ids),
    )
    result = {pid: None for pid in post_ids}
    for row in cur.fetchall():
        result[row["post_id"]] = row["reaction_type"]
    return result


def fetch_post_details(post_ids: List[str], requesting_user_id: Optional[str] = None) -> dict:
    """
    Fetch full post detail rows from the DB for the given post_ids.
    Returns {post_id: dict} with all fields needed to build PostDetail.
    """
    if not post_ids:
        return {}

    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # ── Core post rows ──────────────────────────────────────────
            cur.execute(
                """
                SELECT p.id::text,
                       p.content,
                       p.created_at::text,
                       p.updated_at::text,
                       p.shared_post_id::text AS shared_post,
                       p.views               AS db_views,
                       u.id::text            AS user_id,
                       u.username,
                       pr.avatar
                FROM   social_media_post    p
                JOIN   social_media_user    u  ON u.id = p.user_id
                LEFT   JOIN social_media_profile pr ON pr.user_id = p.user_id
                WHERE  p.id = ANY(%s)
                """,
                (post_ids,),
            )
            posts_raw = {row["id"]: dict(row) for row in cur.fetchall()}

            if not posts_raw:
                return {}

            found_ids       = list(posts_raw.keys())
            owner_ids       = list({r["user_id"] for r in posts_raw.values()})
            shared_post_ids = [r["shared_post"] for r in posts_raw.values() if r.get("shared_post")]

            # ── Parallel lookups ────────────────────────────────────────
            media_map        = _fetch_post_media(cur, found_ids)
            category_map     = _fetch_post_categories(cur, found_ids)
            reaction_map     = _fetch_reactions(cur, found_ids)
            comment_map      = _fetch_comments(cur, found_ids)
            comment_cnt_map  = _fetch_comments_count(cur, found_ids)
            views_map        = _fetch_views_count(cur, found_ids)
            shared_map       = _fetch_shared_post_details(cur, shared_post_ids)
            follow_map       = _is_followed(cur, requesting_user_id or "", owner_ids)
            cur_reaction_map = _current_user_reaction(cur, requesting_user_id or "", found_ids)

            # ── Assemble ────────────────────────────────────────────────
            result = {}
            for pid, row in posts_raw.items():
                rxn     = reaction_map.get(pid, {})
                db_views = row.get("db_views") or 0
                result[pid] = {
                    "id":                   pid,
                    "user_id":              row["user_id"],
                    "username":             row["username"],
                    "avatar":               row["avatar"],
                    "content":              row["content"],
                    "media":                media_map.get(pid, []),
                    "categories_detail":    category_map.get(pid, []),
                    "shared_post":          row.get("shared_post"),
                    "shared_post_details":  shared_map.get(row.get("shared_post")),
                    "reactions_count":      rxn.get("reactions_count", 0),
                    "like_count":           rxn.get("like_count", 0),
                    "reaction_types":       rxn.get("reaction_types", []),
                    "current_user_reaction": cur_reaction_map.get(pid),
                    "is_followed":          follow_map.get(row["user_id"], False),
                    "comments_count":       comment_cnt_map.get(pid, 0),
                    "comments":             comment_map.get(pid, []),
                    "views_count":          views_map.get(pid, 0) or int(db_views),
                    "created_at":           row["created_at"],
                    "updated_at":           row["updated_at"],
                }
            return result
    finally:
        conn.close()


# ──────────────────────────────────────────────
# CONTENT SCORER SUBPROCESS
# ──────────────────────────────────────────────
def get_content_scores(user_id: str) -> pd.DataFrame:
    scorer_dir = os.path.dirname(os.path.abspath(CONTENT_SCORER_FILE))
    scorer_abs = os.path.abspath(CONTENT_SCORER_FILE)
    python_abs = os.path.abspath(PYTHON_BIN)

    result = subprocess.run(
        [python_abs, scorer_abs, user_id],
        capture_output=True,
        text=True,
        cwd=scorer_dir,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Content scorer subprocess failed for user '{user_id}'.\n"
            f"stderr: {result.stderr.strip()}"
        )

    try:
        stdout     = result.stdout.strip()
        json_start = stdout.rfind("[")
        json_end   = stdout.rfind("]") + 1
        if json_start == -1 or json_end == 0:
            raise ValueError("No JSON array found in content scorer output.")
        data = json.loads(stdout[json_start:json_end])
    except (json.JSONDecodeError, ValueError) as e:
        raise RuntimeError(f"Failed to parse content scorer output: {e}")

    df = pd.DataFrame(data)
    df = df.rename(columns={"similarity": "content_score"})
    df["post_id"] = df["post_id"].astype(str)
    return df


# ──────────────────────────────────────────────
# DATA LOADERS
# ──────────────────────────────────────────────
def load_random_scores() -> pd.DataFrame:
    df = pd.read_csv(RANDOM_SCORES_CSV)
    df = df[["post_id", "random_score"]].drop_duplicates("post_id")
    df["post_id"] = df["post_id"].astype(str)
    return df


def load_trending_scores() -> pd.DataFrame:
    cols = [
        "post_id", "trending_score", "views", "total_reactions",
        "like_count", "love_count", "haha_count", "wow_count",
        "sad_count", "angry_count", "comment_count", "created_at",
    ]
    df = pd.read_csv(TRENDING_SCORES_CSV)
    existing = [c for c in cols if c in df.columns]
    df = df[existing].drop_duplicates("post_id")
    df["post_id"] = df["post_id"].astype(str)
    return df


# ──────────────────────────────────────────────
# NORMALIZATION
# ──────────────────────────────────────────────
def min_max_normalize(series: pd.Series) -> pd.Series:
    lo, hi = series.min(), series.max()
    if hi == lo:
        return pd.Series(np.zeros(len(series)), index=series.index)
    return (series - lo) / (hi - lo)


# ──────────────────────────────────────────────
# CORE PIPELINE (shared by API + CLI)
# ──────────────────────────────────────────────
def get_recommendations(
    user_id: str,
    top_n: int = TOP_N,
    save_csv: bool = OUTPUT_CSV,
) -> pd.DataFrame:
    print(f"\n🔍 Generating recommendations for user_id: {user_id}")

    df_random   = load_random_scores()
    df_trending = load_trending_scores()

    df = pd.merge(df_random, df_trending, on="post_id", how="inner")
    print(f"  → Merged CSV dataset: {len(df)} posts")

    df_content = get_content_scores(user_id)
    print(f"  → {len(df_content)} posts scored by content model")

    df = pd.merge(df, df_content, on="post_id", how="left")
    df["content_score"] = df["content_score"].fillna(0.0)

    df["random_score_norm"]   = min_max_normalize(df["random_score"])
    df["trending_score_norm"] = min_max_normalize(df["trending_score"])
    df["content_score_norm"]  = min_max_normalize(df["content_score"])

    df["final_score"] = (
        WEIGHTS["content_score"]  * df["content_score_norm"]  +
        WEIGHTS["trending_score"] * df["trending_score_norm"] +
        WEIGHTS["random_score"]   * df["random_score_norm"]
    )

    df = df.sort_values("final_score", ascending=False).reset_index(drop=True)
    df.index += 1

    base_cols  = ["post_id", "final_score", "content_score", "trending_score", "random_score"]
    extra_cols = ["views", "total_reactions", "comment_count", "created_at"]
    out_cols   = base_cols + [c for c in extra_cols if c in df.columns]
    result     = df[out_cols].head(top_n)

    for col in ["final_score", "content_score", "trending_score", "random_score"]:
        if col in result.columns:
            result[col] = result[col].round(4)

    if save_csv:
        out_file = f"recommended_posts_{user_id}.csv"
        result.to_csv(out_file)
        print(f"  ✅ Saved → {out_file}")

    return result


# ──────────────────────────────────────────────
# API ENDPOINTS
# ──────────────────────────────────────────────
@app.get("/health", tags=["Health"])
def health_check():
    """Check if the API is running."""
    return {"status": "ok", "message": "Recommendation API is running."}


@app.get(
    "/recommend/{user_id}",
    response_model=RecommendationResponse,
    tags=["Recommendations"],
    summary="Get post recommendations for a user",
)
def recommend(
    user_id: str,
    top_n: int = Query(default=TOP_N, ge=1, le=100, description="Number of posts to return"),
):
    """
    Returns the top-N recommended posts for the given **user_id**,
    ranked by a weighted combination of content, trending, and random scores.

    - **content_score** — FAISS cosine similarity (50 %)
    - **trending_score** — engagement-based trending (40 %)
    - **random_score**   — exploration factor (10 %)

    Each post is enriched with full details from the database:
    media, categories, reactions, comments, shared-post info, and follow status.
    """
    try:
        df = get_recommendations(user_id, top_n=top_n, save_csv=False)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=f"Data file not found: {e}")
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # Score lookup — keyed by post_id string
    score_map: dict = {}
    for rank, row in df.iterrows():
        score_map[str(row["post_id"])] = {
            "final_score":   float(row["final_score"]),
            "content_score": float(row["content_score"]),
            "trending_score": float(row["trending_score"]),
            "random_score":  float(row["random_score"]),
        }

    post_ids = list(score_map.keys())

    # Fetch enriched details from DB
    try:
        details_map = fetch_post_details(post_ids, requesting_user_id=user_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB error: {e}")

    posts: List[PostDetail] = []
    for pid in post_ids:          # preserve ranked order
        detail = details_map.get(pid)
        if not detail:
            continue              # post not found in DB — skip
        scores = score_map[pid]
        posts.append(
            PostDetail(
                **detail,
                final_score   = scores["final_score"],
                content_score = scores["content_score"],
                trending_score= scores["trending_score"],
                random_score  = scores["random_score"],
            )
        )

    return RecommendationResponse(
        user_id     = user_id,
        total_posts = len(posts),
        top_n       = top_n,
        posts       = posts,
    )


# ──────────────────────────────────────────────
# CLI ENTRY POINT
# ──────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) < 2:
        uid = input("Enter User ID: ").strip()
    else:
        uid = sys.argv[1].strip()

    if not uid:
        print("❌ No user ID provided.")
        sys.exit(1)

    try:
        result = get_recommendations(uid, top_n=TOP_N, save_csv=True)
        print(f"\n{'─'*76}")
        print(f"  Top {len(result)} Recommended Posts  |  User: {uid}")
        print(f"{'─'*76}")
        print(f"  {'Rank':<5} {'Post ID':<38} {'Final':>7} {'Content':>8} {'Trend':>7} {'Rand':>6}")
        print(f"  {'─'*70}")
        for rank, row in result.iterrows():
            print(
                f"  {rank:<5} {str(row['post_id']):<38} "
                f"{row['final_score']:>7.4f} "
                f"{row['content_score']:>8.4f} "
                f"{row['trending_score']:>7.4f} "
                f"{row['random_score']:>6.4f}"
            )
        print(f"{'─'*76}\n")
    except (ValueError, RuntimeError) as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)
    except FileNotFoundError as e:
        print(f"\n❌ File not found: {e}")
        sys.exit(1)