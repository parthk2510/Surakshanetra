"""
blockchain/__init__.py
Public surface of the blockchain services package.

Importing from this package gives access to:
 - The primary API client class ``BlockchainComFetcher``
 - The configuration dataclass ``FetcherConfig``
 - All custom exception types
 - All typed model dataclasses

Example
-------
>>> from backend.services.blockchain import BlockchainComFetcher, FetcherConfig
>>> fetcher = BlockchainComFetcher()
>>> data = fetcher.fetch_address("1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa")
"""

# ---------------------------------------------------------------------------
# Primary class + config
# ---------------------------------------------------------------------------
from .blockchain_fetcher import BlockchainComFetcher
from .config import FetcherConfig

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------
from .exceptions import (
    BlockchainAPIError,
    BlockNotFoundError,
    InvalidAddressError,
    InvalidParameterError,
    RateLimitError,
    TransactionNotFoundError,
)

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
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

__all__ = [
    # Primary
    "BlockchainComFetcher",
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
