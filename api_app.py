import os
import psycopg2
import pandas as pd
import networkx as nx

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from datetime import datetime, timezone
from typing import Optional, Set

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

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
# DATABASE
# ─────────────────────────────────────────────
def _clean_host(host: str) -> str:
    """Strip http:// or https:// prefix from host — psycopg2 needs a bare IP."""
    for prefix in ("https://", "http://"):
        if host.startswith(prefix):
            host = host[len(prefix):]
    return host.rstrip("/")

DB_CONFIG = dict(
    host=_clean_host(os.getenv("DB_HOST", "36.253.137.34")),
    port=int(os.getenv("DB_PORT", 5436)),
    dbname=os.getenv("DB_NAME", "social_db"),
    user=os.getenv("DB_USER", "innovator_user"),
    password=os.getenv("DB_PASSWORD", "Nep@tronix9335%")
)

def get_conn():
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = True
    return conn

# ─────────────────────────────────────────────
# MODELS
# ─────────────────────────────────────────────
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

def get_interest_cluster_candidates(cur, user_id):
    query = """
        SELECT p2.user_id
        FROM social_media_profile_interests i1
        JOIN social_media_profile_interests i2 ON i1.category_id = i2.category_id
        JOIN social_media_profile p1 ON i1.profile_id = p1.id
        JOIN social_media_profile p2 ON i2.profile_id = p2.id
        WHERE p1.user_id = %s AND p2.user_id != %s
        GROUP BY p2.user_id
        LIMIT 100
    """
    rows = safe_fetch(cur, query, (user_id, user_id))
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

        profile = safe_fetchone(cur,
            "SELECT bio FROM social_media_profile WHERE user_id=%s",
            (uid,)
        ) or ("",)

        result.append({
            "user_id": uid,
            "username": username,
            "full_name": full_name,
            "hobbies": hobbies or "",
            "address": address or "",
            "bio": profile[0] or "",
            "followers": followers,
        })

    return result

# ─────────────────────────────────────────────
# CORE ENGINE (TF-IDF)
# ─────────────────────────────────────────────
def compute_suggestions(cur, user_id: str, top_n: int = 10):

    following = get_already_following(cur, user_id)
    blocked = get_blocked_users(cur, user_id)
    exclude = following | blocked | {user_id}

    pool = (
        get_bfs_candidates(cur, user_id) |
        get_interest_cluster_candidates(cur, user_id)
    ) - exclude

    if len(pool) < top_n:
        pool |= get_fallback(cur, exclude)

    data = get_user_attributes(cur, pool | {user_id})
    df = pd.DataFrame(data)

    if df.empty or user_id not in df["user_id"].values:
        return [], "no_data"

    texts = (df["bio"] + " " + df["hobbies"] + " " + df["address"]).tolist()

    vectorizer = TfidfVectorizer(max_features=500)
    tfidf = vectorizer.fit_transform(texts)

    target_idx = df.index[df["user_id"] == user_id][0]
    target_vec = tfidf[target_idx]

    target_followers = set(df.iloc[target_idx]["followers"])

    results = []

    for i, row in df.iterrows():
        if row["user_id"] == user_id:
            continue

        text_score = cosine_similarity(target_vec, tfidf[i])[0][0]

        row_followers = set(row["followers"])
        shared = target_followers & row_followers

        graph_score = len(shared) / (len(target_followers | row_followers) or 1)

        affinity = 0.6 * text_score + 0.4 * graph_score

        results.append({
            "user_id": row["user_id"],
            "username": row["username"],
            "full_name": row["full_name"],
            "affinity_score": float(affinity),
            "mutual_count": len(shared),
            "shared_tags": [],
            "reason": "Suggested",
            "breakdown": {
                "text_score": float(text_score),
                "graph_score": float(graph_score),
            },
            "weights_used": {
                "text": 0.6,
                "graph": 0.4,
            }
        })

    results.sort(key=lambda x: x["affinity_score"], reverse=True)
    return results[:top_n], "production"

# ─────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────
@app.get("/")
def root():
    return {"message": "API running"}

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/check-config")
def check_config():
    return {
        "db_config": {
            **DB_CONFIG,
            "password": "***" # Hide password
        },
        "env_db_host": os.getenv("DB_HOST"),
        "env_db_port": os.getenv("DB_PORT")
    }

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

# ─────────────────────────────────────────────
# PORT FIX (CRITICAL FOR RENDER)
# ─────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 5000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)