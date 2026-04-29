#!/usr/bin/env python
"""Get real recommendation data from API"""

import requests
import json
import time
from db.queries import get_db_connection

def get_real_user():
    """Get a real user from database"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('SELECT id::text, username FROM social_media_user LIMIT 1')
        user = cur.fetchone()
        conn.close()
        return user
    except Exception as e:
        print(f"❌ Error getting user: {e}")
        return None

def get_recommendations(user_id, top_n=10):
    """Call the recommendation API"""
    try:
        url = f"http://localhost:8000/suggestions/{user_id}"
        params = {"top_n": top_n}
        
        print(f"\n📡 Calling API: {url}")
        print(f"Parameters: {params}")
        print("\n⏳ Waiting for response...")
        
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        
        return response.json()
    except requests.exceptions.ConnectionError:
        print("❌ Connection Error: API not running on port 8000")
        print("   Run: python -m uvicorn main:app --port 8000")
        return None
    except requests.exceptions.Timeout:
        print("❌ Timeout: API took too long to respond")
        return None
    except Exception as e:
        print(f"❌ Error: {e}")
        return None

def print_recommendations(data):
    """Pretty print recommendations"""
    if not data:
        return
    
    print("\n" + "="*80)
    print("✅ ACTUAL RECOMMENDATIONS RECEIVED!")
    print("="*80)
    
    print(f"\n👤 User ID: {data['user_id']}")
    print(f"📊 Total Recommendations: {data['total_posts']}")
    print(f"🎯 Top N Returned: {data.get('top_n', len(data['posts']))}")
    
    print("\n" + "-"*80)
    print("POSTS & REELS")
    print("-"*80)
    
    for i, post in enumerate(data['posts'], 1):
        content_type = "🎬 REEL" if post.get('is_reel') else "📝 POST"
        
        print(f"\n#{i} {content_type}")
        print(f"   ID: {post['id']}")
        print(f"   Author: @{post['username']}")
        
        if post.get('content'):
            preview = post['content'][:80].replace('\n', ' ')
            if len(post['content']) > 80:
                preview += "..."
            print(f"   Content: {preview}")
        
        if post.get('caption'):
            caption = post['caption'][:80]
            if len(post['caption']) > 80:
                caption += "..."
            print(f"   Caption: {caption}")
        
        # Scores
        print(f"\n   ⭐ SCORES:")
        print(f"      Final Score:        {post['final_score']:.4f} (0.0-1.0)")
        print(f"      Content Score:      {post.get('content_score', 0):.4f}")
        print(f"      Trending Score:     {post.get('trending_score', 0):.4f}")
        print(f"      Collaborative:      {post.get('collaborative_score', 0):.4f}")
        print(f"      Random Score:       {post.get('random_score', 0):.4f}")
        
        # Engagement
        print(f"\n   📊 ENGAGEMENT:")
        print(f"      Reactions:  {post['reactions_count']:,}")
        print(f"      Comments:   {post.get('comments_count', 0):,}")
        print(f"      Views:      {post['views_count']:,}")
        
        # Media
        if post.get('image'):
            print(f"\n   🖼️  Image: {post['image'][:60]}...")
        if post.get('video'):
            print(f"\n   🎥 Video: {post['video'][:60]}...")
        
        print(f"\n   ⏰ Created: {post.get('created_at', 'N/A')}")
    
    print("\n" + "="*80)
    print("✅ FULL JSON RESPONSE")
    print("="*80)
    print(json.dumps(data, indent=2))

def main():
    print("\n" + "="*80)
    print("🎬 FETCHING REAL RECOMMENDATION DATA")
    print("="*80)
    
    # Step 1: Get a real user
    print("\n[1/3] Getting a real user from database...")
    user = get_real_user()
    
    if not user:
        print("❌ No users found in database")
        return
    
    user_id, username = user
    print(f"✅ Found user: @{username}")
    print(f"   UUID: {user_id}")
    
    # Step 2: Call the API
    print("\n[2/3] Calling recommendation API...")
    time.sleep(2)  # Give API time to start
    recommendations = get_recommendations(user_id, top_n=10)
    
    if not recommendations:
        return
    
    print("✅ API response received!")
    
    # Step 3: Display the data
    print("\n[3/3] Displaying recommendations...")
    print_recommendations(recommendations)

if __name__ == "__main__":
    main()
