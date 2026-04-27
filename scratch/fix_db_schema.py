import psycopg2
import os
import shutil
from dotenv import load_dotenv

load_dotenv()

ALTER_USER_TABLE = """
ALTER TABLE social_media_user 
ADD COLUMN IF NOT EXISTS email VARCHAR(255),
ADD COLUMN IF NOT EXISTS role VARCHAR(50),
ADD COLUMN IF NOT EXISTS gender VARCHAR(50),
ADD COLUMN IF NOT EXISTS date_of_birth DATE,
ADD COLUMN IF NOT EXISTS phone_number VARCHAR(50);
"""

def fix_db_and_index():
    try:
        # 1. Update Database Schema
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=os.getenv("DB_PORT", 5436),
            dbname=os.getenv("DB_NAME", "social_db"),
            user=os.getenv("DB_USER", "innovator_user"),
            password=os.getenv("DB_PASSWORD", "Nep@tronix9335%")
        )
        conn.autocommit = True
        cur = conn.cursor()
        
        print(f"Updating social_media_user table on port {os.getenv('DB_PORT')}...")
        cur.execute(ALTER_USER_TABLE)
        print("Columns added successfully.")
        
        cur.close()
        conn.close()

        # 2. Clear old FAISS index files to force a rebuild
        embedding_dir = "embedding_data"
        if os.path.exists(embedding_dir):
            print("Clearing old embedding indexes...")
            for f in os.listdir(embedding_dir):
                if f.endswith(".index") or f.endswith(".pkl"):
                    os.remove(os.path.join(embedding_dir, f))
            print("Indexes cleared.")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    fix_db_and_index()

