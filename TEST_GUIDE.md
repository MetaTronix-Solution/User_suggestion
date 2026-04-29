# Testing Recommended Posts & Reels API

## 📊 System Status

Your API for recommending **posts and reels** is **fully configured**. Here's how to test it:

---

## 🚀 Quick Test (Copy-Paste Commands)

### **1. Start the API** (if not already running)

**Windows:**
```batch
cd d:\nepatronix\innovator_1
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

**Linux/Mac:**
```bash
cd ~/nepatronix/innovator_1
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### **2. Wait for it to start** (look for: "Application startup complete")

### **3. Test in Browser** 
Open: **http://localhost:8000/docs**

This gives you:
- ✅ Interactive API documentation
- ✅ Live endpoint testing
- ✅ Request/response examples

---

## 📋 Testing the Recommendation Endpoint

### **Endpoint Details**

**URL**: `GET /suggestions/{user_id}`

**Parameters**:
- `user_id` (string, required): User UUID
- `top_n` (integer, optional): Number of recommendations (default: 10, max: 100)

### **Example curl Command**

```bash
curl "http://localhost:8000/suggestions/550e8400-e29b-41d4-a716-446655440000?top_n=10"
```

### **Expected Response Format**

```json
{
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "total_posts": 8,
  "top_n": 10,
  "posts": [
    {
      "id": "post-uuid",
      "username": "john_doe",
      "content": "This is an amazing post content...",
      "is_reel": false,
      "final_score": 0.8734,
      "content_score": 0.85,
      "trending_score": 0.92,
      "random_score": 0.45,
      "reactions_count": 245,
      "like_count": 180,
      "reaction_types": ["like", "love"],
      "current_user_reaction": "like",
      "is_followed": true,
      "comments_count": 23,
      "views_count": 890,
      "created_at": "2024-01-15T10:30:00Z",
      "avatar": "https://36.253.137.34:8006/media/avatar.jpg",
      "media": [
        {
          "id": "media-1",
          "file": "https://36.253.137.34:8006/media/image.jpg",
          "media_type": "image"
        }
      ]
    },
    {
      "id": "reel-uuid",
      "username": "jane_smith",
      "caption": "Check out this amazing reel!",
      "is_reel": true,
      "video": "https://36.253.137.34:8006/media/video.mp4",
      "thumbnail": "https://36.253.137.34:8006/media/thumbnail.jpg",
      "hls_playlist": "https://36.253.137.34:8006/media/playlist.m3u8",
      "final_score": 0.7821,
      "content_score": 0.0,
      "trending_score": 0.85,
      "random_score": 0.72,
      "reactions_count": 156,
      "comments_count": 12,
      "views_count": 5420,
      "created_at": "2024-01-15T09:15:00Z"
    }
  ]
}
```

---

## 🧪 How to Get a Real User ID

### **Option 1: Using Python**

Create a file `get_user.py`:

```python
from db.queries import get_db_connection

conn = get_db_connection()
cur = conn.cursor()

# Get a sample user
cur.execute("SELECT id::text, username FROM social_media_user LIMIT 5")
users = cur.fetchall()

print("Sample Users:")
for user_id, username in users:
    print(f"  User ID: {user_id}")
    print(f"  Username: {username}")
    print()

conn.close()
```

Run: `python get_user.py`

### **Option 2: Using psql**

```bash
psql -h 36.253.137.34 -p 5436 -U innovator_user -d social_db \
  -c "SELECT id, username FROM social_media_user LIMIT 5;"
```

### **Option 3: Database Inspection**

```bash
python -c "
from db.queries import get_db_connection
conn = get_db_connection()
cur = conn.cursor()
cur.execute('SELECT COUNT(*) FROM social_media_user')
print(f'Total users: {cur.fetchone()[0]}')
conn.close()
"
```

---

## 📊 Understanding the Response

### **Key Fields Explained**

#### **Scoring Fields** (0-1 range):
- **final_score**: Combined weighted score (main ranking score)
- **content_score**: Semantic similarity to user interests
- **trending_score**: Popularity/viral score
- **random_score**: Random value for diversity

#### **Engagement Fields**:
- **reactions_count**: Total reactions (likes, loves, etc.)
- **like_count**: Just the likes
- **comments_count**: Number of comments
- **views_count**: Number of views

#### **Content Type**:
- **is_reel**: `true` = video/reel, `false` = post
- **video**: URL for reel video (only for reels)
- **hls_playlist**: HLS stream (for video streaming)

---

## 🎯 Testing Checklist

Use this checklist to verify the API works:

