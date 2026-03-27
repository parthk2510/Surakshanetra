"""
exceptions.py
Custom exception hierarchy for the Blockchain.com API client.

All public-facing exceptions inherit from ``BlockchainAPIError`` so callers
can catch the entire family with a single except clause when needed.
"""

__all__ = [
    "BlockchainAPIError",
    "RateLimitError",
    "InvalidAddressError",
    "TransactionNotFoundError",
    "BlockNotFoundError",
    "InvalidParameterError",
]


class BlockchainAPIError(Exception):
    """Base exception for all Blockchain.info API errors.

    Raise (or its subclasses) whenever an error originates from interaction
    with the remote API or from invalid input that prevents a well-formed
    request from being made.
    """


class RateLimitError(BlockchainAPIError):
    """Raised when the API responds with HTTP 429 (Too Many Requests).

    The caller should wait before retrying.  If Tor is configured,
    renewing the circuit identity may help bypass the rate limit.
    """


class InvalidAddressError(BlockchainAPIError):
    """Raised when a Bitcoin address fails format validation.

    Supported formats: P2PKH (1…), P2SH (3…), Bech32 (bc1…),
    and extended public keys (xpub/ypub/zpub/tpub).
    """


class TransactionNotFoundError(BlockchainAPIError):
    """Raised when a requested transaction hash cannot be found (HTTP 404)."""


class BlockNotFoundError(BlockchainAPIError):
    """Raised when a requested block hash or height cannot be found (HTTP 404)."""


class InvalidParameterError(BlockchainAPIError):
    """Raised when a method argument has an illegal value (e.g. negative offset,
    out-of-range limit)."""
