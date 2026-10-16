# -*- coding: utf-8 -*-
# Kuasarr
# Project by Ritedt (Fork von https://github.com/rix1337/Quasarr)

"""Thread-safe in-memory search cache.

Radarr/Sonarr poll the same movie/show repeatedly. Serving cached results
cuts follow-up searches from a full multi-scraper run (5-8s) down to ~0ms.
Concept adapted from rix1337/Quasarr SearchCache — Kuasarr uses a
search-level cache (one entry per imdb_id/phrase/mode) rather than
per-source, which is simpler and gives the same benefit for *arr polling
without the per-source lambda-closure pitfalls.
"""

import threading
import time


class SearchCache:
    def __init__(self, max_entries=5000):
        self._lock = threading.Lock()
        self._store = {}  # key -> (value, expiry_ts)
        self._last_cleanup = time.time()
        self._max_entries = max_entries

    @staticmethod
    def make_key(source_initials, mode, imdb_id="", search_phrase="",
                 season="", episode="", mirror=None):
        return (source_initials, mode, imdb_id, search_phrase, season, episode, mirror)

    def get(self, key):
        now = time.time()
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            value, expiry = entry
            if expiry < now:
                self._store.pop(key, None)
                return None
            return value

    def set(self, key, value, ttl):
        now = time.time()
        with self._lock:
            # Opportunistic cleanup every 60s
            if now - self._last_cleanup > 60:
                self._cleanup_locked(now)
            self._store[key] = (value, now + ttl)
            # Safety vent: hard cap on entries
            if len(self._store) > self._max_entries:
                # Drop ~10% oldest-expiring entries
                oldest = sorted(self._store.items(), key=lambda kv: kv[1][1])
                for k, _ in oldest[: len(self._store) // 10]:
                    self._store.pop(k, None)

    def _cleanup_locked(self, now):
        expired = [k for k, (_, exp) in self._store.items() if exp < now]
        for k in expired:
            self._store.pop(k, None)
        self._last_cleanup = now


# Module-level singleton shared across search requests.
search_cache = SearchCache()

# TTLs (seconds)
TTL_SEARCH = 300   # imdb/phrase search
TTL_FEED = 60      # feed
TTL_EMPTY = 30     # empty results — short, avoids retry storms but stays fresh
