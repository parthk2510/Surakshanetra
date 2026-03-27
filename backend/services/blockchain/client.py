"""
client.py
Low-level HTTP client for the Blockchain.com API.

``BaseAPIClient`` wraps a :class:`requests.Session` and provides:

* Rate limiting (per-instance token bucket – floor-style)
* Transparent Tor proxy routing
* On-the-fly Tor circuit rotation (``tor_renew_per_request``)
* In-memory LRU response cache
* Consistent JSON parsing with graceful fallback
* Typed exception mapping (HTTP 4xx → custom exceptions, etc.)
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any, Dict, Optional

import requests

from .exceptions import (
    BlockchainAPIError,
    BlockNotFoundError,
    RateLimitError,
    TransactionNotFoundError,
)
from .tor_layer import TorNetworkLayer

__all__ = ["BaseAPIClient"]

log = logging.getLogger(__name__)


class BaseAPIClient:
    """Thin HTTP wrapper around :class:`requests.Session`.

    Parameters
    ----------
    session:
        A fully configured :class:`requests.Session` (see :mod:`session`).
    rate_limit_s:
        Minimum seconds between consecutive outbound requests.
    timeout:
        Per-request socket timeout in seconds.
    tor_layer:
        Optional :class:`TorNetworkLayer`; if supplied every request is
        routed through the Tor SOCKS proxy.
    cache_enabled:
        Toggle the in-memory LRU response cache.
    cache_ttl:
        Maximum age of a cache entry in seconds.
    max_cache_size:
        Maximum number of cached responses to retain.
    tor_renew_per_request:
        When ``True`` and *tor_layer* is set, attempt a ``SIGNAL NEWNYM``
        before each request (subject to the layer's own cool-down).
    """

    def __init__(
        self,
        session: requests.Session,
        rate_limit_s: float = 0.2,
        timeout: int = 20,
        tor_layer: Optional[TorNetworkLayer] = None,
        cache_enabled: bool = True,
        cache_ttl: int = 300,
        max_cache_size: int = 1000,
        tor_renew_per_request: bool = False,
    ) -> None:
        self._session = session
        self._rate_limit_s = rate_limit_s
        self._timeout = timeout
        self._tor_layer = tor_layer
        self._cache_enabled = cache_enabled
        self._cache_ttl = cache_ttl
        self._max_cache_size = max_cache_size
        self._tor_renew_per_request = tor_renew_per_request

        self._last_request_time: float = 0.0

        # In-memory LRU cache (SHA-1 key → value, oldest-eviction)
        self._cache: Dict[str, Any] = {}
        self._cache_timestamps: Dict[str, float] = {}

    # ------------------------------------------------------------------ #
    # Cache helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _cache_key(url: str, params: Optional[Dict[str, Any]]) -> str:
        raw = f"{url}|{json.dumps(params or {}, sort_keys=True)}"
        return hashlib.sha1(raw.encode()).hexdigest()

    def _cache_get(self, key: str) -> Optional[Any]:
        if not self._cache_enabled or key not in self._cache_timestamps:
            return None
        if time.time() - self._cache_timestamps[key] >= self._cache_ttl:
            # Stale – evict eagerly
            self._cache.pop(key, None)
            self._cache_timestamps.pop(key, None)
            return None
        return self._cache.get(key)

    def _cache_put(self, key: str, value: Any) -> None:
        if not self._cache_enabled:
            return
        if len(self._cache) >= self._max_cache_size:
            oldest = min(self._cache_timestamps, key=self._cache_timestamps.__getitem__)
            self._cache.pop(oldest, None)
            self._cache_timestamps.pop(oldest, None)
        self._cache[key] = value
        self._cache_timestamps[key] = time.time()

    def clear_cache(self) -> None:
        """Flush all cached responses."""
        self._cache.clear()
        self._cache_timestamps.clear()
        log.info("Response cache cleared")

    def get_cache_stats(self) -> Dict[str, Any]:
        """Return current cache utilisation statistics."""
        return {
            "cache_enabled": self._cache_enabled,
            "cache_size": len(self._cache),
            "max_cache_size": self._max_cache_size,
            "cache_ttl": self._cache_ttl,
        }

    # ------------------------------------------------------------------ #
    # Rate limiting
    # ------------------------------------------------------------------ #

    def _rate_limit(self) -> None:
        """Block until the minimum inter-request interval has elapsed."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self._rate_limit_s:
            time.sleep(self._rate_limit_s - elapsed)
        self._last_request_time = time.time()

    # ------------------------------------------------------------------ #
    # Core HTTP method
    # ------------------------------------------------------------------ #

    def _get(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        allow_fallback: bool = False,
        _tor_retry: bool = False,
    ) -> Dict[str, Any]:
        """Perform an HTTP GET and return the parsed JSON body.

        Parameters
        ----------
        url:
            Fully-qualified URL to fetch.
        params:
            Optional query-string parameters.
        allow_fallback:
            When ``True``, non-JSON responses and JSON parse errors return
            ``{"values": [], "status": "fallback", "error": "…"}`` instead
            of raising :exc:`BlockchainAPIError`.
        _tor_retry:
            Internal flag – prevents recursive Tor-fallback loops.

        Returns
        -------
        dict
            Parsed JSON payload.

        Raises
        ------
        :exc:`RateLimitError`
            HTTP 429 and no Tor fallback available / already tried.
        :exc:`TransactionNotFoundError`
            HTTP 404 on a ``/rawtx/…`` endpoint.
        :exc:`BlockNotFoundError`
            HTTP 404 on a ``/rawblock/…`` endpoint.
        :exc:`BlockchainAPIError`
            Any other HTTP error or network-level failure.
        """
        # --- cache lookup ---
        cache_key = self._cache_key(url, params)
        cached = self._cache_get(cache_key)
        if cached is not None:
            log.debug("Cache hit: %s", url)
            return cached

        response: Optional[requests.Response] = None
        try:
            # --- optional Tor rotation ---
            if self._tor_layer and self._tor_renew_per_request:
                self._tor_layer.renew_identity()

            self._rate_limit()

            proxies = self._tor_layer.proxies if self._tor_layer else None
            log.debug("GET %s params=%s tor=%s", url, params, proxies is not None)

            response = self._session.get(
                url,
                params=params,
                timeout=self._timeout,
                proxies=proxies,
            )

            # Log HTTP status
            if response.status_code >= 500:
                log.error("HTTP %d server error: %s", response.status_code, url)
            elif response.status_code >= 400:
                log.warning("HTTP %d client error: %s", response.status_code, url)
            else:
                log.debug("HTTP %d success: %s", response.status_code, url)

            response.raise_for_status()

            # --- validate Content-Type ---
            content_type = response.headers.get("Content-Type", "")
            if "application/json" not in content_type and "text/json" not in content_type:
                log.warning("Unexpected Content-Type '%s' from %s", content_type, url)
                if allow_fallback:
                    return {"values": [], "status": "fallback", "error": "Invalid Content-Type"}
                raise BlockchainAPIError(
                    f"Invalid Content-Type '{content_type}' from {url}. "
                    f"Preview: {response.text[:200]}"
                )

            # --- parse JSON ---
            try:
                data = response.json()
            except json.JSONDecodeError as exc:
                log.error("JSON decode error for %s: %s", url, exc)
                if allow_fallback:
                    return {"values": [], "status": "fallback", "error": str(exc)}
                raise BlockchainAPIError(f"Invalid JSON from {url}: {exc}") from exc

            # --- store in cache ---
            self._cache_put(cache_key, data)
            return data

        except requests.exceptions.HTTPError as exc:
            status_code = getattr(response, "status_code", None) if response is not None else None

            if status_code == 429:
                log.warning("Rate limited (429) at %s", url)
                if not _tor_retry and self._tor_layer is not None:
                    log.info("Retrying %s via Tor after 429", url)
                    time.sleep(2.0)
                    return self._get(url, params=params, allow_fallback=allow_fallback, _tor_retry=True)
                raise RateLimitError(f"Rate limit exceeded for {url}") from exc
            if status_code == 404:
                log.warning("Resource not found: %s", url)
                if "/rawtx/" in url:
                    raise TransactionNotFoundError(
                        f"Transaction not found: {url.rsplit('/', 1)[-1]}"
                    ) from exc
                if "/rawblock/" in url:
                    raise BlockNotFoundError(
                        f"Block not found: {url.rsplit('/', 1)[-1]}"
                    ) from exc
                raise BlockchainAPIError(f"Resource not found: {url}") from exc
            if status_code and status_code >= 500:
                raise BlockchainAPIError(
                    f"Remote server error {status_code} for {url}: {exc}"
                ) from exc
            raise BlockchainAPIError(f"HTTP error {status_code} for {url}: {exc}") from exc

        except requests.exceptions.Timeout as exc:
            log.error("Request timeout: %s", url)
            raise BlockchainAPIError(f"Request timeout for {url}") from exc

        except requests.exceptions.ConnectionError as exc:
            log.error("Connection error: %s", url)
            raise BlockchainAPIError(f"Connection error for {url}") from exc

        except BlockchainAPIError:
            raise  # re-raise without wrapping

        except Exception as exc:
            log.error("Unexpected %s for %s: %s", type(exc).__name__, url, exc)
            raise BlockchainAPIError(f"Unexpected error fetching {url}: {exc}") from exc
