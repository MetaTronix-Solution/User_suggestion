"""
unified_app.py
==============
Merged API combining:
  - User Suggestions  →  GET /suggest/{user_id}
  - Post/Reel Recommendations  →  GET /recommend/{user_id}
  - Health check  →  GET /health

RAM Optimizations Applied:
  1. Switched to paraphrase-MiniLM-L3-v2 (~120MB RAM vs ~380MB for L6)
  2. Batch encoding replaces per-item loop → lower peak RAM
  3. In-process LRU embed cache → no re-encoding same text
  4. Embeddings explicitly deleted after scoring
  5. CPU-only torch, TOKENIZERS_PARALLELISM=false
  6. Model cached to ./models/ so Render never re-downloads on restart
"""

import os
import gc
import math
import time
import random
import hashlib
import numpy as np
import pandas as pd
import networkx as nx
import psycopg2
import psycopg2.extras

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from monitoring import monitor_requests

load_dotenv()

# ─────────────────────────────────────────────
# SHARED CONFIG
# ─────────────────────────────────────────────
DB_CONFIG = {
    "host":     os.getenv("DB_HOST",     "36.253.137.34"),
    "port":     int(os.getenv("DB_PORT", 5436)),
    "dbname":   os.getenv("DB_NAME",     "social_db"),
    "user":     os.getenv("DB_USER",     "innovator_user"),
    "password": os.getenv("DB_PASSWORD", "Nep@tronix9335%"),
}

MEDIA_BASE_URL = os.getenv("MEDIA_BASE_URL", "http://localhost:8000").rstrip("/")

W_CONTENT  = float(os.getenv("W_CONTENT",  0.5))
W_TRENDING = float(os.getenv("W_TRENDING", 0.3))
W_RANDOM   = float(os.getenv("W_RANDOM",   0.2))

# ─────────────────────────────────────────────
# MODEL LOADING — RAM-safe for 512MB instances
# ─────────────────────────────────────────────
MODEL_CACHE_DIR = os.path.join(os.path.dirname(__file__), "models")

# L3 uses ~120MB RAM vs L6's ~380MB — biggest single saving
MODEL_NAME = os.getenv("EMBED_MODEL", "sentence-transformers/paraphrase-MiniLM-L3-v2")

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

_MODEL: Optional[SentenceTransformer] = None
EMBED_DIM = 384

# In-process embedding cache — avoids re-encoding identical texts across requests
_EMBED_CACHE: Dict[str, np.ndarray] = {}
_EMBED_CACHE_MAX = 2000


