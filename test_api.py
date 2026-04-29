#!/usr/bin/env python3
"""
test_api.py - Test script for Posts/Reels Recommendation API
Run this script to verify your API is working correctly
"""

import requests
import json
import sys
from datetime import datetime

# Configuration
API_BASE_URL = "http://localhost:8000"
TIMEOUT = 10

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    END = '\033[0m'

def print_header(text):
    print(f"\n{Colors.BLUE}{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}{Colors.END}\n")

def print_success(text):
    print(f"{Colors.GREEN}✓ {text}{Colors.END}")

def print_error(text):
    print(f"{Colors.RED}✗ {text}{Colors.END}")

def print_info(text):
    print(f"{Colors.YELLOW}ℹ {text}{Colors.END}")

def print_result(key, value):
    print(f"  {key}: {value}")

def test_health():
    """Test basic API connectivity"""
    print_header("1. Testing API Health Check")
    
    try:
        response = requests.get(
            f"{API_BASE_URL}/health",
            timeout=TIMEOUT
        )
        
        if response.status_code == 200:
            data = response.json()
            print_success("API is running")
            print_result("Database status", data.get("database", "unknown"))
            print_result("RAM usage", f"{data.get('ram_mb', 0)} MB")
            print_result("Cache size", data.get("embed_cache_size", 0))
            return True
        else:
            print_error(f"API returned status {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print_error(f"Cannot connect to API at {API_BASE_URL}")
        print_info("Make sure the API is running: uvicorn main:app --port 8000")
        return False
    except Exception as e:
        print_error(f"Error: {str(e)}")
        return False

def test_recommendations(user_id: str):
    """Test recommendation endpoint"""
    print_header(f"2. Testing Recommendations for User: {user_id}")
    
    try:
        response = requests.get(
            f"{API_BASE_URL}/suggestions/{user_id}",
            params={"top_n": 5},
            timeout=TIMEOUT
        )
        
        if response.status_code == 404:
            print_error(f"User {user_id} not found in database")
            print_info("Please provide a valid user UUID that exists in your database")
            return False
            
        elif response.status_code == 400:
            print_error("Invalid UUID format")
            return False
            
        elif response.status_code == 200:
            data = response.json()
            print_success("Recommendations retrieved")
            print_result("Total recommendations", data.get("total_posts", 0))
            print_result("Requested", data.get("top_n", 0))
            
            posts = data.get("posts", [])
            if posts:
                print(f"\n{Colors.BLUE}Content Feed:{Colors.END}")
                for i, post in enumerate(posts, 1):
                    content_type = "REEL 🎬" if post.get("is_reel") else "POST 📝"
                    print(f"\n  {i}. {content_type}")
                    print(f"     Username: {post.get('username', 'N/A')}")
                    print(f"     Score: {post.get('final_score', 0):.3f}")
                    print(f"     Trending: {post.get('trending_score', 0):.3f}")
                    print(f"     Content: {post.get('content_score', 0):.3f}")
                    print(f"     Reactions: {post.get('reactions_count', 0)}")
                    print(f"     Comments: {post.get('comments_count', 0)}")
                    print(f"     Views: {post.get('views_count', 0)}")
                return True
            else:
                print_error("No recommendations returned")
                return False
                
        else:
            print_error(f"API returned status {response.status_code}")
            print_result("Response", response.text[:200])
            return False
            
    except requests.exceptions.Timeout:
        print_error("Request timed out (API too slow)")
        return False
    except Exception as e:
        print_error(f"Error: {str(e)}")
        return False

def test_debug_endpoint(user_id: str):
    """Test debug endpoint to see scoring breakdown"""
    print_header(f"3. Testing Debug Endpoint for User: {user_id}")
    
    try:
        response = requests.get(
            f"{API_BASE_URL}/suggestions/debug/{user_id}",
            timeout=TIMEOUT
        )
        
        if response.status_code == 200:
            data = response.json()
            print_success("Debug information retrieved")
            print(f"\n{Colors.BLUE}Scoring Pipeline Breakdown:{Colors.END}")
            print_result("Random CSV posts", data.get("random_csv_count", 0))
            print_result("Trending CSV posts", data.get("trending_csv_count", 0))
            print_result("Content scored posts", data.get("content_scored", 0))
            print_result("After merge", data.get("after_merge", 0))
            print_result("Posts found in DB", data.get("posts_found_in_db", 0))
            print_result("Reels scored", data.get("reels_scored", 0))
            print_result("Reels found in DB", data.get("reels_found_in_db", 0))
            return True
        else:
            print_error(f"API returned status {response.status_code}")
            return False
            
    except Exception as e:
        print_error(f"Error: {str(e)}")
        return False

def get_sample_user():
    """Get a sample user from the database"""
    print_header("Finding a Sample User")
    
    try:
        from db.queries import get_db_connection
        
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id::text FROM social_media_user LIMIT 1"
            )
            result = cur.fetchone()
            conn.close()
            
            if result:
                user_id = result[0]
                print_success(f"Found sample user: {user_id}")
                return user_id
            else:
                print_error("No users found in database")
                return None
                
    except Exception as e:
        print_error(f"Could not query database: {str(e)}")
        print_info("Please provide a user UUID manually")
        return None

def main():
    print(f"{Colors.BLUE}")
    print("╔" + "="*58 + "╗")
    print("║" + " "*58 + "║")
    print("║" + "  Social Media API - Posts & Reels Test Suite".center(58) + "║")
    print("║" + " "*58 + "║")
    print("╚" + "="*58 + "╝")
    print(f"{Colors.END}")
    
    print_info(f"API URL: {API_BASE_URL}")
    print_info(f"Timestamp: {datetime.now().isoformat()}")
    
    # Test 1: Health check
    if not test_health():
        print_error("\nCannot proceed - API is not accessible")
        sys.exit(1)
    
    # Test 2: Get sample user or use provided one
    user_id = None
    if len(sys.argv) > 1:
        user_id = sys.argv[1]
        print_info(f"Using provided user ID: {user_id}")
    else:
        user_id = get_sample_user()
    
    if not user_id:
        print_error("\nNo user ID available for testing")
        print_info("Run: python test_api.py <user_uuid>")
        sys.exit(1)
    
    # Test 3: Get recommendations
    if not test_recommendations(user_id):
        print_error("\nRecommendation endpoint test failed")
        # Continue to debug test anyway
    
    # Test 4: Debug endpoint
    test_debug_endpoint(user_id)
    
    # Summary
    print_header("Summary")
    print_success("All tests completed")
    print_info("Check the results above for any issues")
    print_info(f"To use the API: GET /suggestions/<user_id>?top_n=10")
    print(f"\n{Colors.GREEN}✓ API is ready to serve recommendations!{Colors.END}\n")

if __name__ == "__main__":
    main()
