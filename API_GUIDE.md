# Social Media API - Posts & Reels Recommendations Guide

## Overview
This API provides intelligent recommendations for posts and reels from your database, combining multiple scoring algorithms for personalized content delivery.

---

## Features

✅ **Database Connection**: Connects to PostgreSQL social media database  
✅ **Posts Recommendations**: Smart scoring using content, trending, random, and collaborative filtering  
✅ **Reels Recommendations**: Trending and random score-based ranking  
✅ **Mixed Feed**: Automatically interleaves posts and reels in recommendations  
✅ **User Validation**: Ensures users exist before generating recommendations  
✅ **CORS Support**: Full cross-origin support for frontend integration  

---

## Environment Configuration

Your `.env` file is already configured with:
```
DB_HOST=36.253.137.34
DB_PORT=5436
DB_NAME=social_db
DB_USER=innovator_user
DB_PASSWORD=Nep@tronix9335%
MEDIA_BASE_URL=http://36.253.137.34:8006
EMBED_MODEL=sentence-transformers/paraphrase-MiniLM-L3-v2
```

---

## Running the API

### Option 1: Development Mode (with auto-reload)
```bash
# From the project root directory
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### Option 2: Production Mode
```bash
gunicorn -w 4 -k uvicorn.workers.UvicornWorker main:app --bind 0.0.0.0:8000
```

### Option 3: Using Docker
```bash
docker-compose up
```

---

## API Endpoints

### Health Check
```
GET /health
```
**Response**: Database connection status and system metrics

### Get Post & Reel Recommendations
```
GET /suggestions/{user_id}?top_n=10
```

**Parameters**:
- `user_id` (string, required): UUID of the user
- `top_n` (integer, optional): Number of recommendations (1-100, default: 10)

**Example**:
```bash
curl "http://localhost:8000/suggestions/550e8400-e29b-41d4-a716-446655440000?top_n=10"
```

**Response**:
```json
{
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "total_posts": 8,
  "top_n": 10,
  "posts": [
    {
      "id": "post-uuid",
      "username": "john_doe",
      "content": "Post content here...",
      "media": [...],
      "is_reel": false,
      "final_score": 0.85,
      "trending_score": 0.72,
      "content_score": 0.90,
      "random_score": 0.45,
      "reactions_count": 120,
      "comments_count": 15,
      "created_at": "2024-01-15T10:30:00Z"
    },
    {
      "id": "reel-uuid",
      "username": "jane_smith",
      "caption": "Reel caption here...",
      "video": "https://...",
      "is_reel": true,
      "final_score": 0.78,
      "trending_score": 0.85,
      "created_at": "2024-01-15T09:15:00Z"
    }
  ]
}
```

### Debug Recommendations
```
GET /suggestions/debug/{user_id}
```
Shows scoring pipeline details for debugging

---

## Recommendation Scoring Algorithm

### Posts Scoring
The system combines **4 scoring signals** with configurable weights:

1. **Content Score** (30% default): Uses sentence embeddings to find similar posts
2. **Trending Score** (20% default): Based on views, reactions, and comments
3. **Collaborative Score** (40% default): Learns from similar users' interactions
4. **Random Score** (10% default): Adds diversity to prevent filter bubbles

**Formula**:
```
final_score = 0.30 × content_norm + 0.20 × trending_norm + 
              0.40 × collaborative_norm + 0.10 × random_norm
```

### Reels Scoring
Reels use a simpler scoring model:
```
final_score = 0.60 × trending_norm + 0.40 × random_norm
```

### Weight Configuration
Edit weights in `utils/helpers.py`:
```python
REC_WEIGHTS = {
    "content_score": 0.30,
    "trending_score": 0.20,
    "random_score": 0.10,
    "collaborative_score": 0.40,
}
```

---

## Database Schema Dependencies

The API expects these tables in your PostgreSQL database:

```
social_media_user              - User profiles
social_media_post              - Post content
social_media_reel              - Reel/video content
social_media_postmedia         - Images/videos attached to posts
social_media_reaction          - Likes and reactions
social_media_comment           - Comments on posts/reels
social_media_profile           - User profiles with avatar
social_media_profile_interests - User interests/categories
social_media_user_following    - User follow relationships
social_media_seen_content      - Track shown content (optional)
```

---

## Testing the API

### 1. Check Database Connection
```bash
curl http://localhost:8000/health
```

### 2. Get Recommendations for a User
```bash
# Replace with a real UUID from your database
curl "http://localhost:8000/suggestions/550e8400-e29b-41d4-a716-446655440000"
```

### 3. Debug Scoring Pipeline
```bash
curl "http://localhost:8000/suggestions/debug/550e8400-e29b-41d4-a716-446655440000"
```

### 4. Test with Python
```python
import requests

user_id = "550e8400-e29b-41d4-a716-446655440000"
response = requests.get(
    f"http://localhost:8000/suggestions/{user_id}",
    params={"top_n": 10}
)

print(response.json())
```

---

## Performance Tuning

### Cache Management
```bash
# Clear embedding cache to free memory
curl -X POST http://localhost:8000/admin/clear-embed-cache
```

### Optimization Tips
1. **Reduce top_n**: Smaller values are faster
2. **Index database columns**: Ensure proper DB indexes on frequently queried fields
3. **Batch requests**: Process multiple users efficiently
4. **Monitor RAM**: Check embedding cache size with `/health` endpoint

---

## Troubleshooting

### Issue: "User does not exist in database"
- **Cause**: Invalid user UUID
- **Solution**: Verify the user_id exists in `social_media_user` table

### Issue: "DB connection error"
- **Cause**: Database unreachable
- **Solution**: Check `.env` credentials and network connectivity to 36.253.137.34:5436

### Issue: "Data file not found"
- **Cause**: Missing CSV files for random/trending scores
- **Solution**: Ensure `post_trending_scores.csv` and random score files exist

### Issue: No reels in recommendations
- **Cause**: No video content in `social_media_reel` table
- **Solution**: Populate reel table with video content

---

## API Response Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 400 | Invalid UUID format |
| 404 | User not found |
| 500 | Server error (check logs) |
| 503 | Database unavailable |

---

## Useful Queries for Verification

### Check user exists
```sql
SELECT id, username FROM social_media_user LIMIT 5;
```

### Count posts
```sql
SELECT COUNT(*) as post_count FROM social_media_post;
```

### Count reels
```sql
SELECT COUNT(*) as reel_count FROM social_media_reel WHERE video IS NOT NULL;
```

### View recommendation scores
```sql
SELECT 
    p.id, p.content, p.views_count,
    COUNT(DISTINCT r.id) as reaction_count,
    COUNT(DISTINCT c.id) as comment_count
FROM social_media_post p
LEFT JOIN social_media_reaction r ON r.post_id = p.id
LEFT JOIN social_media_comment c ON c.post_id = p.id
GROUP BY p.id
ORDER BY p.views_count DESC
LIMIT 10;
```

---

## Next Steps

1. **Start the API**: Run `uvicorn main:app --host 0.0.0.0 --port 8000`
2. **Test health**: Visit `http://localhost:8000/health`
3. **Get user ID**: Query your database for a real user UUID
4. **Get recommendations**: Call `/suggestions/{user_id}`
5. **Monitor**: Check logs for any errors
