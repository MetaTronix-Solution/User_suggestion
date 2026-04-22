"""
main.py — Unified Social Media API
====================================
Run API server:
  uvicorn main:app --host 0.0.0.0 --port 8000 --reload

Run CLI:
  python main.py <user_id>
"""

import warnings
import pandas as pd
warnings.filterwarnings("ignore", category=FutureWarning)
pd.set_option('future.no_silent_downcasting', True)

import gc
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import psycopg2
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from db.queries import get_db_connection, validate_user_in_db
from embeddings.cache import clear as clear_embed_cache, size as embed_cache_size
from embeddings.model import lifespan
from monitoring import monitor_requests
from routers.post_router import router as post_router
from routers.user_router import router as user_router
from services.post_service import TOP_N, compute_post_recommendations
from services.user_service import compute_user_suggestions   # ✅ ADDED
from utils.helpers import _get_ram_mb

load_dotenv()

# ─────────────────────────────────────────────────────────────────────────────
# APP FACTORY
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Unified Social Media API",
    version="4.0.0",
    description="User suggestions + Post/Reel recommendations in one service",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.middleware("http")(monitor_requests)

app.include_router(user_router)
app.include_router(post_router)


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/", tags=["Health"])
def home():
    return {"message": "API running"}


@app.get("/health", tags=["Health"])
def health():
    try:
        conn = get_db_connection()
        conn.close()
        return {
            "status": "ok",
            "database": "connected",
            "ram_mb": round(_get_ram_mb(), 1),
            "embed_cache_size": embed_cache_size(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database unavailable: {e}")


# ── Cache Management ──────────────────────────────────────────────────────────

@app.post("/admin/clear-embed-cache", tags=["Admin"])
def clear_embed_cache_endpoint():
    count = clear_embed_cache()
    return {"cleared": count, "ram_mb": round(_get_ram_mb(), 1)}


# ═════════════════════════════════════════════════════════════════════════════
# BACKGROUND PIPELINE
# ═════════════════════════════════════════════════════════════════════════════

PIPELINE_SCRIPTS = {
    "embeddings": [
        "embedding/post_embeddings.py",
        "embedding/user_embedding.py",
    ],
    "scores": [
        "score/trending_score.py",
    ],
}


def _run_script(script_path: str):
    abs_path = os.path.abspath(script_path)
    name = os.path.basename(script_path)
    try:
        result = subprocess.run(
            ["python", abs_path],
            capture_output=True,
            text=True,
            cwd=os.path.dirname(abs_path),
        )
        if result.returncode == 0:
            print(f"  ✅ [{name}] completed successfully.")
        else:
            print(f"  ❌ [{name}] failed:\n{result.stderr.strip()}")
    except Exception as e:
        print(f"  ❌ [{name}] exception: {e}")


def run_pipeline():
    print("\n🔄 [Pipeline] Starting...")
    with ThreadPoolExecutor(max_workers=2) as executor:
        for f in [executor.submit(_run_script, s) for s in PIPELINE_SCRIPTS["embeddings"]]:
            f.result()
    with ThreadPoolExecutor(max_workers=2) as executor:
        for f in [executor.submit(_run_script, s) for s in PIPELINE_SCRIPTS["scores"]]:
            f.result()
    print("✅ [Pipeline] Complete.\n")


scheduler = BackgroundScheduler()
scheduler.add_job(run_pipeline, "interval", minutes=5, id="pipeline_job")
scheduler.start()

print("🕐 Scheduler started:")
print("   • run_pipeline() → every 5 minutes")
print("     └─ embeddings (parallel)")
print("     └─ trending_score.py")


# ═════════════════════════════════════════════════════════════════════════════
# CLI
# ═════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":

    uid = sys.argv[1].strip() if len(sys.argv) >= 2 else input("Enter User ID: ").strip()

    if not uid:
        print("❌ No user ID provided.")
        sys.exit(1)

    # ── Validate user ─────────────────────────────────────────────
    try:
        info = validate_user_in_db(uid)
        print(f"  ✅ DB user: {info['username']} ({uid})")
    except Exception as e:
        print(f"\n❌ DB error: {e}")
        sys.exit(1)

    # ── Run pipeline ──────────────────────────────────────────────
    print("\n🔄 Running pipeline to build indexes and scores...")
    run_pipeline()

    # ✅ Pre-warm embedding model once for both scorers
    print("🔥 Warming up embedding model...")
    from embeddings.model import get_model
    get_model()
    print("   Model ready.\n")

    # ── POST RECOMMENDATIONS ──────────────────────────────────────
    try:
        response = compute_post_recommendations(uid, top_n=TOP_N)

        print(f"\n📌 Top {len(response.posts)} Posts | User: {uid}")
        print(f"{'#':<4} {'Post ID':<38} {'Final':>7} {'Content':>8} {'Trend':>7} {'Rand':>6}")

        for rank, post in enumerate(response.posts, 1):
            print(
                f"{rank:<4} {post.id:<38} "
                f"{post.final_score:>7.4f} {post.content_score:>8.4f} "
                f"{post.trending_score:>7.4f} {post.random_score:>6.4f}"
            )

    except Exception as e:
        print(f"\n❌ Post recommendation failed: {e}")
        sys.exit(1)

    # ── USER RECOMMENDATIONS (NEW) ───────────────────────────────
    try:
        print("\n🔍 Computing user recommendations...")

        # ✅ Pre-warm model once before user suggestions
        # (post scoring already loaded it; this ensures it's cached)
        from embeddings.model import get_model as _warm
        _warm()

        user_suggestions = compute_user_suggestions(uid)

        if not user_suggestions:
            print("⚠️ No user recommendations found")
        else:
            print("\n👥 Top User Suggestions:")
            print(f"{'#':<4} {'User ID':<38} {'Score':>8}")

            for i, u in enumerate(user_suggestions[:10], 1):

                if isinstance(u, dict):
                    user_id = u.get("user_id", "N/A")
                    score = u.get("affinity_score", 0.0)
                else:
                    user_id, score = u

                print(f"{i:<4} {user_id:<38} {float(score):>8.4f}")

    except Exception as e:
        print(f"\n❌ User recommendation failed: {e}")