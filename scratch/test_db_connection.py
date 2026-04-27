import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

def test_connection(host, port, dbname, user, password):
    print(f"--- Testing {host}:{port} ---")
    try:
        conn = psycopg2.connect(
            host=host,
            port=port,
            dbname=dbname,
            user=user,
            password=password,
            connect_timeout=3
        )
        print(f"SUCCESS: Connected to {host}")
        conn.close()
        return True
    except Exception as e:
        print(f"FAILED: Could not connect to {host}. Error: {e}")
        return False

if __name__ == "__main__":
    db_name = os.getenv("DB_NAME", "social_db")
    db_user = os.getenv("DB_USER", "innovator_user")
    db_pass = os.getenv("DB_PASSWORD", "Nep@tronix9335%")
    
    # Test 1: Localhost first (most likely to work)
    test_connection("localhost", 5436, db_name, db_user, db_pass)
    
    # Test 2: 127.0.0.1
    test_connection("127.0.0.1", 5436, db_name, db_user, db_pass)

    # Test 3: Public IP
    test_connection("36.253.137.34", 5436, db_name, db_user, db_pass)

