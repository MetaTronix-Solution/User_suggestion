import gc
from typing import Set

import networkx as nx
import numpy as np
import pandas as pd
from sklearn.metrics.pairwise import cosine_similarity

from db.queries import get_db_connection
from embeddings.cache import batch_populate, get_embed
from embeddings.model import get_model


# 
# PRIVATE DB HELPERS
# 

def _get_already_following(cur, user_id: str) -> Set[str]:
    try:
        cur.execute(
            "SELECT to_user_id FROM social_media_user_following WHERE from_user_id=%s",
            (user_id,),
        )
        return {r[0] for r in cur.fetchall()}
    except Exception:
        cur.connection.rollback()
        return set()


def _get_blocked_users(cur, user_id: str) -> Set[str]:
    try:
        cur.execute(
            """
            SELECT to_user_id FROM social_media_user_blocked_users WHERE from_user_id=%s
            UNION
            SELECT from_user_id FROM social_media_user_blocked_users WHERE to_user_id=%s
            """,
            (user_id, user_id),
        )
        return {r[0] for r in cur.fetchall()}
    except Exception:
        cur.connection.rollback()
        return set()


def _get_bfs_candidates(cur, user_id: str) -> Set[str]:
    try:
        cur.execute(
            """
            WITH RECURSIVE fof AS (
                SELECT to_user_id AS uid, 1 AS depth
                FROM   social_media_user_following
                WHERE  from_user_id = %s
                UNION
                SELECT f.to_user_id, fof.depth + 1
                FROM   social_media_user_following f
                JOIN   fof ON f.from_user_id = fof.uid
                WHERE  fof.depth < 2
            )
            SELECT DISTINCT uid FROM fof WHERE uid != %s
            """,
            (user_id, user_id),
        )
        return {r[0] for r in cur.fetchall()}
    except Exception:
        cur.connection.rollback()
        return set()


def _get_interest_cluster_candidates(
    cur, user_id: str, min_shared: int = 1, top_k: int = 100
) -> Set[str]:
    try:
        cur.execute(
            """
            SELECT p2.user_id, COUNT(*)
            FROM   social_media_profile_interests i1
            JOIN   social_media_profile_interests i2 ON i1.category_id = i2.category_id
            JOIN   social_media_profile p1 ON i1.profile_id = p1.id
            JOIN   social_media_profile p2 ON i2.profile_id = p2.id
            WHERE  p1.user_id=%s AND p2.user_id!=%s
            GROUP  BY p2.user_id
            HAVING COUNT(*) >= %s
            LIMIT  %s
            """,
            (user_id, user_id, min_shared, top_k),
        )
        return {r[0] for r in cur.fetchall()}
    except Exception:
        cur.connection.rollback()
        return set()


def _get_fallback_users(
    cur, user_id: str, following: Set, blocked: Set, limit: int = 200
) -> Set[str]:
    try:
        exclude = list(following | blocked | {user_id})
        if exclude:
            ph = ",".join(["%s"] * len(exclude))
            cur.execute(
                f"SELECT id FROM social_media_user WHERE id NOT IN ({ph}) ORDER BY RANDOM() LIMIT %s",
                (*exclude, limit),
            )
        else:
            cur.execute(
                "SELECT id FROM social_media_user ORDER BY RANDOM() LIMIT %s", (limit,)
            )
        return {r[0] for r in cur.fetchall()}
    except Exception:
        cur.connection.rollback()
        return set()