def _cache_embed(text: str, model: SentenceTransformer) -> np.ndarray:
    """Return cached embedding or compute + store it."""
    if not text.strip():
        return np.zeros(EMBED_DIM, dtype=np.float32)
    key = hashlib.md5(text.encode()).hexdigest()
    if key not in _EMBED_CACHE:
        if len(_EMBED_CACHE) >= _EMBED_CACHE_MAX:
            evict = list(_EMBED_CACHE.keys())[: _EMBED_CACHE_MAX // 10]
            for k in evict:
                del _EMBED_CACHE[k]
        _EMBED_CACHE[key] = model.encode(text, show_progress_bar=False)
    return _EMBED_CACHE[key]


def _get_ram_mb() -> float:
    try:
        import psutil
        return psutil.Process().memory_info().rss / 1024 / 1024
    except Exception:
        return 0.0


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _MODEL
    print(f"[startup] Loading SentenceTransformer: {MODEL_NAME}")
    os.makedirs(MODEL_CACHE_DIR, exist_ok=True)

    # No 'backend' kwarg — not supported in older sentence-transformers versions
    _MODEL = SentenceTransformer(
        MODEL_NAME,
        cache_folder=MODEL_CACHE_DIR,
    )
    _MODEL = _MODEL.to("cpu")

    _MODEL.encode("warmup", show_progress_bar=False)
    gc.collect()

    print(f"[startup] Model ready. RAM: ~{_get_ram_mb():.0f}MB")
    yield
    print("[shutdown] Cleaning up.")
    _EMBED_CACHE.clear()


def get_model() -> SentenceTransformer:
    if _MODEL is None:
        raise RuntimeError("Model not loaded — lifespan did not run.")
    return _MODEL


# ─────────────────────────────────────────────
# DB HELPERS
# ─────────────────────────────────────────────
def get_db_connection():
    return psycopg2.connect(**DB_CONFIG)

def get_dict_connection():
    conn = psycopg2.connect(**DB_CONFIG)
    return conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


# ─────────────────────────────────────────────
# URL HELPERS
# ─────────────────────────────────────────────
def full_url(path: Optional[str]) -> Optional[str]:
    if not path:
        return None
    return path if path.startswith("http") else f"{MEDIA_BASE_URL}/media/{path.lstrip('/')}"


# ═══════════════════════════════════════════════════════════
# USER SUGGESTION ENGINE
# ═══════════════════════════════════════════════════════════

def get_already_following(cur, user_id: str) -> Set[str]:
    try:
        cur.execute(
            "SELECT to_user_id FROM social_media_user_following WHERE from_user_id=%s",
            (user_id,)
        )
        return {r[0] for r in cur.fetchall()}
    except Exception:
        cur.connection.rollback()
        return set()

def get_blocked_users(cur, user_id: str) -> Set[str]:
    try:
        cur.execute("""
            SELECT to_user_id FROM social_media_user_blocked_users WHERE from_user_id=%s
            UNION
            SELECT from_user_id FROM social_media_user_blocked_users WHERE to_user_id=%s
        """, (user_id, user_id))
        return {r[0] for r in cur.fetchall()}
    except Exception:
        cur.connection.rollback()
        return set()

def get_bfs_candidates(cur, user_id: str) -> Set[str]:
    try:
        cur.execute("""
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
            SELECT DISTINCT uid FROM fof WHERE uid != %s
        """, (user_id, user_id))
        return {r[0] for r in cur.fetchall()}
    except Exception:
        cur.connection.rollback()
        return set()

def get_interest_cluster_candidates(cur, user_id: str, min_shared: int = 1, top_k: int = 100) -> Set[str]:
    try:
        cur.execute("""
            SELECT p2.user_id, COUNT(*)
            FROM social_media_profile_interests i1
            JOIN social_media_profile_interests i2 ON i1.category_id = i2.category_id
            JOIN social_media_profile p1 ON i1.profile_id = p1.id
            JOIN social_media_profile p2 ON i2.profile_id = p2.id
            WHERE p1.user_id=%s AND p2.user_id!=%s
            GROUP BY p2.user_id
            HAVING COUNT(*) >= %s
            LIMIT %s
        """, (user_id, user_id, min_shared, top_k))
        return {r[0] for r in cur.fetchall()}
    except Exception:
        cur.connection.rollback()
        return set()

def get_all_user_ids_fallback(cur, user_id: str, following: Set, blocked: Set, limit: int = 200) -> Set[str]:
    try:
        exclude = list(following | blocked | {user_id})
        if exclude:
            placeholders = ",".join(["%s"] * len(exclude))
            cur.execute(
                f"SELECT id FROM social_media_user WHERE id NOT IN ({placeholders}) ORDER BY RANDOM() LIMIT %s",
                (*exclude, limit)
            )
        else:
            cur.execute("SELECT id FROM social_media_user ORDER BY RANDOM() LIMIT %s", (limit,))
        return {r[0] for r in cur.fetchall()}
    except Exception:
        cur.connection.rollback()
        return set()


def get_user_attributes_bulk(cur, user_ids: Set[str]) -> list:
    if not user_ids:
        return []

    uid_list     = list(user_ids)
    placeholders = ",".join(["%s"] * len(uid_list))

    try:
        cur.execute(f"""
            SELECT
                u.id, u.username, u.full_name, u.hobbies, u.address,
                COALESCE(p.bio, '')        AS bio,
                COALESCE(p.education, '')  AS education,
                COALESCE(p.occupation, '') AS occupation,
                p.id                       AS profile_id
            FROM social_media_user u
            LEFT JOIN social_media_profile p ON p.user_id = u.id
            WHERE u.id IN ({placeholders})
        """, uid_list)
        base_rows = cur.fetchall()
    except Exception:
        cur.connection.rollback()
        return []

    user_map    = {}
    profile_ids = []
    for row in base_rows:
        uid = row[0]
        user_map[uid] = {
            "user_id": uid, "username": row[1], "full_name": row[2],
            "hobbies": row[3] or "", "address": row[4] or "",
            "bio": row[5], "education": row[6], "occupation": row[7],
            "followers": [], "following": [], "interests": [],
        }
        if row[8]:
            profile_ids.append(row[8])

    try:
        cur.execute(f"""
            SELECT to_user_id, from_user_id
            FROM social_media_user_following
            WHERE to_user_id IN ({placeholders})
        """, uid_list)
        for to_uid, from_uid in cur.fetchall():
            if to_uid in user_map:
                user_map[to_uid]["followers"].append(from_uid)
    except Exception:
        cur.connection.rollback()

    try:
        cur.execute(f"""
            SELECT from_user_id, to_user_id
            FROM social_media_user_following
            WHERE from_user_id IN ({placeholders})
        """, uid_list)
        for from_uid, to_uid in cur.fetchall():
            if from_uid in user_map:
                user_map[from_uid]["following"].append(to_uid)
    except Exception:
        cur.connection.rollback()

    if profile_ids:
        try:
            prof_placeholders = ",".join(["%s"] * len(profile_ids))
            cur.execute(f"""
                SELECT pi.profile_id, pi.category_id,
                       (SELECT user_id FROM social_media_profile WHERE id = pi.profile_id) AS user_id
                FROM social_media_profile_interests pi
                WHERE pi.profile_id IN ({prof_placeholders})
            """, profile_ids)
            for _, cat_id, uid in cur.fetchall():
                if uid in user_map:
                    user_map[uid]["interests"].append(cat_id)
        except Exception:
            cur.connection.rollback()

    return list(user_map.values())


def location_similarity(a1: str, a2: str) -> float:
    if not a1 or not a2:
        return 0.0
    if a1.strip().lower() == a2.strip().lower():
        return 1.0
    t1 = set(a1.lower().replace(",", " ").split())
    t2 = set(a2.lower().replace(",", " ").split())
    overlap = t1 & t2
    return 0.6 if overlap and len(overlap) >= 2 else 0.0


def compute_user_suggestions(user_id: str, top_n: int = 10) -> list:
    conn = get_db_connection()
    cur  = conn.cursor()

    try:
        following = get_already_following(cur, user_id)
        blocked   = get_blocked_users(cur, user_id)
        exclude   = following | blocked | {user_id}

        bfs     = get_bfs_candidates(cur, user_id) - exclude
        cluster = get_interest_cluster_candidates(cur, user_id) - exclude
        pool    = bfs | cluster

        if len(pool) < top_n:
            pool |= get_all_user_ids_fallback(cur, user_id, following, blocked, 200)
        pool -= exclude

        data = get_user_attributes_bulk(cur, pool | {user_id})

    finally:
        cur.close()
        conn.close()

    if not data:
        return []

    df         = pd.DataFrame(data)
    target_row = df[df["user_id"] == user_id]
    if target_row.empty:
        return []
    target = target_row.iloc[0].to_dict()

    model = get_model()

    def safe_text(r):
        return " ".join([str(r.get("bio", "")), str(r.get("hobbies", "")), str(r.get("address", ""))])

    df["text"] = df.apply(safe_text, axis=1)
    all_texts  = df["text"].tolist()

    # Batch encode only uncached texts in one forward pass
    uncached_texts = [t for t in all_texts if t.strip() and hashlib.md5(t.encode()).hexdigest() not in _EMBED_CACHE]
    if uncached_texts:
        new_embeds = model.encode(uncached_texts, batch_size=32, show_progress_bar=False)
        for t, emb in zip(uncached_texts, new_embeds):
            key = hashlib.md5(t.encode()).hexdigest()
            if len(_EMBED_CACHE) < _EMBED_CACHE_MAX:
                _EMBED_CACHE[key] = emb

    embeddings   = np.array([_cache_embed(t, model) for t in all_texts])
    df["embed"]  = list(embeddings)
    target_embed = _cache_embed(safe_text(target), model)

    G = nx.DiGraph()
    for _, r in df.iterrows():
        for f in r["followers"]:
            G.add_edge(f, r["user_id"])
        for f in r["following"]:
            G.add_edge(r["user_id"], f)

    candidate_df = df[df["user_id"] != user_id].copy()

    if len(candidate_df) > 0:
        cand_embeds = np.vstack(candidate_df["embed"].tolist())
        text_scores = cosine_similarity([target_embed], cand_embeds)[0]
    else:
        cand_embeds = np.array([])
        text_scores = np.array([])

    results = []
    for idx, (_, r) in enumerate(candidate_df.iterrows()):
        text_score  = float(text_scores[idx]) if idx < len(text_scores) else 0.0
        gf_t        = set(G.successors(user_id))      if G.has_node(user_id)      else set()
        gf_c        = set(G.successors(r["user_id"])) if G.has_node(r["user_id"]) else set()
        shared      = gf_t & gf_c
        graph_score = len(shared) / (len(gf_t | gf_c) or 1)
        ti          = set(target["interests"])
        ci          = set(r["interests"])
        interest_score = len(ti & ci) / (len(ti | ci) or 1)
        location_score = location_similarity(target["address"], r["address"])

        affinity = (
            0.5 * text_score +
            0.2 * graph_score +
            0.2 * interest_score +
            0.1 * location_score
        )

        results.append({
            "user_id":        r["user_id"],
            "username":       r["username"],
            "full_name":      r["full_name"],
            "affinity_score": float(affinity),
            "mutual_count":   len(shared),
            "shared_tags":    list(ti & ci),
            "reason":         "Suggested",
            "interests":      list(r["interests"]),
            "breakdown": {
                "text_score":      round(text_score, 4),
                "graph_score":     round(graph_score, 4),
                "interest_score":  round(interest_score, 4),
                "location_score":  round(location_score, 4),
            },
            "weights_used": {"text": 0.5, "graph": 0.2, "interest": 0.2, "location": 0.1},
        })

    # Explicitly free large arrays after scoring
    del df["embed"]
    del embeddings
    if cand_embeds.size:
        del cand_embeds
    gc.collect()

    results.sort(key=lambda x: x["affinity_score"], reverse=True)
    return results[:top_n]


# ═══════════════════════════════════════════════════════════
#  SECTION 2 — POST / REEL RECOMMENDATION ENGINE
# ═══════════════════════════════════════════════════════════

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
    id:                    str
    user_id:               str
    username:              str
    avatar:                Optional[str]
    content:               Optional[str]
    media:                 List[MediaItem]
    categories_detail:     List[Any]
    shared_post:           Optional[str]
    shared_post_details:   Optional[SharedPostDetails]
    reactions_count:       int
    like_count:            int
    reaction_types:        List[str]
    current_user_reaction: Optional[str]
    is_followed:           bool
    comments_count:        int
    comments:              List[CommentItem]
    views_count:           int
    created_at:            str
    updated_at:            str
    final_score:           float
    content_score:         float
    trending_score:        float
    random_score:          float

class RecommendationResponse(BaseModel):
    user_id:     str
    total_posts: int
    top_n:       int
    posts:       List[PostDetail]


def validate_user_in_db(user_id: str) -> dict:
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT u.id::text AS id, u.username, u.full_name, p.avatar
                FROM   social_media_user u
                LEFT   JOIN social_media_profile p ON p.user_id = u.id
                WHERE  u.id = %s::uuid
            """, (user_id,))
            row = cur.fetchone()
            if not row:
                raise ValueError(f"User '{user_id}' does not exist.")
            return dict(row)
    finally:
        conn.close()

def get_followed_posts(from_user_id: str) -> list:
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT
                    p.id::text        AS post_id,
                    p.user_id::text   AS post_user_id,
                    p.created_at,
                    p.views_count,
                    COUNT(DISTINCT r.id) AS reaction_count,
                    COUNT(DISTINCT c.id) AS comment_count
                FROM   social_media_user_following f
                JOIN   social_media_post p ON f.to_user_id = p.user_id
                LEFT   JOIN social_media_reaction r ON r.post_id = p.id
                LEFT   JOIN social_media_comment  c ON c.post_id = p.id
                WHERE  f.from_user_id = %s::uuid
                GROUP  BY p.id, p.user_id, p.created_at, p.views_count
                ORDER  BY p.created_at DESC
            """, (from_user_id,))
            return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()

