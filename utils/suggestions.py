import psycopg2
import csv
import json
import pandas as pd
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import networkx as nx

# Connect to PostgreSQL
conn = psycopg2.connect(
    host="182.93.94.220",
    port=5436,
    dbname="social_db",
    user="innovator_user",
    password="Nep@tronix9335%"
)
cur = conn.cursor()

# Get mutual friends with details and connection info
def get_mutual_friends(user_id, candidate_id):
    query = """
    SELECT DISTINCT f1.to_user_id
    FROM social_media_user_following f1
    JOIN social_media_user_following f2
      ON f1.to_user_id = f2.to_user_id
    WHERE f1.from_user_id = %s AND f2.from_user_id = %s;
    """
    cur.execute(query, (user_id, candidate_id))
    mutual_friends = cur.fetchall()
    
    # Get user details for mutual friends
    mutual_details = []
    for (friend_id,) in mutual_friends:
        cur.execute("""
            SELECT id, username, full_name
            FROM social_media_user
            WHERE id = %s
        """, (friend_id,))
        friend_info = cur.fetchone()
        if friend_info:
            # Get connection relationship (follower count, etc)
            cur.execute("""
                SELECT COUNT(*) FROM social_media_user_following
                WHERE to_user_id = %s
            """, (friend_id,))
            follower_count = cur.fetchone()[0]
            
            mutual_details.append({
                "id": friend_info[0],
                "username": friend_info[1],
                "full_name": friend_info[2],
                "followers": follower_count,
                "connection": f"You -> {friend_info[1]} <- Candidate"
            })
    
    return {
        "connections": mutual_details
    }

# Count mutual friends
def count_mutual_friends(user_id, candidate_id):
    result = get_mutual_friends(user_id, candidate_id)
    return len(result["connections"])

# Count common interests
def get_common_interests(user_id, candidate_id):
    query = """
    SELECT DISTINCT i1.category_id
    FROM social_media_profile_interests i1
    JOIN social_media_profile_interests i2
      ON i1.category_id = i2.category_id
    JOIN social_media_profile p1 ON i1.profile_id = p1.id
    JOIN social_media_profile p2 ON i2.profile_id = p2.id
    WHERE p1.user_id = %s AND p2.user_id = %s;
    """
    cur.execute(query, (user_id, candidate_id))
    return [row[0] for row in cur.fetchall()]

# Compute text similarity (bio, education, occupation, hobbies)
def text_similarity(text1, text2):
    if not text1 or not text2:
        return 0
    words1 = set(text1.lower().split())
    words2 = set(text2.lower().split())
    if not words1 or not words2:
        return 0
    return len(words1 & words2) / len(words1 | words2)

# Compute location similarity (simple string match)
def location_similarity(addr1, addr2):
    if not addr1 or not addr2:
        return 0
    return 1 if addr1.strip().lower() == addr2.strip().lower() else 0

def get_all_user_attributes():
    # Get all users
    query = """
    SELECT id, username, full_name, hobbies, address
    FROM social_media_user
    """
    cur.execute(query)
    users = cur.fetchall()

    attributes = []

    for u in users:
        user_id, username, full_name, hobbies, address = u

        # Get follower list
        cur.execute("""
            SELECT from_user_id FROM social_media_user_following
            WHERE to_user_id = %s
        """, (user_id,))
        followers = [row[0] for row in cur.fetchall()]

        # Get following list
        cur.execute("""
            SELECT to_user_id FROM social_media_user_following
            WHERE from_user_id = %s
        """, (user_id,))
        following = [row[0] for row in cur.fetchall()]

        # Get profile info
        cur.execute("""
            SELECT bio, education, occupation
            FROM social_media_profile
            WHERE user_id = %s
        """, (user_id,))
        profile = cur.fetchone()
        if profile:
            bio, education, occupation = profile
        else:
            bio = education = occupation = ""

        # Get interests
        cur.execute("""
            SELECT category_id FROM social_media_profile_interests
            WHERE profile_id = (SELECT id FROM social_media_profile WHERE user_id = %s)
        """, (user_id,))
        interests = [row[0] for row in cur.fetchall()]

        attributes.append({
            "user_id": user_id,
            "username": username,
            "full_name": full_name,
            "hobbies": hobbies,
            "address": address,
            "bio": bio,
            "education": education,
            "occupation": occupation,
            "followers": followers,
            "following": following,
            "interests": interests
        })

    return attributes


def load_user_attributes_from_csv(csv_path='all_users_attributes_v3.csv'):
    """Load user attributes from a CSV file and parse JSON/list columns."""
    df = pd.read_csv(csv_path, dtype=str)

    array_columns = ['followers', 'following', 'interests']
    for col in array_columns:
        if col in df.columns:
            df[col] = df[col].apply(lambda v: json.loads(v) if pd.notna(v) and isinstance(v, str) else [])

    string_columns = ['user_id', 'username', 'full_name', 'hobbies', 'address', 'bio', 'education', 'occupation']
    for col in string_columns:
        if col in df.columns:
            df[col] = df[col].where(df[col].notna(), None)

    return df.to_dict(orient='records')


