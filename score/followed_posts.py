import os

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
load_dotenv()
DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "port": int(os.getenv("DB_PORT")),
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD")
}



# Get input from user
input_ids = input("Enter from_user_id(s) (comma-separated): ")
from_user_ids = [uid.strip() for uid in input_ids.split(",")]

conn = psycopg2.connect(**DB_CONFIG)
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
def get_followed_posts(from_user_ids):
    cur.execute("""
        SELECT f.from_user_id, f.to_user_id, p.id AS post_id, p.user_id AS post_user_id, p.created_at
        FROM social_media_user_following f
        JOIN social_media_post p
            ON f.to_user_id = p.user_id
        WHERE f.from_user_id = ANY(%s::uuid[]);
    """, (from_user_ids,))  # Pass as list of strings, cast to uuid[] in SQL

    rows = cur.fetchall()
    return rows
followed_posts = get_followed_posts(from_user_ids)
  
if followed_posts:
        
        formatted = [
        {"post_id": post["post_id"]} for post in followed_posts
          # optionally filter out zero/negative scores
    ]
        print(f"\nFormatted Output (post_id, similarity):\n{formatted}")
        
else:
        print("No posts found for the given from_user_id(s)")
cur.close()
conn.close()
