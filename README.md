# 👥 User Suggestion Engine

A multi-signal, graph-aware friend recommendation system for social platforms. It combines semantic text embeddings, social graph analysis, interest overlap, location proximity, interaction history, and collaborative filtering into a single affinity score — with a 3-tier fallback to handle cold-start users.

---

## Features

- **3-Tier Candidate Generation** — BFS depth-2 graph traversal → interest cluster matching → random fallback for cold-start users
- **7-Signal Affinity Scoring** — blends text similarity, graph topology, interest tags, location, interactions, collaborative filtering, and activity
- **Adaptive Weight Blending** — automatically shifts weight toward graph signals for well-connected users and toward text/interest signals for new users
- **Adamic-Adar Graph Scoring** — penalises hub nodes; rewards meaningful shared connections
- **Semantic Embeddings** — `all-MiniLM-L6-v2` encodes bio, education, occupation, hobbies, and location into a 384-dim vector
- **Diversity Pass** — post-ranking Jaccard deduplication prevents interest-homogeneous result sets
- **Reason Labels** — every suggestion surfaces a human-readable explanation (e.g. *"3 mutual friends incl. Jane Doe · Both into Photography"*)

---

## Requirements

```bash
pip install psycopg2-binary pandas numpy scikit-learn networkx sentence-transformers
```

| Package | Purpose |
|---|---|
| `psycopg2` | PostgreSQL connection |
| `pandas` | Tabular data handling |
| `numpy` | Vector operations |
| `scikit-learn` | Cosine similarity |
| `networkx` | Social graph construction |
| `sentence-transformers` | Text embedding model |

---

## Database Schema (Expected Tables)

| Table | Key Columns |
|---|---|
| `social_media_user` | `id`, `username`, `full_name`, `hobbies`, `address` |
| `social_media_profile` | `user_id`, `bio`, `education`, `occupation` |
| `social_media_profile_interests` | `profile_id`, `category_id` |
| `social_media_user_following` | `from_user_id`, `to_user_id` |
| `social_media_user_blocked_users` | `from_user_id`, `to_user_id` |
| `social_media_post` | `user_id`, `created_at` |
| `social_media_reaction` | `post_id` |
| `social_media_like` | `user_id`, `post_id` |
| `social_media_comment` | `user_id`, `post_id` |

---

## Configuration

Edit the connection block at the top of the script:

```python
conn = psycopg2.connect(
    host="YOUR_HOST",
    port=5436,
    dbname="YOUR_DB",
    user="YOUR_USER",
    password="YOUR_PASSWORD"
)
```

---

## Usage

### Run directly

```bash
python suggestion_engine.py
```

Set your target user and result count in the `__main__` block:

```python
TARGET_USER_ID = "your-user-uuid-here"
TOP_N = 10
```

Output is printed to the console and saved to `suggestions.json`.

### Call as a module

```python
from suggestion_engine import compute_user_suggestions

suggestions = compute_user_suggestions(target_user_id="uuid-here", top_n=10)
for s in suggestions:
    print(s["full_name"], s["affinity_score"], s["reason"])
```

---

## Output Format

`suggestions.json` and the return value of `compute_user_suggestions()` share the same structure:

```json
{
  "target_user_id": "...",
  "generated_at": "2025-01-01T00:00:00",
  "total": 10,
  "suggestions": [
    {
      "user_id": "...",
      "username": "john_doe",
      "full_name": "John Doe",
      "affinity_score": 0.7241,
      "mutual_count": 3,
      "shared_tags": [42, 17],
      "reason": "3 mutual friends incl. Jane Smith · Both into 42 + 17",
      "interests": [42, 17, 88],
      "breakdown": {
        "text_score": 0.812,
        "graph_score": 0.540,
        "adamic_adar": 0.600,
        "second_degree": 0.450,
        "interest_score": 0.667,
        "location_score": 0.600,
        "interaction_score": 0.000,
        "collab_score": 0.250,
        "activity_score": 0.730
      },
      "weights_used": {
        "text": 0.2,
        "graph": 0.25,
        "interest": 0.2,
        "location": 0.08,
        "interaction": 0.1,
        "collab": 0.07,
        "activity": 0.05
      }
    }
  ]
}
```

---

## Architecture

```
compute_user_suggestions(target_user_id)
│
├── 1. CANDIDATE POOL
│   ├── Tier 1: BFS depth-2 (friends-of-friends)
│   ├── Tier 2: Interest cluster (≥1 shared tag)
│   └── Tier 3: Random fallback (cold-start)
│
├── 2. ATTRIBUTE FETCHING
│   └── Profile, interests, followers, following, activity stats
│
├── 3. SIGNAL COMPUTATION (per candidate)
│   ├── Text similarity     — sentence-transformers cosine similarity
│   ├── Graph score         — Adamic-Adar (60%) + 2nd-degree Jaccard (40%)
│   ├── Interest score      — Jaccard over interest tag IDs
│   ├── Location score      — token overlap on address strings
│   ├── Interaction score   — likes + weighted comments on target's posts
│   ├── Collab score        — shared followers (collaborative filtering)
│   └── Activity score      — post frequency + likes received + recency
│
├── 4. WEIGHT BLENDING
│   └── Network size drives graph ↔ text weight trade-off
│
├── 5. RANKING + DIVERSITY PASS
│   └── Jaccard deduplication across top-40 pool → top-N output
│
└── 6. REASON LABEL GENERATION
    └── Human-readable string from top contributing signals
```

---

## Signal Weights

Weights adapt to the user's network size. The table below shows approximate ranges:

| Signal | Cold-start weight | Established user weight |
|---|---|---|
| Text (semantic) | ~0.45 | ~0.10 |
| Graph (Adamic-Adar + 2nd-degree) | ~0.05 | ~0.40 |
| Interest (Jaccard) | 0.20 | 0.20 |
| Interaction | 0.10 | 0.10 |
| Location | 0.08 | 0.08 |
| Collaborative filtering | 0.07 | 0.07 |
| Activity | 0.05 | 0.05 |

---

## Notes

- Blocked users and already-followed users are excluded from all candidate tiers.
- The diversity pass uses a Jaccard threshold of **0.80** — candidates more similar than this to an already-selected result are skipped.
- The embedding model (`all-MiniLM-L6-v2`) is downloaded automatically by `sentence-transformers` on first run (~80 MB).
- All database exceptions are caught and rolled back individually; a failure in one signal does not abort the pipeline.