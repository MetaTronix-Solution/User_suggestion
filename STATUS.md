# 📊 API Setup Status & Summary

## ✅ System Status: FULLY CONFIGURED

Your Social Media API for Posts & Reels Recommendations is **fully configured and ready to run**!

---

## 📋 What Has Been Set Up

### 1. **Database Connection** ✅
- **Host**: 36.253.137.34:5436
- **Database**: social_db
- **User**: innovator_user
- **Configuration File**: `.env`
- **Status**: Ready to connect

### 2. **API Server** ✅
- **Framework**: FastAPI
- **Server**: Uvicorn
- **Port**: 8000 (default, configurable)
- **CORS**: Enabled for all origins
- **Main File**: `main.py`

### 3. **Core Endpoints** ✅

| Endpoint | Purpose | Status |
|----------|---------|--------|
| `GET /health` | Check API & DB status | ✅ Ready |
| `GET /suggestions/{user_id}` | Get posts/reels recommendations | ✅ Ready |
| `GET /suggestions/debug/{user_id}` | Debug scoring pipeline | ✅ Ready |
| `GET /suggest/{user_id}` | Get user suggestions | ✅ Ready |
| `POST /admin/clear-embed-cache` | Clear cache | ✅ Ready |

### 4. **Recommendation Engine** ✅

**Algorithms Implemented**:
- ✅ Content-based scoring (semantic similarity)
- ✅ Trending score (views + reactions + comments)
- ✅ Collaborative filtering (user-based)
- ✅ Random diversity score
- ✅ Automatic posts/reels interleaving

**Customizable Weights** (in `.env`):
```
W_CONTENT=0.30          # Content similarity
W_TRENDING=0.20         # Popularity/viral
W_COLLABORATIVE=0.40    # User patterns
W_RANDOM=0.10           # Diversity
```

### 5. **Data Fetching** ✅

**Posts Data**:
- Post content and metadata
- Media attachments (images/videos)
- Reactions and comments
- Views count
- Category tags
- Shared posts

**Reels Data**:
- Video and thumbnail URLs
- HLS playlist support
- Views count
- Caption text
- Creator information

### 6. **Supporting Services** ✅

- Embedding model: `sentence-transformers/paraphrase-MiniLM-L3-v2`
- Embedding cache system
- Database connection pooling
- Request monitoring
- Error handling

---

## 🚀 Quick Start

### **Option 1: Windows Users**
```batch
run_api.bat
```

### **Option 2: Linux/Mac Users**
```bash
bash run_api.sh
```

### **Option 3: Manual**
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

---

## 🧪 Testing

### **Quick Health Check**
```bash
curl http://localhost:8000/health
```

### **Run Full Test Suite**
```bash
python test_api.py
```

### **Test with Specific User**
```bash
python test_api.py 550e8400-e29b-41d4-a716-446655440000
```

### **Use Python Client**
```bash
python client.py 550e8400-e29b-41d4-a716-446655440000
```

---

## 📁 Project Structure

```
innovator_1/
├── main.py                     # Main API entry point ⭐
├── api_app.py                  # User suggestions API
├── requirements.txt            # Python dependencies
├── .env                        # Configuration (DB credentials)
├── run_api.sh                  # Unix/Mac startup script 🆕
├── run_api.bat                 # Windows startup script 🆕
├── test_api.py                 # Test suite 🆕
├── client.py                   # Python client library 🆕
│
├── API_GUIDE.md                # Detailed API documentation 🆕
├── QUICK_START.md              # Quick start guide 🆕
├── STATUS.md                   # This file 🆕
│
├── routers/
│   ├── post_router.py          # Posts/reels recommendations routes
│   └── user_router.py          # User suggestions routes
│
├── services/
│   ├── post_service.py         # Recommendation logic
│   └── user_service.py         # User suggestion logic
│
├── db/
│   ├── connection.py           # (placeholder)
│   └── queries.py              # Database query functions
│
├── models/
│   └── schemas.py              # Pydantic data models
│
├── score/
│   ├── content_score.py        # Content-based scoring
│   ├── collaborative_score.py  # User-based filtering
│   ├── trending_score.py       # Trending/viral score
│   └── random_score.py         # Diversity score
│
├── embeddings/
│   ├── model.py                # Embedding model loader
│   └── cache.py                # Embedding cache
│
└── data/
    └── post_trending_scores.csv # Trending data
```

---

## 🔄 Data Flow

```
User Request
    ↓
/suggestions/{user_id}
    ↓
[1] Validate user exists
    ↓
[2] Score Posts (4 algorithms):
    • Content scoring (embedding similarity)
    • Trending scoring (views + reactions + comments)
    • Collaborative filtering (user patterns)
    • Random diversity
    ↓
[3] Score Reels:
    • Trending (views)
    • Random
    ↓
[4] Merge & Deduplicate
    ↓
[5] Interleave Posts & Reels
    ↓
[6] Fetch Full Details:
    • Media attachments
    • Comments
    • Reactions
    • User info
    ↓
[7] Return Response
```

---

## 🎯 API Response Example

