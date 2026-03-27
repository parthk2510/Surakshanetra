"""
block.py
``BlockMixin`` – methods that deal with Bitcoin blocks and network stats.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Union

from .constant import BLOCKCHAIN_BASE, BLOCKCHAIN_CHARTS_BASE
from .exceptions import (
    BlockchainAPIError,
    BlockNotFoundError,
    InvalidParameterError,
)
from .models import BlockInfo, LatestBlock
from .utils import validate_block_hash, validate_block_height

__all__ = ["BlockMixin"]

log = logging.getLogger(__name__)


class BlockMixin:
    """Bitcoin-block and network–related methods for ``BlockchainComFetcher``."""

    # ------------------------------------------------------------------ #
    # Block by hash
    # ------------------------------------------------------------------ #

    def fetch_block(
        self,
        block_hash: str,
        format: str = "json",  # noqa: A002
    ) -> Dict[str, Any]:
        """Fetch a block by hash from ``/rawblock``.

        Parameters
        ----------
        block_hash:
            64-character hexadecimal block hash.
        format:
            ``"json"`` (default) or ``"hex"``.
        """
        validate_block_hash(block_hash)
        url = f"{BLOCKCHAIN_BASE}/rawblock/{block_hash}"
        params: Optional[Dict[str, Any]] = {"format": "hex"} if format == "hex" else None
        return self.api._get(url, params=params)  # type: ignore[attr-defined]

    def get_block(self, block_hash: str) -> BlockInfo:
        """Fetch a block and return it as a typed :class:`BlockInfo`."""
        data = self.fetch_block(block_hash)
        return BlockInfo(
            hash=data.get("hash", block_hash),
            ver=data.get("ver", 0),
            prev_block=data.get("prev_block", ""),
            mrkl_root=data.get("mrkl_root", ""),
            time=data.get("time", 0),
            bits=data.get("bits", 0),
            nonce=data.get("nonce", 0),
            n_tx=data.get("n_tx", 0),
            size=data.get("size", 0),
            block_index=data.get("block_index", 0),
            main_chain=data.get("main_chain", True),
            height=data.get("height", 0),
            received_time=data.get("received_time", 0),
            relayed_by=data.get("relayed_by", ""),
            transactions=data.get("tx", []),
        )

    # ------------------------------------------------------------------ #
    # Block by height
    # ------------------------------------------------------------------ #

    def fetch_block_by_height(self, height: int) -> Dict[str, Any]:
        """Fetch block(s) at a given blockchain height.

        Returns
        -------
        dict
            ``{"blocks": [block_data, …]}``
        """
        validate_block_height(height)
        url = f"{BLOCKCHAIN_BASE}/block-height/{height}"
        return self.api._get(url, params={"format": "json"})  # type: ignore[attr-defined]

    # ------------------------------------------------------------------ #
    # Latest block
    # ------------------------------------------------------------------ #

    def fetch_latest_block(self) -> Dict[str, Any]:
        """Fetch the latest block from ``/latestblock``."""
        return self.api._get(f"{BLOCKCHAIN_BASE}/latestblock")  # type: ignore[attr-defined]

    def get_latest_block(self) -> LatestBlock:
        """Return the latest block as a typed :class:`LatestBlock`."""
        data = self.fetch_latest_block()
        return LatestBlock(
            hash=data.get("hash", ""),
            time=data.get("time", 0),
            block_index=data.get("block_index", 0),
            height=data.get("height", 0),
            tx_indexes=data.get("txIndexes", []),
        )

    def get_current_block_height(self) -> int:
        """Return the current blockchain tip height."""
        return self.get_latest_block().height

    # ------------------------------------------------------------------ #
    # Blocks by day / pool
    # ------------------------------------------------------------------ #

    def fetch_blocks_for_day(self, timestamp_ms: Optional[int] = None) -> Dict[str, Any]:
        """Fetch blocks mined on a specific day.

        Parameters
        ----------
        timestamp_ms:
            Unix timestamp in **milliseconds**; defaults to today.
        """
        if timestamp_ms is None:
            timestamp_ms = int(time.time() * 1000)
        url = f"{BLOCKCHAIN_BASE}/blocks/{timestamp_ms}"
        return self.api._get(url, params={"format": "json"})  # type: ignore[attr-defined]

    def fetch_blocks_for_pool(self, pool_name: str) -> Dict[str, Any]:
        """Fetch blocks mined by a specific mining pool.

        Parameters
        ----------
        pool_name:
            Pool name as recognised by Blockchain.info (e.g. ``"AntPool"``).
        """
        if not pool_name or not isinstance(pool_name, str):
            raise InvalidParameterError("Pool name must be a non-empty string")
        url = f"{BLOCKCHAIN_BASE}/blocks/{pool_name}"
        return self.api._get(url, params={"format": "json"})  # type: ignore[attr-defined]

    def get_blocks_today(self) -> List[Dict[str, Any]]:
        """Return the list of blocks mined today."""
        return self.fetch_blocks_for_day().get("blocks", [])

    # ------------------------------------------------------------------ #
    # Charts
    # ------------------------------------------------------------------ #

    def fetch_chart(
        self,
        chart_type: str,
        timespan: str = "1year",
    ) -> Dict[str, Any]:
        """Fetch time-series data from the Charts API.

        Common chart types: ``market-price``, ``hash-rate``, ``difficulty``,
        ``n-transactions``, ``total-bitcoins``, ``unique-addresses``, …

        Parameters
        ----------
        chart_type:
            Chart identifier as used by ``api.blockchain.info/charts/``.
        timespan:
            One of ``"1days"``, ``"7days"``, ``"30days"``, ``"3months"``,
            ``"1year"``, ``"2years"``, ``"all"``.

        Returns
        -------
        dict
            ``{"status": "ok", "name": …, "unit": …, "values": [{x, y}, …]}``
            or a fallback ``{"status": "fallback"/"error", "values": []}``
            when the remote API returns a non-JSON body.
        """
        if not chart_type or not isinstance(chart_type, str):
            raise InvalidParameterError("Chart type must be a non-empty string")
        url = f"{BLOCKCHAIN_CHARTS_BASE}/charts/{chart_type}"
        params = {"format": "json", "timespan": timespan}
        log.info("fetch_chart type=%s timespan=%s", chart_type, timespan)
        try:
            result = self.api._get(url, params=params, allow_fallback=True)  # type: ignore[attr-defined]
            if result.get("status") == "fallback":
                log.warning("Chart API returned non-JSON for %s", chart_type)
            return result
        except BlockchainAPIError as exc:
            log.error("fetch_chart failed for %s: %s", chart_type, exc)
            return {"status": "error", "name": chart_type, "values": [], "error": str(exc)}

    def get_market_price_history(self, timespan: str = "1year") -> List[Dict[str, Any]]:
        """Return BTC market-price history as list of ``{x, y}`` dicts."""
        return self.fetch_chart("market-price", timespan).get("values", [])

    def get_hash_rate_history(self, timespan: str = "1year") -> List[Dict[str, Any]]:
        """Return network hash-rate history."""
        return self.fetch_chart("hash-rate", timespan).get("values", [])

    def get_difficulty_history(self, timespan: str = "1year") -> List[Dict[str, Any]]:
        """Return mining difficulty history."""
        return self.fetch_chart("difficulty", timespan).get("values", [])

    def get_transaction_count_history(self, timespan: str = "1year") -> List[Dict[str, Any]]:
        """Return daily transaction count history."""
        return self.fetch_chart("n-transactions", timespan).get("values", [])

    # ------------------------------------------------------------------ #
    # Comprehensive helpers
    # ------------------------------------------------------------------ #

    def fetch_block_comprehensive(
        self, block_identifier: Union[str, int]
    ) -> Dict[str, Any]:
        """Fetch all available data for a block (by hash or height).

        Returns a normalised dict with the raw block data plus a list of
        transaction summaries for the first 100 transactions.
        """
        log.info("fetch_block_comprehensive identifier=%s", block_identifier)
        result: Dict[str, Any] = {
            "block_data": {},
            "transaction_count": 0,
            "transaction_summaries": [],
        }
        try:
            if isinstance(block_identifier, int) or (
                isinstance(block_identifier, str) and block_identifier.isdigit()
            ):
                height = int(block_identifier)
                validate_block_height(height)
                height_data = self.fetch_block_by_height(height)
                blocks = height_data.get("blocks", [])
                if not blocks:
                    raise BlockNotFoundError(f"No block found at height {height}")
                result["block_data"] = blocks[0]
            else:
                result["block_data"] = self.fetch_block(str(block_identifier))

            txs = result["block_data"].get("tx", [])
            result["transaction_count"] = len(txs)
            result["transaction_summaries"] = [
                {
                    "hash": tx.get("hash", ""),
                    "size": tx.get("size", 0),
                    "fee": tx.get("fee", 0),
                    "input_count": len(tx.get("inputs", [])),
                    "output_count": len(tx.get("out", [])),
                }
                for tx in txs[:100]
            ]
        except BlockchainAPIError as exc:
            log.warning("fetch_block_comprehensive failed for %s: %s", block_identifier, exc)
        return result

    def fetch_network_stats(self) -> Dict[str, Any]:
        """Fetch a snapshot of current Bitcoin network statistics.

        Pulls the latest block, mempool size, today's block count, and recent
        chart data for hash-rate, difficulty, and transaction count.

        Returns
        -------
        dict
            ``{latest_block, mempool_size, blocks_today, charts}``.
        """
        log.info("fetch_network_stats")
        stats: Dict[str, Any] = {
            "latest_block": {},
            "mempool_size": 0,
            "blocks_today": 0,
            "charts": {},
        }

        try:
            stats["latest_block"] = self.fetch_latest_block()
        except BlockchainAPIError as exc:
            log.warning("fetch_network_stats: latest_block failed: %s", exc)

        try:
            mempool = self.fetch_unconfirmed_transactions()  # type: ignore[attr-defined]
            stats["mempool_size"] = len(mempool.get("txs", []))
        except BlockchainAPIError as exc:
            log.warning("fetch_network_stats: mempool failed: %s", exc)

        try:
            today = self.fetch_blocks_for_day()
            stats["blocks_today"] = len(today.get("blocks", []))
        except BlockchainAPIError as exc:
            log.warning("fetch_network_stats: blocks_for_day failed: %s", exc)

        for chart_type in ("hash-rate", "difficulty", "n-transactions", "market-price"):
            try:
                chart_data = self.fetch_chart(chart_type, timespan="1days")
                values = chart_data.get("values", [])
                stats["charts"][chart_type] = values[-1].get("y") if values else None
            except Exception as exc:
                log.warning("fetch_network_stats: chart %s failed: %s", chart_type, exc)
                stats["charts"][chart_type] = None

        return stats
