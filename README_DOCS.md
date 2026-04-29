# 📚 Complete Documentation Index

## 🎯 Start Here

**New to the project?** Start with this guide:

1. **[QUICK_START.md](QUICK_START.md)** ⭐ - Read this first!
   - 5-minute quick start
   - Copy-paste commands to run the API
   - Basic testing

2. **[SETUP_COMPLETE.md](SETUP_COMPLETE.md)** - Overview of what's been set up
   - What I created for you
   - How to get started
   - Summary of features

---

## 📖 Detailed Documentation

### **[API_GUIDE.md](API_GUIDE.md)** 
Complete API reference including:
- All available endpoints
- Request/response formats
- Scoring algorithm details
- Database schema
- Performance tuning
- Troubleshooting

### **[STATUS.md](STATUS.md)**
System status and architecture including:
- Setup checklist
- Project structure
- Data flow diagram
- Customization options
- Quick reference table

### **[ARCHITECTURE.md](ARCHITECTURE.md)**
Visual diagrams and technical architecture including:
- System architecture diagram
- Request/response flow
- Scoring algorithm formula
- Component interactions
- Deployment architecture

---

## 🛠️ Helper Scripts

### **[test_api.py](test_api.py)** - Automated Testing
```bash
python test_api.py              # Auto-discover user and test
python test_api.py <user_uuid>  # Test specific user
```

Features:
- Health check
- Recommendation test
- Debug endpoint test
- Pretty-printed results

### **[client.py](client.py)** - Python Client Library
```python
from client import RecommendationClient

client = RecommendationClient()
posts = client.get_recommendations("user-uuid", top_n=10)
```

Features:
- Simple wrapper for API
- Post/Reel data structures
- Error handling

### **[run_api.sh](run_api.sh)** - Unix/Mac Startup Script
```bash
bash run_api.sh           # Development
bash run_api.sh prod      # Production
bash run_api.sh test      # Test
```

### **[run_api.bat](run_api.bat)** - Windows Startup Script
```batch
run_api.bat              :: Development
run_api.bat prod 8000    :: Production
run_api.bat test         :: Test
```

---

## 🚀 Quick Commands

### Start the API

**Windows:**
```batch
run_api.bat
```

**Linux/Mac:**
```bash
bash run_api.sh
```

**Manual (any OS):**
```bash
uvicorn main:app --port 8000
```

### Test the API

```bash
# Automated tests
python test_api.py

# Manual health check
curl http://localhost:8000/health

# Get recommendations
curl "http://localhost:8000/suggestions/USER_UUID?top_n=10"
```

### View API Documentation

Open in browser: **http://localhost:8000/docs**

---

## 📊 What the API Does

Your API:
1. ✅ Connects to PostgreSQL database
2. ✅ Fetches posts and reels
3. ✅ Recommends content using 4 algorithms
4. ✅ Interleaves posts and reels
5. ✅ Enriches with full details
6. ✅ Returns JSON to frontend

---

## 🎓 Learning Paths

### **Path 1: Quick Start (5 minutes)**
1. Open [QUICK_START.md](QUICK_START.md)
2. Run startup command
3. Visit http://localhost:8000/docs
4. Try the `/suggestions/{user_id}` endpoint

### **Path 2: Full Understanding (30 minutes)**
1. Read [SETUP_COMPLETE.md](SETUP_COMPLETE.md)
2. Read [API_GUIDE.md](API_GUIDE.md)
3. Run `python test_api.py`
4. Review [ARCHITECTURE.md](ARCHITECTURE.md)

### **Path 3: Integration (1 hour)**
1. Review [API_GUIDE.md](API_GUIDE.md) responses
2. Study [client.py](client.py) for Python integration
3. Check Swagger docs at http://localhost:8000/docs
4. Write your frontend code

---

## 🎯 Key Files to Know

| File | Purpose | Status |
|------|---------|--------|
| `main.py` | API entry point | ⭐ **RUN THIS** |
| `.env` | Configuration | Configured with your DB |
| `requirements.txt` | Dependencies | Ready to install |
| `routers/post_router.py` | Endpoints | ✅ Works |
| `services/post_service.py` | Recommendations | ✅ Works |
| `db/queries.py` | Database | ✅ Works |

---

## 🔧 Customization

### Change Recommendation Weights

Edit `.env`:
```env
W_CONTENT=0.40          # More personalized
W_TRENDING=0.15         # Less viral content
W_COLLABORATIVE=0.35    # User patterns
W_RANDOM=0.10           # Serendipity
```

