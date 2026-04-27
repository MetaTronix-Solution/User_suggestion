from typing import List, Optional

import psycopg2
import psycopg2.extras

from models.schemas import CommentItem, MediaItem, SharedPostDetails
from utils.helpers import DB_CONFIG, full_url


# ──────────────────────────────────────────────────────────────────────────────
# CONNECTION
# ──────────────────────────────────────────────────────────────────────────────

def get_db_connection():
    return psycopg2.connect(**DB_CONFIG)


# ──────────────────────────────────────────────────────────────────────────────
# VALIDATION & FILTERING
# ──────────────────────────────────────────────────────────────────────────────

def validate_user_in_db(user_id: str) -> dict:
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT u.id::text AS id, u.username, u.full_name, p.avatar
                FROM   social_media_user u
                LEFT   JOIN social_media_profile p ON p.user_id = u.id
                WHERE  u.id = %s::uuid
                """,
                (user_id,),
            )
            row = cur.fetchone()
            if not row:
                raise ValueError(f"User '{user_id}' does not exist in the database.")
            return dict(row)
    finally:
        conn.close()


def filter_posts_existing_in_db(post_ids: List[str]) -> List[str]:
    if not post_ids:
        return []
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT id::text FROM social_media_post WHERE id = ANY(%s::uuid[])",
                (post_ids,),
            )
            existing = {row["id"] for row in cur.fetchall()}
    finally:
        conn.close()
    return [pid for pid in post_ids if pid in existing]


def filter_reels_existing_in_db(reel_ids: List[str]) -> List[str]:
    if not reel_ids:
        return []
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id::text FROM social_media_reel WHERE id = ANY(%s::uuid[])",
                (reel_ids,),
            )
            existing = {row[0] for row in cur.fetchall()}
    finally:
        conn.close()
    return [rid for rid in reel_ids if rid in existing]


# ──────────────────────────────────────────────────────────────────────────────
# SEEN CONTENT TRACKING
# ──────────────────────────────────────────────────────────────────────────────

def fetch_seen_content_ids(user_id: str, content_type: str) -> set:
    """Return IDs of posts or reels this user has already been shown."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT content_id::text
                FROM   social_media_seen_content
                WHERE  user_id = %s::uuid AND content_type = %s
                """,
                (user_id, content_type),
            )
            return {row[0] for row in cur.fetchall()}
    finally:
        conn.close()


def mark_content_as_seen(user_id: str, content_ids: List[str], content_type: str):
    """Insert seen records, ignoring duplicates."""
    if not content_ids:
        return
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            psycopg2.extras.execute_values(
                cur,
                """
                INSERT INTO social_media_seen_content (user_id, content_id, content_type)
                VALUES %s
                ON CONFLICT (user_id, content_id, content_type) DO NOTHING
                """,
                [(user_id, cid, content_type) for cid in content_ids],
            )
        conn.commit()
    finally:
        conn.close()


# ──────────────────────────────────────────────────────────────────────────────
# POST ENRICHMENT HELPERS
# ──────────────────────────────────────────────────────────────────────────────

def _fetch_post_media(cur, post_ids: List[str]) -> dict:
    if not post_ids:
        return {pid: [] for pid in post_ids}
    cur.execute(
        """
        SELECT id::text, post_id::text, file, media_type
        FROM   social_media_postmedia
        WHERE  post_id = ANY(%s::uuid[])
        """,
        (post_ids,),
    )
    result: dict = {pid: [] for pid in post_ids}
    for row in cur.fetchall():
        result[row["post_id"]].append(
            MediaItem(id=row["id"], file=full_url(row["file"]), media_type=row["media_type"])
        )
    return result


def _fetch_post_categories(cur, post_ids: List[str]) -> dict:
    if not post_ids:
        return {pid: [] for pid in post_ids}
    cur.execute(
        """
        SELECT pc.post_id::text, c.id::text AS cat_id, c.name AS cat_name
        FROM   social_media_post_categories pc
        JOIN   social_media_category        c ON c.id = pc.category_id
        WHERE  pc.post_id = ANY(%s::uuid[])
        """,
        (post_ids,),
    )
    result: dict = {pid: [] for pid in post_ids}
    for row in cur.fetchall():
        result[row["post_id"]].append({"id": row["cat_id"], "name": row["cat_name"]})
    return result


def _fetch_reactions(cur, content_ids: List[str]) -> dict:
    """Works for both posts and reels — reactions table uses post_id column for both."""
    if not content_ids:
        return {cid: {"reactions_count": 0, "like_count": 0, "reaction_types": []} for cid in content_ids}
    cur.execute(
        """
        SELECT post_id::text, type AS reaction_type, COUNT(*) AS cnt
        FROM   social_media_reaction
        WHERE  post_id = ANY(%s::uuid[])
        GROUP  BY post_id, type
        """,
        (content_ids,),
    )
    result: dict = {
        cid: {"reactions_count": 0, "like_count": 0, "reaction_types": []}
        for cid in content_ids
    }
    for row in cur.fetchall():
        cid, rtype, cnt = row["post_id"], row["reaction_type"], row["cnt"]
        if cid not in result:
            continue
        result[cid]["reactions_count"] += cnt
        if rtype not in result[cid]["reaction_types"]:
            result[cid]["reaction_types"].append(rtype)
        if rtype == "like":
            result[cid]["like_count"] += cnt
    return result


def _fetch_comments(cur, content_ids: List[str]) -> dict:
    """Works for both posts and reels — comments table uses post_id column for both."""
    if not content_ids:
        return {cid: [] for cid in content_ids}
    cur.execute(
        """
        SELECT c.id::text, c.post_id::text, c.parent_id::text AS parent,
               c.content, c.created_at::text, u.username, p.avatar
        FROM   social_media_comment  c
        JOIN   social_media_user     u ON u.id = c.user_id
        LEFT   JOIN social_media_profile p ON p.user_id = c.user_id
        WHERE  c.post_id = ANY(%s::uuid[])
        ORDER  BY c.created_at DESC
        """,
        (content_ids,),
    )
    result: dict = {cid: [] for cid in content_ids}
    counts: dict = {cid: 0 for cid in content_ids}
    for row in cur.fetchall():
        cid = row["post_id"]
        if cid not in result or counts[cid] >= 10:
            continue
        result[cid].append(
            CommentItem(
                id=row["id"], username=row["username"], avatar=row["avatar"],
                post=row["post_id"], parent=row["parent"],
                content=row["content"], created_at=row["created_at"],
            )
        )
        counts[cid] += 1
    return result


def _fetch_comments_count(cur, content_ids: List[str]) -> dict:
    """Works for both posts and reels."""
    if not content_ids:
        return {cid: 0 for cid in content_ids}
    cur.execute(
        """
        SELECT post_id::text, COUNT(*) AS cnt
        FROM   social_media_comment
        WHERE  post_id = ANY(%s::uuid[])
        GROUP  BY post_id
        """,
        (content_ids,),
    )
    result = {cid: 0 for cid in content_ids}
    for row in cur.fetchall():
        result[row["post_id"]] = row["cnt"]
    return result


def _fetch_shared_post_details(cur, shared_ids: List[str]) -> dict:
    ids = [pid for pid in shared_ids if pid]
    if not ids:
        return {}
    cur.execute(
        """
        SELECT p.id::text, p.content, p.created_at::text,
               u.username, u.full_name, pr.avatar
        FROM   social_media_post p
        JOIN   social_media_user u  ON u.id = p.user_id
        LEFT   JOIN social_media_profile pr ON pr.user_id = p.user_id
        WHERE  p.id = ANY(%s::uuid[])
        """,
        (ids,),
    )
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


def _fetch_shared_reel_details(cur, shared_reel_ids: List[str]) -> dict:
    """Fetch basic details of a reel that was reshared."""
    ids = [rid for rid in shared_reel_ids if rid]
    if not ids:
        return {}
    cur.execute(
        """
        SELECT r.id::text, r.caption, r.video, r.thumbnail,
               r.hls_playlist, r.created_at::text,
               u.username, u.full_name, pr.avatar
        FROM   social_media_reel r
        JOIN   social_media_user u  ON u.id = r.user_id
        LEFT   JOIN social_media_profile pr ON pr.user_id = r.user_id
        WHERE  r.id = ANY(%s::uuid[])
        """,
        (ids,),
    )
    result = {}
    for row in cur.fetchall():
        rid = row["id"]
        result[rid] = {
            "id":          rid,
            "username":    row["username"],
            "full_name":   row["full_name"] or None,
            "avatar":      full_url(row["avatar"]),
            "caption":     row["caption"] or "",
            "video":       full_url(row["video"]) if row["video"] else None,
            "thumbnail":   full_url(row["thumbnail"]) if row["thumbnail"] else None,
            "hls_playlist": full_url(row["hls_playlist"]) if row["hls_playlist"] else None,
            "created_at":  row["created_at"],
        }
    return result


def _is_followed(cur, requesting_user_id: str, owner_ids: List[str]) -> dict:
    if not owner_ids or not requesting_user_id:
        return {uid: False for uid in owner_ids}
    cur.execute(
        """
        SELECT to_user_id::text
        FROM   social_media_user_following
        WHERE  from_user_id = %s::uuid AND to_user_id = ANY(%s::uuid[])
        """,
        (requesting_user_id, owner_ids),
    )
    followed = {row["to_user_id"] for row in cur.fetchall()}
    return {uid: (uid in followed) for uid in owner_ids}


def _current_user_reaction(cur, requesting_user_id: str, content_ids: List[str]) -> dict:
    if not content_ids or not requesting_user_id:
        return {cid: None for cid in content_ids}
    cur.execute(
        """
        SELECT post_id::text, type AS reaction_type
        FROM   social_media_reaction
        WHERE  user_id = %s::uuid AND post_id = ANY(%s::uuid[])
        """,
        (requesting_user_id, content_ids),
    )
    result = {cid: None for cid in content_ids}
    for row in cur.fetchall():
        result[row["post_id"]] = row["reaction_type"]
    return result


# ──────────────────────────────────────────────────────────────────────────────
# FULL POST ENRICHMENT  (single DB round-trip)
# ──────────────────────────────────────────────────────────────────────────────

def fetch_post_details(post_ids: List[str], requesting_user_id: str) -> dict:
    """Single DB round-trip to fully enrich a list of post IDs."""
    if not post_ids:
        return {}
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT p.id::text, p.content, p.created_at::text, p.updated_at::text,
                       p.shared_post_id::text AS shared_post, p.views_count,
                       u.id::text AS user_id, u.username, u.full_name, pr.avatar
                FROM   social_media_post p
                JOIN   social_media_user u  ON u.id = p.user_id
                LEFT   JOIN social_media_profile pr ON pr.user_id = p.user_id
                WHERE  p.id = ANY(%s::uuid[])
                """,
                (post_ids,),
            )
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
                    "is_reel":               False,
                    "video":                 None,
                    "thumbnail":             None,
                    "hls_playlist":          None,
                    "shared_reel":           None,
                    "shared_reel_details":   None,
                }
            return result
    finally:
        conn.close()


