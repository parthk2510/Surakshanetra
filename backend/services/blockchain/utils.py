"""
utils.py
Validation helpers and small utility functions shared across the module.

None of these functions perform I/O; they operate solely on their arguments
and raise exceptions from ``exceptions.py`` when validation fails.
"""
from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
from uuid import uuid4

from .exceptions import (
    BlockNotFoundError,
    InvalidAddressError,
    InvalidParameterError,
    TransactionNotFoundError,
)

__all__ = [
    "validate_address",
    "validate_addresses",
    "validate_tx_hash",
    "validate_block_hash",
    "validate_block_height",
    "sanitize_case_id",
    "unique_case_path",
    "utcnow_iso",
]

# ---------------------------------------------------------------------------
# Bitcoin address regular expressions
# ---------------------------------------------------------------------------

#: Matches P2PKH (1…), P2SH (3…), Bech32 (bc1q…), Bech32m (bc1p…),
#: and extended public keys (xpub / ypub / zpub / tpub).
_ADDR_RE = re.compile(
    r"^[13][a-km-zA-HJ-NP-Z1-9]{25,34}$"     # P2PKH / P2SH
    r"|^bc1[a-z0-9]{6,87}$"                    # Bech32 / Bech32m
    r"|^[xyzt]pub[a-km-zA-HJ-NP-Z1-9]{100,}$" # BIP-32 extended pub keys
)

_TX_HASH_RE = re.compile(r"^[a-fA-F0-9]{64}$")
_BLOCK_HASH_RE = re.compile(r"^[a-fA-F0-9]{64}$")


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def validate_address(address: str) -> None:
    """Raise :exc:`InvalidAddressError` if *address* is not a recognized
    Bitcoin address format.

    Supported formats:
    - P2PKH  (starts with ``1``)
    - P2SH   (starts with ``3``)
    - Bech32 / Bech32m (starts with ``bc1``)
    - Extended public keys: ``xpub``, ``ypub``, ``zpub``, ``tpub``
    """
    if not address or not isinstance(address, str):
        raise InvalidAddressError(f"Address must be a non-empty string, got: {address!r}")
    if not _ADDR_RE.match(address):
        raise InvalidAddressError(
            f"Invalid Bitcoin address format: {address!r}. "
            "Expected P2PKH (1…), P2SH (3…), Bech32 (bc1…), or xpub/ypub/zpub/tpub."
        )


def validate_addresses(addresses: List[str]) -> None:
    """Validate every element of *addresses*.

    Raises :exc:`InvalidAddressError` if the list is empty or any element
    fails format validation.
    """
    if not addresses or not isinstance(addresses, list):
        raise InvalidAddressError("Addresses must be a non-empty list")
    for addr in addresses:
        validate_address(addr)


def validate_tx_hash(tx_hash: str) -> None:
    """Raise :exc:`TransactionNotFoundError` if *tx_hash* is not a 64-char hex
    string."""
    if not tx_hash or not isinstance(tx_hash, str):
        raise TransactionNotFoundError(
            f"Transaction hash must be a non-empty string, got: {tx_hash!r}"
        )
    if not _TX_HASH_RE.match(tx_hash):
        raise TransactionNotFoundError(
            f"Invalid transaction hash format: {tx_hash!r} "
            "(expected 64 lowercase/uppercase hex characters)"
        )


def validate_block_hash(block_hash: str) -> None:
    """Raise :exc:`BlockNotFoundError` if *block_hash* is not a 64-char hex
    string."""
    if not block_hash or not isinstance(block_hash, str):
        raise BlockNotFoundError(
            f"Block hash must be a non-empty string, got: {block_hash!r}"
        )
    if not _BLOCK_HASH_RE.match(block_hash):
        raise BlockNotFoundError(
            f"Invalid block hash format: {block_hash!r} "
            "(expected 64 lowercase/uppercase hex characters)"
        )


def validate_block_height(height: int) -> None:
    """Raise :exc:`InvalidParameterError` if *height* is not a non-negative
    integer."""
    if not isinstance(height, int) or height < 0:
        raise InvalidParameterError(
            f"Block height must be a non-negative integer, got: {height!r}"
        )


# ---------------------------------------------------------------------------
# Case-file helpers
# ---------------------------------------------------------------------------

def sanitize_case_id(case_id: str) -> str:
    """Return a clean ``CASE-<id>`` string with only safe characters.

    Rules:
    - Strip any trailing ``.json``.
    - Strip the ``CASE-`` prefix so that it is re-added unconditionally.
    - Allow only alphanumeric, dash, and underscore in the ID part.
    - Fall back to a timestamp-based ID if the result is empty.
    """
    if not case_id:
        return f"CASE-{int(time.time())}"

    clean = case_id[:-5] if case_id.endswith(".json") else case_id
    id_part = clean[5:] if clean.startswith("CASE-") else clean
    safe_part = "".join(c for c in id_part if c.isalnum() or c in ("-", "_"))

    return f"CASE-{safe_part}" if safe_part else f"CASE-{int(time.time())}"


def unique_case_path(cases_dir: Path, case_id: str):
    """Return ``(filename, full_path)`` for a case file.

    Always returns the canonical ``<case_id>.json`` path, overwriting any
    existing file with the same ID so only one normalised file is kept per case.
    """
    base = sanitize_case_id(case_id)
    candidate = cases_dir / f"{base}.json"
    return candidate.name, candidate


# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------

def utcnow_iso() -> str:
    """Return the current UTC time as an ISO-8601 string with trailing ``Z``."""
    return datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z")
