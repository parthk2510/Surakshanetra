"""
models.py
Typed dataclasses for all domain objects returned by the Blockchain.com API.

Using ``dataclass`` gives us free ``__repr__``, ``__eq__``, and IDE
auto-complete without pulling in heavy dependencies.  All fields that may be
absent from the API JSON are annotated as ``Optional`` with a default of
``None`` (or an empty list via ``field(default_factory=…)``).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

__all__ = [
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


# ---------------------------------------------------------------------------
# Graph primitives
# ---------------------------------------------------------------------------

@dataclass
class GraphNode:
    """A node in the transaction graph (either an address or a transaction)."""
    id: str
    label: str
    type: str


@dataclass
class GraphEdge:
    """A directed edge in the transaction graph."""
    id: str
    source: str
    target: str
    type: str
    value: int


@dataclass
class GraphMeta:
    """Metadata summary for a transaction graph."""
    address: str
    tx_count: int
    node_count: int
    edge_count: int


@dataclass
class GraphData:
    """Complete, self-contained transaction graph."""
    nodes: List[GraphNode]
    edges: List[GraphEdge]
    meta: GraphMeta


# ---------------------------------------------------------------------------
# Address
# ---------------------------------------------------------------------------

@dataclass
class AddressInfo:
    """Comprehensive information for a single Bitcoin address."""
    address: str
    hash160: str
    n_tx: int
    n_unredeemed: int
    total_received: int
    total_sent: int
    final_balance: int
    transactions: List[Dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Transaction
# ---------------------------------------------------------------------------

@dataclass
class TransactionInfo:
    """Comprehensive information for a single Bitcoin transaction."""
    hash: str
    ver: int
    vin_sz: int
    vout_sz: int
    size: int
    weight: int
    fee: int
    relayed_by: str
    lock_time: int
    tx_index: int
    double_spend: bool
    time: int
    block_index: Optional[int]
    block_height: Optional[int]
    inputs: List[Dict[str, Any]] = field(default_factory=list)
    outputs: List[Dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Block
# ---------------------------------------------------------------------------

@dataclass
class BlockInfo:
    """Comprehensive information for a single Bitcoin block."""
    hash: str
    ver: int
    prev_block: str
    mrkl_root: str
    time: int
    bits: int
    nonce: int
    n_tx: int
    size: int
    block_index: int
    main_chain: bool
    height: int
    received_time: int
    relayed_by: str
    transactions: List[Dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# UTXO
# ---------------------------------------------------------------------------

@dataclass
class UnspentOutput:
    """An unspent transaction output (UTXO)."""
    tx_hash: str
    tx_hash_big_endian: str
    tx_index: int
    tx_output_n: int
    script: str
    value: int
    # The fields below may or may not be present depending on API version.
    value_hex: Optional[str] = None
    confirmations: Optional[int] = None
    tx_age: Optional[int] = None


# ---------------------------------------------------------------------------
# Latest block summary
# ---------------------------------------------------------------------------

@dataclass
class LatestBlock:
    """Lightweight summary of the most recently mined block."""
    hash: str
    time: int
    block_index: int
    height: int
    tx_indexes: List[int] = field(default_factory=list)
