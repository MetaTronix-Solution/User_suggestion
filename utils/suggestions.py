import json
import math
import psycopg2
import pandas as pd
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import networkx as nx
from datetime import datetime

# ─────────────────────────────────────────────
# DATABASE CONNECTION
# ─────────────────────────────────────────────
conn = psycopg2.connect(
    host="182.93.94.220",
    port=5436,
    dbname="social_db",
    user="innovator_user",
    password="Nep@tronix9335%"
)
cur = conn.cursor()
conn.rollback()


# ─────────────────────────────────────────────
# FILTERS
# ─────────────────────────────────────────────
def get_already_following(target_user_id):
    try:
        cur.execute(
            "SELECT to_user_id FROM social_media_user_following WHERE from_user_id = %s",
            (target_user_id,)
        )
        return {row[0] for row in cur.fetchall()}
    except Exception:
        conn.rollback()
        return set()


def get_blocked_users(target_user_id):
    try:
        cur.execute("""
            SELECT to_user_id FROM social_media_user_blocked_users WHERE from_user_id = %s
            UNION
            SELECT from_user_id FROM social_media_user_blocked_users WHERE to_user_id = %s
        """, (target_user_id, target_user_id))
        return {row[0] for row in cur.fetchall()}
    except Exception:
        conn.rollback()
        return set()