```json
{
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "total_posts": 8,
  "top_n": 10,
  "posts": [
    {
      "id": "post-123",
      "username": "john_doe",
      "avatar": "https://...",
      "content": "Amazing sunset today! 🌅",
      "media": [
        {
          "id": "media-1",
          "file": "https://36.253.137.34:8006/media/...",
          "media_type": "image"
        }
      ],
      "is_reel": false,
      "final_score": 0.8734,
      "content_score": 0.85,
      "trending_score": 0.92,
      "random_score": 0.45,
      "reactions_count": 245,
      "like_count": 180,
      "comments_count": 23,
      "views_count": 890,
      "is_followed": true,
      "created_at": "2024-01-15T10:30:00Z"
    },
    {
      "id": "reel-456",
      "username": "jane_smith",
      "caption": "Check this out! 🎬",
      "video": "https://36.253.137.34:8006/media/...",
      "thumbnail": "https://...",
      "hls_playlist": "https://...",
      "is_reel": true,
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

## 📊 Scoring Breakdown

### **Content Score** (0-1)
- Calculates semantic similarity using embeddings
- Compares user's interaction history with post content
- Higher = More relevant to user interests

### **Trending Score** (0-1)
- Views count + (reactions × 3) + (comments × 5)
- Normalized to 0-1 range
- Higher = More viral/popular

### **Collaborative Score** (0-1)
- Finds similar users based on interactions
- Recommends posts liked by similar users
- Higher = Similar users enjoyed this

### **Random Score** (0-1)
- Random value 0-1
- Prevents filter bubble
- Introduces serendipity

### **Final Score** (0-1)
```
= 0.30 × content_score
+ 0.20 × trending_score
+ 0.40 × collaborative_score
+ 0.10 × random_score
```

---

## 🛠️ Customization

### Change Recommendation Weights

Edit `.env`:
```env
W_CONTENT=0.40          # Increase personalization
W_TRENDING=0.15         # Decrease viral content
W_COLLABORATIVE=0.35    # User patterns
W_RANDOM=0.10           # Diversity
```

### Change Port

```bash
# Unix/Mac
uvicorn main:app --port 9000

# Windows
python run_api.py 8001
```

### Use Production Server

```bash
gunicorn -w 4 -k uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  main:app
```

---

## 🐛 Troubleshooting

### Port Already in Use
```bash
# Use different port
uvicorn main:app --port 8001
```

### Database Connection Error
```bash
# Check .env file
cat .env

# Test database connection
python -c "from db.queries import get_db_connection; \
conn = get_db_connection(); print('Connected!'); conn.close()"
```

### Module Import Errors
```bash
# Reinstall dependencies
pip install -r requirements.txt --force-reinstall
```

### No Data in Response
```bash
# Check if database has posts
python -c "from db.queries import get_db_connection; \
conn = get_db_connection(); \
cur = conn.cursor(); \
cur.execute('SELECT COUNT(*) FROM social_media_post'); \
print(cur.fetchone()[0]); \
conn.close()"
```

---

## 📖 Documentation Files

| File | Purpose |
|------|---------|
| `QUICK_START.md` | 5-minute getting started guide |
| `API_GUIDE.md` | Comprehensive API documentation |
| `STATUS.md` | This file - system overview |

---

## 🚀 Next Steps

1. **Start API**
   ```bash
   python run_api.bat    # Windows
   bash run_api.sh       # Linux/Mac
   ```

2. **Test Health**
   ```bash
   curl http://localhost:8000/health
   ```

3. **Get Sample User**
   ```bash
   python -c "from db.queries import get_db_connection; \
   conn = get_db_connection(); \
   cur = conn.cursor(); \
   cur.execute('SELECT id::text FROM social_media_user LIMIT 1'); \
   print(cur.fetchone()[0]); conn.close()"
   ```

4. **Get Recommendations**
   ```bash
   curl "http://localhost:8000/suggestions/<USER_UUID>?top_n=10"
   ```

5. **Access Swagger UI**
   - Open: http://localhost:8000/docs
   - Try endpoints interactively

6. **Integrate with Frontend**
   - Use provided `client.py` library
   - Or make direct HTTP requests
   - CORS is enabled

---

## 📞 API Support

### Swagger/OpenAPI Documentation
Access automatic docs at: `http://localhost:8000/docs`

### Get Health & System Info
```bash
curl http://localhost:8000/health
```

### Debug Scoring for User
```bash
curl "http://localhost:8000/suggestions/debug/USER_UUID"
```

---

## ✨ Features at a Glance

- ✅ Personalized post recommendations
- ✅ Mixed posts and reels feed
- ✅ Multi-algorithm scoring
- ✅ Trending content detection
- ✅ User-based filtering
- ✅ Real-time suggestions
- ✅ Production-ready
- ✅ CORS enabled
- ✅ Comprehensive caching
- ✅ Error handling
- ✅ Health monitoring
- ✅ Debug endpoints

---

## 🎉 You're All Set!

Your Social Media Posts & Reels Recommendation API is **fully configured and ready to deliver personalized content to your users**.

**Start the API and begin recommending!** 🚀

```bash
# Quick start
python run_api.bat    # Windows
bash run_api.sh       # Linux/Mac
```

For detailed guidance, see `QUICK_START.md`