def _fetch_post_media(cur, post_ids: List[str]) -> dict:
    if not post_ids:
        return {pid: [] for pid in post_ids}
    cur.execute("""
        SELECT id::text, post_id::text, file, media_type
        FROM   social_media_postmedia
        WHERE  post_id = ANY(%s::uuid[])
    """, (post_ids,))
    result = {pid: [] for pid in post_ids}
    for row in cur.fetchall():
        result[row["post_id"]].append(MediaItem(
            id=row["id"], file=full_url(row["file"]), media_type=row["media_type"]
        ))
    return result

def _fetch_post_categories(cur, post_ids: List[str]) -> dict:
    if not post_ids:
        return {pid: [] for pid in post_ids}
    cur.execute("""
        SELECT pc.post_id::text, c.id::text AS cat_id, c.name AS cat_name
        FROM   social_media_post_categories pc
        JOIN   social_media_category        c ON c.id = pc.category_id
        WHERE  pc.post_id = ANY(%s::uuid[])
    """, (post_ids,))
    result = {pid: [] for pid in post_ids}
    for row in cur.fetchall():
        result[row["post_id"]].append({"id": row["cat_id"], "name": row["cat_name"]})
    return result

def _fetch_reactions(cur, post_ids: List[str]) -> dict:
    if not post_ids:
        return {pid: {"reactions_count": 0, "like_count": 0, "reaction_types": []} for pid in post_ids}
    cur.execute("""
        SELECT post_id::text, type AS reaction_type, COUNT(*) AS cnt
        FROM   social_media_reaction
        WHERE  post_id = ANY(%s::uuid[])
        GROUP  BY post_id, type
    """, (post_ids,))
    result = {pid: {"reactions_count": 0, "like_count": 0, "reaction_types": []} for pid in post_ids}
    for row in cur.fetchall():
        pid, rtype, cnt = row["post_id"], row["reaction_type"], row["cnt"]
        result[pid]["reactions_count"] += cnt
        if rtype not in result[pid]["reaction_types"]:
            result[pid]["reaction_types"].append(rtype)
        if rtype == "like":
            result[pid]["like_count"] += cnt
    return result

