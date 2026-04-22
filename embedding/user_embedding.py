import psycopg2
import numpy as np
import os
import faiss
import pickle
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "port": int(os.getenv("DB_PORT")),
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD")
}

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# IMPORTANT FIX: separate files for users
INDEX_FILE = os.path.join(BASE_DIR, "embedding_data", "user_faiss.index")
ID_FILE = os.path.join(BASE_DIR, "embedding_data", "user_ids.pkl")

MODEL_NAME = "all-MiniLM-L6-v2"

# Load existing index
if os.path.exists(ID_FILE) and os.path.exists(INDEX_FILE):
    with open(ID_FILE, "rb") as f:
        existing_user_ids = pickle.load(f)
    index = faiss.read_index(INDEX_FILE)
    print(f"Loaded existing FAISS index with {len(existing_user_ids)} users")
else:
    existing_user_ids = []
    index = None
    print("No existing index found. Creating new one")

print("Connecting to database...")
conn = psycopg2.connect(**DB_CONFIG)
cur = conn.cursor()

cur.execute("""
    SELECT
        u.id AS user_id,
        u.username, u.full_name, u.email, u.role, u.gender,
        u.date_of_birth, u.address, u.phone_number, u.hobbies,
        p.bio, p.education, p.occupation,
        COALESCE(STRING_AGG(DISTINCT c.name, ', ' ORDER BY c.name), '') AS interests
    FROM social_media_user u
    INNER JOIN social_media_profile p ON p.user_id = u.id
    LEFT JOIN social_media_profile_interests pi ON pi.profile_id = p.id
    LEFT JOIN social_media_category c ON c.id = pi.category_id
    GROUP BY
        u.id, u.email, u.role, u.gender,
        u.date_of_birth, u.address, u.phone_number, u.hobbies,
        p.bio, p.education, p.occupation
    ORDER BY u.id;
""")

rows = cur.fetchall()
headers = [desc[0] for desc in cur.description]

cur.close()
conn.close()

print(f"Fetched {len(rows)} users from DB")

def row_to_text(headers, row):
    return " | ".join(
        f"{col}: {val}" for col, val in zip(headers, row)
        if val is not None and str(val).strip()
    )

user_ids = [str(row[0]) for row in rows]
texts = [row_to_text(headers, row) for row in rows]

new_ids = [uid for uid in user_ids if uid not in existing_user_ids]

if not new_ids:
    print("All users already embedded. Nothing to do")
else:
    print(f"Embedding {len(new_ids)} new users")

    new_texts = [texts[user_ids.index(uid)] for uid in new_ids]

    model = SentenceTransformer(MODEL_NAME)

    new_vectors = model.encode(
        new_texts,
        convert_to_numpy=True
    ).astype("float32")

    if index is None:
        index = faiss.IndexFlatL2(new_vectors.shape[1])

    index.add(new_vectors)

    existing_user_ids.extend(new_ids)

    faiss.write_index(index, INDEX_FILE)

    with open(ID_FILE, "wb") as f:
        pickle.dump(existing_user_ids, f)

    print(f"Saved FAISS index ({len(existing_user_ids)} users)")