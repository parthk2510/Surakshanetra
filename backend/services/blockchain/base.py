"""
base.py
``BaseFetcher`` – glues together the HTTP client, Tor layer, session factory,
coordinator, and configuration into a single coherent object that all concrete
mixins inherit from.

Concrete fetcher class::

    class BlockchainComFetcher(
        AddressMixin, TransactionMixin, BlockMixin, BaseFetcher
    ): ...

Python's MRO guarantees that ``BaseFetcher.__init__`` is called last, which
means all mixin methods can safely access ``self.api``, ``self.coordinator``,
``self.config``, and ``self.tor_layer`` without additional guards.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

from .client import BaseAPIClient
from .config import FetcherConfig
from .constant import DEFAULT_DATA_DIR
from .coordinator import MultiAddressCoordinator
from .session import create_session
from .tor_layer import TorNetworkLayer

__all__ = ["BaseFetcher"]

log = logging.getLogger(__name__)


class BaseFetcher:
    """Infrastructure base for ``BlockchainComFetcher``.

    Sets up:

    * ``self.config``       – :class:`FetcherConfig` (with sane defaults)
    * ``self.api``          – :class:`BaseAPIClient` (HTTP + cache + rate-limit)
    * ``self.coordinator``  – :class:`MultiAddressCoordinator` (address graph)
    * ``self.tor_layer``    – :class:`TorNetworkLayer` (or ``None``)
    * ``self.data_dir``     – :class:`pathlib.Path` for graph file output
    """

    def __init__(self, config: Optional[FetcherConfig] = None) -> None:
        self.config = config or FetcherConfig()

        # --- session ---------------------------------------------------
        session = create_session(
            max_retries=self.config.max_retries,
            backoff_factor=self.config.backoff_factor,
            timeout=self.config.timeout,
        )

        # --- Tor layer -------------------------------------------------
        self.tor_layer: Optional[TorNetworkLayer] = None
        self._tor_auto_enabled: bool = False
        if self.config.use_tor:
            self._activate_tor()

        # --- HTTP client -----------------------------------------------
        self.api = BaseAPIClient(
            session=session,
            rate_limit_s=self.config.rate_limit_s,
            timeout=self.config.timeout,
            tor_layer=self.tor_layer,
            cache_enabled=self.config.cache_enabled,
            cache_ttl=self.config.cache_ttl,
            max_cache_size=self.config.max_cache_size,
            tor_renew_per_request=self.config.tor_renew_per_request,
        )

        # --- data directory --------------------------------------------
        self.data_dir: Path = self.config.data_dir or DEFAULT_DATA_DIR
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # --- address-cluster coordinator --------------------------------
        self.coordinator = MultiAddressCoordinator(
            max_workers=self.config.concurrent_requests
        )

        log.info(
            "BaseFetcher initialised – tor=%s rate_limit=%.2fs workers=%d",
            bool(self.tor_layer),
            self.config.rate_limit_s,
            self.config.concurrent_requests,
        )

    # ------------------------------------------------------------------ #
    # Tor management
    # ------------------------------------------------------------------ #

    def _activate_tor(self) -> None:
        """Instantiate and activate the Tor network layer."""
        self.tor_layer = TorNetworkLayer(
            socks_proxy=self.config.tor_socks_proxy,
            control_host=self.config.tor_control_host,
            control_port=self.config.tor_control_port,
            auth_password=self.config.tor_auth_password,
            cookie_auth=self.config.tor_cookie_auth,
            data_directory=self.config.tor_data_directory,
            min_renew_interval_s=self.config.tor_min_renew_interval_s,
        )
        log.info("Tor layer activated – proxy=%s", self.config.tor_socks_proxy)

    def _enable_tor_fallback(self) -> bool:
        """Lazily activate Tor as a rate-limit fallback.

        Returns ``True`` if the Tor layer was newly activated; ``False`` if
        it was already active (nothing to do) or if activation failed.
        """
        if self.tor_layer is not None:
            return False
        try:
            self._activate_tor()
            # Wire the newly created layer into the existing API client
            self.api._tor_layer = self.tor_layer
            self._tor_auto_enabled = True
            log.warning(
                "Tor auto-enabled as rate-limit fallback via %s",
                self.config.tor_socks_proxy,
            )
            return True
        except Exception as exc:
            log.error("Failed to auto-enable Tor: %s", exc)
            return False

    def get_current_ip(self) -> str:
        """Return the current exit IP (via Tor) or ``"Tor disabled"``."""
        return self.tor_layer.get_current_ip() if self.tor_layer else "Tor disabled"

    # ------------------------------------------------------------------ #
    # Cache pass-through
    # ------------------------------------------------------------------ #

    def clear_cache(self) -> None:
        """Clear the in-memory HTTP response cache."""
        self.api.clear_cache()

    def get_cache_stats(self):
        """Return cache utilisation stats from the underlying API client."""
        return self.api.get_cache_stats()

    # ------------------------------------------------------------------ #
    # Address validation helpers (used by mixins)
    # ------------------------------------------------------------------ #

    @staticmethod
    def _safe_address_prefix(address: str, *, length: int = 12) -> str:
        """Return a safe log-friendly prefix of *address* (never raises)."""
        return address[:length] if address else "<empty>"

    @staticmethod
    def _make_graph_filename(address: str, *, prefix: str = "graph_") -> str:
        """Build a safe graph JSON filename from *address*."""
        safe = re.sub(r"[^A-Za-z0-9_\-]", "_", address)
        if address.startswith(("1", "3", "bc1")):
            prefix = "btc_graph_"
        elif address.startswith("0x") and len(address) == 42:
            prefix = "eth_graph_"
        return f"{prefix}{safe[:20]}.json"
