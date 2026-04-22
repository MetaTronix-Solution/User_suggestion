import os

import psycopg2
import psycopg2.extras
import pandas as pd
from sklearn.metrics.pairwise import cosine_similarity
from dotenv import load_dotenv
load_dotenv()
DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "port": int(os.getenv("DB_PORT")),
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD")
}

SCORE_MAP = {
    "like":       1,
    "love":       1,
    "wow":        1,
    "haha":       1,
    "celebrate":  1,
    "dislike":   -0.5,
    "sad":       -0.5,
}

def fetch_reactions():
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT user_id, post_id, type
        FROM social_media_reaction
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(r) for r in rows]

def build_reaction_matrix(rows):
    df = pd.DataFrame(rows)
    df["score"] = df["type"].str.lower().map(SCORE_MAP).fillna(0).astype(float)

    matrix = df.pivot_table(
        index="user_id",
        columns="post_id",
        values="score",
        aggfunc="sum",   # sum if a user reacted multiple times to one post
        fill_value=0
    )
    matrix.columns.name = None
    matrix.index.name = "user_id"
    return matrix

def compute_user_similarity(matrix):
    similarity = cosine_similarity(matrix)
    return pd.DataFrame(similarity, index=matrix.index, columns=matrix.index)

def compute_item_similarity(matrix):
    similarity = cosine_similarity(matrix.T)  # .T = transpose the matrix
    return pd.DataFrame(similarity, index=matrix.columns, columns=matrix.columns)

def user_based_recommendations(user_id, matrix, similarity_user):
    """
    Predict scores for unseen posts using weighted sum collaborative filtering:

        r̂(u,i) = Σ s(u,v)·r(v,i)  /  Σ |s(u,v)|
                  v ∈ N(u)              v ∈ N(u)

    Only predicts for posts the target user has NOT interacted with.
    """
    if user_id not in similarity_user.index:
        print(f"User '{user_id}' not found.")
        return []

    # Top N most similar users (exclude self)
    similar_users = (
        similarity_user[user_id]
        .drop(index=user_id)
        .sort_values(ascending=False)
        
    )

    # Posts the target user has NOT interacted with (score == 0)
    unseen_posts = matrix.columns[matrix.loc[user_id] == 0].tolist()

    predictions = {}
    for post in unseen_posts:
        numerator   = 0.0  # Σ s(u,v) · r(v,i)
        denominator = 0.0  # Σ |s(u,v)|

        for sim_user, sim_score in similar_users.items():
            r_vi = matrix.loc[sim_user, post]
            if r_vi != 0:                      # only consider users who interacted
                numerator   += sim_score * r_vi
                denominator += abs(sim_score)

        if denominator > 0:
            predictions[post] = numerator / denominator

    # Sort by predicted score descending, return top N
    top_posts = sorted(predictions.items(), key=lambda x: x[1], reverse=True)
    return top_posts

def item_based_recommendations(user_id, matrix, similarity_item):
    """
    Predict scores for unseen posts using item-based collaborative filtering:
        r̂(u,i) = Σ s(i,j)·r(u,j)  /  Σ |s(i,j)|
                  j ∈ N(i)              j ∈ N(i)
    Only predicts for posts the target user has NOT interacted with.
    """
    if user_id not in matrix.index:
        print(f"User '{user_id}' not found.")
        return []

    # Posts the target user HAS interacted with
    seen_posts = matrix.columns[matrix.loc[user_id] > 0].tolist()

    # Posts the target user has NOT interacted with
    unseen_posts = matrix.columns[matrix.loc[user_id] == 0].tolist()

    predictions = {}
    for unseen_post in unseen_posts:
        numerator   = 0.0  # Σ s(i,j) · r(u,j)
        denominator = 0.0  # Σ |s(i,j)|

        for seen_post in seen_posts:
            s_ij = similarity_item.loc[unseen_post, seen_post]  # item-item similarity
            r_uj = matrix.loc[user_id, seen_post]             # user's rating on seen post

            if s_ij != 0:
                numerator   += s_ij * r_uj
                denominator += abs(s_ij)

        if denominator > 0:
            predictions[unseen_post] = numerator / denominator

    # Sort by predicted score descending, return top N
    top_posts = sorted(predictions.items(), key=lambda x: x[1], reverse=True)
    return top_posts