def _fetch_comments(cur, post_ids: List[str]) -> dict:
    if not post_ids:
        return {pid: [] for pid in post_ids}
    cur.execute("""
        SELECT c.id::text, c.post_id::text, c.parent_id::text AS parent,
               c.content, c.created_at::text, u.username, p.avatar
        FROM   social_media_comment  c
        JOIN   social_media_user     u ON u.id = c.user_id
        LEFT   JOIN social_media_profile p ON p.user_id = c.user_id
        WHERE  c.post_id = ANY(%s::uuid[])
        ORDER  BY c.created_at DESC
    """, (post_ids,))
    result = {pid: [] for pid in post_ids}
    counts = {pid: 0  for pid in post_ids}
    for row in cur.fetchall():
        pid = row["post_id"]
        if counts[pid] >= 10:
            continue
        result[pid].append(CommentItem(
            id=row["id"], username=row["username"], avatar=row["avatar"],
            post=row["post_id"], parent=row["parent"],
            content=row["content"], created_at=row["created_at"],
        ))
        counts[pid] += 1
    return result

def _fetch_comments_count(cur, post_ids: List[str]) -> dict:
    if not post_ids:
        return {pid: 0 for pid in post_ids}
    cur.execute("""
        SELECT post_id::text, COUNT(*) AS cnt
        FROM   social_media_comment
        WHERE  post_id = ANY(%s::uuid[])
        GROUP  BY post_id
    """, (post_ids,))
    result = {pid: 0 for pid in post_ids}
    for row in cur.fetchall():
        result[row["post_id"]] = row["cnt"]
    return result

