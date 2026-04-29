import os
import sys
from dotenv import load_dotenv

# Load local env for local testing
load_dotenv('.env')

# Add path so we can import modules correctly
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from services.post_service import compute_post_recommendations
except ImportError as e:
    print(f"Import error: {e}")
    sys.exit(1)

user_id = "bd4cade0-3abd-45e5-a1c0-30f8c64681cd"
print(f"Testing recommendations for user {user_id} with top_n=10...")

try:
    res = compute_post_recommendations(user_id, top_n=10)
    print(f"\nTotal items returned: {res.total_posts}")
    
    reels_count = sum(1 for p in res.posts if p.is_reel)
    posts_count = sum(1 for p in res.posts if not p.is_reel)
    
    print(f"Total Posts (Non-Reels): {posts_count}")
    print(f"Total Reels: {reels_count}\n")
    
    for idx, p in enumerate(res.posts):
        print(f"{idx+1}. ID: {p.id} | Type: {'Reel' if p.is_reel else 'Post'}")

except Exception as e:
    print(f"Error computing recommendations: {e}")
