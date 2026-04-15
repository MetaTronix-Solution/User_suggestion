import json
import math
import psycopg2
import pandas as pd
import numpy as np
import networkx as nx

from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from datetime import datetime


# ─────────────────────────────────────────────
# MODEL (SAFE LAZY LOAD - FIXED)
# ─────────────────────────────────────────────
MODEL = None

def get_model():
    global MODEL
    if MODEL is None:
        MODEL = SentenceTransformer("all-MiniLM-L6-v2")
    return MODEL


# ─────────────────────────────────────────────
# DB CONFIG
# ─────────────────────────────────────────────
DB_CONFIG = dict(
    host="182.93.94.220",
    port=5436,
    dbname="social_db",
    user="innovator_user",
    password="Nep@tronix9335%"
)

conn = None
cur = None

def get_db():
    global conn, cur
    if conn is None:
        conn = psycopg2.connect(**DB_CONFIG)
        conn.autocommit = True
        cur = conn.cursor()
    return conn, cur


# ─────────────────────────────────────────────
# SAFE DB
# ─────────────────────────────────────────────
def safe_fetch(query, params=()):
    try:
        _, cur = get_db()
        cur.execute(query, params)
        return cur.fetchall()
    except Exception:
        conn.rollback()
        return []

def safe_fetchone(query, params=()):
    try:
        _, cur = get_db()
        cur.execute(query, params)
        return cur.fetchone()
    except Exception:
        conn.rollback()
        return None


# ─────────────────────────────────────────────
# FILTERS
# ─────────────────────────────────────────────
def get_already_following(user_id):
    return {r[0] for r in safe_fetch(
        "SELECT to_user_id FROM social_media_user_following WHERE from_user_id=%s",
        (user_id,)
    )}

def get_blocked_users(user_id):
    return {r[0] for r in safe_fetch("""
        SELECT to_user_id FROM social_media_user_blocked_users WHERE from_user_id=%s
        UNION
        SELECT from_user_id FROM social_media_user_blocked_users WHERE to_user_id=%s
    """, (user_id, user_id))}


# ─────────────────────────────────────────────
# CANDIDATES
# ─────────────────────────────────────────────
def get_bfs_candidates(user_id):
    rows = safe_fetch("""
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
        WHERE uid != %s
    """, (user_id, user_id))
    return {r[0] for r in rows}


