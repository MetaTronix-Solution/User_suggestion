import psycopg2
from psycopg2.extras import DictCursor
import pandas as pd   # Optional: for nice tabular view

# DATABASE CONFIG
DB_CONFIG = {
    "host": "182.93.94.220",
    "port": 5436,
    "dbname": "social_db",
    "user": "innovator_user",
    "password": "Nep@tronix9335%"
}

def read_all_following_data():
    try:
        # Connect to database
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor(cursor_factory=DictCursor)   # DictCursor makes rows dictionary-like

        print("✅ Connected to database successfully!\n")

        # 1. Get table structure (columns)
        cur.execute("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns 
            WHERE table_name = 'social_media_user_following'
            ORDER BY ordinal_position;
        """)
        columns = cur.fetchall()
        
        print("📋 Table Columns:")
        for col in columns:
            print(f"   • {col['column_name']} ({col['data_type']}) - Nullable: {col['is_nullable']}")

        # 2. Get total row count
        cur.execute("SELECT COUNT(*) FROM social_media_user_following;")
        total_rows = cur.fetchone()[0]
        print(f"\n📊 Total records in table: {total_rows:,}")

        # 3. Fetch ALL data
        cur.execute("SELECT * FROM social_media_user_following ORDER BY 1;")  # ORDER BY first column
        all_rows = cur.fetchall()

        print(f"\n✅ Successfully fetched {len(all_rows)} rows\n")

        # Option A: Print as list of dictionaries (clean)
        print("Sample of first 5 rows:")
        for row in all_rows[:5]:
            print(dict(row))

        # Option B: Use Pandas for beautiful table view (Recommended)
        if all_rows:
            df = pd.DataFrame(all_rows, columns=[col['column_name'] for col in columns])
            df.to_csv('social_media_user_following_data.csv', index=True)  # Save to CSV with headers
            print("\n📋 Full Data as DataFrame:")
            print(df.to_string(index=False))

        # Close connection
        cur.close()
        conn.close()
        print("\n🔌 Database connection closed.")

    except Exception as e:
        print(f"❌ Error: {e}")
def read_all_reactions():
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor(cursor_factory=DictCursor)
        
        print("✅ Connected to database successfully!\n")

        # ====================== Get Column Names ======================
        cur.execute("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'social_media_reaction'
            ORDER BY ordinal_position;
        """)
        columns_info = cur.fetchall()
        
        # Extract only column names
        column_names = [col['column_name'] for col in columns_info]

        print("📋 Column Names in social_media_reaction table:")
        print("-" * 60)
        for name in column_names:
            print(f" • {name}")
        print("-" * 60)
        print(f"Total Columns: {len(column_names)}\n")

        # ====================== Get Total Rows ======================
        cur.execute("SELECT COUNT(*) FROM social_media_reaction;")
        total_rows = cur.fetchone()[0]
        print(f"📊 Total records: {total_rows:,}\n")

        # ====================== Fetch All Data ======================
        print("Fetching all data...")
        cur.execute("SELECT * FROM social_media_reaction ORDER BY created_at DESC;")
        all_rows = cur.fetchall()

        print(f"✅ Successfully fetched {len(all_rows)} rows\n")

        # ====================== Print in Dictionary Format ======================
        if all_rows:
            print("📋 All Reactions (Dictionary Format):")
            print("=" * 90)
            for row in all_rows:
                print(dict(row))
            print("=" * 90)

        # ====================== Save to CSV with Column Names ======================
        if all_rows:
            df = pd.DataFrame(all_rows, columns=column_names)
            
            # Save using pandas (clean headers)
            df.to_csv('social_media_reaction_data.csv', index=False)
            
            print(f"\n💾 Data successfully saved to 'social_media_reaction_data.csv'")
            print(f"   → File contains {len(df)} rows and {len(column_names)} columns")
            print(f"   → Column names are written as header row")

        # Close connection
        cur.close()
        conn.close()
        print("\n🔌 Database connection closed.")

    except Exception as e:
        print(f"❌ Error: {e}")
# Run the function
if __name__ == "__main__":
    read_all_following_data()
    read_all_reactions()