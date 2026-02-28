"""Thread-safe in-memory LRU cache with TTL (KIK-531).

Provides short-lived caching (default 5 min) to avoid redundant API calls
within a single screening session.  Two module-level singletons are exposed:

    price_history_cache  – keyed by "SYMBOL:period"
    stock_detail_cache   – keyed by symbol

Environment variable ``MEMORY_CACHE_TTL`` (seconds) overrides the default TTL.
Set it to ``0`` to disable in-memory caching entirely.
"""

import os
import threading
import time
from collections import OrderedDict
from typing import Any, Optional


class MemoryCache:
    """Thread-safe in-memory LRU cache with TTL."""

    def __init__(self, maxsize: int = 128, ttl_seconds: float = 300):
        self._cache: OrderedDict[str, tuple[Any, float]] = OrderedDict()
        self._lock = threading.Lock()
        self._maxsize = maxsize
        self._ttl = ttl_seconds
        self._hits = 0
        self._misses = 0

    # -- public API --

    def get(self, key: str) -> Optional[Any]:
        """Return cached value or None if missing / expired."""
        if self._ttl <= 0:
            self._misses += 1
            return None
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._misses += 1
                return None
            value, expiry = entry
            if time.monotonic() > expiry:
                # lazy eviction
                del self._cache[key]
                self._misses += 1
                return None
            # LRU: move to end
            self._cache.move_to_end(key)
            self._hits += 1
            return value

    def set(self, key: str, value: Any) -> None:
        """Store *value* under *key* with current TTL."""
        if self._ttl <= 0:
            return
        with self._lock:
            expiry = time.monotonic() + self._ttl
            if key in self._cache:
                self._cache.move_to_end(key)
                self._cache[key] = (value, expiry)
            else:
                self._cache[key] = (value, expiry)
                if len(self._cache) > self._maxsize:
                    self._cache.popitem(last=False)

    def clear(self) -> None:
        """Drop all entries and reset stats."""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0

    def stats(self) -> dict:
        """Return hit/miss/size statistics."""
        with self._lock:
            return {
                "hits": self._hits,
                "misses": self._misses,
                "size": len(self._cache),
                "maxsize": self._maxsize,
                "ttl_seconds": self._ttl,
            }


# ---------------------------------------------------------------------------
# Module-level singletons
# ---------------------------------------------------------------------------

_env_ttl = os.environ.get("MEMORY_CACHE_TTL")
_default_ttl = float(_env_ttl) if _env_ttl is not None else 300.0

price_history_cache = MemoryCache(maxsize=256, ttl_seconds=_default_ttl)
stock_detail_cache = MemoryCache(maxsize=256, ttl_seconds=_default_ttl)


def clear_memory_cache() -> None:
    """Clear both singleton caches (useful for tests)."""
    price_history_cache.clear()
    stock_detail_cache.clear()
