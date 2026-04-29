"""
client.py - Python Client for Social Media Recommendation API

Simple wrapper to interact with the Posts & Reels Recommendation API
"""

import requests
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime

@dataclass
class Post:
    """Represents a post or reel from the API"""
    id: str
    username: str
    content: Optional[str]
    is_reel: bool
    final_score: float
    trending_score: float
    content_score: float
    random_score: float
    reactions_count: int
    comments_count: int
    views_count: int
    created_at: str
    video: Optional[str] = None
    thumbnail: Optional[str] = None
    media: List[Dict] = None
    
    def __str__(self):
        content_type = "🎬 REEL" if self.is_reel else "📝 POST"
        return f"{content_type} - @{self.username} (Score: {self.final_score:.3f})"


class RecommendationClient:
    """Client for the Social Media Recommendation API"""
    
    def __init__(self, base_url: str = "http://localhost:8000", timeout: int = 30):
        """
        Initialize the client
        
        Args:
            base_url: Base URL of the API (default: http://localhost:8000)
            timeout: Request timeout in seconds (default: 30)
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
    
    def health(self) -> Dict[str, Any]:
        """Check API health and database connection"""
        response = self.session.get(
            f"{self.base_url}/health",
            timeout=self.timeout
        )
        response.raise_for_status()
        return response.json()
    
    def get_recommendations(self, user_id: str, top_n: int = 10) -> List[Post]:
        """
        Get post and reel recommendations for a user
        
        Args:
            user_id: UUID of the user
            top_n: Number of recommendations (1-100, default: 10)
            
        Returns:
            List of Post objects containing posts and reels
            
        Raises:
            requests.exceptions.HTTPError: If API returns error
        """
        response = self.session.get(
            f"{self.base_url}/suggestions/{user_id}",
            params={"top_n": top_n},
            timeout=self.timeout
        )
        response.raise_for_status()
        data = response.json()
        
        posts = []
        for item in data.get("posts", []):
            posts.append(Post(
                id=item["id"],
                username=item["username"],
                content=item.get("content"),
                is_reel=item.get("is_reel", False),
                final_score=item["final_score"],
                trending_score=item["trending_score"],
                content_score=item["content_score"],
                random_score=item["random_score"],
                reactions_count=item.get("reactions_count", 0),
                comments_count=item.get("comments_count", 0),
                views_count=item.get("views_count", 0),
                created_at=item.get("created_at", ""),
                video=item.get("video"),
                thumbnail=item.get("thumbnail"),
                media=item.get("media", [])
            ))
        
        return posts
    
    def debug_recommendations(self, user_id: str) -> Dict[str, Any]:
        """Get debug information about the recommendation scoring pipeline"""
        response = self.session.get(
            f"{self.base_url}/suggestions/debug/{user_id}",
            timeout=self.timeout
        )
        response.raise_for_status()
        return response.json()
    
    def print_recommendations(self, user_id: str, top_n: int = 10):
        """
        Get and pretty-print recommendations for a user
        
        Args:
            user_id: UUID of the user
            top_n: Number of recommendations
        """
        print(f"\n{'='*60}")
        print(f"Recommendations for User: {user_id}")
        print(f"{'='*60}\n")
        
        try:
            posts = self.get_recommendations(user_id, top_n=top_n)
            
            if not posts:
                print("No recommendations available")
                return
            
            for i, post in enumerate(posts, 1):
                content_type = "🎬 REEL" if post.is_reel else "📝 POST"
                print(f"{i}. {content_type}")
                print(f"   User: @{post.username}")
                print(f"   Score: {post.final_score:.3f} (Trending: {post.trending_score:.3f}, Content: {post.content_score:.3f})")
                print(f"   Reactions: {post.reactions_count} | Comments: {post.comments_count} | Views: {post.views_count}")
                print(f"   Created: {post.created_at}")
                if post.content:
                    preview = post.content[:100] + "..." if len(post.content) > 100 else post.content
                    print(f"   Content: {preview}")
                print()
        
        except requests.exceptions.HTTPError as e:
            print(f"Error: {e.response.status_code} - {e.response.json().get('detail', str(e))}")
        except Exception as e:
            print(f"Error: {str(e)}")


def main():
    """Example usage of the client"""
    import sys
    
    client = RecommendationClient()
    
    # Check health
    print("Checking API health...")
    try:
        health = client.health()
        print(f"✓ API is running - Database: {health.get('database', 'unknown')}")
    except Exception as e:
        print(f"✗ API is not accessible: {str(e)}")
        return
    
    # Get sample user if provided as argument
    if len(sys.argv) > 1:
        user_id = sys.argv[1]
    else:
        # Try to get a sample user from database
        try:
            from db.queries import get_db_connection
            conn = get_db_connection()
            with conn.cursor() as cur:
                cur.execute("SELECT id::text FROM social_media_user LIMIT 1")
                result = cur.fetchone()
                conn.close()
                user_id = result[0] if result else None
        except:
            user_id = None
    
    if user_id:
        client.print_recommendations(user_id, top_n=10)
    else:
        print("\nUsage: python client.py <user_uuid>")
        print("Example: python client.py 550e8400-e29b-41d4-a716-446655440000")


if __name__ == "__main__":
    main()