def hybrid_recommendations(user_id, matrix, user_sim_df, item_sim_df, alpha=0.5):
    """
    Hybrid score:
        score(u,i) = α · r̂_user(u,i) + (1 - α) · r̂_item(u,i)
    """
    # Get user-based predicted scores
    user_scores = dict(
        user_based_recommendations(user_id, matrix, user_sim_df)
    )

    # Get item-based predicted scores
    item_scores = dict(
        item_based_recommendations(user_id, matrix, item_sim_df)
    )

    # Combine all posts from both
    all_posts = set(user_scores.keys()) | set(item_scores.keys())

    hybrid_scores = []
    for post in all_posts:
        u_score = user_scores.get(post, 0.0)
        i_score = item_scores.get(post, 0.0)
        h_score = alpha * u_score + (1 - alpha) * i_score
        hybrid_scores.append((post, h_score))

    # Sort by hybrid score descending
    top_posts = sorted(hybrid_scores, key=lambda x: x[1], reverse=True)

    # ✅ Print in your format
    # print("\nFinal Predicted unseen post:")
    # for post, h_score in top_posts:
        
    #     print(f"{post}  (predicted score: {h_score:.4f})")

    return top_posts

def collaborative_filter_response(user_input):
    
    rows = fetch_reactions()

    # if not rows:
    #     print("No reactions found.")
    #     return

    # print(f"Fetched {len(rows)} reactions.\n")

    # Step 1: Reaction Matrix
    matrix = build_reaction_matrix(rows)
   
    # print("USER-POST REACTION SCORE MATRIX")
    
    # print(matrix.to_string())
    # print()

    # Step 2: Cosine Similarity
    similarity_user = compute_user_similarity(matrix)
    similarity_item = compute_item_similarity(matrix)

    # print("USER-USER COSINE SIMILARITY")
    
    # print(similarity_item.round(4).to_string())
    # print()

    # Step 3: Predict Scores for Unseen Posts per User
   
    
    
    
    predictions_user = user_based_recommendations(user_input, matrix, similarity_user)
    # if predictions_user:
    #         print(f"\n{user_input}:user-based recommendations:\n")
    #         for post, score in predictions_user:
    #             print(f"{post}  (predicted score: {score:.4f})")
    # else:
    #     print(f"\n{user_input}: No unseen posts to predict.")



    predictions_item = item_based_recommendations(user_input, matrix, similarity_item)
    # if predictions_item:
    #     print(f"\n{user_input}:item-based recommendations:\n")
    #     for post, score in predictions_item:
    #         print(f"{post}  (predicted score: {score:.4f})")
    # else:
    #     print(f"\n{user_input}: No unseen posts to predict.")


    results = hybrid_recommendations(
    user_id    = user_input,
    matrix     = matrix,
    user_sim_df = similarity_user,
    item_sim_df = similarity_item,
    alpha      = 0.5,   # tweak this
   
        )
    formatted = [
        {"post_id": post_id, "similarity": round(score, 2)}
        for post_id, score in results
        if score > 0  # optionally filter out zero/negative scores
    ]
    return formatted

   


    # Step 4: Save outputs
    # matrix.to_csv("reaction_matrix.csv")
    # similarity_item.round(4).to_csv("item_similarity.csv")
    # print("\nOutputs saved: reaction_matrix.csv, user_similarity.csv")

# if __name__ == "__main__":
#     print("PREDICTED SCORES FOR UNSEEN POSTS")
#     # print("Formula: r̂(u,i) = Σ s(u,v)·r(v,i) / Σ |s(u,v)|")
#     print("enter user_id to predict for (or 'all' for all users):")
#     user_input = input().strip()
#     collaborative_filter_response(user_input )