# ──────────────────────────────────────────────────────────────────────────────
# FULL REEL ENRICHMENT  (single DB round-trip)
# ──────────────────────────────────────────────────────────────────────────────

def fetch_reel_details(reel_ids: List[str], requesting_user_id: str) -> dict:
    if not reel_ids:
        return {}
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT r.id::text, r.caption, r.video, r.thumbnail,
                       r.hls_playlist, r.views_count,
                       r.created_at::text, r.updated_at::text,
                       u.id::text AS user_id, u.username, u.full_name, pr.avatar
                FROM   social_media_reel r
                JOIN   social_media_user u   ON u.id = r.user_id
                LEFT   JOIN social_media_profile pr ON pr.user_id = r.user_id
                WHERE  r.id = ANY(%s::uuid[])
                """,
                (reel_ids,),
            )
            reels_raw = {row["id"]: dict(row) for row in cur.fetchall()}
            if not reels_raw:
                return {}

            found_ids = list(reels_raw.keys())
            owner_ids = list({r["user_id"] for r in reels_raw.values()})

            reaction_map     = _fetch_reactions(cur, found_ids)
            comment_map      = _fetch_comments(cur, found_ids)
            comment_cnt_map  = _fetch_comments_count(cur, found_ids)
            follow_map       = _is_followed(cur, requesting_user_id, owner_ids)
            cur_reaction_map = _current_user_reaction(cur, requesting_user_id, found_ids)

            result = {}
            for rid, row in reels_raw.items():
                rxn = reaction_map.get(rid, {})
                result[rid] = {
                    "id":                    rid,
                    "user_id":               row["user_id"],
                    "username":              row["username"],
                    "avatar":                full_url(row["avatar"]),
                    "content":               row["caption"] or "",
                    "video":                 full_url(row["video"]) if row["video"] else None,
                    "thumbnail":             full_url(row["thumbnail"]) if row["thumbnail"] else None,
                    "hls_playlist":          full_url(row["hls_playlist"]) if row["hls_playlist"] else None,
                    "media":                 [],
                    "categories_detail":     [],
                    "shared_post":           None,
                    "shared_post_details":   None,
                    "shared_reel":           None,
                    "shared_reel_details":   None,
                    "reactions_count":       rxn.get("reactions_count", 0),
                    "like_count":            rxn.get("like_count", 0),
                    "reaction_types":        rxn.get("reaction_types", []),
                    "current_user_reaction": cur_reaction_map.get(rid),
                    "is_followed":           follow_map.get(row["user_id"], False),
                    "comments_count":        comment_cnt_map.get(rid, 0),
                    "comments":              comment_map.get(rid, []),
                    "views_count":           row["views_count"] or 0,
                    "created_at":            row["created_at"],
                    "updated_at":            row["updated_at"],
                    "is_reel":               True,
                }
            return result
    finally:
        conn.close()