# Load data and compute suggestions
def compute_user_suggestions(target_user_id, top_n=5):
    # Load CSV
    df = pd.read_csv('all_users_attributes_v3.csv', dtype=str)
    
    # Parse JSON columns
    for col in ['followers', 'following', 'interests']:
        df[col] = df[col].apply(lambda v: json.loads(v) if pd.notna(v) and isinstance(v, str) else [])
    
    # Normalize text fields to avoid NaN values
    for col in ['bio', 'education', 'occupation', 'hobbies', 'address']:
        if col in df.columns:
            df[col] = df[col].where(df[col].notna(), '')
    
    # Initialize model for embeddings
    model = SentenceTransformer('paraphrase-MiniLM-L3-v2')
    
    # Precompute embeddings for text fields
    text_fields = ['bio', 'education', 'occupation', 'hobbies', 'address']
    for field in text_fields:
        df[f'{field}_embed'] = df[field].fillna('').apply(lambda x: model.encode(x) if x else np.zeros(384))
    
    # Filter target user
    target_row = df[df['user_id'] == target_user_id]
    if target_row.empty:
        return []
    target = target_row.iloc[0]
    
    # Determine if target is a new user (no connections)
    is_new_user = len(target['followers']) == 0 and len(target['following']) == 0
    
    # Build graph for graph-based scores
    G = nx.DiGraph()
    for _, row in df.iterrows():
        for follower in row['followers']:
            G.add_edge(follower, row['user_id'])  # follower -> user
        for following in row['following']:
            G.add_edge(row['user_id'], following)  # user -> following
    
    suggestions = []
    
    for _, candidate in df.iterrows():
        if candidate['user_id'] == target_user_id:
            continue
        
        # 1. Text Similarity (Embeddings)
        text_sim = 0
        count = 0
        for field in text_fields:
            if target[field] and candidate[field]:
                sim = cosine_similarity([target[f'{field}_embed']], [candidate[f'{field}_embed']])[0][0]
                text_sim += sim
                count += 1
        text_score = text_sim / count if count > 0 else 0
        
        # 2. Graph-Based: Common Neighbors (mutual following)
        target_following = set(target['following'])
        candidate_following = set(candidate['following'])
        mutual_following = len(target_following & candidate_following)
        graph_score = mutual_following / len(target_following | candidate_following) if target_following or candidate_following else 0
        
        # 3. Content-Based: Interests overlap
        target_interests = set(target['interests'])
        candidate_interests = set(candidate['interests'])
        interest_score = len(target_interests & candidate_interests) / len(target_interests | candidate_interests) if target_interests or candidate_interests else 0
        
        # 4. Collaborative: Simple - based on shared followers (basic CF proxy)
        target_followers = set(target['followers'])
        candidate_followers = set(candidate['followers'])
        collab_score = len(target_followers & candidate_followers) / len(target_followers | candidate_followers) if target_followers or candidate_followers else 0
        
        # Hybrid Score - adjust weights based on user type
        if is_new_user:
            final_score = 0.6 * text_score + 0.1 * graph_score + 0.2 * interest_score + 0.1 * collab_score
        else:
            final_score = 0.1 * text_score + 0.4 * graph_score + 0.2 * interest_score + 0.3 * collab_score
        
        suggestions.append({
            'user_id': candidate['user_id'],
            'username': candidate['username'],
            'full_name': candidate['full_name'],
            'score': final_score,
            'breakdown': {
                'text_score': text_score,
                'graph_score': graph_score,
                'interest_score': interest_score,
                'collab_score': collab_score
            }
        })
    
    # Sort and return top N
    suggestions.sort(key=lambda x: x['score'], reverse=True)
    return suggestions[:top_n]

if __name__ == "__main__":
    results = get_all_user_attributes()
    
    # Write to CSV
    with open('all_users_attributes_v3.csv', 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['user_id', 'username', 'full_name', 'hobbies', 'address', 'bio', 'education', 'occupation', 'followers', 'following', 'interests']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            writer.writerow({
                'user_id': r['user_id'],
                'username': r['username'],
                'full_name': r['full_name'],
                'hobbies': r['hobbies'],
                'address': r['address'],
                'bio': r['bio'],
                'education': r['education'],
                'occupation': r['occupation'],
                'followers': json.dumps(r['followers']),
                'following': json.dumps(r['following']),
                'interests': json.dumps(r['interests'])
            })
    
    print("All user attributes exported to all_users_attributes_v3.csv")
    
    # Now compute suggestions for a sample user
    target_user_id = "bd4cade0-3abd-45e5-a1c0-30f8c64681cd"  # Example user
    print("Computing suggestions...")
    suggestions = compute_user_suggestions(target_user_id)
    print("Suggestions computed.")
    
    print(f"\nTop {len(suggestions)} Suggestions for {target_user_id}:")
    for s in suggestions:
        print(f"ID: {s['user_id']}, Username: {s['username']}, Score: {s['score']:.3f}")
        print(f"  Breakdown: Text: {s['breakdown']['text_score']:.3f}, Graph: {s['breakdown']['graph_score']:.3f}, Interest: {s['breakdown']['interest_score']:.3f}, Collab: {s['breakdown']['collab_score']:.3f}")
        print()