# Architecture & Data Flow Diagram

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        CLIENT/FRONTEND                                  │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────┐   │
│  │ JavaScript/React/Mobile App                                    │   │
│  │ Makes HTTP Request: GET /suggestions/{user_id}?top_n=10        │   │
│  └────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ↓ (HTTP GET)
┌─────────────────────────────────────────────────────────────────────────┐
│                          FASTAPI SERVER                                  │
│                    (main.py - Port 8000)                                │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────┐       │
│  │ routers/post_router.py                                      │       │
│  │ ├─ GET /suggestions/{user_id}      ← MAIN ENDPOINT         │       │
│  │ ├─ GET /suggestions/debug/{user_id}                         │       │
│  │ └─ GET /suggest/{user_id}                                  │       │
│  └─────────────────────────────────────────────────────────────┘       │
│                                    │                                    │
│                                    ↓                                    │
│  ┌─────────────────────────────────────────────────────────────┐       │
│  │ services/post_service.py                                    │       │
│  │ compute_post_recommendations()                              │       │
│  └─────────────────────────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    ↓               ↓               ↓
    ┌──────────────────────────────────────────────────────────┐
    │         SCORING ALGORITHMS (4 signals)                   │
    │                                                           │
    │ ┌──────────────────────────────────────────────────────┐ │
    │ │ 1. Content Score                                     │ │
    │ │    score/content_score.py                            │ │
    │ │    - Semantic similarity via embeddings              │ │
    │ │    - Weight: 30%                                     │ │
    │ └──────────────────────────────────────────────────────┘ │
    │                                                           │
    │ ┌──────────────────────────────────────────────────────┐ │
    │ │ 2. Trending Score                                    │ │
    │ │    score/trending_score.py                           │ │
    │ │    - Views + Reactions + Comments                    │ │
    │ │    - Weight: 20%                                     │ │
    │ └──────────────────────────────────────────────────────┘ │
    │                                                           │
    │ ┌──────────────────────────────────────────────────────┐ │
    │ │ 3. Collaborative Score                               │ │
    │ │    score/collaborative_score.py                      │ │
    │ │    - User-based filtering                            │ │
    │ │    - Weight: 40%                                     │ │
    │ └──────────────────────────────────────────────────────┘ │
    │                                                           │
    │ ┌──────────────────────────────────────────────────────┐ │
    │ │ 4. Random Score                                      │ │
    │ │    score/random_score.py                             │ │
    │ │    - Randomness for diversity                        │ │
    │ │    - Weight: 10%                                     │ │
    │ └──────────────────────────────────────────────────────┘ │
    │                                                           │
    └──────────────────────────────────────────────────────────┘
                            │
                            ↓
    ┌────────────────────────────────────────────────────────────┐
    │              MERGE & INTERLEAVE                            │
    │                                                             │
    │  - Combine post scores and reel scores                     │
    │  - Remove duplicates                                      │
    │  - Shuffle for randomness                                 │
    │  - Interleave: ~3 posts per 1 reel                        │
    └────────────────────────────────────────────────────────────┘
                            │
                            ↓
    ┌────────────────────────────────────────────────────────────┐
    │              ENRICH WITH DETAILS                           │
    │                                                             │
    │  db/queries.py:                                           │
    │  - fetch_post_details()  → Media, reactions, comments     │
    │  - fetch_reel_details()  → Video, thumbnail, HLS          │
    └────────────────────────────────────────────────────────────┘
                            │
                            ↓
┌─────────────────────────────────────────────────────────────────────────┐
│                    DATABASE (PostgreSQL)                                │
│                 36.253.137.34:5436 / social_db                         │
│                                                                          │
│  Tables:                                                               │
│  ├─ social_media_user          (User profiles)                        │
│  ├─ social_media_post          (Post content)                         │
│  ├─ social_media_reel          (Reel/video content)                   │
│  ├─ social_media_postmedia     (Images/videos)                        │
│  ├─ social_media_reaction      (Likes & reactions)                    │
│  ├─ social_media_comment       (Comments)                             │
│  ├─ social_media_profile       (User avatars)                         │
│  ├─ social_media_user_following (Follow relationships)                │
│  └─ social_media_seen_content  (Track shown content)                  │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Request/Response Flow

