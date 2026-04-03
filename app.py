import psycopg2

conn = psycopg2.connect(
    host="182.93.94.220",
    port=5436,
    dbname="social_db",
    user="innovator_user",
    password="Nep@tronix9335%"
)
cur = conn.cursor()

# Get all tables
cur.execute("""
    SELECT table_name
    FROM information_schema.tables
    WHERE table_schema = 'public'
    ORDER BY table_name;
""")
tables = cur.fetchall()
print("=== TABLES ===")
for t in tables:
    print(" ", t[0])

# Get columns for each table
for (table,) in tables:
    cur.execute("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = %s
        ORDER BY ordinal_position;
    """, (table,))
    cols = cur.fetchall()
    print(f"\n--- {table} ---")
    for col, dtype in cols:
        print(f"  {col:30s}  {dtype}")

cur.close()
conn.close()