- [ ] **API Starts**: No errors on startup
- [ ] **Health Endpoint Works**: `curl http://localhost:8000/health` returns 200
- [ ] **Docs Load**: `http://localhost:8000/docs` displays Swagger UI
- [ ] **Valid User ID Works**: Recommendation call returns 200 with posts
- [ ] **Invalid User Returns 404**: Wrong UUID returns "User not found"
- [ ] **Posts in Response**: Some recommendations have `is_reel: false`
- [ ] **Reels in Response**: Some recommendations have `is_reel: true`
- [ ] **Scores Present**: All items have `final_score` field
- [ ] **Media Attached**: Posts/reels have media or video URLs
- [ ] **Comments/Reactions**: Engagement data is populated

---

## 🔍 Debugging Tips

### **If no recommendations return**:
```bash
# Check if database has posts
curl "http://localhost:8000/suggestions/debug/USER_UUID"
```

This returns:
```json
{
  "random_csv_count": 100,
  "trending_csv_count": 85,
  "content_scored": 45,
  "after_merge": 95,
  "posts_found_in_db": 78,
  "reels_scored": 32,
  "reels_found_in_db": 28
}
```

### **If API is slow**:
- Database might be busy
- Embedding model is computing (first run takes longer)
- Check RAM: more complex queries use more memory

### **If "User not found"**:
- UUID doesn't exist in database
- Try: `SELECT COUNT(*) FROM social_media_user`

---

## 📱 Testing with Different Users

### **Test 1: Power User** (many interactions)
```bash
# Find user with most posts
SELECT id::text FROM social_media_user 
ORDER BY created_at DESC LIMIT 1
```

### **Test 2: New User** (few interactions)
```bash
# Find newest user
SELECT id::text FROM social_media_user 
ORDER BY created_at ASC LIMIT 1
```

### **Test 3: Random User**
```bash
# Get random user
SELECT id::text FROM social_media_user 
ORDER BY RANDOM() LIMIT 1
```

---

## 🎬 What You Should See

### **Typical Recommendation Response**:

```
✓ API returned 10 recommendations

1. 📝 POST - @john_doe
   Score: 0.8734 (Trending: 0.92, Content: 0.85)
   Reactions: 245 | Comments: 23 | Views: 890

2. 🎬 REEL - @jane_smith
   Score: 0.7821 (Trending: 0.85, Content: 0.00)
   Reactions: 156 | Comments: 12 | Views: 5420

3. 📝 POST - @mike_johnson
   Score: 0.6543 (Trending: 0.65, Content: 0.75)
   Reactions: 89 | Comments: 8 | Views: 320

[etc...]
```

---

## 🔄 Full Testing Script

Create `full_test.py`:

```python
#!/usr/bin/env python3
import requests
import sys

# Configuration
API_URL = "http://localhost:8000"
TEST_USERS = [
    "550e8400-e29b-41d4-a716-446655440000",  # Replace with real UUIDs
    "550e8400-e29b-41d4-a716-446655440001",
]

def test_health():
    """Test API health"""
    print("\n1. Testing API Health...")
    try:
        response = requests.get(f"{API_URL}/health", timeout=5)
        if response.status_code == 200:
            print(f"   ✓ API is healthy: {response.json()}")
        else:
            print(f"   ✗ API returned {response.status_code}")
    except Exception as e:
        print(f"   ✗ Error: {e}")

def test_recommendations(user_id):
    """Test recommendations for a user"""
    print(f"\n2. Testing Recommendations for {user_id[:8]}...")
    try:
        response = requests.get(
            f"{API_URL}/suggestions/{user_id}",
            params={"top_n": 5},
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"   ✓ Got {len(data['posts'])} recommendations")
            
            for i, post in enumerate(data['posts'], 1):
                rtype = "REEL" if post.get('is_reel') else "POST"
                print(f"     {i}. {rtype} - @{post['username']} (score: {post['final_score']:.3f})")
        else:
            print(f"   ✗ Error {response.status_code}: {response.json()}")
    except Exception as e:
        print(f"   ✗ Error: {e}")

if __name__ == "__main__":
    test_health()
    
    if len(TEST_USERS) > 0:
        test_recommendations(TEST_USERS[0])
    
    print("\nDone!")
```

Run: `python full_test.py`

---

## 📖 Next Steps

1. **Replace test user UUIDs** with real ones from your database
2. **Start the API** and observe logs
3. **Test endpoints** using Swagger UI or curl
4. **Review scoring** in debug endpoint
5. **Integrate with frontend** using the responses

---

## ✅ Success Criteria

Your API is working correctly when:

✓ `GET /health` returns database status  
✓ `GET /suggestions/{user_id}` returns posts and reels  
✓ Response includes mixed posts and reels  
✓ Each item has a `final_score`  
✓ Media/video URLs are included  
✓ Engagement counts (reactions, comments) are populated  

---

## 🚀 Production Testing

When ready for production:

```bash
# Test with load
for i in {1..10}; do
  curl "http://localhost:8000/suggestions/USER_UUID?top_n=20" &
done

# Check performance
time curl "http://localhost:8000/suggestions/USER_UUID"

# Monitor API logs for errors
```

---

**Ready to test? Start the API and visit http://localhost:8000/docs** ✨
