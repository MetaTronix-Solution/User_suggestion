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
INDEX_FILE = os.path.join(BASE_DIR, "embedding_data", "post_faiss.index")
ID_FILE = os.path.join(BASE_DIR, "embedding_data", "post_ids.pkl")
MODEL_NAME = "all-MiniLM-L6-v2"

# Load existing index
if os.path.exists(ID_FILE) and os.path.exists(INDEX_FILE):
    with open(ID_FILE, "rb") as f:
        existing_post_ids = pickle.load(f)
    index = faiss.read_index(INDEX_FILE)
    print(f"Loaded existing FAISS index with {len(existing_post_ids)} posts")
else:
    existing_post_ids = []
    index = None
    print("No existing index found. Creating new one")

# DB connection
print("Connecting to database...")
conn = psycopg2.connect(**DB_CONFIG)
cur = conn.cursor()

cur.execute("""
    SELECT
        p.id AS post_id,
        p.content,
        STRING_AGG(DISTINCT cat.name, ', ') AS categories
    FROM social_media_post p
    LEFT JOIN social_media_post_categories pc ON p.id = pc.post_id
    LEFT JOIN social_media_category cat ON pc.category_id = cat.id
    GROUP BY p.id, p.content
    ORDER BY p.created_at DESC;
""")

rows = cur.fetchall()
headers = [desc[0] for desc in cur.description]

cur.close()
conn.close()

print(f"Fetched {len(rows)} posts from DB")

def row_to_text(headers, row):
    post = dict(zip(headers, row))
    content = str(post.get("content", "")).strip()
    categories = str(post.get("categories", "")).strip() or "general"
    return f"{content} [Categories: {categories}]"

post_ids = [str(row[0]) for row in rows]
texts = [row_to_text(headers, row) for row in rows]

new_ids = [pid for pid in post_ids if pid not in existing_post_ids]

if not new_ids:
    print("All posts already embedded. Nothing to do.")
else:
    print(f"Embedding {len(new_ids)} new posts")

    new_texts = [texts[post_ids.index(pid)] for pid in new_ids]

    model = SentenceTransformer(MODEL_NAME)

    new_vectors = model.encode(
        new_texts,
        batch_size=32,
        convert_to_numpy=True,
        normalize_embeddings=True
    ).astype("float32")

    if index is None:
        index = faiss.IndexFlatL2(new_vectors.shape[1])

    index.add(new_vectors)

    existing_post_ids.extend(new_ids)

    faiss.write_index(index, INDEX_FILE)

    with open(ID_FILE, "wb") as f:
        pickle.dump(existing_post_ids, f)

    print(f"Saved FAISS index ({len(existing_post_ids)} posts)")
