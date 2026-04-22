import os
import sys

import faiss
import pickle
import numpy as np
import psycopg2
from dotenv import load_dotenv
load_dotenv()
DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "port": int(os.getenv("DB_PORT")),
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD")
}

# CONFIG
USER_INDEX_FILE = "embedding_data/user_faiss.index"
USER_ID_FILE    = "embedding_data/user_ids.pkl"

POST_INDEX_FILE = "embedding_data/post_faiss.index"
POST_ID_FILE    = "embedding_data/post_ids.pkl"

TOP_K = 20



# LOAD FAISS INDEXES
# print("Loading user FAISS index...")
user_index = faiss.read_index(USER_INDEX_FILE)
with open(USER_ID_FILE, "rb") as f:
    user_ids = pickle.load(f)
# print(f"  → {len(user_ids)} users loaded")

# print("Loading post FAISS index...")
post_index = faiss.read_index(POST_INDEX_FILE)
with open(POST_ID_FILE, "rb") as f:
    post_ids = pickle.load(f)
# print(f"  → {len(post_ids)} posts loaded")

# EXTRACT ALL POST VECTORS
def reconstruct_all_vectors(index, ids) -> np.ndarray:
    dim = index.d
    vectors = np.zeros((len(ids), dim), dtype="float32")
    for i in range(len(ids)):
        index.reconstruct(i, vectors[i])
    return vectors

print("Reconstructing post vectors...")
post_vectors = reconstruct_all_vectors(post_index, post_ids)

# DB: FETCH POST IDs OWNED BY USER
def get_user_post_ids(user_id: str) -> set:
    """Fetch all post IDs created by the given user from the database."""
    print(f"Fetching posts owned by user {user_id} from DB...")
    conn = psycopg2.connect(**DB_CONFIG)
    cur  = conn.cursor()
    cur.execute(
        "SELECT id FROM social_media_post WHERE user_id = %s;",
        (user_id,)
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    owned = {str(row[0]) for row in rows}
    print(f"  → {len(owned)} posts owned by this user (will be excluded)")
    return owned

# HELPERS
def get_user_vector(user_id: str) -> np.ndarray:
    user_id = str(user_id)
    if user_id not in user_ids:
        raise ValueError(f"User ID '{user_id}' not found in FAISS index.")
    idx = user_ids.index(user_id)
    vector = np.zeros((user_index.d,), dtype="float32")
    user_index.reconstruct(idx, vector)
    return vector


def cosine_similarity(vec_a: np.ndarray, matrix_b: np.ndarray) -> np.ndarray:
    norm_a = np.linalg.norm(vec_a)
    if norm_a == 0:
        raise ValueError("User vector is zero — cannot compute cosine similarity.")
    vec_a_norm = vec_a / norm_a

    norms_b = np.linalg.norm(matrix_b, axis=1, keepdims=True)
    norms_b = np.where(norms_b == 0, 1e-10, norms_b)
    matrix_b_norm = matrix_b / norms_b

    return np.dot(matrix_b_norm, vec_a_norm)


def search_posts_for_user(user_id: str):
    """
    Find top_k most similar posts for a user, excluding their own posts.
    """
    user_vector   = get_user_vector(user_id)
    owned_post_ids = get_user_post_ids(user_id)

    scoresx = cosine_similarity(user_vector, post_vectors)
    scores = (scoresx + 1) / 2
    # Sort all by descending score
    sorted_indices = np.argsort(scores)[::-1]

    results = []
    for idx in sorted_indices:
        pid = post_ids[idx]

        # Skip posts created by this user
        if pid in owned_post_ids:
            continue

        results.append({
            "post_id":    pid,
            "similarity": round(float(scores[idx]), 2)
        })

       

    return results


# MAIN
# Replace the existing __main__ block at the bottom of content_score.py with this:

# if __name__ == "__main__":
#     import json
#     user_id = sys.argv[1].strip() if len(sys.argv) > 1 else input("Enter User ID: ").strip()
#     try:
#         results = search_posts_for_user(user_id)
#         print(json.dumps(results))   # ← main.py reads this JSON from stdout
#     except ValueError as e:
#         print(f"ERROR: {e}", file=sys.stderr)
#         sys.exit(1)