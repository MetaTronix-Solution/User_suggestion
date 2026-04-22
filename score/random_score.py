# score/random_score.py
"""
Generates a random_score (0.0 - 1.0) for every post in the database.
Used as one of the four signals in the recommendation engine.
"""
import random
import pandas as pd
from db.queries import get_db_connection   # ← Fixed import

def generate_random_scores() -> list[dict]:
    """
    Returns list of {"post_id": "...", "random_score": 0.XX} for ALL posts.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id::text AS post_id FROM social_media_post")
            posts = [row[0] for row in cur.fetchall()]
    finally:
        conn.close()

    data = []
    for pid in posts:
        data.append({
            "post_id": pid,
            "random_score": round(random.uniform(0.0, 1.0), 6)
        })

    print(f"✅ Generated random scores for {len(data)} posts")
    return data