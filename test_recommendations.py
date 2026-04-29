#!/usr/bin/env python3
"""Test Posts and Reels Recommendations"""

import requests
import json
from db.queries import get_db_connection

def test_recommendations():
    """Test the recommendation endpoint"""
    
    # Get a sample user
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT id::text FROM social_media_user LIMIT 1')
    result = cur.fetchone()
    conn.close()
    
    if not result:
        print('✗ No users found in database')
        return
    
    user_id = result[0]
    print(f'Testing with user: {user_id}\n')
    
    # Test the API
    try:
        response = requests.get(f'http://localhost:8000/suggestions/{user_id}?top_n=10')
        
        if response.status_code == 200:
            data = response.json()
            total = len(data['posts'])
            print(f'✓ API returned {total} recommendations\n')
            
            if total > 0:
                print('=' * 70)
                print('RECOMMENDED POSTS & REELS')
                print('=' * 70 + '\n')
                
                for i, post in enumerate(data['posts'], 1):
                    content_type = '🎬 REEL' if post.get('is_reel') else '📝 POST'
                    print(f'{i}. {content_type}')
                    print(f'   Username: @{post["username"]}')
                    print(f'   Final Score: {post["final_score"]:.4f}')
                    print(f'   Scores breakdown:')
                    print(f'     - Content:      {post["content_score"]:.4f}')
                    print(f'     - Trending:     {post["trending_score"]:.4f}')
                    print(f'     - Random:       {post["random_score"]:.4f}')
                    print(f'   Engagement:')
                    print(f'     - Reactions: {post["reactions_count"]}')
                    print(f'     - Comments:  {post["comments_count"]}')
                    print(f'     - Views:     {post["views_count"]}')
                    
                    if post.get('content'):
                        preview = post['content'][:80]
                        if len(post['content']) > 80:
                            preview += '...'
                        print(f'   Content: {preview}')
                    
                    if post.get('caption'):
                        print(f'   Caption: {post["caption"][:80]}...')
                    
                    print(f'   Created: {post["created_at"]}')
                    print()
            else:
                print('No recommendations generated')
        else:
            error_data = response.json()
            print(f'✗ API Error {response.status_code}')
            print(f'Details: {error_data}')
    
    except requests.exceptions.ConnectionError:
        print('✗ Cannot connect to API at http://localhost:8000')
        print('  Make sure the API is running: python -m uvicorn main:app --port 8000')
    except Exception as e:
        print(f'✗ Error: {str(e)}')

if __name__ == '__main__':
    test_recommendations()
