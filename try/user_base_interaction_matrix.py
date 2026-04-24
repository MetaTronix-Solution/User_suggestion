import psycopg2
import psycopg2.extras
import pandas as pd

db_config = {
    "host": "36.253.137.34",
    "port": 5436,
    "dbname": "social_db",
    "user": "innovator_user",
    "password": "Nep@tronix9335%"
}

# Reaction scoring map
SCORE_MAP = {
    "like":      1,
    "love":      1,
    "wow":       1,
    "haha":      1,
    "celebrate": 1,
    "dislike":  -0.5,
    "sad":      -0.5,
}

conn = psycopg2.connect(**db_config)
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

# Fixed query: original had "SELECT type user_id" (missing comma)
cur.execute("""
    SELECT user_id, post_id, type, created_at
    FROM social_media_reaction
""")
rows = cur.fetchall()
cur.close()
conn.close()

if not rows:
    print("No reactions found.")
else:
    print(f"Fetched {len(rows)} reactions.")

    # Build a DataFrame from the raw rows
    df = pd.DataFrame([dict(r) for r in rows])

    # Map reaction type to score
    df["score"] = df["type"].str.lower().map(SCORE_MAP).fillna(0).astype(int)

    # Pivot: rows = user_id, columns = post_id, values = score, missing = 0
    matrix = df.pivot_table(
        index="user_id",
        columns="post_id",
        values="score",
        aggfunc="sum",   # if a user reacted multiple times to one post, sum scores
        fill_value=0
    )

    matrix.columns.name = None   # clean up column axis label
    matrix.index.name = "user_id"

    print("\nUser-Post Reaction Score Matrix:")
    print(matrix.to_string())

    # Optionally save to CSV
    matrix.to_csv("reaction_matrix.csv")
    print("\nMatrix saved to reaction_matrix.csv")