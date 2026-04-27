import gc
import os
from contextlib import asynccontextmanager
from typing import Optional

from sentence_transformers import SentenceTransformer

from embeddings.cache import clear as clear_embed_cache
from utils.helpers import _get_ram_mb

MODEL_CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "models")
MODEL_NAME = os.getenv(
    "EMBED_MODEL",
    "sentence-transformers/paraphrase-MiniLM-L3-v2"
)

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

_MODEL: Optional[SentenceTransformer] = None


# 
# CORE LOADER (USED BY BOTH FASTAPI + CLI)
# 
def load_model() -> SentenceTransformer:
    global _MODEL

    if _MODEL is None:
        print(f"[model] Loading SentenceTransformer: {MODEL_NAME}")
        os.makedirs(MODEL_CACHE_DIR, exist_ok=True)

        _MODEL = SentenceTransformer(
            MODEL_NAME,
            cache_folder=MODEL_CACHE_DIR
        ).to("cpu")

        # warmup
        _MODEL.encode("warmup", show_progress_bar=False)

        gc.collect()
        print(f"[model] Ready. RAM ~{_get_ram_mb():.0f}MB")

    return _MODEL


# 
# FASTAPI LIFESPAN (USES SAME LOADER)
# 
@asynccontextmanager
async def lifespan(app):
    load_model()
    yield
    print("[shutdown] Cleaning up.")
    clear_embed_cache()


# 
# OPTIONAL STRICT ACCESS (ONLY IF YOU WANT SAFETY)
# 
def get_model() -> SentenceTransformer:
    return load_model()