```
CLIENT REQUEST
    │
    ├─ Method: GET
    ├─ Path: /suggestions/{user_id}
    └─ Params: ?top_n=10
                    │
                    ↓
            VALIDATION LAYER
                    │
        ├─ Check user UUID format
        └─ Verify user exists in DB
                    │
                    ↓
        1. SCORE POSTS
           ├─ Load random scores (CSV)
           ├─ Load trending scores (DB)
           ├─ Calculate content scores (embeddings)
           ├─ Get collaborative scores (user patterns)
           └─ Merge & normalize all scores
                    │
                    ↓
        2. SCORE REELS
           ├─ Query reel data from DB
           ├─ Calculate trending scores
           └─ Add random diversity
                    │
                    ↓
        3. INTERLEAVE & SELECT
           ├─ Deduplicate
           ├─ Shuffle
           └─ Select top N mixed content
                    │
                    ↓
        4. ENRICH DETAILS
           ├─ Fetch media attachments
           ├─ Get reactions & comments
           ├─ Check if user follows creator
           └─ Get user avatars
                    │
                    ↓
        5. FORMAT RESPONSE
           ├─ Convert to JSON
           ├─ Add scoring breakdown
           └─ Include all enriched data
                    │
                    ↓
        JSON RESPONSE (HTTP 200)
        {
          "user_id": "...",
          "total_posts": 8,
          "posts": [
            {
              "id": "...",
              "username": "...",
              "content": "...",
              "final_score": 0.85,
              ...
            }
          ]
        }
                    │
                    ↓
            CLIENT RECEIVES
            & DISPLAYS FEED
```

---

## Scoring Algorithm Formula

```
FOR EACH POST:

final_score = (
    0.30 × content_score_normalized +
    0.20 × trending_score_normalized +
    0.40 × collaborative_score_normalized +
    0.10 × random_score_normalized
)

WHERE:
  - content_score = semantic similarity (0-1)
  - trending_score = (views + reactions×3 + comments×5) normalized (0-1)
  - collaborative_score = similarity to user patterns (0-1)
  - random_score = random value (0-1)

FOR EACH REEL:

final_score = (
    0.60 × trending_score_normalized +
    0.40 × random_score_normalized
)

WEIGHTS CONFIGURABLE IN .env:
  - W_CONTENT=0.30
  - W_TRENDING=0.20
  - W_RANDOM=0.10
  - W_COLLABORATIVE=0.40
```

---

## Component Interaction Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│                    CORE RECOMMENDATION ENGINE                      │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ services/post_service.py                                    │  │
│  │ • compute_post_recommendations()                            │  │
│  │ • _build_score_df() - Combine post scores                  │  │
│  │ • _build_reel_score_df() - Score reels                     │  │
│  └──────────────────────────────────────────────────────────────┘  │
│         │              │              │              │             │
│         ↓              ↓              ↓              ↓             │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ │
│  │ Content     │ │ Trending    │ │Collab       │ │Random       │ │
│  │ Scorer      │ │ Scorer      │ │Scorer       │ │Scorer       │ │
│  │             │ │             │ │             │ │             │ │
│  │ Embeddings  │ │ Views +     │ │ User        │ │ Random      │ │
│  │ Similarity  │ │ Reactions + │ │ Patterns    │ │ Values      │ │
│  │             │ │ Comments    │ │             │ │             │ │
│  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘ │
│         │              │              │              │             │
│         └──────────────┬───────────────┴──────────────┘             │
│                        ↓                                            │
│         ┌───────────────────────────────────┐                      │
│         │ Merge & Normalize Scores          │                      │
│         │ • min-max normalization           │                      │
│         │ • deduplicate                     │                      │
│         │ • create final_score              │                      │
│         └───────────────────────────────────┘                      │
│                        ↓                                            │
│         ┌───────────────────────────────────┐                      │
│         │ Interleave Posts & Reels          │                      │
│         │ • shuffle pool                    │                      │
│         │ • select top N                    │                      │
│         │ • ~1 reel per 4 posts             │                      │
│         └───────────────────────────────────┘                      │
│                        ↓                                            │
│         ┌───────────────────────────────────┐                      │
│         │ Fetch Full Details                │                      │
│         │ • Media attachments               │                      │
│         │ • Reactions/comments              │                      │
│         │ • Creator info                    │                      │
│         │ • Follow status                   │                      │
│         └───────────────────────────────────┘                      │
│                        ↓                                            │
│         ┌───────────────────────────────────┐                      │
│         │ Format & Return Response          │                      │
│         │ • PostDetail objects              │                      │
│         │ • Score breakdown                 │                      │
│         │ • Enriched metadata               │                      │
│         └───────────────────────────────────┘                      │
│                        ↓                                            │
│               SEND TO CLIENT                                       │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Data Model Relationships

