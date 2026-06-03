"""
ContextOS cache_layer.py — LRU context response cache.

Caches /context endpoint responses to avoid re-embedding identical queries.
Keyed by hash(query + project + max_tokens). Invalidated on context index.
Thread-safe via threading.Lock.
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Optional

from contextos.schema import ContextResponse

logger = logging.getLogger(__name__)

DEFAULT_MAX_SIZE  = 50
DEFAULT_TTL_SECS  = 300   # 5 minutes


class ContextCache:
    """
    Thread-safe LRU cache for ContextResponse objects.
    Entries expire after ttl_seconds regardless of access.
    """

    def __init__(self, max_size: int = DEFAULT_MAX_SIZE, ttl_seconds: int = DEFAULT_TTL_SECS):
        self.max_size   = max_size
        self.ttl_seconds = ttl_seconds
        self._store: OrderedDict[str, tuple[ContextResponse, float]] = OrderedDict()
        self._lock  = threading.Lock()
        self._hits   = 0
        self._misses = 0

    # ------------------------------------------------------------------
    # Key generation
    # ------------------------------------------------------------------

    @staticmethod
    def make_key(query: str, project: Optional[str], max_tokens: int) -> str:
        payload = json.dumps(
            {"q": query.lower().strip(), "p": project or "", "t": max_tokens},
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def get(self, key: str) -> Optional[ContextResponse]:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self._misses += 1
                return None

            response, stored_at = entry
            age = time.time() - stored_at

            if age > self.ttl_seconds:
                del self._store[key]
                self._misses += 1
                return None

            # LRU: move to end
            self._store.move_to_end(key)
            self._hits += 1
            return response

    def set(self, key: str, response: ContextResponse) -> None:
        with self._lock:
            if key in self._store:
                self._store.move_to_end(key)
            self._store[key] = (response, time.time())

            # Evict oldest if over capacity
            while len(self._store) > self.max_size:
                self._store.popitem(last=False)

    def invalidate(self) -> int:
        """Clear all entries. Called after context index. Returns count cleared."""
        with self._lock:
            count = len(self._store)
            self._store.clear()
            logger.info("Context cache invalidated: %d entries cleared", count)
            return count

    def stats(self) -> dict:
        with self._lock:
            total = self._hits + self._misses
            hit_rate = round(self._hits / total * 100, 1) if total > 0 else 0.0
            # Count non-expired entries
            now = time.time()
            live = sum(1 for _, (_, ts) in self._store.items()
                       if now - ts <= self.ttl_seconds)
            return {
                "hits":         self._hits,
                "misses":       self._misses,
                "hit_rate_pct": hit_rate,
                "size":         live,
                "max_size":     self.max_size,
                "ttl_seconds":  self.ttl_seconds,
            }

    def __len__(self) -> int:
        with self._lock:
            return len(self._store)


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------

_cache: Optional[ContextCache] = None


def get_cache(max_size: int = DEFAULT_MAX_SIZE, ttl_seconds: int = DEFAULT_TTL_SECS) -> ContextCache:
    global _cache
    if _cache is None:
        _cache = ContextCache(max_size=max_size, ttl_seconds=ttl_seconds)
    return _cache


def invalidate_cache() -> int:
    """Invalidate the global cache. Call after index runs."""
    if _cache is not None:
        return _cache.invalidate()
    return 0
