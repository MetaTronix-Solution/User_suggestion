import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

ALTER_SCHEMA = """
CREATE TABLE IF NOT EXISTS social_media_reel (
    id UUID PRIMARY KEY,
    user_id UUID REFERENCES social_media_user(id) ON DELETE CASCADE,
    video VARCHAR(255),
    hls_playlist VARCHAR(255),
    thumbnail VARCHAR(255),
    caption TEXT,
    views_count INT DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
"""

def add_reel_table():
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
        
        print("Adding social_media_reel table...")
        cur.execute(ALTER_SCHEMA)
        print("Table added successfully.")
        
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    add_reel_table()

