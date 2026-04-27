import psycopg2
import pandas as pd
import os
from dotenv import load_dotenv

load_dotenv()

def populate_reels():
    try:
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=os.getenv("DB_PORT", 5436),
            dbname=os.getenv("DB_NAME", "social_db"),
            user=os.getenv("DB_USER", "innovator_user"),
            password=os.getenv("DB_PASSWORD", "Nep@tronix9335%")
        )
        conn.autocommit = True
        cur = conn.cursor()

        print("Importing reels from trending scores...")
        df_reels = pd.read_csv("data/post_trending_scores.csv")
        
        # Get a valid user ID to assign these reels to
        cur.execute("SELECT id FROM social_media_user LIMIT 1")
        res = cur.fetchone()
        if not res:
            print("No users found. Please run populate_db.py first.")
            return
        user_id = res[0]
        
        for _, row in df_reels.iterrows():
            rid = row['post_id']
            cur.execute(
                """
                INSERT INTO social_media_reel (id, user_id, video, thumbnail, views_count, created_at) 
                VALUES (%s, %s, %s, %s, %s, %s) 
                ON CONFLICT (id) DO NOTHING
                """,
                (rid, user_id, f"videos/{rid}.mp4", f"thumbnails/{rid}.jpg", int(row['views']), row['created_at'])
            )

        print("Reels population complete.")
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    populate_reels()

