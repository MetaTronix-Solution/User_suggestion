# utils/helpers.py
import os
import sys
from dotenv import load_dotenv
import psutil
import pandas as pd

load_dotenv()

def _get_env(key: str, default=None, required=False):
    value = os.getenv(key)
    if required and value is None:
        print(f"❌ ERROR: Missing required environment variable: {key}")
        print("   Please add it to your .env file and try again.")
        sys.exit(1)
    return value if value is not None else default

DB_CONFIG = {
    "host": _get_env("DB_HOST", required=True),
    "port": int(_get_env("DB_PORT", "5432", required=True)),
    "dbname": _get_env("DB_NAME", required=True),
    "user": _get_env("DB_USER", required=True),
    "password": _get_env("DB_PASSWORD", required=True),
}

MEDIA_BASE_URL = os.getenv("MEDIA_BASE_URL", "http://36.253.137.34:8005").rstrip("/")
TRENDING_CSV = "data/post_trending_scores.csv"

# Four-signal recommendation weights
REC_WEIGHTS = {
    "content_score": float(os.getenv("W_CONTENT", 0.30)),
    "trending_score": float(os.getenv("W_TRENDING", 0.20)),
    "random_score": float(os.getenv("W_RANDOM", 0.10)),
    "collaborative_score": float(os.getenv("W_COLLABORATIVE", 0.40)),
}

def full_url(path: str | None) -> str | None:
    if not path:
        return None
    return path if path.startswith("http") else f"{MEDIA_BASE_URL}/media/{path.lstrip('/')}"

def min_max_normalize(series):
    lo, hi = series.min(), series.max()
    if hi == lo:
        return series * 0
    return (series - lo) / (hi - lo)

def _get_ram_mb():
    try:
        return psutil.Process().memory_info().rss / 1024 / 1024
    except Exception:
        return 0.0
    
def _min_max_normalize(series: pd.Series):
    lo, hi = series.min(), series.max()
    if hi == lo:
        return pd.Series([0] * len(series), index=series.index)
    return (series - lo) / (hi - lo)    