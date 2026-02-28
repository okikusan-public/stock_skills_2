"""Tests for in-memory LRU cache (KIK-531)."""

import time
import threading

import pytest

from src.data.yahoo_client._memory_cache import MemoryCache, clear_memory_cache


# ---------------------------------------------------------------------------
# Basic get / set
# ---------------------------------------------------------------------------

class TestMemoryCacheBasic:
    def test_get_returns_none_for_missing_key(self):
        cache = MemoryCache()
        assert cache.get("nonexistent") is None

    def test_set_and_get(self):
        cache = MemoryCache()
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

    def test_overwrite_existing_key(self):
        cache = MemoryCache()
        cache.set("k", "old")
        cache.set("k", "new")
        assert cache.get("k") == "new"

    def test_stores_various_types(self):
        cache = MemoryCache()
        cache.set("int", 42)
        cache.set("list", [1, 2, 3])
        cache.set("dict", {"a": 1})
        assert cache.get("int") == 42
        assert cache.get("list") == [1, 2, 3]
        assert cache.get("dict") == {"a": 1}


# ---------------------------------------------------------------------------
# TTL expiration
# ---------------------------------------------------------------------------

class TestMemoryCacheTTL:
    def test_expired_entry_returns_none(self):
        cache = MemoryCache(ttl_seconds=0.05)
        cache.set("k", "v")
        assert cache.get("k") == "v"
        time.sleep(0.1)
        assert cache.get("k") is None

    def test_non_expired_entry_returns_value(self):
        cache = MemoryCache(ttl_seconds=10)
        cache.set("k", "v")
        assert cache.get("k") == "v"

    def test_zero_ttl_disables_cache(self):
        cache = MemoryCache(ttl_seconds=0)
        cache.set("k", "v")
        assert cache.get("k") is None


# ---------------------------------------------------------------------------
# LRU eviction
# ---------------------------------------------------------------------------

class TestMemoryCacheLRU:
    def test_evicts_oldest_when_full(self):
        cache = MemoryCache(maxsize=2)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)  # should evict "a"
        assert cache.get("a") is None
        assert cache.get("b") == 2
        assert cache.get("c") == 3

    def test_get_refreshes_lru_order(self):
        cache = MemoryCache(maxsize=2)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.get("a")     # refresh "a" → now "b" is oldest
        cache.set("c", 3)  # should evict "b"
        assert cache.get("a") == 1
        assert cache.get("b") is None
        assert cache.get("c") == 3


# ---------------------------------------------------------------------------
# Clear and stats
# ---------------------------------------------------------------------------

class TestMemoryCacheClearStats:
    def test_clear_empties_cache(self):
        cache = MemoryCache()
        cache.set("a", 1)
        cache.set("b", 2)
        cache.clear()
        assert cache.get("a") is None
        assert cache.get("b") is None

    def test_stats_tracks_hits_and_misses(self):
        cache = MemoryCache()
        cache.set("a", 1)
        cache.get("a")       # hit
        cache.get("missing")  # miss
        s = cache.stats()
        assert s["hits"] == 1
        assert s["misses"] == 1
        assert s["size"] == 1

    def test_clear_resets_stats(self):
        cache = MemoryCache()
        cache.set("a", 1)
        cache.get("a")
        cache.clear()
        s = cache.stats()
        assert s["hits"] == 0
        assert s["misses"] == 0
        assert s["size"] == 0


# ---------------------------------------------------------------------------
# Thread safety
# ---------------------------------------------------------------------------

class TestMemoryCacheThreadSafety:
    def test_concurrent_set_and_get(self):
        cache = MemoryCache(maxsize=1000, ttl_seconds=10)
        errors: list[str] = []

        def writer(start: int):
            for i in range(100):
                cache.set(f"key-{start + i}", start + i)

        def reader(start: int):
            for i in range(100):
                val = cache.get(f"key-{start + i}")
                if val is not None and val != start + i:
                    errors.append(f"Expected {start + i}, got {val}")

        threads = []
        for t in range(5):
            threads.append(threading.Thread(target=writer, args=(t * 100,)))
            threads.append(threading.Thread(target=reader, args=(t * 100,)))

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Thread safety errors: {errors}"


# ---------------------------------------------------------------------------
# clear_memory_cache helper
# ---------------------------------------------------------------------------

class TestClearMemoryCache:
    def test_clears_both_singletons(self):
        from src.data.yahoo_client._memory_cache import (
            price_history_cache,
            stock_detail_cache,
        )
        price_history_cache.set("test", "ph")
        stock_detail_cache.set("test", "sd")
        clear_memory_cache()
        assert price_history_cache.get("test") is None
        assert stock_detail_cache.get("test") is None
