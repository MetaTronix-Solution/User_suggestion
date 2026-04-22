import csv
import math
import os
import psycopg2
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "port": int(os.getenv("DB_PORT")),
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD")
}

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_FILE = os.path.join(BASE_DIR, "data", "post_trending_scores.csv")

WEIGHT_VIEW = 1
WEIGHT_REACTION = 3
WEIGHT_COMMENT = 5
GRAVITY = 1.5


# ---------------- DB ----------------
print("Connecting to database...")
conn = psycopg2.connect(**DB_CONFIG)
cur = conn.cursor()

query = """
    SELECT
        p.id AS post_id,
        p.views_count AS views,
        p.created_at AS created_at,
        COUNT(DISTINCT cm.id) AS comment_count,
        COUNT(DISTINCT r.id) AS total_reactions,
        COUNT(DISTINCT CASE WHEN r.type = 'like'  THEN r.id END) AS like_count,
        COUNT(DISTINCT CASE WHEN r.type = 'love'  THEN r.id END) AS love_count,
        COUNT(DISTINCT CASE WHEN r.type = 'haha'  THEN r.id END) AS haha_count,
        COUNT(DISTINCT CASE WHEN r.type = 'wow'   THEN r.id END) AS wow_count,
        COUNT(DISTINCT CASE WHEN r.type = 'sad'   THEN r.id END) AS sad_count,
        COUNT(DISTINCT CASE WHEN r.type = 'angry' THEN r.id END) AS angry_count
    FROM social_media_post p
    LEFT JOIN social_media_comment cm ON cm.post_id = p.id
    LEFT JOIN social_media_reaction r ON r.post_id = p.id
    GROUP BY p.id, p.views_count, p.created_at
    ORDER BY p.created_at DESC;
"""

print("Running query...")
cur.execute(query)
rows = cur.fetchall()
headers = [desc[0] for desc in cur.description]

cur.close()
conn.close()

print(f"Posts fetched: {len(rows)}")


# ---------------- HELPERS ----------------
def parse_dt(value):
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    value = str(value).strip()
    for fmt in [
        "%Y-%m-%d %H:%M:%S.%f%z",
        "%Y-%m-%d %H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
    ]:
        try:
            dt = datetime.strptime(value, fmt)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except:
            pass

    return datetime.now(timezone.utc)


def trending_score(views, reactions, comments, created_at):
    now = datetime.now(timezone.utc)
    hours_old = max((now - parse_dt(created_at)).total_seconds() / 3600, 0)

    engagement = (
        views * WEIGHT_VIEW +
        reactions * WEIGHT_REACTION +
        comments * WEIGHT_COMMENT
    )

    return engagement / ((hours_old + 2) ** GRAVITY)


# ---------------- COMPUTE ----------------
results = []

for row in rows:
    data = dict(zip(headers, row))

    score = trending_score(
        int(data.get("views") or 0),
        int(data.get("total_reactions") or 0),
        int(data.get("comment_count") or 0),
        data["created_at"]
    )

    results.append({
        "post_id": data["post_id"],
        "trending_score": round(score, 6),
        "views": int(data.get("views") or 0),
        "total_reactions": int(data.get("total_reactions") or 0),
        "comment_count": int(data.get("comment_count") or 0),
        "created_at": data["created_at"],
    })


# sort
results.sort(key=lambda x: x["trending_score"], reverse=True)


# ---------------- SAVE ----------------
os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)

with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=results[0].keys())
    writer.writeheader()
    writer.writerows(results)

print("Saved trending scores:", OUTPUT_FILE)


# ---------------- TOP 10 ----------------
print("\nTop 10 Posts:")
print("Rank  Post ID                          Score     Views  Reactions  Comments")
print("-" * 80)

for i, r in enumerate(results[:10], 1):
    print(
        i,
        r["post_id"],
        round(r["trending_score"], 4),
        r["views"],
        r["total_reactions"],
        r["comment_count"]
    )