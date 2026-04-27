import os
import gc
import math
import random
import hashlib
import numpy as np
import pandas as pd
import networkx as nx
import psycopg2
import psycopg2.extras

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional, Dict, List, Set

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

# 
# MODEL
# 

MODEL_NAME = "sentence-transformers/paraphrase-MiniLM-L3-v2"
MODEL_CACHE_DIR = "./models"

_MODEL = None
EMBED_DIM = 384

_EMBED_CACHE: Dict[str, np.ndarray] = {}
_EMBED_CACHE_MAX = 2000


def get_model():
    global _MODEL
    if _MODEL is None:
        _MODEL = SentenceTransformer(MODEL_NAME, cache_folder=MODEL_CACHE_DIR)
        _MODEL = _MODEL.to("cpu")
        _MODEL.encode("warmup", show_progress_bar=False)
    return _MODEL


def normalize(vec):
    vec = np.array(vec, dtype=np.float32)
    norm = np.linalg.norm(vec)
    return vec / (norm + 1e-9)


def cache_embed(text: str, model):
    if not text or not text.strip():
        return np.zeros(EMBED_DIM, dtype=np.float32)

    key = hashlib.md5(text.encode()).hexdigest()

    if key in _EMBED_CACHE:
        return _EMBED_CACHE[key]

    emb = model.encode(text, show_progress_bar=False)
    emb = normalize(emb)

    if len(_EMBED_CACHE) > _EMBED_CACHE_MAX:
        _EMBED_CACHE.clear()

    _EMBED_CACHE[key] = emb
    return emb


# 
# DB
# 

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "36.253.137.34"),
    "port": int(os.getenv("DB_PORT", 5436)),
    "dbname": os.getenv("DB_NAME", "social_db"),
    "user": os.getenv("DB_USER", "innovator_user"),
    "password": os.getenv("DB_PASSWORD", ""),
}


def db():
    return psycopg2.connect(**DB_CONFIG)


# 
# FIXED USER SUGGESTION ENGINE
# 

def get_already_following(cur, user_id):
    cur.execute("SELECT to_user_id FROM social_media_user_following WHERE from_user_id=%s", (user_id,))
    return {r[0] for r in cur.fetchall()}


def get_blocked(cur, user_id):
    cur.execute("""
        SELECT to_user_id FROM social_media_user_blocked_users WHERE from_user_id=%s
        UNION
        SELECT from_user_id FROM social_media_user_blocked_users WHERE to_user_id=%s
    """, (user_id, user_id))
    return {r[0] for r in cur.fetchall()}


def get_candidates(cur, user_id, exclude):
    cur.execute("""
        SELECT id FROM social_media_user
        WHERE id != %s
        ORDER BY RANDOM()
        LIMIT 200
    """, (user_id,))
    return {r[0] for r in cur.fetchall()} - exclude


def get_user_data(cur, user_ids):
    if not user_ids:
        return []

    q = ",".join(["%s"] * len(user_ids))

    cur.execute(f"""
        SELECT u.id, u.hobbies, u.address,
               COALESCE(p.bio,'') AS bio
        FROM social_media_user u
        LEFT JOIN social_media_profile p ON p.user_id=u.id
        WHERE u.id IN ({q})
    """, list(user_ids))

    return cur.fetchall()


def compute_suggestions(user_id, top_n=10):
    conn = db()
    cur = conn.cursor()

    try:
        following = get_already_following(cur, user_id)
        blocked = get_blocked(cur, user_id)

        exclude = following | blocked | {user_id}

        pool = get_candidates(cur, user_id, exclude)

        data = get_user_data(cur, pool | {user_id})

    finally:
        cur.close()
        conn.close()

    model = get_model()

    df = pd.DataFrame(data, columns=["id", "hobbies", "address", "bio"])
    df = df[df["id"] != user_id].copy()

    def text(r):
        return f"{r['bio']} {r['hobbies']} {r['address']}"

    df["text"] = df.apply(text, axis=1)

    # embeddings
    embeds = [cache_embed(t, model) for t in df["text"]]
    embeds = np.vstack(embeds)

    target = df.iloc[0]["text"]
    target_emb = cache_embed(target, model)

    scores = cosine_similarity([target_emb], embeds)[0]

    df["score"] = scores

    df = df.sort_values("score", ascending=False)

    return df[["id", "score"]].head(top_n).to_dict(orient="records")


# 
# FASTAPI
# 

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/suggest/{user_id}")
def suggest(user_id: str, limit: int = 10):
    try:
        results = compute_suggestions(user_id, limit)
        return {
            "user_id": user_id,
            "suggestions": results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
def health():
    return {"status": "ok"}
