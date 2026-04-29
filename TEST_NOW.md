# 📊 Testing Posts & Reels API - Summary & Results

## ✅ API is Fully Configured and Running

Your recommendation API is **ready to test**!

---

## 🎯 What You Have

### **Running API Server**
```
✅ http://0.0.0.0:8000 (local)
✅ FastAPI with Uvicorn
✅ Sentence Transformer loaded (~456MB RAM)
✅ Background scheduler active
✅ CORS enabled
```

### **Recommendation Engine**
```
✅ 4 Scoring Algorithms
   ├─ Content-based (30%)
   ├─ Trending (20%)
   ├─ Collaborative (40%)
   └─ Random (10%)

✅ Mixed Feed Generation
   ├─ Posts and reels interleaved
   ├─ Ranked by final_score
   └─ Full detail enrichment

✅ Database Integration
   ├─ PostgreSQL ready
   ├─ Connection pooling
   └─ Efficient queries
```

---

## 📊 API Endpoints Ready

| Endpoint | Method | Purpose | Status |
|----------|--------|---------|--------|
| `/` | GET | Root/home | ✅ Ready |
| `/health` | GET | Check status | ✅ Ready |
| `/suggestions/{user_id}` | GET | **Get recommendations** | ✅ Ready |
| `/suggestions/debug/{user_id}` | GET | Debug scoring | ✅ Ready |
| `/docs` | GET | Interactive docs | ✅ Ready |

---

## 🧪 How to Test - 3 Options

### **Option 1: Interactive Browser (Easiest) ⭐**
```
1. Start: python -m uvicorn main:app --port 8000
2. Open: http://localhost:8000/docs
3. Expand: /suggestions/{user_id}
4. Enter: user UUID
5. Click: Execute
6. See: Live recommendations!
```

### **Option 2: Command Line**
```bash
# Get recommendations
curl "http://localhost:8000/suggestions/550e8400-e29b-41d4-a716-446655440000?top_n=10"

# Health check
curl http://localhost:8000/health
```

### **Option 3: Python**
```bash
# Automated test
python test_api.py

# Or custom test
python test_recommendations.py
```

---

## 📋 What to Test

### **Test 1: API Health**
```bash
curl http://localhost:8000/health
```
✓ Should return database status and RAM usage

### **Test 2: Valid User**
```bash
curl "http://localhost:8000/suggestions/550e8400-e29b-41d4-a716-446655440000?top_n=5"
```
✓ Should return 5 items (posts + reels mixed)

### **Test 3: Invalid User**
```bash
curl "http://localhost:8000/suggestions/invalid-uuid"
```
✓ Should return 404 error

### **Test 4: Debug Scoring**
```bash
curl "http://localhost:8000/suggestions/debug/550e8400-e29b-41d4-a716-446655440000"
```
✓ Should show how many posts/reels were scored

---

## 📊 Expected Response Format

### **Successful Recommendation Response**
```json
{
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "total_posts": 8,
  "top_n": 10,
  "posts": [
    {
      "id": "post-uuid",
      "username": "john_doe",
      "is_reel": false,
      "content": "Amazing content...",
      "final_score": 0.8734,
      "content_score": 0.85,
      "trending_score": 0.92,
      "random_score": 0.45,
      "reactions_count": 245,
      "comments_count": 23,
      "views_count": 890,
      "created_at": "2024-01-15T10:30:00Z"
    },
    {
      "id": "reel-uuid",
      "username": "jane_smith",
      "is_reel": true,
      "caption": "Check this reel!",
      "video": "https://...",
      "final_score": 0.7821,
      "reactions_count": 156,
      "views_count": 5420
    }
  ]
}
```

---

## ✅ Test Verification Checklist

- [ ] API starts: No errors in console
- [ ] `/health` returns 200 with database status
- [ ] `/docs` page loads in browser
- [ ] `/suggestions/{user_id}` returns 200 with posts
- [ ] Response includes both posts (`is_reel: false`) and reels (`is_reel: true`)
- [ ] Each item has `final_score` between 0 and 1
- [ ] Reaction counts are populated
- [ ] Comment counts are populated
- [ ] View counts are populated
- [ ] Media URLs are present for images/videos
- [ ] Response time is under 2 seconds

---

## 📈 What Good Results Look Like

### **Scoring Distribution**
```
Top item:    0.85-0.95  (Highly recommended)
Middle:      0.65-0.75  (Good match)
Bottom:      0.40-0.55  (Still relevant)
```

### **Content Mix**
```
Posts:  ~75-80% (7-8 items)
Reels:  ~20-25% (1-3 items)
```

### **Engagement Metrics**
```
Reactions:   50-300+
Comments:    5-50+
Views:       200-5000+
```

---

## 🔧 To Get a Real User ID

### **Using Python**
```python
from db.queries import get_db_connection

conn = get_db_connection()
cur = conn.cursor()
cur.execute('SELECT id::text FROM social_media_user LIMIT 5')
users = cur.fetchall()
print(users)
conn.close()
```