def _fetch_shared_post_details(cur, shared_ids: List[str]) -> dict:
    ids = [pid for pid in shared_ids if pid]
    if not ids:
        return {}
    cur.execute("""
        SELECT p.id::text, p.content, p.created_at::text,
               u.username, u.full_name, pr.avatar
        FROM   social_media_post p
        JOIN   social_media_user u  ON u.id = p.user_id
        LEFT   JOIN social_media_profile pr ON pr.user_id = p.user_id
        WHERE  p.id = ANY(%s::uuid[])
    """, (ids,))
    rows  = {row["id"]: dict(row) for row in cur.fetchall()}
    media = _fetch_post_media(cur, ids)
    return {
        pid: SharedPostDetails(
            id=pid, username=row["username"], full_name=row["full_name"] or None,
            avatar=full_url(row["avatar"]), content=row["content"],
            created_at=row["created_at"], media=media.get(pid, []),
        )
        for pid, row in rows.items()
    }

def _is_followed(cur, requesting_user_id: str, owner_ids: List[str]) -> dict:
    if not owner_ids or not requesting_user_id:
        return {uid: False for uid in owner_ids}
    cur.execute("""
        SELECT to_user_id::text
        FROM   social_media_user_following
        WHERE  from_user_id = %s::uuid AND to_user_id = ANY(%s::uuid[])
    """, (requesting_user_id, owner_ids))
    followed = {row["to_user_id"] for row in cur.fetchall()}
    return {uid: (uid in followed) for uid in owner_ids}