def get_interest_cluster_candidates(user_id, min_shared=1, top_k=100):
    rows = safe_fetch("""
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

    return {r[0] for r in rows}


def get_all_user_ids_fallback(user_id, following, blocked, limit=200):
    exclude = list(following | blocked | {user_id})

    if exclude:
        placeholders = ",".join(["%s"] * len(exclude))
        rows = safe_fetch(
            f"SELECT id FROM social_media_user WHERE id NOT IN ({placeholders}) LIMIT %s",
            (*exclude, limit)
        )
    else:
        rows = safe_fetch(
            "SELECT id FROM social_media_user ORDER BY RANDOM() LIMIT %s",
            (limit,)
        )

    return {r[0] for r in rows}


# ─────────────────────────────────────────────
# USER ATTRIBUTES
# ─────────────────────────────────────────────
def get_user_attributes(user_ids):
    if not user_ids:
        return []

    placeholders = ",".join(["%s"] * len(user_ids))

    users = safe_fetch(f"""
        SELECT id, username, full_name, hobbies, address
        FROM social_media_user
        WHERE id IN ({placeholders})
    """, tuple(user_ids))

    result = []

    for uid, username, full_name, hobbies, address in users:

        followers = [r[0] for r in safe_fetch(
            "SELECT from_user_id FROM social_media_user_following WHERE to_user_id=%s",
            (uid,)
        )]

        following = [r[0] for r in safe_fetch(
            "SELECT to_user_id FROM social_media_user_following WHERE from_user_id=%s",
            (uid,)
        )]

        profile = safe_fetchone("""
            SELECT bio, education, occupation
            FROM social_media_profile WHERE user_id=%s
        """, (uid,)) or ("", "", "")

        interests = [r[0] for r in safe_fetch("""
            SELECT category_id
            FROM social_media_profile_interests
            WHERE profile_id=(SELECT id FROM social_media_profile WHERE user_id=%s)
        """, (uid,))]

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
            "interests": interests,
        })

    return result


# ─────────────────────────────────────────────
# LOCATION
# ─────────────────────────────────────────────
def location_similarity(a1, a2):
    if not a1 or not a2:
        return 0.0
    if a1.strip().lower() == a2.strip().lower():
        return 1.0

    t1 = set(a1.lower().replace(",", " ").split())
    t2 = set(a2.lower().replace(",", " ").split())

    overlap = t1 & t2
    return 0.6 if overlap and len(overlap) >= 2 else 0.0


# ─────────────────────────────────────────────
# MAIN ENGINE (FIXED ONLY EMBEDDING SAFETY)
# ─────────────────────────────────────────────
def compute_user_suggestions(user_id, top_n=10):

    following = get_already_following(user_id)
    blocked = get_blocked_users(user_id)
    exclude = following | blocked | {user_id}

    bfs = get_bfs_candidates(user_id) - exclude
    cluster = get_interest_cluster_candidates(user_id) - exclude

    pool = bfs | cluster

    if len(pool) < top_n:
        pool |= get_all_user_ids_fallback(user_id, following, blocked, 200)

    pool -= exclude

    data = get_user_attributes(pool | {user_id})
    if not data:
        return []

    df = pd.DataFrame(data)

    target = df[df["user_id"] == user_id]
    if target.empty:
        return []

    target = target.iloc[0].to_dict()

    # ── SAFE MODEL USAGE ──
    model = get_model()

    def safe_text(r):
        return " ".join([
            str(r.get("bio", "")),
            str(r.get("hobbies", "")),
            str(r.get("address", ""))
        ])

    df["text"] = df.apply(safe_text, axis=1)

    df["embed"] = [
        model.encode(text) if text.strip() else np.zeros(384)
        for text in df["text"]
    ]

    target_embed = model.encode(safe_text(target))

    G = nx.DiGraph()

    for _, r in df.iterrows():
        for f in r["followers"]:
            G.add_edge(f, r["user_id"])
        for f in r["following"]:
            G.add_edge(r["user_id"], f)

    results = []

    for _, r in df.iterrows():
        if r["user_id"] == user_id:
            continue

        text_score = float(cosine_similarity(
            [target_embed], [r["embed"]]
        )[0][0])

        gf_t = set(G.successors(user_id)) if G.has_node(user_id) else set()
        gf_c = set(G.successors(r["user_id"])) if G.has_node(r["user_id"]) else set()
        shared = gf_t & gf_c

        graph_score = len(shared) / (len(gf_t | gf_c) or 1)

        interest_score = len(set(target["interests"]) & set(r["interests"])) / (
            len(set(target["interests"]) | set(r["interests"])) or 1
        )

        location_score = location_similarity(target["address"], r["address"])

        affinity = (
            0.5 * text_score +
            0.2 * graph_score +
            0.2 * interest_score +
            0.1 * location_score
        )

        results.append({
            "user_id": r["user_id"],
            "username": r["username"],
            "full_name": r["full_name"],
            "affinity_score": float(affinity),
            "mutual_count": len(shared),
            "shared_tags": list(set(target["interests"]) & set(r["interests"])),
            "reason": "Suggested",
            "interests": list(r["interests"]),
            "breakdown": {
                "text_score": text_score,
                "graph_score": graph_score,
                "interest_score": interest_score,
                "location_score": location_score
            },
            "weights_used": {
                "text": 0.5,
                "graph": 0.2,
                "interest": 0.2,
                "location": 0.1
            }
        })

    results.sort(key=lambda x: x["affinity_score"], reverse=True)
    return results[:top_n]


# ─────────────────────────────────────────────
# ENTRY
# ─────────────────────────────────────────────
if __name__ == "__main__":
    uid = "bd4cade0-3abd-45e5-a1c0-30f8c64681cd"
    print(json.dumps(compute_user_suggestions(uid, 10), indent=2))