### Change API Port

```bash
uvicorn main:app --port 9000    # Use port 9000 instead
```

### Add Custom Endpoint

Edit `routers/post_router.py` and add:
```python
@router.get("/custom-endpoint/{user_id}")
def custom_endpoint(user_id: str):
    return {"message": "Custom response"}
```

---

## 📞 Common Questions

### **Q: How do I get started?**
A: Run `python run_api.bat` (Windows) or `bash run_api.sh` (Linux/Mac), then visit http://localhost:8000/docs

### **Q: What's my user ID?**
A: Query your database:
```bash
python -c "from db.queries import get_db_connection; \
conn = get_db_connection(); \
cur = conn.cursor(); \
cur.execute('SELECT id::text FROM social_media_user LIMIT 1'); \
print(cur.fetchone()[0]); conn.close()"
```

### **Q: How do I integrate with my frontend?**
A: Call the API endpoint:
```javascript
fetch('http://localhost:8000/suggestions/USER_UUID?top_n=10')
  .then(r => r.json())
  .then(data => console.log(data.posts))
```

### **Q: How do I customize recommendations?**
A: Edit `.env` to change weights (W_CONTENT, W_TRENDING, etc.)

### **Q: Can I deploy to production?**
A: Yes! Use gunicorn:
```bash
gunicorn -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000 main:app
```

---

## 🔗 Reference Links

**Internal Documentation:**
- [QUICK_START.md](QUICK_START.md) - 5-minute guide
- [API_GUIDE.md](API_GUIDE.md) - Complete reference
- [STATUS.md](STATUS.md) - System overview
- [ARCHITECTURE.md](ARCHITECTURE.md) - Technical diagrams

**External Links:**
- FastAPI Docs: https://fastapi.tiangolo.com/
- PostgreSQL Docs: https://www.postgresql.org/docs/
- Uvicorn Docs: https://www.uvicorn.org/
- Requests Library: https://requests.readthedocs.io/

---

## ✅ Pre-Launch Checklist

Before going to production:

- ✅ Database is accessible and has data
- ✅ `.env` file has correct credentials
- ✅ `requirements.txt` dependencies installed
- ✅ API runs locally without errors
- ✅ Test endpoint returns data
- ✅ Scoring makes sense
- ✅ Frontend ready to consume API
- ✅ CORS headers correct

---

## 🚀 Deployment Checklist

For production deployment:

- ✅ Use gunicorn instead of uvicorn
- ✅ Set up SSL/TLS certificate
- ✅ Configure reverse proxy (nginx/Apache)
- ✅ Set up database backups
- ✅ Enable monitoring/logging
- ✅ Add rate limiting
- ✅ Test under load
- ✅ Set up error tracking (Sentry)

---

## 📝 API Response Examples

### Get Recommendations
```bash
GET /suggestions/550e8400-e29b-41d4-a716-446655440000?top_n=10
```

**Response:**
```json
{
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "total_posts": 8,
  "top_n": 10,
  "posts": [
    {
      "id": "post-1",
      "username": "john_doe",
      "content": "Amazing content!",
      "is_reel": false,
      "final_score": 0.85,
      "trending_score": 0.72,
      "content_score": 0.90,
      "random_score": 0.45,
      "reactions_count": 120,
      "comments_count": 15,
      "views_count": 450,
      "created_at": "2024-01-15T10:30:00Z"
    }
  ]
}
```

---

## 🎉 Summary

**You now have:**
- ✅ Fully configured recommendation API
- ✅ 4 scoring algorithms
- ✅ Production-ready code
- ✅ Complete documentation
- ✅ Testing scripts
- ✅ Python client library
- ✅ Startup scripts
- ✅ Architecture diagrams

**Next steps:**
1. Start the API
2. Test endpoints
3. Integrate with frontend
4. Customize weights
5. Deploy to production

---

## 📞 Support Resources

**Internal:**
- Check [API_GUIDE.md](API_GUIDE.md) troubleshooting section
- Review [ARCHITECTURE.md](ARCHITECTURE.md) for understanding
- Run [test_api.py](test_api.py) for debugging

**External:**
- FastAPI: https://fastapi.tiangolo.com/
- PostgreSQL: https://www.postgresql.org/
- Stack Overflow: Tag your questions with `fastapi` + `postgresql`

---

**You're all set! Start the API and happy coding! 🚀**

```bash
# Windows
run_api.bat

# Linux/Mac
bash run_api.sh
```

Visit: http://localhost:8000/docs
