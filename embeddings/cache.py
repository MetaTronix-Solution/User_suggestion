import gc
import hashlib

import numpy as np
from sentence_transformers import SentenceTransformer

EMBED_DIM      = 384
EMBED_CACHE_MAX = 2000

_EMBED_CACHE: dict[str, np.ndarray] = {}


def _key(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()


def get_embed(text: str, model: SentenceTransformer) -> np.ndarray:
    """Return cached embedding or encode and store it."""
    if not text.strip():
        return np.zeros(EMBED_DIM, dtype=np.float32)
    k = _key(text)
    if k not in _EMBED_CACHE:
        if len(_EMBED_CACHE) >= EMBED_CACHE_MAX:
            # Evict oldest 10 %
            for old_key in list(_EMBED_CACHE.keys())[: EMBED_CACHE_MAX // 10]:
                del _EMBED_CACHE[old_key]
        _EMBED_CACHE[k] = model.encode(text, show_progress_bar=False)
    return _EMBED_CACHE[k]


def batch_populate(texts: list[str], model: SentenceTransformer) -> None:
    """Encode only uncached texts in a single batched forward pass."""
    uncached = [t for t in texts if t.strip() and _key(t) not in _EMBED_CACHE]
    if not uncached:
        return
    new_embeds = model.encode(uncached, batch_size=32, show_progress_bar=False)
    for t, emb in zip(uncached, new_embeds):
        k = _key(t)
        if len(_EMBED_CACHE) < EMBED_CACHE_MAX:
            _EMBED_CACHE[k] = emb


def clear() -> int:
    """Flush the entire cache. Returns number of entries cleared."""
    count = len(_EMBED_CACHE)
    _EMBED_CACHE.clear()
    gc.collect()
    return count


def size() -> int:
    return len(_EMBED_CACHE)