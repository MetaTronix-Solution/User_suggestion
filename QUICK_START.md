# Quick Start Guide - Posts & Reels Recommendation API

## What You Have

Your project is **fully configured** with:
- ✅ Database connection to PostgreSQL (36.253.137.34:5436)
- ✅ Posts & Reels recommendation engine
- ✅ FastAPI server ready to run
- ✅ Multiple recommendation algorithms (Content, Trending, Collaborative)
- ✅ CORS support for frontend integration

---

## Step 1: Install Dependencies (if not already done)

```bash
pip install -r requirements.txt
```

---

## Step 2: Run the API Server

### Option A: Development (with auto-reload)
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### Option B: Production
```bash
gunicorn -w 4 -k uvicorn.workers.UvicornWorker main:app --bind 0.0.0.0:8000
```

### Option C: Using Docker
```bash
docker-compose up --build
```

**Expected output:**
```
INFO:     Started server process [PID]
INFO:     Waiting for application startup.
INFO:     Application startup complete [timestamp]
INFO:     Uvicorn running on http://0.0.0.0:8000
```

---

## Step 3: Test the API

### Option A: Quick Test (Terminal)
```bash
# Check if API is running
curl http://localhost:8000/health

# Get recommendations (replace UUID with real user ID)
curl "http://localhost:8000/suggestions/550e8400-e29b-41d4-a716-446655440000?top_n=10"
```

### Option B: Python Test Script
```bash
# Run with automatic user detection
python test_api.py

# Or with specific user
python test_api.py 550e8400-e29b-41d4-a716-446655440000
```

### Option C: Python Client
```python
from client import RecommendationClient

client = RecommendationClient()

# Check health
print(client.health())

# Get recommendations
posts = client.get_recommendations("550e8400-e29b-41d4-a716-446655440000", top_n=10)
for post in posts:
    print(post)
```

---

## Step 4: Get a Real User ID

Your database should have users. Get one:

```bash
# Using psql
psql -h 36.253.137.34 -p 5436 -U innovator_user -d social_db -c \
  "SELECT id FROM social_media_user LIMIT 5;"

# Or query from Python
python -c "from db.queries import get_db_connection; \
conn = get_db_connection(); \
cur = conn.cursor(); \
cur.execute('SELECT id FROM social_media_user LIMIT 5'); \
print([row[0] for row in cur.fetchall()]); \
conn.close()"
```

---

## Step 5: Use the API

### Get Recommendations
```bash
curl "http://localhost:8000/suggestions/<USER_ID>?top_n=10"
```

**Response Format:**
```json
{
  "user_id": "...",
  "total_posts": 8,
  "top_n": 10,
  "posts": [
    {
      "id": "...",
      "username": "john_doe",
      "content": "Post text...",
      "is_reel": false,
      "final_score": 0.85,
      "trending_score": 0.72,
      "content_score": 0.90,
      "reactions_count": 120,
      "comments_count": 15,
      "views_count": 450,
      "created_at": "2024-01-15T10:30:00Z"
    },
    {
      "id": "...",
      "username": "jane_smith",
      "caption": "Reel video...",
      "is_reel": true,
      "video": "https://...",
      "final_score": 0.78,
      ...
    }
  ]
}
```

---

## What the API Does

### 1. Validates User
- Checks if user exists in database
- Returns 404 if not found

### 2. Scores Posts
Combines 4 signals:
- **Content Score** (30%): Semantic similarity to user interests
- **Trending Score** (20%): Views + reactions + comments
- **Collaborative Score** (40%): What similar users liked
- **Random Score** (10%): Diversity

### 3. Scores Reels
- Views count as trending signal
- Random shuffling for variety

### 4. Interleaves Posts & Reels
- Mixes posts and reels in the feed
- Roughly 1 reel per 4 posts

### 5. Enriches Content
- Fetches media attachments
- Gets reactions and comments
- Shows if you follow the creator

---

## Common Issues & Solutions

| Issue | Solution |
|-------|----------|
| `Connection refused on 0.0.0.0:8000` | Port 8000 already in use, try: `--port 8001` |
| `User does not exist` | Verify user UUID exists in database |
| `DB connection error` | Check .env file, verify DB credentials |
| `No reels in output` | Populate `social_media_reel` table with videos |
| `Module not found` | Run `pip install -r requirements.txt` |
| `API is slow` | Reduce `top_n` parameter or add DB indexes |

---

## API Endpoints Summary

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/` | Root/home |
| GET | `/health` | Check API & DB status |
| GET | `/suggestions/{user_id}` | **Get posts/reels recommendations** |
| GET | `/suggestions/debug/{user_id}` | Debug scoring pipeline |
| GET | `/suggest/{user_id}` | Get user suggestions (different API) |
| POST | `/admin/clear-embed-cache` | Clear embedding cache |

---

## Frontend Integration

### JavaScript/React Example
```javascript
async function getRecommendations(userId, topN = 10) {
  const response = await fetch(
    `http://localhost:8000/suggestions/${userId}?top_n=${topN}`
  );
  const data = await response.json();
  return data.posts; // Array of posts and reels
}
```

### cURL Example
```bash
curl -H "Content-Type: application/json" \
  "http://localhost:8000/suggestions/USER_UUID?top_n=10"
```

---

## Database Verification

Verify your data exists:

```sql
-- Check users
SELECT COUNT(*) as user_count FROM social_media_user;

-- Check posts
SELECT COUNT(*) as post_count FROM social_media_post;

-- Check reels
SELECT COUNT(*) as reel_count FROM social_media_reel WHERE video IS NOT NULL;

-- Check reactions
SELECT COUNT(*) as reaction_count FROM social_media_reaction;

-- Get sample post data
SELECT p.id, p.content, p.views_count, COUNT(r.id) as reactions
FROM social_media_post p
LEFT JOIN social_media_reaction r ON r.post_id = p.id
GROUP BY p.id
LIMIT 5;
```

---

## Performance Tips

1. **Add Database Indexes** (faster queries)
   ```sql
   CREATE INDEX idx_post_user ON social_media_post(user_id);
   CREATE INDEX idx_post_created ON social_media_post(created_at DESC);
   CREATE INDEX idx_reel_views ON social_media_reel(views_count DESC);
   CREATE INDEX idx_reaction_post ON social_media_reaction(post_id);
   ```

2. **Tune Weights** in `utils/helpers.py`:
   - Higher content_score → More personalized
   - Higher trending_score → More viral content
   - Higher collaborative_score → Follow user patterns
   - Higher random_score → More diverse

3. **Use Pagination**:
   - Start with `top_n=5`
   - Increase based on performance

4. **Monitor Memory**:
   ```bash
   curl http://localhost:8000/health  # Check RAM usage
   ```

---

## Next Steps

1. ✅ Start API: `uvicorn main:app --port 8000`
2. ✅ Test endpoint: `curl http://localhost:8000/health`
3. ✅ Get user ID from database
4. ✅ Call recommendations endpoint
5. ✅ Integrate with frontend
6. ✅ Fine-tune weights for better recommendations

---

## Support

- **API Documentation**: Visit `http://localhost:8000/docs` (Swagger UI)
- **Full Guide**: See `API_GUIDE.md`
- **Test Suite**: Run `python test_api.py`
- **Python Client**: See `client.py`

Enjoy your recommendation API! 🚀
