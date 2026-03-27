"""
address.py
``AddressMixin`` – all methods that deal with Bitcoin addresses.

Mixed into ``BlockchainComFetcher`` via multiple inheritance.  Relies on
``self.api`` (:class:`client.BaseAPIClient`) and ``self.coordinator``
(:class:`coordinator.MultiAddressCoordinator`) being present on the instance.
"""
from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Tuple, Union

from .constant import (
    BLOCKCHAIN_BASE,
    RAWADDR_DEFAULT_LIMIT,
    RAWADDR_PAGE_HARD_LIMIT,
    UNSPENT_DEFAULT_LIMIT,
    UNSPENT_HARD_LIMIT,
)
from .exceptions import (
    BlockchainAPIError,
    InvalidParameterError,
    RateLimitError,
)
from .models import AddressInfo, UnspentOutput
from .utils import validate_address, validate_addresses

__all__ = ["AddressMixin"]

log = logging.getLogger(__name__)


class AddressMixin:
    """Bitcoin-address–related methods for ``BlockchainComFetcher``."""

    # ------------------------------------------------------------------ #
    # Single address – raw data
    # ------------------------------------------------------------------ #

    def fetch_address(
        self,
        address: str,
        limit: int = RAWADDR_DEFAULT_LIMIT,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """Fetch one page of address data from ``/rawaddr``.

        Parameters
        ----------
        address:
            Bitcoin address (P2PKH, P2SH, Bech32, or xpub).
        limit:
            Transactions to include in this page (API hard-cap: 50).
        offset:
            Skip the first *offset* transactions (for pagination).

        Returns
        -------
        dict
            Raw API JSON payload including ``address``, ``hash160``,
            ``n_tx``, ``total_received``, ``total_sent``,
            ``final_balance``, and ``txs``.
        """
        validate_address(address)
        actual_limit = min(limit, RAWADDR_PAGE_HARD_LIMIT)
        if offset < 0:
            raise InvalidParameterError(f"Offset must be non-negative, got {offset}")
        url = f"{BLOCKCHAIN_BASE}/rawaddr/{address}"
        params: Dict[str, Any] = {"limit": actual_limit, "offset": offset}
        log.debug("fetch_address addr=%s limit=%d offset=%d", address[:12], actual_limit, offset)
        return self.api._get(url, params=params)  # type: ignore[attr-defined]

    def fetch_all_transactions(
        self,
        address: str,
        max_limit: int = 1000,
        rate_limit_delay: float = 0.25,
    ) -> Dict[str, Any]:
        """Paginate through ``/rawaddr`` to collect *up to* *max_limit* txs.

        Parameters
        ----------
        address:
            Bitcoin address to query.
        max_limit:
            Cap on total transactions to fetch (default 1000, max 10000).
        rate_limit_delay:
            Seconds to sleep between batch requests.

        Returns
        -------
        dict
            Combined payload with ``txs`` list of *all* fetched transactions
            plus a ``pagination_info`` sub-dict with progress stats.
        """
        validate_address(address)
        safe_max = min(max(max_limit, 1), 10_000)
        log.info("fetch_all_transactions addr=%s max_limit=%d", address[:12], safe_max)

        try:
            initial = self.fetch_address(address, limit=RAWADDR_PAGE_HARD_LIMIT, offset=0)
        except Exception as exc:
            log.error("fetch_all_transactions initial fetch failed for %s: %s", address, exc)
            raise

        total_on_chain: int = initial.get("n_tx", 0)
        all_txs: List[Dict] = list(initial.get("txs", []))
        target = min(safe_max, total_on_chain)

        log.info(
            "fetch_all_transactions addr=%s total_on_chain=%d target=%d",
            address[:12], total_on_chain, target,
        )

        offset = RAWADDR_PAGE_HARD_LIMIT
        batch_count = 1
        errors = 0
        max_errors = 5

        while len(all_txs) < target and offset < total_on_chain:
            time.sleep(rate_limit_delay)
            try:
                batch = self.fetch_address(address, limit=RAWADDR_PAGE_HARD_LIMIT, offset=offset)
                new_txs = batch.get("txs", [])
                if not new_txs:
                    log.info("No more txs at offset %d, stopping pagination", offset)
                    break
                all_txs.extend(new_txs)
                batch_count += 1
                offset += RAWADDR_PAGE_HARD_LIMIT
                if batch_count % 5 == 0:
                    log.info(
                        "Pagination progress addr=%s fetched=%d/%d batch=%d",
                        address[:12], len(all_txs), target, batch_count,
                    )
                if len(new_txs) < RAWADDR_PAGE_HARD_LIMIT:
                    log.info("Partial batch (%d txs), pagination complete", len(new_txs))
                    break
            except RateLimitError:
                errors += 1
                log.warning("Rate limit at offset %d (%d/%d errors)", offset, errors, max_errors)
                time.sleep(2.0)
                if errors >= max_errors:
                    log.error("Too many rate-limit errors, stopping at %d txs", len(all_txs))
                    break
            except Exception as exc:
                errors += 1
                log.warning("Batch error at offset %d: %s (%d/%d)", offset, exc, errors, max_errors)
                if errors >= max_errors:
                    log.error("Too many errors, stopping at %d txs", len(all_txs))
                    break
                time.sleep(1.0)

        result = {
            **{k: v for k, v in initial.items() if k != "txs"},
            "txs": all_txs[:safe_max],
            "pagination_info": {
                "total_on_chain": total_on_chain,
                "fetched_count": len(all_txs),
                "batches_fetched": batch_count,
                "errors_encountered": errors,
                "max_limit_requested": safe_max,
            },
        }
        log.info(
            "fetch_all_transactions done addr=%s fetched=%d batches=%d",
            address[:12], len(all_txs), batch_count,
        )
        return result

    # ------------------------------------------------------------------ #
    # Multiple addresses
    # ------------------------------------------------------------------ #

    def fetch_multiple_addresses(
        self,
        addresses: List[str],
        limit_per_address: int = 50,
        fetch_all: bool = False,
    ) -> Dict[str, Dict[str, Any]]:
        """Concurrently fetch data for multiple addresses.

        Parameters
        ----------
        addresses:
            List of Bitcoin addresses.
        limit_per_address:
            Transactions per address (when *fetch_all* is ``False``).
        fetch_all:
            When ``True`` paginate each address using :meth:`fetch_all_transactions`.

        Returns
        -------
        dict
            Mapping ``{address: payload}``; errors are stored as
            ``{address: {"error": "…"}}`` so partial failures don't abort
            the entire batch.
        """
        validate_addresses(addresses)
        results: Dict[str, Dict[str, Any]] = {}

        def _fetch_one(addr: str) -> Tuple[str, Dict[str, Any]]:
            try:
                data = (
                    self.fetch_all_transactions(addr)  # type: ignore[attr-defined]
                    if fetch_all
                    else self.fetch_address(addr, limit=min(limit_per_address, RAWADDR_PAGE_HARD_LIMIT))
                )
                self._extract_address_relationships(addr, data)  # type: ignore[attr-defined]
                return addr, data
            except Exception as exc:
                log.error("fetch_multiple_addresses failed for %s: %s", addr[:12], exc)
                return addr, {"error": str(exc)}

        max_workers = getattr(self, "config", None)
        max_workers = getattr(max_workers, "concurrent_requests", 5) if max_workers else 5

        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = {ex.submit(_fetch_one, addr): addr for addr in addresses}
            for future in as_completed(futures):
                addr, data = future.result()
                results[addr] = data

        log.info(
            "fetch_multiple_addresses completed %d/%d",
            sum(1 for v in results.values() if "error" not in v),
            len(addresses),
        )
        return results

    def _extract_address_relationships(self, address: str, data: Dict[str, Any]) -> None:
        """Populate ``self.coordinator`` with address-cluster metadata from *data*."""
        coordinator = getattr(self, "coordinator", None)  # type: ignore[attr-defined]
        if coordinator is None:
            return
        coordinator.address_metadata[address] = {
            "balance": data.get("final_balance", 0),
            "tx_count": data.get("n_tx", 0),
            "total_received": data.get("total_received", 0),
            "total_sent": data.get("total_sent", 0),
        }
        for tx in data.get("txs", []):
            tx_hash = tx.get("hash")
            if not tx_hash:
                continue
            for inp in tx.get("inputs", []):
                addr = (inp.get("prev_out") or {}).get("addr")
                if addr and addr != address:
                    coordinator.add_address_relationship(address, addr, tx_hash)
            for out in tx.get("out", []):
                addr = out.get("addr")
                if addr and addr != address:
                    coordinator.add_address_relationship(address, addr, tx_hash)

    # ------------------------------------------------------------------ #
    # Balance
    # ------------------------------------------------------------------ #

    def fetch_balance(
        self, addresses: Union[str, List[str]]
    ) -> Dict[str, Any]:
        """Fetch balances for one or more addresses from ``/balance``.

        Parameters
        ----------
        addresses:
            Single address string or a list of addresses.

        Returns
        -------
        dict
            Mapping ``{address: {final_balance, n_tx, total_received}}``.
        """
        if isinstance(addresses, str):
            addresses = [addresses]
        validate_addresses(addresses)
        url = f"{BLOCKCHAIN_BASE}/balance"
        params = {"active": "|".join(addresses)}
        return self.api._get(url, params=params)  # type: ignore[attr-defined]

    def get_address_balance(self, address: str) -> int:
        """Return the ``final_balance`` (satoshis) for a single address."""
        data = self.fetch_balance(address)
        return data.get(address, {}).get("final_balance", 0)

    # ------------------------------------------------------------------ #
    # Unspent outputs (UTXOs)
    # ------------------------------------------------------------------ #

    def fetch_unspent(
        self,
        addresses: Union[str, List[str]],
        limit: int = UNSPENT_DEFAULT_LIMIT,
        confirmations: int = 0,
    ) -> Dict[str, Any]:
        """Fetch unspent outputs from ``/unspent``.

        Parameters
        ----------
        addresses:
            Single address string or list.
        limit:
            Maximum UTXOs (1–1000).
        confirmations:
            Minimum number of confirmations required.

        Returns
        -------
        dict
            ``{"unspent_outputs": [utxo, …]}``.
        """
        if isinstance(addresses, str):
            addresses = [addresses]
        validate_addresses(addresses)
        if not 1 <= limit <= UNSPENT_HARD_LIMIT:
            raise InvalidParameterError(
                f"Limit must be between 1 and {UNSPENT_HARD_LIMIT}, got {limit}"
            )
        url = f"{BLOCKCHAIN_BASE}/unspent"
        params: Dict[str, Any] = {
            "active": "|".join(addresses),
            "limit": limit,
            "confirmations": confirmations,
        }
        try:
            return self.api._get(url, params=params)  # type: ignore[attr-defined]
        except BlockchainAPIError as exc:
            if "No free outputs" in str(exc):
                return {"unspent_outputs": []}
            raise

    def get_unspent_outputs(self, address: str) -> List[UnspentOutput]:
        """Return UTXOs for *address* as typed :class:`UnspentOutput` objects."""
        data = self.fetch_unspent(address)
        return [
            UnspentOutput(
                tx_hash=u.get("tx_hash", ""),
                tx_hash_big_endian=u.get("tx_hash_big_endian", ""),
                tx_index=u.get("tx_index", 0),
                tx_output_n=u.get("tx_output_n", 0),
                script=u.get("script", ""),
                value=u.get("value", 0),
                value_hex=u.get("value_hex"),
                confirmations=u.get("confirmations"),
                tx_age=u.get("tx_age"),
            )
            for u in data.get("unspent_outputs", [])
        ]

    # ------------------------------------------------------------------ #
    # Multi-address (combined view)
    # ------------------------------------------------------------------ #

    def fetch_multi_address(
        self,
        addresses: List[str],
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """Fetch combined data for multiple addresses via ``/multiaddr``.

        Returns a single JSON view that includes per-address balances and
        recent transactions across all supplied addresses.

        Parameters
        ----------
        addresses:
            List of Bitcoin addresses (or xpub keys).
        limit:
            Transactions to return (API max 100).
        offset:
            Transaction offset for pagination.
        """
        validate_addresses(addresses)
        url = f"{BLOCKCHAIN_BASE}/multiaddr"
        params: Dict[str, Any] = {
            "active": "|".join(addresses),
            "n": min(limit, 100),
            "offset": offset,
        }
        return self.api._get(url, params=params)  # type: ignore[attr-defined]

    def fetch_multi_address_balances(
        self, addresses: List[str]
    ) -> Dict[str, Dict[str, Any]]:
        """Fetch balance-only summary for multiple addresses.

        Returns
        -------
        dict
            Mapping ``{address: {n_tx, total_received, total_sent, final_balance}}``.
        """
        data = self.fetch_multi_address(addresses, limit=1)
        return {
            addr_data.get("address", ""): {
                "n_tx": addr_data.get("n_tx", 0),
                "total_received": addr_data.get("total_received", 0),
                "total_sent": addr_data.get("total_sent", 0),
                "final_balance": addr_data.get("final_balance", 0),
            }
            for addr_data in data.get("addresses", [])
        }

    # ------------------------------------------------------------------ #
    # Address cluster
    # ------------------------------------------------------------------ #

    def fetch_address_cluster(
        self, address: str, max_depth: int = 2
    ) -> Dict[str, Any]:
        """Populate the coordinator and return the address cluster."""
        self.fetch_address(address)  # ensure coordinator is seeded
        return self.coordinator.get_address_cluster(address, max_depth=max_depth)  # type: ignore[attr-defined]

    # ------------------------------------------------------------------ #
    # Typed helpers
    # ------------------------------------------------------------------ #

    def fetch_address_full(
        self, address: str, max_limit: int = 1000
    ) -> AddressInfo:
        """Fetch complete address data and return it as an :class:`AddressInfo`."""
        data = self.fetch_all_transactions(address, max_limit=max_limit)
        return AddressInfo(
            address=data.get("address", address),
            hash160=data.get("hash160", ""),
            n_tx=data.get("n_tx", 0),
            n_unredeemed=data.get("n_unredeemed", 0),
            total_received=data.get("total_received", 0),
            total_sent=data.get("total_sent", 0),
            final_balance=data.get("final_balance", 0),
            transactions=data.get("txs", []),
        )
