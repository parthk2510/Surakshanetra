"""
config.py
``FetcherConfig`` dataclass – central configuration object for the
Blockchain.com API client.

All fields have production-safe defaults so callers can construct a config
with ``FetcherConfig()`` and override only what they need.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Union

__all__ = ["FetcherConfig"]


@dataclass
class FetcherConfig:
    """Immutable-ish configuration bag for :class:`BlockchainComFetcher`.

    Attributes
    ----------
    rate_limit_s:
        Minimum seconds to wait between consecutive outbound requests.
    timeout:
        Socket connect-and-read timeout in seconds for every HTTP call.
    max_retries:
        Total number of automatic retries on transient server errors (5xx).
    backoff_factor:
        Exponential-backoff multiplier passed to ``urllib3.Retry``.
    cache_enabled:
        Whether to use an in-memory LRU response cache.
    cache_ttl:
        Maximum age of a cache entry in seconds.
    max_cache_size:
        Maximum number of entries to keep in the cache at one time.
    data_dir:
        Override the default data/graph directory for saved graph files.
    concurrent_requests:
        Maximum concurrent threads used in multi-address fetch helpers.
    use_tor:
        Route all requests through the local Tor SOCKS proxy when ``True``.
    tor_socks_proxy:
        SOCKS5 proxy URL that Tor is listening on.
    tor_control_host:
        Hostname of the Tor control port (for NEWNYM circuit rotation).
    tor_control_port:
        Port number for the Tor control interface.
    tor_auth_password:
        Plain-text password for the Tor control port (``HashedControlPassword``
        must be set in ``torrc``).  Ignored if ``tor_cookie_auth`` succeeds.
    tor_cookie_auth:
        When ``True``, attempt cookie authentication before password auth.
    tor_data_directory:
        Path to the Tor data directory that contains ``control_auth_cookie``.
    tor_renew_per_request:
        Rotate the Tor circuit before every single request (use sparingly).
    tor_min_renew_interval_s:
        Minimum seconds that must elapse between ``SIGNAL NEWNYM`` commands.
    """

    # ------------------------------------------------------------------ #
    # HTTP / rate limiting
    # ------------------------------------------------------------------ #
    rate_limit_s: float = 0.2
    timeout: int = 20
    max_retries: int = 3
    backoff_factor: float = 0.3

    # ------------------------------------------------------------------ #
    # In-memory cache
    # ------------------------------------------------------------------ #
    cache_enabled: bool = True
    cache_ttl: int = 300        # 5 minutes
    max_cache_size: int = 1000

    # ------------------------------------------------------------------ #
    # Persistence
    # ------------------------------------------------------------------ #
    data_dir: Optional[Path] = None

    # ------------------------------------------------------------------ #
    # Concurrency
    # ------------------------------------------------------------------ #
    concurrent_requests: int = 5

    # ------------------------------------------------------------------ #
    # Tor anonymity layer
    # ------------------------------------------------------------------ #
    use_tor: bool = False
    tor_socks_proxy: str = "socks5h://127.0.0.1:9050"
    tor_control_host: str = "127.0.0.1"
    tor_control_port: int = 9051
    tor_auth_password: Optional[str] = None
    tor_cookie_auth: bool = True
    tor_data_directory: Optional[Union[str, Path]] = None
    tor_renew_per_request: bool = False
    tor_min_renew_interval_s: float = 10.0

    # ------------------------------------------------------------------ #
    # Factory helpers
    # ------------------------------------------------------------------ #
    @classmethod
    def from_dict(cls, data: dict) -> "FetcherConfig":
        """Instantiate from a plain dictionary (e.g. loaded from JSON).

        Unknown keys are silently ignored so that future config files remain
        backwards-compatible with older code.
        """
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        filtered = {k: v for k, v in data.items() if k in known}
        # Convert data_dir / tor_data_directory to Path when present
        if "data_dir" in filtered and filtered["data_dir"] is not None:
            filtered["data_dir"] = Path(filtered["data_dir"])
        if "tor_data_directory" in filtered and filtered["tor_data_directory"] is not None:
            filtered["tor_data_directory"] = Path(filtered["tor_data_directory"])
        return cls(**filtered)

    @classmethod
    def from_json_file(cls, path: Union[str, Path]) -> "FetcherConfig":
        """Load configuration from a JSON file on disk."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")
        with open(path, "r", encoding="utf-8") as fh:
            return cls.from_dict(json.load(fh))