def _current_user_reaction(cur, requesting_user_id: str, post_ids: List[str]) -> dict:
    if not post_ids or not requesting_user_id:
        return {pid: None for pid in post_ids}
    cur.execute("""
        SELECT post_id::text, type AS reaction_type
        FROM   social_media_reaction
        WHERE  user_id = %s::uuid AND post_id = ANY(%s::uuid[])
    """, (requesting_user_id, post_ids))
    result = {pid: None for pid in post_ids}
    for row in cur.fetchall():
        result[row["post_id"]] = row["reaction_type"]
    return result

def fetch_post_details(post_ids: List[str], requesting_user_id: str) -> dict:
    if not post_ids:
        return {}
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT p.id::text, p.content, p.created_at::text, p.updated_at::text,
                       p.shared_post_id::text AS shared_post, p.views_count,
                       u.id::text AS user_id, u.username, u.full_name, pr.avatar
                FROM   social_media_post p
                JOIN   social_media_user u  ON u.id = p.user_id
                LEFT   JOIN social_media_profile pr ON pr.user_id = p.user_id
                WHERE  p.id = ANY(%s::uuid[])
            """, (post_ids,))
            posts_raw = {row["id"]: dict(row) for row in cur.fetchall()}
            if not posts_raw:
                return {}

            found_ids  = list(posts_raw.keys())
            owner_ids  = list({r["user_id"] for r in posts_raw.values()})
            shared_ids = [r["shared_post"] for r in posts_raw.values() if r.get("shared_post")]

            media_map        = _fetch_post_media(cur, found_ids)
            category_map     = _fetch_post_categories(cur, found_ids)
            reaction_map     = _fetch_reactions(cur, found_ids)
            comment_map      = _fetch_comments(cur, found_ids)
            comment_cnt_map  = _fetch_comments_count(cur, found_ids)
            shared_map       = _fetch_shared_post_details(cur, shared_ids)
            follow_map       = _is_followed(cur, requesting_user_id, owner_ids)
            cur_reaction_map = _current_user_reaction(cur, requesting_user_id, found_ids)

            result = {}
            for pid, row in posts_raw.items():
                rxn = reaction_map.get(pid, {})
                result[pid] = {
                    "id":                    pid,
                    "user_id":               row["user_id"],
                    "username":              row["username"],
                    "avatar":                full_url(row["avatar"]),
                    "content":               row["content"],
                    "media":                 media_map.get(pid, []),
                    "categories_detail":     category_map.get(pid, []),
                    "shared_post":           row.get("shared_post"),
                    "shared_post_details":   shared_map.get(row.get("shared_post")),
                    "reactions_count":       rxn.get("reactions_count", 0),
                    "like_count":            rxn.get("like_count", 0),
                    "reaction_types":        rxn.get("reaction_types", []),
                    "current_user_reaction": cur_reaction_map.get(pid),
                    "is_followed":           follow_map.get(row["user_id"], False),
                    "comments_count":        comment_cnt_map.get(pid, 0),
                    "comments":              comment_map.get(pid, []),
                    "views_count":           row["views_count"] or 0,
                    "created_at":            row["created_at"],
                    "updated_at":            row["updated_at"],
                }
            return result
    finally:
        conn.close()

def score_posts(posts: list) -> dict:
    now_ts = time.time()

    def _ts(post: dict) -> float:
        ca = post.get("created_at")
        if ca is None:
            return 0.0
        if hasattr(ca, "timestamp"):
            try:
                return ca.replace(tzinfo=timezone.utc).timestamp()
            except Exception:
                return ca.timestamp()
        return 0.0

    score_map = {}
    for post in posts:
        pid        = post["post_id"]
        engagement = (post.get("reaction_count", 0)
                      + post.get("comment_count", 0)
                      + (post.get("views_count") or 0))
        content_score  = math.log1p(engagement)
        age_hours      = max((now_ts - _ts(post)) / 3600, 0)
        trending_score = math.exp(-0.693 * age_hours / 24)
        random_score   = random.random()
        final_score    = W_CONTENT * content_score + W_TRENDING * trending_score + W_RANDOM * random_score
        score_map[pid] = {
            "final_score":    round(final_score,    6),
            "content_score":  round(content_score,  6),
            "trending_score": round(trending_score, 6),
            "random_score":   round(random_score,   6),
        }
    return score_map


# ═══════════════════════════════════════════════════════════
#  FASTAPI APP
# ═══════════════════════════════════════════════════════════
app = FastAPI(
    title="Unified Social Media API",
    version="1.0.0",
    description="User suggestions + Post/Reel recommendations in one service",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.middleware("http")(monitor_requests)


# ── Health ────────────────────────────────────────────────
@app.get("/health")
def health():
    try:
        conn = get_db_connection()
        conn.close()
        return {
            "status":    "ok",
            "database":  "connected",
            "ram_mb":    round(_get_ram_mb(), 1),
            "embed_cache_size": len(_EMBED_CACHE),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database unavailable: {e}")


# ── Cache Management ──────────────────────────────────────
@app.post("/admin/clear-embed-cache")
def clear_embed_cache():
    """Manually flush the in-process embedding cache."""
    count = len(_EMBED_CACHE)
    _EMBED_CACHE.clear()
    gc.collect()
    return {"cleared": count, "ram_mb": round(_get_ram_mb(), 1)}


# ── User Suggestions ──────────────────────────────────────
@app.get("/suggest/{user_id}")
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


# ── Post / Reel Recommendations ───────────────────────────
@app.get("/recommend/{user_id}", response_model=RecommendationResponse)
def recommend(
    user_id: str,
    top_n: int = Query(20, ge=1, le=200, description="Max posts / reels to return"),
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
        candidate_posts = get_followed_posts(user_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB fetch error: {e}")

    if not candidate_posts:
        return RecommendationResponse(user_id=user_id, total_posts=0, top_n=top_n, posts=[])

    score_map  = score_posts(candidate_posts)
    ranked_ids = sorted(score_map.keys(), key=lambda pid: score_map[pid]["final_score"], reverse=True)
    final_ids  = ranked_ids[:top_n]

    try:
        details_map = fetch_post_details(final_ids, requesting_user_id=user_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB detail error: {e}")

    posts: List[PostDetail] = []
    for pid in final_ids:
        detail = details_map.get(pid)
        if not detail:
            continue
        scores = score_map[pid]
        posts.append(PostDetail(
            **detail,
            final_score    = scores["final_score"],
            content_score  = scores["content_score"],
            trending_score = scores["trending_score"],
            random_score   = scores["random_score"],
        ))

    return RecommendationResponse(user_id=user_id, total_posts=len(posts), top_n=top_n, posts=posts)