```
social_media_user
├── username
├── full_name
├── id (UUID)
└── avatar_profile_id
        │
        ├─→ social_media_profile
        │   ├── avatar
        │   ├── bio
        │   └── interests
        │
        ├─→ social_media_post (one user → many posts)
        │   ├── content
        │   ├── created_at
        │   └── id (UUID)
        │       │
        │       ├─→ social_media_postmedia (one post → many media)
        │       │   ├── file (image/video path)
        │       │   └── media_type
        │       │
        │       ├─→ social_media_reaction (one post → many reactions)
        │       │   ├── type (like, love, etc.)
        │       │   └── user_id
        │       │
        │       └─→ social_media_comment (one post → many comments)
        │           ├── content
        │           ├── user_id
        │           └── created_at
        │
        └─→ social_media_reel (one user → many reels)
            ├── caption
            ├── video
            ├── thumbnail
            ├── hls_playlist
            └── id (UUID)
                └─→ [same attachments as posts]
```

---

## Deployment Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   PRODUCTION SERVER                    │
│                                                         │
│  ┌───────────────────────────────────────────────────┐ │
│  │  Gunicorn (WSGI) - 4 workers                     │ │
│  │  Port: 8000 / 443 (behind proxy)                 │ │
│  └───────────────────────────────────────────────────┘ │
│         │        │        │        │                   │
│         ↓        ↓        ↓        ↓                   │
│  ┌─────────────────────────────────────────────────┐   │
│  │  Uvicorn Workers (ASGI)                         │   │
│  │  • Handle concurrent requests                   │   │
│  │  • Process recommendations                      │   │
│  │  • Return JSON responses                        │   │
│  └─────────────────────────────────────────────────┘   │
│         │        │        │        │                   │
│         └────────┼────────┼────────┘                   │
│                  ↓                                     │
│         ┌────────────────────────────┐               │
│         │ Connection Pool            │               │
│         │ (PostgreSQL connections)   │               │
│         └────────────────────────────┘               │
│                  │                                    │
│                  ↓                                    │
│         ┌────────────────────────────┐               │
│         │ Embedding Cache (Redis)    │               │
│         │ (optional for performance) │               │
│         └────────────────────────────┘               │
│                  │                                    │
│                  ↓                                    │
│  ┌───────────────────────────────────────────────┐  │
│  │  PostgreSQL Database                          │  │
│  │  36.253.137.34:5436 / social_db               │  │
│  │  • social_media_user                          │  │
│  │  • social_media_post                          │  │
│  │  • social_media_reel                          │  │
│  │  • reactions, comments, media                 │  │
│  └───────────────────────────────────────────────┘  │
│                                                     │
└─────────────────────────────────────────────────────┘
```

---

## File Dependency Tree

```
main.py (Entry Point)
    │
    ├── routers/post_router.py
    │   └── services/post_service.py
    │       ├── score/content_score.py
    │       ├── score/trending_score.py
    │       ├── score/collaborative_score.py
    │       ├── score/random_score.py
    │       ├── db/queries.py
    │       │   ├── models/schemas.py
    │       │   └── utils/helpers.py
    │       └── embeddings/model.py
    │
    ├── routers/user_router.py
    │   └── services/user_service.py
    │       └── db/queries.py
    │
    ├── db/queries.py
    │   ├── models/schemas.py
    │   └── utils/helpers.py
    │
    ├── embeddings/model.py
    │   └── embeddings/cache.py
    │
    ├── monitoring.py
    │
    └── .env (Configuration)
```

---

## Caching Strategy

```
┌────────────────────────────────────────┐
│  Embedding Model Cache                 │
│                                        │
│  In-Memory Cache (Redis/Dict)         │
│  - Sentence embeddings (1-3GB)        │
│  - User interaction matrices          │
│  - Trending scores                    │
│                                        │
│  ✓ Fast access                        │
│  ✓ Reduce computation                 │
│  ✗ Memory usage increases             │
└────────────────────────────────────────┘
     │
     ├─→ Clear on demand:
     │   POST /admin/clear-embed-cache
     │
     └─→ Periodic refresh:
         - Background scheduler
         - Pre-compute scores
         - Update cache
```

---

This architecture provides:
- ✅ **Scalable**: Multiple workers
- ✅ **Resilient**: Connection pooling
- ✅ **Fast**: Embedding cache
- ✅ **Real-time**: Live data from DB
- ✅ **Flexible**: Configurable weights
