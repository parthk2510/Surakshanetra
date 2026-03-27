"""
UPI Community Detection Cache
==============================
In-memory cache for community detection results to avoid redundant computation.
Keyed by hash of (sorted node IDs + edge pairs + algorithm + resolution).
TTL-based expiration (default 300s).
"""

import hashlib
import json
import time
import threading
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger('upi_community_cache')


class CommunityDetectionCache:
    """Thread-safe in-memory cache for community detection results."""

    def __init__(self, ttl: int = 300):
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._ttl = ttl

    @staticmethod
    def _make_key(graph_data: Dict[str, Any], algorithm: str, resolution: float) -> str:
        """Create a deterministic cache key from graph data + params."""
        node_ids = sorted(n.get('id', '') for n in graph_data.get('nodes', []))
        edge_pairs = sorted(
            f"{e.get('source','')}->{e.get('target','')}"
            for e in graph_data.get('edges', [])
        )
        raw = json.dumps({
            'nodes': node_ids,
            'edges': edge_pairs,
            'algorithm': algorithm,
            'resolution': round(resolution, 4),
        }, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()

    def get(self, graph_data: Dict[str, Any], algorithm: str, resolution: float) -> Optional[Dict[str, Any]]:
        """Return cached result or None if miss / expired."""
        key = self._make_key(graph_data, algorithm, resolution)
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            if time.time() - entry['ts'] > self._ttl:
                del self._cache[key]
                return None
            logger.debug(f"Cache hit: {algorithm} res={resolution}")
            return entry['result']

    def put(self, graph_data: Dict[str, Any], algorithm: str, resolution: float, result: Dict[str, Any]):
        """Store a result in the cache."""
        key = self._make_key(graph_data, algorithm, resolution)
        with self._lock:
            self._cache[key] = {'result': result, 'ts': time.time()}
        logger.debug(f"Cached: {algorithm} res={resolution}")

    def clear(self):
        """Clear all cached entries."""
        with self._lock:
            self._cache.clear()

    def size(self) -> int:
        with self._lock:
            return len(self._cache)


# Singleton instance
community_cache = CommunityDetectionCache(ttl=300)
