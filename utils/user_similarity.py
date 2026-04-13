import pandas as pd
from sklearn.metrics.pairwise import cosine_similarity
from sentence_transformers import SentenceTransformer
from suggestions import get_all_user_attributes 

def simple_similarity(user1_id, user2_id):
    # Load all users from DB
    users = get_all_user_attributes()
    df = pd.DataFrame(users)

    # Text fields to compare
    text_fields = ['bio', 'hobbies', 'address']

    # Fill missing text
    for col in text_fields:
        df[col] = df[col].fillna('')

    # Load model
    model = SentenceTransformer('paraphrase-MiniLM-L3-v2')

    # Compute embeddings for all text fields
    for field in text_fields:
        df[f'{field}_embed'] = df[field].apply(lambda x: model.encode(x) if x else [0]*384)

    # Get the two users
    u1 = df[df['user_id'] == user1_id].iloc[0]
    u2 = df[df['user_id'] == user2_id].iloc[0]

    # Text similarity
    text_score = 0
    count = 0
    for field in text_fields:
        if u1[field] and u2[field]:
            sim = cosine_similarity([u1[f'{field}_embed']], [u2[f'{field}_embed']])[0][0]
            text_score += sim
            count += 1
    text_score = text_score / count if count else 0

    # Followers/Following similarity
    followers1, followers2 = set(u1['followers']), set(u2['followers'])
    following1, following2 = set(u1['following']), set(u2['following'])

    follower_score = len(followers1 & followers2) / len(followers1 | followers2) if followers1 or followers2 else 0
    following_score = len(following1 & following2) / len(following1 | following2) if following1 or following2 else 0
    network_score = 0.5 * follower_score + 0.5 * following_score

    # Interests similarity
    interests1, interests2 = set(u1['interests']), set(u2['interests'])
    interest_score = len(interests1 & interests2) / len(interests1 | interests2) if interests1 or interests2 else 0

    # Location similarity
    location_score = 1 if u1['address'].strip().lower() == u2['address'].strip().lower() else 0

    # Final weighted similarity
    final_score = 0.5*text_score + 0.2*network_score + 0.2*interest_score + 0.1*location_score

    breakdown = {
        'text_score': text_score,
        'network_score': network_score,
        'interest_score': interest_score,
        'location_score': location_score
    }

    return final_score, breakdown

if __name__ == "__main__":
    user1_id = "575f6af1-c60c-4373-9d02-278750ac2c6e"  
    user2_id = "3135383a-7163-42d1-806b-e87d20231d68"           

    score, breakdown = simple_similarity(user1_id, user2_id)
    print(f"Similarity between the two users: {score:.3f}")
    print("Breakdown:", breakdown)