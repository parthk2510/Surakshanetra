"""
blockchain_fetcher.py
``BlockchainComFetcher`` – the primary public class for the Blockchain.com API.

This module is the **single integration point** for the rest of the backend.
All API routes import from here; the module remains backward-compatible with
the original monolithic implementation while delegating to fully-modular
sub-modules under the same package.

Architecture (MRO left-to-right):

    BlockchainComFetcher
      ├─ AddressMixin    (address.py)
      ├─ TransactionMixin (transaction.py)
      ├─ BlockMixin      (block.py)
      └─ BaseFetcher     (base.py)
              ├─ BaseAPIClient  (client.py)
              ├─ TorNetworkLayer (tor_layer.py)
              ├─ MultiAddressCoordinator (coordinator.py)
              └─ FetcherConfig  (config.py)

Re-exports from sub-modules keep every existing ``from … import …`` statement
in the wider codebase working without modification.
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

# ---------------------------------------------------------------------------
# Sub-module imports (flat package – all siblings)
# ---------------------------------------------------------------------------
from .address import AddressMixin
from .base import BaseFetcher
from .block import BlockMixin
from .client import BaseAPIClient
from .config import FetcherConfig
from .constant import DEFAULT_DATA_DIR
from .coordinator import MultiAddressCoordinator
from .exceptions import (
    BlockchainAPIError,
    BlockNotFoundError,
    InvalidAddressError,
    InvalidParameterError,
    RateLimitError,
    TransactionNotFoundError,
)
from .models import (
    AddressInfo,
    BlockInfo,
    GraphData,
    GraphEdge,
    GraphMeta,
    GraphNode,
    LatestBlock,
    TransactionInfo,
    UnspentOutput,
)
from .session import create_session
from .tor_layer import TorNetworkLayer
from .transaction import TransactionMixin
from .utils import (
    sanitize_case_id,
    unique_case_path,
    utcnow_iso,
    validate_address,
    validate_addresses,
    validate_block_hash,
    validate_block_height,
    validate_tx_hash,
)

__all__ = [
    # Main class
    "BlockchainComFetcher",
    # Config
    "FetcherConfig",
    # Exceptions
    "BlockchainAPIError",
    "RateLimitError",
    "InvalidAddressError",
    "TransactionNotFoundError",
    "BlockNotFoundError",
    "InvalidParameterError",
    # Models
    "GraphNode",
    "GraphEdge",
    "GraphMeta",
    "GraphData",
    "AddressInfo",
    "TransactionInfo",
    "BlockInfo",
    "UnspentOutput",
    "LatestBlock",
]

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Composite fetcher class
# ---------------------------------------------------------------------------

class BlockchainComFetcher(AddressMixin, TransactionMixin, BlockMixin, BaseFetcher):
    """Full-featured Blockchain.info API client.

    Composes :class:`AddressMixin`, :class:`TransactionMixin`,
    :class:`BlockMixin`, and :class:`BaseFetcher` into a single object that
    exposes every endpoint of the Blockchain Data API.

    Supported endpoints
    -------------------
    * ``/rawaddr``                – single address & transaction history
    * ``/multiaddr``              – combined multi-address view
    * ``/balance``                – address balances
    * ``/unspent``                – UTXOs
    * ``/rawtx``                  – individual transactions
    * ``/rawblock``               – blocks by hash
    * ``/block-height``           – blocks by height
    * ``/latestblock``            – latest block summary
    * ``/unconfirmed-transactions`` – mempool
    * ``/blocks``                 – blocks by day / mining pool
    * ``api.blockchain.info/charts`` – market & network charts

    Parameters
    ----------
    config:
        :class:`FetcherConfig` controlling rate-limiting, caching, Tor, etc.
        Defaults to ``FetcherConfig()`` (safe production settings).
    session:
        Inject a custom :class:`requests.Session` (mainly for testing).
        When *None* a session is created automatically via :func:`create_session`.

    Examples
    --------
    >>> fetcher = BlockchainComFetcher()
    >>> data = fetcher.fetch_address("1A1zP1eP5QGefi2DMPTfTL5SLmv7Divf Na")
    >>> fetcher.save_graph(fetcher.build_graph_for_address("1A1zP1…"))
    """

    def __init__(
        self,
        config: Optional[FetcherConfig] = None,
        session=None,
    ) -> None:
        # BaseFetcher.__init__ handles: config, session, api, tor_layer,
        # coordinator, data_dir
        super().__init__(config=config)

        # Inject a custom session after the base is initialised when provided
        if session is not None:
            self.api._session = session

    # ------------------------------------------------------------------ #
    # Factory class method (JSON config file)
    # ------------------------------------------------------------------ #

    @classmethod
    def from_config_file(cls, config_path: Union[str, Path]) -> "BlockchainComFetcher":
        """Create an instance from a JSON configuration file.

        The file must contain a JSON object whose keys match the fields of
        :class:`FetcherConfig`.  Unknown keys are silently ignored.

        Parameters
        ----------
        config_path:
            Path to the ``.json`` config file.

        Returns
        -------
        BlockchainComFetcher
        """
        config_path = Path(config_path)
        if not config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")
        with open(config_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return cls(config=FetcherConfig.from_dict(data))

    # ------------------------------------------------------------------ #
    # Comprehensive address analysis (graph + metadata in one call)
    # ------------------------------------------------------------------ #

    def fetch_address_comprehensive(
        self,
        address: str,
        max_limit: int = 2000,
    ) -> Dict[str, Any]:
        """Fetch a rich forensic snapshot of a Bitcoin address.

        Retrieves transaction history (paginated), UTXOs, and balance info,
        then constructs graph nodes / edges suitable for the frontend
        investigation panel.

        Parameters
        ----------
        address:
            Bitcoin address to investigate.
        max_limit:
            Maximum transactions to fetch (capped at 2000).

        Returns
        -------
        dict
            A large composite dict with keys:
            ``metadata``, ``nodes``, ``edges``, ``transactions``, ``blocks``,
            ``globalContext``, ``detectedCommunities``, ``investigativeLeads``,
            ``suspiciousPatterns``, ``pagination``, ``address``,
            ``basic_info``, ``unspent_outputs``, ``balance_details``,
            ``fetched_at``, ``fetch_status``.
        """
        validate_address(address)
        safe_limit = min(max(max_limit, 1), 2000)
        log.info("fetch_address_comprehensive addr=%s max_limit=%d", address[:12], safe_limit)

        # --- primary address data w/ pagination ---
        addr_data = self.fetch_all_transactions(
            address, max_limit=safe_limit, rate_limit_delay=0.3
        )
        total_on_chain: int = addr_data.get("n_tx", 0)
        fetched_txs: List[Dict[str, Any]] = addr_data.get("txs", [])

        # --- UTXOs (best-effort) ---
        unspent_outputs: List = []
        try:
            unspent_data = self.fetch_unspent(address)
            unspent_outputs = unspent_data.get("unspent_outputs", [])
        except BlockchainAPIError as exc:
            log.warning("fetch_address_comprehensive: unspent failed for %s: %s", address[:12], exc)

        # --- balance details (best-effort) ---
        balance_details: Dict[str, Any] = {}
        try:
            balance_data = self.fetch_balance(address)
            balance_details = balance_data.get(address, {})
        except BlockchainAPIError as exc:
            log.warning("fetch_address_comprehensive: balance failed for %s: %s", address[:12], exc)

        # --- build graph ---
        total_received = addr_data.get("total_received", 0)
        total_sent = addr_data.get("total_sent", 0)
        final_balance = addr_data.get("final_balance", 0)

        nodes: Dict[str, Any] = {
            address: {
                "id": address,
                "type": "address",
                "balance": final_balance,
                "totalReceived": total_received,
                "totalSent": total_sent,
                "txCount": total_on_chain,
                "riskScore": 0,
                "isSuspicious": False,
                "tags": [],
                "communityId": None,
                "betweennessCentrality": 0,
                "firstSeen": None,
                "lastActive": None,
                "utxos": unspent_outputs,
                "rawData": {
                    "hash160": addr_data.get("hash160", ""),
                    "n_tx": total_on_chain,
                    "n_unredeemed": addr_data.get("n_unredeemed", 0),
                    "total_received": total_received,
                    "total_sent": total_sent,
                    "final_balance": final_balance,
                },
            }
        }
        edges: List[Dict[str, Any]] = []
        transactions_map: Dict[str, Any] = {}

        def _ensure_addr_node(addr: str) -> None:
            if addr not in nodes:
                nodes[addr] = {
                    "id": addr,
                    "type": "address",
                    "balance": 0,
                    "totalReceived": 0,
                    "totalSent": 0,
                    "txCount": 0,
                    "riskScore": 0,
                    "isSuspicious": False,
                    "tags": [],
                    "communityId": None,
                    "betweennessCentrality": 0,
                }

        for tx in fetched_txs:
            tx_hash: str = tx.get("hash", "")
            if not tx_hash:
                continue
            tx_time = tx.get("time")
            tx_fee = tx.get("fee", 0)
            tx_block_height = tx.get("block_height")
            tx_block_hash = tx.get("block_hash")

            nodes[tx_hash] = {
                "id": tx_hash,
                "type": "transaction",
                "hash": tx_hash,
                "time": tx_time,
                "blockHash": tx_block_hash,
                "blockHeight": tx_block_height,
                "fee": tx_fee,
                "riskScore": 0,
                "communityId": None,
                "betweennessCentrality": 0,
                "rawData": tx,
            }

            tx_inputs: List[Dict] = []
            for vin in tx.get("inputs", []):
                prev_out = vin.get("prev_out") or {}
                src_addr = prev_out.get("addr")
                src_value = prev_out.get("value", 0)
                if src_addr:
                    tx_inputs.append({"addr": src_addr, "value": src_value, "n": prev_out.get("n")})
                    _ensure_addr_node(src_addr)
                    edges.append({
                        "id": f"{src_addr}->{tx_hash}",
                        "source": src_addr,
                        "target": tx_hash,
                        "value": src_value,
                        "timestamp": tx_time,
                        "txHash": tx_hash,
                        "type": "input",
                    })

            tx_outputs: List[Dict] = []
            for vout in tx.get("out", []):
                dst_addr = vout.get("addr")
                dst_value = vout.get("value", 0)
                out_n = vout.get("n")
                if dst_addr:
                    tx_outputs.append({"addr": dst_addr, "value": dst_value, "n": out_n})
                    _ensure_addr_node(dst_addr)
                    edges.append({
                        "id": f"{tx_hash}->{dst_addr}-{out_n}",
                        "source": tx_hash,
                        "target": dst_addr,
                        "value": dst_value,
                        "timestamp": tx_time,
                        "txHash": tx_hash,
                        "type": "output",
                    })

            transactions_map[tx_hash] = {
                "hash": tx_hash,
                "time": tx_time,
                "blockHash": tx_block_hash,
                "blockHeight": tx_block_height,
                "confirmations": tx_block_height,
                "fee": tx_fee,
                "inputs": tx_inputs,
                "outputs": tx_outputs,
                "minerPool": None,
                "rawData": tx,
            }

        has_more = total_on_chain > len(fetched_txs)
        next_offset = len(fetched_txs) if has_more else None
        now_iso = utcnow_iso()
        case_id = f"CASE-Investigation-{datetime.now(tz=timezone.utc).strftime('%b-%d-%Y')}"

        return {
            "metadata": {
                "caseId": case_id,
                "createdAt": now_iso,
                "lastUpdated": now_iso,
                "primaryAddress": address,
                "investigatedAddresses": [address],
            },
            "nodes": nodes,
            "edges": edges,
            "transactions": transactions_map,
            "blocks": {},
            "globalContext": {
                "marketPrice": 0,
                "networkHashRate": 0,
                "networkDifficulty": 0,
                "transactionRate": [],
                "lastBlockHeight": 0,
                "mempoolSize": 0,
            },
            "detectedCommunities": {},
            "investigativeLeads": [],
            "suspiciousPatterns": {
                "mixerCandidates": [],
                "bridgeNodes": [],
                "timingAnomalies": [],
                "dustingTargets": [],
                "whales": [],
            },
            "pagination": {
                "totalTransactions": total_on_chain,
                "fetchedCount": len(fetched_txs),
                "pageSize": safe_limit,
                "hasMore": has_more,
                "nextOffset": next_offset,
            },
            "address": address,
            "basic_info": {
                "address": addr_data.get("address", address),
                "hash160": addr_data.get("hash160", ""),
                "n_tx": total_on_chain,
                "n_unredeemed": addr_data.get("n_unredeemed", 0),
                "total_received": total_received,
                "total_sent": total_sent,
                "final_balance": final_balance,
            },
            "unspent_outputs": unspent_outputs,
            "balance_details": balance_details,
            "fetched_at": now_iso,
            "fetch_status": "complete",
        }

    def fetch_address_transactions_page(
        self,
        address: str,
        offset: int = 0,
        limit: int = 50,
    ) -> Dict[str, Any]:
        """Fetch a single page of transaction graph data for *address*.

        Lighter-weight than :meth:`fetch_address_comprehensive`; returns only
        the nodes, edges, transactions, and pagination state for the requested
        page slice.

        Parameters
        ----------
        address:
            Bitcoin address.
        offset:
            Number of transactions to skip (0-indexed).
        limit:
            Page size (1–50).

        Returns
        -------
        dict
            Keys: ``nodes``, ``edges``, ``transactions``, ``pagination``.
        """
        validate_address(address)
        safe_limit = min(max(limit, 1), 50)
        safe_offset = max(offset, 0)
        log.info(
            "fetch_address_transactions_page addr=%s offset=%d limit=%d",
            address[:12], safe_offset, safe_limit,
        )

        addr_data = self.fetch_address(address, limit=safe_limit, offset=safe_offset)
        total_on_chain: int = addr_data.get("n_tx", 0)
        page_txs: List[Dict[str, Any]] = addr_data.get("txs", [])

        nodes: Dict[str, Any] = {}
        edges: List[Dict[str, Any]] = []
        transactions_map: Dict[str, Any] = {}

        def _ensure_addr_node(addr: str) -> None:
            if addr not in nodes:
                nodes[addr] = {
                    "id": addr,
                    "type": "address",
                    "balance": 0,
                    "totalReceived": 0,
                    "totalSent": 0,
                    "txCount": 0,
                    "riskScore": 0,
                    "isSuspicious": False,
                    "tags": [],
                    "communityId": None,
                    "betweennessCentrality": 0,
                }

        for tx in page_txs:
            tx_hash = tx.get("hash", "")
            if not tx_hash:
                continue
            tx_time = tx.get("time")
            tx_fee = tx.get("fee", 0)
            tx_block_height = tx.get("block_height")
            tx_block_hash = tx.get("block_hash")

            nodes[tx_hash] = {
                "id": tx_hash,
                "type": "transaction",
                "hash": tx_hash,
                "time": tx_time,
                "blockHash": tx_block_hash,
                "blockHeight": tx_block_height,
                "fee": tx_fee,
                "riskScore": 0,
                "communityId": None,
                "betweennessCentrality": 0,
                "rawData": tx,
            }

            tx_inputs: List[Dict] = []
            for vin in tx.get("inputs", []):
                prev_out = vin.get("prev_out") or {}
                src_addr = prev_out.get("addr")
                src_value = prev_out.get("value", 0)
                if src_addr:
                    tx_inputs.append({"addr": src_addr, "value": src_value, "n": prev_out.get("n")})
                    _ensure_addr_node(src_addr)
                    edges.append({
                        "id": f"{src_addr}->{tx_hash}",
                        "source": src_addr,
                        "target": tx_hash,
                        "value": src_value,
                        "timestamp": tx_time,
                        "txHash": tx_hash,
                        "type": "input",
                    })

            tx_outputs: List[Dict] = []
            for vout in tx.get("out", []):
                dst_addr = vout.get("addr")
                dst_value = vout.get("value", 0)
                out_n = vout.get("n")
                if dst_addr:
                    tx_outputs.append({"addr": dst_addr, "value": dst_value, "n": out_n})
                    _ensure_addr_node(dst_addr)
                    edges.append({
                        "id": f"{tx_hash}->{dst_addr}-{out_n}",
                        "source": tx_hash,
                        "target": dst_addr,
                        "value": dst_value,
                        "timestamp": tx_time,
                        "txHash": tx_hash,
                        "type": "output",
                    })

            transactions_map[tx_hash] = {
                "hash": tx_hash,
                "time": tx_time,
                "blockHash": tx_block_hash,
                "blockHeight": tx_block_height,
                "confirmations": tx_block_height,
                "fee": tx_fee,
                "inputs": tx_inputs,
                "outputs": tx_outputs,
                "minerPool": None,
                "rawData": tx,
            }

        end_index = safe_offset + len(page_txs)
        has_more = end_index < total_on_chain
        return {
            "nodes": nodes,
            "edges": edges,
            "transactions": transactions_map,
            "pagination": {
                "totalTransactions": total_on_chain,
                "offset": safe_offset,
                "limit": safe_limit,
                "fetchedCount": len(page_txs),
                "hasMore": has_more,
                "nextOffset": end_index if has_more else None,
            },
        }

    # ------------------------------------------------------------------ #
    # Graph building helpers
    # ------------------------------------------------------------------ #

    def build_graph_for_address(
        self,
        address: str,
        tx_limit: int = 50,
        fetch_all: bool = False,
    ) -> Dict[str, Any]:
        """Build a transaction graph for a single *address*.

        Shorthand for :meth:`build_multi_address_graph` with a single address.
        """
        validate_address(address)
        log.info(
            "build_graph_for_address addr=%s tx_limit=%d fetch_all=%s",
            address[:12], tx_limit, fetch_all,
        )
        return self.build_multi_address_graph([address], tx_limit=tx_limit, fetch_all=fetch_all)

    def build_multi_address_graph(
        self,
        addresses: List[str],
        tx_limit: Optional[int] = None,
        fetch_all: bool = False,
    ) -> Dict[str, Any]:
        """Build a combined transaction graph for multiple addresses.

        Fetches data for each address (optionally with full pagination) and
        assembles a graph dict with ``nodes`` and ``edges`` arrays compatible
        with the frontend graph visualisation component.

        Parameters
        ----------
        addresses:
            List of Bitcoin addresses to include.
        tx_limit:
            Maximum transactions per address; defaults to 50.
        fetch_all:
            When ``True`` paginate each address fully.

        Returns
        -------
        dict
            ``{"nodes": […], "edges": […], "meta": {…}}``.
        """
        validate_addresses(addresses)
        log.info(
            "build_multi_address_graph n=%d tx_limit=%s fetch_all=%s",
            len(addresses), tx_limit, fetch_all,
        )

        limit_per = min(tx_limit, 50) if tx_limit else 50
        multi_data = self.fetch_multiple_addresses(
            addresses,
            limit_per_address=limit_per,
            fetch_all=fetch_all,
        )

        nodes_dict: Dict[str, Any] = {}
        edges_dict: Dict[str, Any] = {}

        def _ensure_addr_node(addr: str, addr_type: str = "address") -> None:
            if addr not in nodes_dict:
                nodes_dict[addr] = {"id": addr, "label": addr[:12], "type": addr_type}

        for address in addresses:
            data = multi_data.get(address, {})
            if "error" in data:
                log.warning(
                    "build_multi_address_graph: skip %s error=%s",
                    address[:12], data["error"],
                )
                continue

            _ensure_addr_node(address, "address")
            for tx in data.get("txs", []):
                txid = tx.get("hash")
                if not txid:
                    continue
                if txid not in nodes_dict:
                    nodes_dict[txid] = {
                        "id": txid,
                        "label": txid[:12],
                        "type": "transaction",
                        "time": tx.get("time"),
                        "fee": tx.get("fee", 0),
                    }
                for vin in tx.get("inputs", []):
                    prev_out = vin.get("prev_out") or {}
                    src = prev_out.get("addr")
                    if not src:
                        continue
                    _ensure_addr_node(src)
                    eid = f"{src}->{txid}"
                    if eid not in edges_dict:
                        edges_dict[eid] = {
                            "id": eid,
                            "source": src,
                            "target": txid,
                            "type": "SENT_FROM",
                            "value": prev_out.get("value", 0),
                        }
                for vout in tx.get("out", []):
                    dst = vout.get("addr")
                    if not dst:
                        continue
                    _ensure_addr_node(dst)
                    eid = f"{txid}->{dst}"
                    if eid not in edges_dict:
                        edges_dict[eid] = {
                            "id": eid,
                            "source": txid,
                            "target": dst,
                            "type": "SENT_TO",
                            "value": vout.get("value", 0),
                        }

        graph = {
            "nodes": list(nodes_dict.values()),
            "edges": list(edges_dict.values()),
            "meta": {
                "addresses": addresses,
                "address": addresses[0] if len(addresses) == 1 else None,
                "node_count": len(nodes_dict),
                "edge_count": len(edges_dict),
                "tx_count": sum(
                    len(multi_data.get(a, {}).get("txs", []))
                    for a in addresses
                    if "error" not in multi_data.get(a, {})
                ),
                "fetched_all": fetch_all,
            },
        }
        log.info(
            "build_multi_address_graph done nodes=%d edges=%d",
            len(nodes_dict), len(edges_dict),
        )
        return graph

    # ------------------------------------------------------------------ #
    # Persistence helpers
    # ------------------------------------------------------------------ #

    def save_graph(
        self,
        graph: Dict[str, Any],
        filename: Optional[str] = None,
    ) -> str:
        """Persist a graph dict to a JSON file in ``self.data_dir``.

        Parameters
        ----------
        graph:
            Graph dict (must have ``"nodes"``, ``"edges"``, and optionally
            ``"meta"`` with an ``"address"`` key).
        filename:
            Override the auto-generated filename.

        Returns
        -------
        str
            Absolute path to the saved file.
        """
        data_dir = self.data_dir
        data_dir.mkdir(parents=True, exist_ok=True)

        if not filename:
            address = str((graph.get("meta") or {}).get("address") or "graph")
            filename = self._make_graph_filename(address)

        path = data_dir / filename
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(graph, fh, ensure_ascii=False, indent=2)

        log.info(
            "Graph saved: path=%s nodes=%d edges=%d",
            path,
            len(graph.get("nodes", [])),
            len(graph.get("edges", [])),
        )
        return str(path)

    def save_case_file(
        self,
        case_file: Dict[str, Any],
        case_id: Optional[str] = None,
        cases_dir: Union[str, Path] = Path("data/cases"),
    ) -> Path:
        """Persist an investigation case dict to a unique JSON file.

        Parameters
        ----------
        case_file:
            Case data dict; must contain a ``"metadata"`` sub-dict.
        case_id:
            Override the case identifier (sanitised automatically).
        cases_dir:
            Directory for case files (created if absent).

        Returns
        -------
        pathlib.Path
            Path to the saved case file.
        """
        if not isinstance(case_file, dict):
            raise ValueError("case_file must be a dict")

        metadata = case_file.get("metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {}

        requested_id = case_id or str(metadata.get("caseId") or "")
        safe_id = sanitize_case_id(requested_id)

        metadata["caseId"] = safe_id
        metadata["lastUpdated"] = utcnow_iso()
        case_file["metadata"] = metadata

        out_dir = Path(cases_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        filename, out_path = unique_case_path(out_dir, safe_id)
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(case_file, fh, indent=2, ensure_ascii=False)

        log.info("Saved case file: %s", out_path)
        return out_path

    # ------------------------------------------------------------------ #
    # Deprecated shims for backward compatibility
    # (kept so nothing breaks if someone still calls these directly)
    # ------------------------------------------------------------------ #

    def _validate_address(self, address: str) -> None:  # noqa: D401
        """Thin shim – delegates to :func:`utils.validate_address`."""
        validate_address(address)

    def _validate_addresses(self, addresses) -> None:
        validate_addresses(addresses)

    def _validate_tx_hash(self, tx_hash: str) -> None:
        validate_tx_hash(tx_hash)

    def _validate_block_hash(self, block_hash: str) -> None:
        validate_block_hash(block_hash)

    def _validate_block_height(self, height: int) -> None:
        validate_block_height(height)

    @staticmethod
    def _sanitize_case_id(case_id: str) -> str:
        return sanitize_case_id(case_id)

    @staticmethod
    def _unique_case_path(cases_dir: Path, case_id: str):
        return unique_case_path(cases_dir, case_id)
