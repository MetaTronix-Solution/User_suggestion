import psycopg2
import pandas as pd
import os
import json
import uuid
from dotenv import load_dotenv

load_dotenv()

def populate_db():
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

        # 1. Load Users and Profiles from CSV
        print("Importing users...")
        df_users = pd.read_csv("all_users_attributes_v3.csv")
        
        for _, row in df_users.iterrows():
            uid = row['user_id']
            # Insert user
            cur.execute(
                "INSERT INTO social_media_user (id, username, full_name, hobbies, address) VALUES (%s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING",
                (uid, row['username'], row['full_name'], row['hobbies'], row['address'])
            )
            # Insert profile
            cur.execute(
                "INSERT INTO social_media_profile (user_id, bio, education, occupation) VALUES (%s, %s, %s, %s) ON CONFLICT (user_id) DO NOTHING",
                (uid, row['bio'], row['education'], row['occupation'])
            )

        # 2. Import Followers/Following
        print("Importing followers/following...")
        for _, row in df_users.iterrows():
            uid = row['user_id']
            try:
                followers = json.loads(row['followers'])
                for f_id in followers:
                    if f_id:
                        cur.execute(
                            "INSERT INTO social_media_user_following (from_user_id, to_user_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                            (f_id, uid)
                        )
            except: pass

            try:
                following = json.loads(row['following'])
                for t_id in following:
                    if t_id:
                        cur.execute(
                            "INSERT INTO social_media_user_following (from_user_id, to_user_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                            (uid, t_id)
                        )
            except: pass

        # 3. Import Posts from Trending Scores CSV
        print("Importing dummy posts from trending scores...")
        df_posts = pd.read_csv("data/post_trending_scores.csv")
        
        # We need at least one user to assign these posts to if the CSV doesn't have a user_id
        # Let's use the first user from our users list
        first_user = df_users.iloc[0]['user_id']
        
        for _, row in df_posts.iterrows():
            pid = row['post_id']
            cur.execute(
                "INSERT INTO social_media_post (id, user_id, content, views_count, created_at) VALUES (%s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING",
                (pid, first_user, f"Reel/Post content for {pid}", int(row['views']), row['created_at'])
            )

        print("Data population complete.")
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Error populating DB: {e}")

if __name__ == "__main__":
    populate_db()

