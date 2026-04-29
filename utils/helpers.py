# utils/helpers.py
import os
import sys
from dotenv import load_dotenv
import psutil
import pandas as pd

# Load .env relative to this file's location
load_dotenv(
    dotenv_path=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"),
    override=True
)

print(f"[ENV] DB_PORT from env: {os.getenv('DB_PORT')}")  # debug line

def _get_env(key: str, default=None, required=False):
    value = os.getenv(key)
    if required and value is None:
        print(f" ERROR: Missing required environment variable: {key}")
        sys.exit(1)
    return value if value is not None else default

DB_CONFIG = {
    "host":     _get_env("DB_HOST", required=True),
    "port":     int(_get_env("DB_PORT", "5432")),
    "dbname":   _get_env("DB_NAME", required=True),
    "user":     _get_env("DB_USER", required=True),
    "password": _get_env("DB_PASSWORD", required=True),
}
print(f"[DB] Connecting to {DB_CONFIG['host']}:{DB_CONFIG['port']} / {DB_CONFIG['dbname']}")

MEDIA_BASE_URL = os.getenv("MEDIA_BASE_URL", "http://36.253.137.34:8006").rstrip("/")
TRENDING_CSV = "data/post_trending_scores.csv"

# Four-signal recommendation weights
REC_WEIGHTS = {
    "content_score": float(os.getenv("W_CONTENT", 0.30)),
    "trending_score": float(os.getenv("W_TRENDING", 0.20)),
    "random_score": float(os.getenv("W_RANDOM", 0.10)),
    "collaborative_score": float(os.getenv("W_COLLABORATIVE", 0.40)),
}

from typing import Optional

def full_url(path: Optional[str]) -> Optional[str]:
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