def _get_user_attributes_bulk(cur, user_ids: Set[str]) -> list:
    if not user_ids:
        return []
    uid_list = list(user_ids)
    ph       = ",".join(["%s"] * len(uid_list))
    try:
        cur.execute(
            f"""
            SELECT u.id, u.username, u.full_name, u.hobbies, u.address,
                   COALESCE(p.bio, '')        AS bio,
                   COALESCE(p.education, '')  AS education,
                   COALESCE(p.occupation, '') AS occupation,
                   p.id                       AS profile_id
            FROM   social_media_user u
            LEFT   JOIN social_media_profile p ON p.user_id = u.id
            WHERE  u.id IN ({ph})
            """,
            uid_list,
        )
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
        cur.execute(
            f"SELECT to_user_id, from_user_id FROM social_media_user_following WHERE to_user_id IN ({ph})",
            uid_list,
        )
        for to_uid, from_uid in cur.fetchall():
            if to_uid in user_map:
                user_map[to_uid]["followers"].append(from_uid)
    except Exception:
        cur.connection.rollback()

    try:
        cur.execute(
            f"SELECT from_user_id, to_user_id FROM social_media_user_following WHERE from_user_id IN ({ph})",
            uid_list,
        )
        for from_uid, to_uid in cur.fetchall():
            if from_uid in user_map:
                user_map[from_uid]["following"].append(to_uid)
    except Exception:
        cur.connection.rollback()

    if profile_ids:
        try:
            pph = ",".join(["%s"] * len(profile_ids))
            cur.execute(
                f"""
                SELECT pi.profile_id, pi.category_id,
                       (SELECT user_id FROM social_media_profile WHERE id = pi.profile_id) AS user_id
                FROM   social_media_profile_interests pi
                WHERE  pi.profile_id IN ({pph})
                """,
                profile_ids,
            )
            for _, cat_id, uid in cur.fetchall():
                if uid in user_map:
                    user_map[uid]["interests"].append(cat_id)
        except Exception:
            cur.connection.rollback()

    return list(user_map.values())


# 
# LOCATION SIMILARITY
# 

def _location_similarity(a1: str, a2: str) -> float:
    if not a1 or not a2:
        return 0.0
    if a1.strip().lower() == a2.strip().lower():
        return 1.0
    t1 = set(a1.lower().replace(",", " ").split())
    t2 = set(a2.lower().replace(",", " ").split())
    overlap = t1 & t2
    return 0.6 if overlap and len(overlap) >= 2 else 0.0


# 
# PUBLIC  API
# 

def compute_user_suggestions(user_id: str, top_n: int = 10) -> list:
    """Score candidate users by text similarity, graph overlap, interests, and location."""
    conn = get_db_connection()
    cur  = conn.cursor()
    try:
        following = _get_already_following(cur, user_id)
        blocked   = _get_blocked_users(cur, user_id)
        exclude   = following | blocked | {user_id}

        pool = (
            _get_bfs_candidates(cur, user_id)
            | _get_interest_cluster_candidates(cur, user_id)
        ) - exclude
        if len(pool) < top_n:
            pool |= _get_fallback_users(cur, user_id, following, blocked, 200)
        pool -= exclude

        data = _get_user_attributes_bulk(cur, pool | {user_id})
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
    model  = get_model()

    def _safe_text(r):
        return " ".join([str(r.get("bio", "")), str(r.get("hobbies", "")), str(r.get("address", ""))])

    df["text"] = df.apply(_safe_text, axis=1)
    batch_populate(df["text"].tolist(), model)

    embeddings   = np.array([get_embed(t, model) for t in df["text"].tolist()])
    df["embed"]  = list(embeddings)
    target_embed = get_embed(_safe_text(target), model)

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
        int_score   = len(ti & ci) / (len(ti | ci) or 1)
        loc_score   = _location_similarity(target["address"], r["address"])
        affinity    = 0.5 * text_score + 0.2 * graph_score + 0.2 * int_score + 0.1 * loc_score

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
                "text_score":     round(text_score,  4),
                "graph_score":    round(graph_score, 4),
                "interest_score": round(int_score,   4),
                "location_score": round(loc_score,   4),
            },
            "weights_used": {"text": 0.5, "graph": 0.2, "interest": 0.2, "location": 0.1},
        })

    # Free large arrays after scoring
    del df["embed"], embeddings
    if cand_embeds.size:
        del cand_embeds
    gc.collect()

    results.sort(key=lambda x: x["affinity_score"], reverse=True)
    return results[:top_n]
