import psycopg2
import psycopg2.extras
import csv

# 🔹 DB CONFIG
DB_CONFIG = {
    "host": "36.253.137.34",
    "port": 5436,
    "dbname": "social_db",
    "user": "innovator_user",
    "password": "Nep@tronix9335%"
}


def get_connection():
    return psycopg2.connect(**DB_CONFIG)


# 🔹 GENERIC FETCH
def fetch_table(cur, table_name):
    cur.execute(f"SELECT * FROM {table_name};")
    return cur.fetchall()


# 🔹 SAVE TO CSV
def save_to_csv(data, filename):
    if not data:
        print(f"⚠️ No data for {filename}")
        return

    keys = data[0].keys()

    with open(filename, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(data)

    print(f"💾 Saved {filename}")


# 🔹 MAIN
def main():
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        print("📥 Extracting data...")

        users = fetch_table(cur, "social_media_user")
        following = fetch_table(cur, "social_media_user_following")
        reactions = fetch_table(cur, "social_media_reaction")
        comments = fetch_table(cur, "social_media_comment")

        print("✅ Data fetched!")

        # 🔹 Save each table
        save_to_csv(users, "users.csv")
        save_to_csv(following, "following.csv")
        save_to_csv(reactions, "reactions.csv")
        save_to_csv(comments, "comments.csv")

    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()