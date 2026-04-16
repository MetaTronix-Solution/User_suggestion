import os
import math
import psycopg2
import pandas as pd
import numpy as np
import networkx as nx
import asyncio

from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

from datetime import datetime, timezone
from typing import Optional, Set

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ─────────────────────────────────────────────
# GLOBAL MODEL (SAFE + FAST STARTUP)
# ─────────────────────────────────────────────
MODEL = None

def get_model():
    global MODEL
    if MODEL is None:
        MODEL = SentenceTransformer("all-MiniLM-L6-v2")
    return MODEL


# ─────────────────────────────────────────────
# APP SETUP
# ─────────────────────────────────────────────
app = FastAPI(
    title="Friend Suggestion API",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────
# LOAD MODEL ON STARTUP (IMPORTANT FIX FOR RENDER)
# ─────────────────────────────────────────────
@app.on_event("startup")
def startup_event():
    global MODEL
    MODEL = SentenceTransformer("all-MiniLM-L6-v2")


# ─────────────────────────────────────────────
# DATABASE
# ─────────────────────────────────────────────
DB_CONFIG = dict(
    host="182.93.94.220",
    port=5436,
    dbname="social_db",
    user="innovator_user",
    password="Nep@tronix9335%"
)

def get_conn():
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = True
    return conn


# ─────────────────────────────────────────────
# PYDANTIC MODELS
# ─────────────────────────────────────────────
class ScoreBreakdown(BaseModel):
    text_score: float
    graph_score: float
    adamic_adar: float
    second_degree: float
    interest_score: float
    location_score: float
    interaction_score: float
    collab_score: float
    activity_score: float

class WeightsUsed(BaseModel):
    text: float
    graph: float
    interest: float
    location: float
    interaction: float
    collab: float
    activity: float

class SuggestedUser(BaseModel):
    user_id: str
    username: Optional[str]
    full_name: Optional[str]
    affinity_score: float
    mutual_count: int
    shared_tags: list
    reason: str
    breakdown: dict
    weights_used: dict


# ─────────────────────────────────────────────
# SAFE DB HELPERS
# ─────────────────────────────────────────────
def safe_fetch(cur, query, params=()):
    try:
        cur.execute(query, params)
        return cur.fetchall()
    except Exception:
        cur.connection.rollback()
        return []

def safe_fetchone(cur, query, params=()):
    try:
        cur.execute(query, params)
        return cur.fetchone()
    except Exception:
        cur.connection.rollback()
        return None


# ─────────────────────────────────────────────
# FILTERS
# ─────────────────────────────────────────────
def get_already_following(cur, user_id) -> Set[str]:
    rows = safe_fetch(cur,
        "SELECT to_user_id FROM social_media_user_following WHERE from_user_id = %s",
        (user_id,)
    )
    return {r[0] for r in rows}

def get_blocked_users(cur, user_id) -> Set[str]:
    rows = safe_fetch(cur, """
        SELECT to_user_id FROM social_media_user_blocked_users WHERE from_user_id = %s
        UNION
        SELECT from_user_id FROM social_media_user_blocked_users WHERE to_user_id = %s
    """, (user_id, user_id))
    return {r[0] for r in rows}

def validate_user(cur, user_id: str) -> bool:
    row = safe_fetchone(cur,
        "SELECT 1 FROM social_media_user WHERE id = %s",
        (user_id,)
    )
    return row is not None


# ─────────────────────────────────────────────
# CANDIDATES
# ─────────────────────────────────────────────
def get_bfs_candidates(cur, user_id):
    query = """
        WITH RECURSIVE fof AS (
            SELECT to_user_id AS uid, 1 AS depth
            FROM social_media_user_following
            WHERE from_user_id = %s
            UNION
            SELECT f.to_user_id, fof.depth + 1
            FROM social_media_user_following f
            JOIN fof ON f.from_user_id = fof.uid
            WHERE fof.depth < 2
        )
        SELECT DISTINCT uid FROM fof
        WHERE uid != %s;
    """
    rows = safe_fetch(cur, query, (user_id, user_id))
    return {r[0] for r in rows}

def get_interest_cluster_candidates(cur, user_id, min_shared=1, top_k=100):
    query = """
        SELECT p2.user_id
        FROM social_media_profile_interests i1
        JOIN social_media_profile_interests i2 ON i1.category_id = i2.category_id
        JOIN social_media_profile p1 ON i1.profile_id = p1.id
        JOIN social_media_profile p2 ON i2.profile_id = p2.id
        WHERE p1.user_id = %s
          AND p2.user_id != %s
        GROUP BY p2.user_id
        HAVING COUNT(*) >= %s
        LIMIT %s
    """
    rows = safe_fetch(cur, query, (user_id, user_id, min_shared, top_k))
    return {r[0] for r in rows}

def get_fallback(cur, exclude, limit=200):
    if not exclude:
        rows = safe_fetch(cur,
            "SELECT id FROM social_media_user ORDER BY RANDOM() LIMIT %s",
            (limit,)
        )
    else:
        placeholders = ",".join(["%s"] * len(exclude))
        rows = safe_fetch(cur,
            f"SELECT id FROM social_media_user WHERE id NOT IN ({placeholders}) LIMIT %s",
            (*exclude, limit)
        )
    return {r[0] for r in rows}


# ─────────────────────────────────────────────
# USER ATTRIBUTES
# ─────────────────────────────────────────────
def get_user_attributes(cur, user_ids):
    if not user_ids:
        return []

    placeholders = ",".join(["%s"] * len(user_ids))

    users = safe_fetch(cur, f"""
        SELECT id, username, full_name, hobbies, address
        FROM social_media_user
        WHERE id IN ({placeholders})
    """, tuple(user_ids))

    result = []
    for uid, username, full_name, hobbies, address in users:

        followers = [r[0] for r in safe_fetch(cur,
            "SELECT from_user_id FROM social_media_user_following WHERE to_user_id=%s",
            (uid,)
        )]

        following = [r[0] for r in safe_fetch(cur,
            "SELECT to_user_id FROM social_media_user_following WHERE from_user_id=%s",
            (uid,)
        )]

        profile = safe_fetchone(cur,
            "SELECT bio, education, occupation FROM social_media_profile WHERE user_id=%s",
            (uid,)
        ) or ("", "", "")

        result.append({
            "user_id": uid,
            "username": username,
            "full_name": full_name,
            "hobbies": hobbies or "",
            "address": address or "",
            "bio": profile[0] or "",
            "education": profile[1] or "",
            "occupation": profile[2] or "",
            "followers": followers,
            "following": following,
        })

    return result


# ─────────────────────────────────────────────
# CORE ENGINE
# ─────────────────────────────────────────────
def compute_suggestions(cur, user_id: str, top_n: int = 10):

    following = get_already_following(cur, user_id)
    blocked = get_blocked_users(cur, user_id)
    exclude = following | blocked | {user_id}

    bfs = get_bfs_candidates(cur, user_id) - exclude
    cluster = get_interest_cluster_candidates(cur, user_id) - exclude

    pool = bfs | cluster

    if len(pool) < top_n:
        pool |= get_fallback(cur, exclude, 200)

    pool -= exclude

    data = get_user_attributes(cur, pool | {user_id})
    df = pd.DataFrame(data)

    if df.empty or user_id not in df["user_id"].values:
        return [], "no_data"

    target = df[df["user_id"] == user_id].iloc[0].to_dict()

    model = get_model()

    texts = (
        df["bio"].fillna("") + " " +
        df["hobbies"].fillna("") + " " +
        df["address"].fillna("")
    ).tolist()

    embeddings = model.encode(texts, show_progress_bar=False)
    df["text_embed"] = list(embeddings)

    target_text = " ".join([target.get("bio",""), target.get("hobbies",""), target.get("address","")])
    target_embed = model.encode(target_text)

    results = []

    target_followers = set(target.get("followers", []))

    for _, row in df.iterrows():
        cid = row["user_id"]
        if cid == user_id:
            continue

        text_score = cosine_similarity(
            [target_embed], [row["text_embed"]]
        )[0][0]

        row_followers = set(row["followers"])
        shared = target_followers & row_followers

        graph_score = len(shared) / (len(target_followers | row_followers) or 1)

        affinity = 0.6 * text_score + 0.4 * graph_score

        results.append({
            "user_id": cid,
            "username": row["username"],
            "full_name": row["full_name"],
            "affinity_score": float(affinity),
            "mutual_count": len(shared),
            "shared_tags": [],
            "reason": "Suggested",
            "breakdown": {
                "text_score": float(text_score),
                "graph_score": float(graph_score),
                "adamic_adar": 0,
                "second_degree": 0,
                "interest_score": 0,
                "location_score": 0,
                "interaction_score": 0,
                "collab_score": 0,
                "activity_score": 0,
            },
            "weights_used": {
                "text": 0.6,
                "graph": 0.4,
                "interest": 0,
                "location": 0,
                "interaction": 0,
                "collab": 0,
                "activity": 0,
            }
        })

    results.sort(key=lambda x: x["affinity_score"], reverse=True)
    return results[:top_n], "production"


# ─────────────────────────────────────────────
# API ROUTES
# ─────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/suggest/{user_id}")
def suggest(user_id: str, limit: int = Query(10, ge=1, le=50)):

    conn = get_conn()
    cur = conn.cursor()

    try:
        if not validate_user(cur, user_id):
            raise HTTPException(404, "User not found")

        suggestions, mode = compute_suggestions(cur, user_id, limit)

        return {
            "user_id": user_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "mode": mode,
            "total": len(suggestions),
            "suggestions": suggestions
        }

    finally:
        cur.close()
        conn.close()


@app.get("/posts/suggest/{user_id}")
def suggest_posts(user_id: str, limit: int = 20):

    conn = get_conn()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT p.id, p.content, p.user_id, p.created_at
            FROM social_media_post p
            WHERE p.user_id IN (
                SELECT to_user_id
                FROM social_media_user_following
                WHERE from_user_id = %s
            )
            ORDER BY p.created_at DESC
            LIMIT %s
        """, (user_id, limit))

        posts = cur.fetchall()

        return {
            "user_id": user_id,
            "total": len(posts),
            "posts": [
                {
                    "post_id": p[0],
                    "content": p[1],
                    "user_id": p[2],
                    "created_at": str(p[3])
                }
                for p in posts
            ]
        }

    finally:
        cur.close()
        conn.close()