import psycopg2
import os

DB_CONFIG = {
    "host": "36.253.137.34",
    "port": 5436,
    "dbname": "social_db",
    "user": "innovator_user",
    "password": "Nep@tronix9335%"
}

try:
    print(f"Connecting to {DB_CONFIG['host']}:{DB_CONFIG['port']}...")
    conn = psycopg2.connect(**DB_CONFIG, connect_timeout=10)
    print("✅ Connected successfully!")
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM social_media_user")
    count = cur.fetchone()[0]
    print(f"Total users in DB: {count}")
    cur.close()
    conn.close()
except Exception as e:
    print(f"❌ Connection failed: {e}")
