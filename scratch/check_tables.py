import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

def check_tables():
    try:
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=os.getenv("DB_PORT", 5436),
            dbname=os.getenv("DB_NAME", "social_db"),
            user=os.getenv("DB_USER", "innovator_user"),
            password=os.getenv("DB_PASSWORD", "Nep@tronix9335%")
        )
        cur = conn.cursor()
        cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
        tables = cur.fetchall()
        print("Tables in public schema:")
        for t in tables:
            print(f"- {t[0]}")
        
        if tables:
            cur.execute("SELECT COUNT(*) FROM social_media_post")
            print(f"Post count: {cur.fetchone()[0]}")
            
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Error checking tables: {e}")

if __name__ == "__main__":
    check_tables()

