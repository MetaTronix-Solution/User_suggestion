import psycopg2
import psycopg2.extras

db_config = {
    "host": "182.93.94.220",
    "port": 5436,
    "dbname": "social_db",
    "user": "innovator_user",
    "password": "Nep@tronix9335%"
}

# Get input from user
input_ids = input("Enter from_user_id(s) (comma-separated): ")
from_user_ids = [uid.strip() for uid in input_ids.split(",")]

conn = psycopg2.connect(**db_config)
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

cur.execute("""
    SELECT f.from_user_id, f.to_user_id, r.post_id, r.user_id,r.type, r.created_at
    FROM social_media_user_following f
    JOIN social_media_reaction r
        ON f.to_user_id = r.user_id
    WHERE f.from_user_id = ANY(%s::uuid[]);
""", (from_user_ids,))  # Pass as list of strings, cast to uuid

rowa = cur.fetchall()
if rowa:
    print("list of posts reacted by followed users:")
    for row in rowa:
        print(f"Post ID: {row['post_id']}, Type: {row['type']}, Created At: {row['created_at']}")
else:
    print("No posts found for the given from_user_id(s)")   