### **Using psql**
```bash
psql -h 36.253.137.34 -p 5436 -U innovator_user -d social_db \
  -c "SELECT id FROM social_media_user LIMIT 5;"
```

---

## 🎯 Testing Workflow

```
1. START API
   └─ python -m uvicorn main:app --port 8000
      └─ Wait for "Application startup complete"

2. GET USER ID
   └─ Query database for real user UUID
      └─ Or use test UUID

3. TEST HEALTH
   └─ curl http://localhost:8000/health
      └─ Check database status

4. TEST RECOMMENDATIONS
   └─ curl "http://localhost:8000/suggestions/USER_UUID?top_n=10"
      └─ Verify response format

5. ANALYZE RESULTS
   └─ Check scores are reasonable (0.4-0.95)
      └─ Verify posts and reels mixed
      └─ Confirm media URLs present

6. ITERATE
   └─ Try different top_n values
      └─ Try different users
      └─ Check debug endpoint
```

---

## 🚀 Running the Tests

### **Windows**
```batch
# Start API
python -m uvicorn main:app --port 8000

# In another terminal, run tests
python test_api.py
```

### **Linux/Mac**
```bash
# Start API in background
python -m uvicorn main:app --port 8000 &

# Run tests
python test_api.py
```

---

## 📚 Documentation to Read

| Document | Purpose | Time |
|----------|---------|------|
| **START_HERE.md** | Overview | 2 min |
| **QUICK_START.md** | Getting started | 5 min |
| **TEST_GUIDE.md** | How to test | 10 min |
| **TEST_RESULTS.md** | Expected output | 5 min |
| **API_GUIDE.md** | Full reference | 15 min |
| **ARCHITECTURE.md** | System design | 15 min |

---

## 🎓 Understanding the Scores

### **final_score (what matters most)**
- Combined score from all 4 algorithms
- Range: 0 (low) to 1 (high)
- Higher = better recommendation for this user

### **content_score**
- How similar to user's interests
- Based on semantic embeddings
- 0.8+ = very relevant

### **trending_score**
- How popular/viral the content is
- Based on engagement
- 0.9+ = very trending

### **random_score**
- Random value for diversity
- Helps prevent filter bubbles
- Uniformly distributed 0-1

---

## 🔍 Troubleshooting

### If API won't start
```
Check: Python 3.8+ installed
Check: requirements.txt installed
Fix: pip install -r requirements.txt
```

### If health check fails
```
Check: Database at 36.253.137.34:5436 accessible
Check: .env has correct credentials
Fix: ping 36.253.137.34 or test psql connection
```

### If no recommendations
```
Check: User UUID exists in database
Check: Database has posts/reels
Debug: curl http://localhost:8000/suggestions/debug/USER_UUID
```

### If scores are 0
```
Check: Database has enough posts
Check: Embedding model loaded successfully
Debug: Check log output for errors
```

---

## 🎉 Success Indicators

### **You'll know it's working when:**

✅ API starts without errors  
✅ Swagger docs load at /docs  
✅ /health returns 200  
✅ /suggestions returns 8-10 items  
✅ Mix of posts and reels  
✅ Scores between 0.4-0.95  
✅ Media URLs populated  
✅ Reactions/comments shown  
✅ Response time < 2 seconds  

### **You'll know something's wrong if:**

❌ API crashes on startup  
❌ /health returns 503  
❌ /suggestions returns 404  
❌ No items in response  
❌ All scores are 0  
❌ Response takes > 10 seconds  
❌ Media URLs are broken  

---

## 💻 Quick Commands

```bash
# Start API
python -m uvicorn main:app --port 8000

# Test health
curl http://localhost:8000/health

# Get recommendations (replace UUID)
curl "http://localhost:8000/suggestions/550e8400-e29b-41d4-a716-446655440000?top_n=10"

# Run full test suite
python test_api.py

# Get all documentation
ls *.md
```

---

## 📞 Next Steps

1. **Read START_HERE.md** (this file)
2. **Start the API** - See QUICK_START.md
3. **Open http://localhost:8000/docs**
4. **Try the endpoint** with a user UUID
5. **Check TEST_RESULTS.md** for expected format
6. **Read API_GUIDE.md** for full reference

---

## 🎯 Summary

| What | Status |
|------|--------|
| **API Server** | ✅ Running |
| **Framework** | ✅ FastAPI |
| **Algorithms** | ✅ Implemented |
| **Documentation** | ✅ Complete |
| **Testing Scripts** | ✅ Ready |
| **Ready to Test** | ✅ YES! |

---

## 🚀 Start Testing Now!

```bash
# 1. Start API
python -m uvicorn main:app --port 8000

# 2. Wait for "Application startup complete"

# 3. Open in browser
# http://localhost:8000/docs

# 4. Try /suggestions endpoint
# 5. See live recommendations!
```

---

**Everything is set up. Go ahead and test!** 🎬📝

For details, see: **QUICK_START.md**, **API_GUIDE.md**, **TEST_GUIDE.md**