# ─────────────────────────────────────────────
# STEP 1 — CANDIDATE POOL (3-tier fallback)
# Tier 1: BFS depth-2 friends-of-friends
# Tier 2: Interest cluster matches (>=2 shared tags)
# Tier 3: All users fallback (cold-start / isolated users)
# ─────────────────────────────────────────────
def get_bfs_candidates(target_user_id):
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
        WHERE uid != %s
          AND uid NOT IN (
              SELECT to_user_id FROM social_media_user_following WHERE from_user_id = %s
          )
          AND uid NOT IN (
              SELECT to_user_id FROM social_media_user_blocked_users WHERE from_user_id = %s
              UNION
              SELECT from_user_id FROM social_media_user_blocked_users WHERE to_user_id = %s
          );
    """
    try:
        cur.execute(query, (
            target_user_id, target_user_id,
            target_user_id,
            target_user_id, target_user_id
        ))
        return {row[0] for row in cur.fetchall()}
    except Exception as e:
        conn.rollback()
        print(f"[WARN] BFS failed: {e}")
        return set()


def get_interest_cluster_candidates(target_user_id, min_shared=1, top_k=100):
    """
    Returns users sharing >= min_shared interest tags.
    min_shared=1 is intentionally loose to maximise cold-start coverage.
    """
    query = """
        SELECT p2.user_id, COUNT(*) AS shared_count
        FROM social_media_profile_interests i1
        JOIN social_media_profile_interests i2 ON i1.category_id = i2.category_id
        JOIN social_media_profile p1 ON i1.profile_id = p1.id
        JOIN social_media_profile p2 ON i2.profile_id = p2.id
        WHERE p1.user_id = %s
          AND p2.user_id != %s
          AND p2.user_id NOT IN (
              SELECT to_user_id FROM social_media_user_following WHERE from_user_id = %s
          )
          AND p2.user_id NOT IN (
              SELECT to_user_id FROM social_media_user_blocked_users WHERE from_user_id = %s
              UNION
              SELECT from_user_id FROM social_media_user_blocked_users WHERE to_user_id = %s
          )
        GROUP BY p2.user_id
        HAVING COUNT(*) >= %s
        ORDER BY shared_count DESC
        LIMIT %s;
    """
    try:
        cur.execute(query, (
            target_user_id, target_user_id,
            target_user_id,
            target_user_id, target_user_id,
            min_shared, top_k
        ))
        return {row[0] for row in cur.fetchall()}
    except Exception as e:
        conn.rollback()
        print(f"[WARN] Interest cluster failed: {e}")
        return set()


def get_all_user_ids_fallback(target_user_id, already_following, blocked, limit=200):
    """
    Tier 3 fallback: return up to `limit` random users when BFS + interest
    clusters both return nothing (new user with no connections/interests).
    """
    try:
        exclude = list(already_following | blocked | {target_user_id})
        placeholders = ",".join(["%s"] * len(exclude)) if exclude else "NULL"
        query = f"""
            SELECT id FROM social_media_user
            WHERE id NOT IN ({placeholders})
            ORDER BY RANDOM()
            LIMIT %s
        """
        cur.execute(query, exclude + [limit])
        return {row[0] for row in cur.fetchall()}
    except Exception as e:
        conn.rollback()
        print(f"[WARN] Fallback user fetch failed: {e}")
        return set()


# ─────────────────────────────────────────────
# STEP 2 — ATTRIBUTE FETCHING
# ─────────────────────────────────────────────
def get_activity_score(user_id):
    try:
        cur.execute("""
            SELECT COUNT(*), MAX(created_at)
            FROM social_media_post
            WHERE user_id = %s AND created_at > NOW() - INTERVAL '30 days'
        """, (user_id,))
        post_count, last_active = cur.fetchone()
        post_score    = min((post_count or 0) / 10.0, 1.0)
        recency_score = 1.0 if last_active else 0.0
    except Exception:
        conn.rollback()
        post_score = recency_score = 0.0

    try:
        cur.execute("""
            SELECT COUNT(*) FROM social_media_reaction r
            JOIN social_media_post p ON r.post_id = p.id
            WHERE p.user_id = %s
        """, (user_id,))
        likes_received = cur.fetchone()[0] or 0
        likes_score = min(likes_received / 100.0, 1.0)
    except Exception:
        conn.rollback()
        likes_score = 0.0

    return post_score, likes_score, recency_score


def get_user_attributes(user_ids):
    if not user_ids:
        return []

    placeholders = ",".join(["%s"] * len(user_ids))
    try:
        cur.execute(f"""
            SELECT id, username, full_name, hobbies, address
            FROM social_media_user
            WHERE id IN ({placeholders})
        """, list(user_ids))
        users = cur.fetchall()
    except Exception as e:
        conn.rollback()
        print(f"[WARN] get_user_attributes failed: {e}")
        return []

    attributes = []
    for u in users:
        user_id, username, full_name, hobbies, address = u

        cur.execute(
            "SELECT from_user_id FROM social_media_user_following WHERE to_user_id = %s",
            (user_id,)
        )
        followers = [row[0] for row in cur.fetchall()]

        cur.execute(
            "SELECT to_user_id FROM social_media_user_following WHERE from_user_id = %s",
            (user_id,)
        )
        following = [row[0] for row in cur.fetchall()]

        cur.execute("""
            SELECT bio, education, occupation
            FROM social_media_profile WHERE user_id = %s
        """, (user_id,))
        profile = cur.fetchone()
        bio = education = occupation = ""
        if profile:
            bio, education, occupation = (
                profile[0] or "", profile[1] or "", profile[2] or ""
            )

        cur.execute("""
            SELECT category_id FROM social_media_profile_interests
            WHERE profile_id = (SELECT id FROM social_media_profile WHERE user_id = %s)
        """, (user_id,))
        interests = [row[0] for row in cur.fetchall()]

        post_score, likes_score, recency_score = get_activity_score(user_id)

        attributes.append({
            "user_id":       user_id,
            "username":      username,
            "full_name":     full_name,
            "hobbies":       hobbies or "",
            "address":       address or "",
            "bio":           bio,
            "education":     education,
            "occupation":    occupation,
            "followers":     followers,
            "following":     following,
            "interests":     interests,
            "post_score":    post_score,
            "likes_score":   likes_score,
            "recency_score": recency_score,
        })

    return attributes


# ─────────────────────────────────────────────
# STEP 3 — SIGNAL FUNCTIONS
# ─────────────────────────────────────────────
def get_interaction_score(target_id, candidate_id):
    try:
        cur.execute("""
            SELECT COUNT(*) FROM social_media_like l
            JOIN social_media_post p ON l.post_id = p.id
            WHERE l.user_id = %s AND p.user_id = %s
        """, (candidate_id, target_id))
        likes = cur.fetchone()[0] or 0
    except Exception:
        conn.rollback()
        likes = 0

    try:
        cur.execute("""
            SELECT COUNT(*) FROM social_media_comment c
            JOIN social_media_post p ON c.post_id = p.id
            WHERE c.user_id = %s AND p.user_id = %s
        """, (candidate_id, target_id))
        comments = cur.fetchone()[0] or 0
    except Exception:
        conn.rollback()
        comments = 0

    return min((likes * 1 + comments * 2) / 10.0, 1.0)


def get_mutual_friends(user_id, candidate_id):
    query = """
        SELECT DISTINCT f1.to_user_id
        FROM social_media_user_following f1
        JOIN social_media_user_following f2 ON f1.to_user_id = f2.to_user_id
        WHERE f1.from_user_id = %s AND f2.from_user_id = %s;
    """
    try:
        cur.execute(query, (user_id, candidate_id))
        mutual_ids = cur.fetchall()
    except Exception:
        conn.rollback()
        return {"connections": [], "count": 0}

    mutual_details = []
    for (friend_id,) in mutual_ids:
        cur.execute(
            "SELECT id, username, full_name FROM social_media_user WHERE id = %s",
            (friend_id,)
        )
        info = cur.fetchone()
        if info:
            mutual_details.append({
                "id": info[0], "username": info[1], "full_name": info[2]
            })

    return {"connections": mutual_details, "count": len(mutual_details)}


def location_similarity(addr1, addr2):
    if not addr1 or not addr2:
        return 0.0
    a1 = addr1.strip().lower()
    a2 = addr2.strip().lower()
    if a1 == a2:
        return 1.0
    tokens1 = set(a1.replace(",", " ").split())
    tokens2 = set(a2.replace(",", " ").split())
    overlap = tokens1 & tokens2
    if overlap and len(overlap) / max(len(tokens1), len(tokens2)) >= 0.5:
        return 0.6
    return 0.0


def compute_graph_features(G, target_id, candidate_id):
    target_neighbors = set(G.successors(target_id))    if G.has_node(target_id)    else set()
    cand_neighbors   = set(G.successors(candidate_id)) if G.has_node(candidate_id) else set()
    shared           = target_neighbors & cand_neighbors

    union_size          = len(target_neighbors | cand_neighbors)
    second_degree_score = len(shared) / union_size if union_size else 0.0

    adamic_adar_raw = sum(
        1.0 / math.log(G.degree(n) + 1e-9)
        for n in shared if G.degree(n) > 1
    )
    adamic_adar_score = min(adamic_adar_raw / 10.0, 1.0)

    return {
        "second_degree_score": second_degree_score,
        "adamic_adar_score":   adamic_adar_score,
        "mutual_count":        len(shared),
        "mutual_ids":          list(shared),
    }


# ─────────────────────────────────────────────
# STEP 4 — REASON LABEL
# ─────────────────────────────────────────────
def build_reason_label(mutual_info, shared_tags, location_score, interaction_score):
    reasons = []

    count = mutual_info.get("count", 0)
    if count:
        label = f"{count} mutual friend{'s' if count > 1 else ''}"
        if mutual_info["connections"]:
            label += f" incl. {mutual_info['connections'][0]['full_name']}"
        reasons.append(label)

    if shared_tags:
        tags = " + ".join(str(t) for t in list(shared_tags)[:2])
        reasons.append(f"Both into {tags}")

    if location_score >= 0.6:
        reasons.append("Near you")

    if interaction_score > 0.3:
        reasons.append("Already engaged with your posts")

    return " · ".join(reasons) if reasons else "Suggested for you"


# ─────────────────────────────────────────────
# STEP 5 — WEIGHT BLENDING
# ─────────────────────────────────────────────
def compute_weights(target):
    network_size = len(target.get("followers", [])) + len(target.get("following", []))
    graph_weight = min(network_size / 50.0, 0.40)
    text_weight  = max(0.45 - graph_weight, 0.10)

    return {
        "text":        round(text_weight, 3),
        "graph":       round(graph_weight, 3),
        "interest":    0.20,
        "location":    0.08,
        "interaction": 0.10,
        "collab":      0.07,
        "activity":    0.05,
    }


# ─────────────────────────────────────────────
# STEP 6 — DIVERSITY PASS
# ─────────────────────────────────────────────
def diversify_suggestions(suggestions, top_n=10, pool_k=40, threshold=0.80):
    pool = suggestions[:pool_k]
    if not pool:
        return pool

    selected = [pool[0]]
    for candidate in pool[1:]:
        if len(selected) >= top_n:
            break
        cand_interests = set(candidate.get("interests", []))
        max_sim = max(
            len(cand_interests & set(s.get("interests", []))) /
            max(len(cand_interests | set(s.get("interests", []))), 1)
            for s in selected
        )
        if max_sim < threshold:
            selected.append(candidate)

    if len(selected) < top_n:
        remaining = [c for c in pool if c not in selected]
        selected.extend(remaining[:top_n - len(selected)])

    return selected[:top_n]


# ─────────────────────────────────────────────
# TEXT REPRESENTATION
# ─────────────────────────────────────────────
def build_user_text(row):
    parts = {
        "Bio":        row.get("bio", ""),
        "Education":  row.get("education", ""),
        "Occupation": row.get("occupation", ""),
        "Hobbies":    row.get("hobbies", ""),
        "Location":   row.get("address", ""),
    }
    return " | ".join(f"{k}: {v}" for k, v in parts.items() if v and str(v).strip())


# ─────────────────────────────────────────────
# JSON HELPER
# ─────────────────────────────────────────────
def save_to_json(data, filepath):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Saved -> {filepath}")


# ─────────────────────────────────────────────
# MAIN SUGGESTION ENGINE
# ─────────────────────────────────────────────
def compute_user_suggestions(target_user_id, top_n=10):

    already_following = get_already_following(target_user_id)
    blocked           = get_blocked_users(target_user_id)
    exclude           = already_following | blocked | {target_user_id}

    # ── Tier 1: BFS depth-2 ──────────────────────────────────────────────
    print("Tier 1: BFS depth-2 candidate generation ...")
    bfs_candidates = get_bfs_candidates(target_user_id) - exclude
    print(f"  BFS candidates: {len(bfs_candidates)}")

    # ── Tier 2: Interest clusters (min 1 shared tag) ─────────────────────
    print("Tier 2: Interest cluster candidates ...")
    cluster_candidates = get_interest_cluster_candidates(
        target_user_id, min_shared=1, top_k=100
    ) - exclude
    print(f"  Cluster candidates: {len(cluster_candidates)}")

    candidate_pool = bfs_candidates | cluster_candidates

    # ── Tier 3: Fallback — all users (cold-start) ────────────────────────
    if len(candidate_pool) < top_n:
        print(f"  Pool too small ({len(candidate_pool)}), activating Tier 3 fallback ...")
        fallback = get_all_user_ids_fallback(target_user_id, already_following, blocked, limit=200)
        candidate_pool |= fallback
        print(f"  Pool after fallback: {len(candidate_pool)}")

    candidate_pool -= exclude   # re-apply just in case
    print(f"  Final candidate pool: {len(candidate_pool)}")

    if not candidate_pool:
        print("No candidates found at all.")
        return []

    # ── Fetch attributes ─────────────────────────────────────────────────
    print("Fetching user attributes ...")
    all_ids   = candidate_pool | {target_user_id}
    user_data = get_user_attributes(all_ids)
    df        = pd.DataFrame(user_data)

    target_row = df[df["user_id"] == target_user_id]
    if target_row.empty:
        print(f"Target user {target_user_id} not found in DB.")
        return []
    target  = target_row.iloc[0].to_dict()
    weights = compute_weights(target)

    print(f"  User network size: {len(target['followers'])} followers, "
          f"{len(target['following'])} following  →  "
          f"{'cold-start' if len(target['followers'])+len(target['following']) < 5 else 'established'} mode")

    # ── Embeddings ───────────────────────────────────────────────────────
    print("Computing embeddings ...")
    model = SentenceTransformer("all-MiniLM-L6-v2")
    df["combined_text"]  = df.apply(build_user_text, axis=1)
    df["combined_embed"] = df["combined_text"].apply(
        lambda t: model.encode(t) if str(t).strip() else np.zeros(384)
    )
    target_embed = df[df["user_id"] == target_user_id].iloc[0]["combined_embed"]

    # ── Social graph ─────────────────────────────────────────────────────
    print("Building social graph ...")
    G = nx.DiGraph()
    for _, row in df.iterrows():
        for follower in row["followers"]:
            G.add_edge(follower, row["user_id"])
        for followee in row["following"]:
            G.add_edge(row["user_id"], followee)

    target_interests = set(target["interests"])
    target_followers = set(target["followers"])

    # ── Score candidates ─────────────────────────────────────────────────
    print("Scoring candidates ...")
    suggestions = []

    for _, candidate_row in df.iterrows():
        cid = candidate_row["user_id"]
        if cid == target_user_id:
            continue

        candidate = candidate_row.to_dict()

        # Signal 1: Semantic text similarity
        c_embed    = candidate["combined_embed"]
        text_score = float(cosine_similarity([target_embed], [c_embed])[0][0]) \
            if np.any(target_embed) and np.any(c_embed) else 0.0

        # Signal 2: Graph — Adamic-Adar (60%) + 2nd-degree (40%)
        gf          = compute_graph_features(G, target_user_id, cid)
        graph_score = 0.60 * gf["adamic_adar_score"] + 0.40 * gf["second_degree_score"]

        # Signal 3: Interest tag overlap (Jaccard)
        cand_interests   = set(candidate["interests"])
        shared_interests = target_interests & cand_interests
        union_i          = target_interests | cand_interests
        interest_score   = len(shared_interests) / len(union_i) if union_i else 0.0

        # Signal 4: Location proximity
        location_score = location_similarity(
            target.get("address", ""), candidate.get("address", "")
        )

        # Signal 5: Directional interaction
        interaction_score = get_interaction_score(target_user_id, cid)

        # Signal 6: Shared followers (collaborative filtering)
        cand_followers = set(candidate["followers"])
        union_f        = target_followers | cand_followers
        collab_score   = len(target_followers & cand_followers) / len(union_f) if union_f else 0.0

        # Signal 7: Candidate activity / recency
        activity_score = (
            candidate["post_score"]    * 0.4 +
            candidate["likes_score"]   * 0.3 +
            candidate["recency_score"] * 0.3
        )

        affinity_score = (
            weights["text"]        * text_score        +
            weights["graph"]       * graph_score        +
            weights["interest"]    * interest_score     +
            weights["location"]    * location_score     +
            weights["interaction"] * interaction_score  +
            weights["collab"]      * collab_score       +
            weights["activity"]    * activity_score
        )

        mutual_info = get_mutual_friends(target_user_id, cid)
        reason      = build_reason_label(
            mutual_info, shared_interests, location_score, interaction_score
        )

        suggestions.append({
            "user_id":        cid,
            "username":       candidate["username"],
            "full_name":      candidate["full_name"],
            "affinity_score": round(affinity_score, 4),
            "mutual_count":   gf["mutual_count"],
            "shared_tags":    list(shared_interests),
            "reason":         reason,
            "interests":      list(cand_interests),
            "breakdown": {
                "text_score":        round(text_score, 4),
                "graph_score":       round(graph_score, 4),
                "adamic_adar":       round(gf["adamic_adar_score"], 4),
                "second_degree":     round(gf["second_degree_score"], 4),
                "interest_score":    round(interest_score, 4),
                "location_score":    round(location_score, 4),
                "interaction_score": round(interaction_score, 4),
                "collab_score":      round(collab_score, 4),
                "activity_score":    round(activity_score, 4),
            },
            "weights_used": weights,
        })

    suggestions.sort(key=lambda x: x["affinity_score"], reverse=True)
    final = diversify_suggestions(suggestions, top_n=top_n, pool_k=top_n * 4)

    return final


# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────
if __name__ == "__main__":
    TARGET_USER_ID = "bd4cade0-3abd-45e5-a1c0-30f8c64681cd"
    TOP_N = 10

    print(f"Computing suggestions for: {TARGET_USER_ID}\n")
    suggestions = compute_user_suggestions(TARGET_USER_ID, top_n=TOP_N)

    output = {
        "target_user_id": TARGET_USER_ID,
        "generated_at":   datetime.utcnow().isoformat(),
        "total":          len(suggestions),
        "suggestions":    suggestions,
    }
    save_to_json(output, "suggestions.json")

    print(f"\nTop {len(suggestions)} Suggestions:")
    print("=" * 70)
    for i, s in enumerate(suggestions, 1):
        print(f"{i}. {s['full_name']} (@{s['username']})")
        print(f"   Score : {s['affinity_score']:.4f}  |  Mutuals: {s['mutual_count']}")
        print(f"   Reason: {s['reason']}")
        b = s["breakdown"]
        print(
            f"   text={b['text_score']:.3f}  graph={b['graph_score']:.3f}"
            f"  interest={b['interest_score']:.3f}  location={b['location_score']:.3f}"
            f"  interaction={b['interaction_score']:.3f}  collab={b['collab_score']:.3f}"
            f"  activity={b['activity_score']:.3f}"
        )
        print()