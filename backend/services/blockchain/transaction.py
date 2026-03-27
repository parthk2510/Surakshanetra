"""
transaction.py
``TransactionMixin`` – methods that deal with individual Bitcoin transactions.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .constant import BLOCKCHAIN_BASE
from .models import TransactionInfo
from .utils import validate_tx_hash

__all__ = ["TransactionMixin"]

log = logging.getLogger(__name__)


class TransactionMixin:
    """Bitcoin-transaction–related methods for ``BlockchainComFetcher``."""

    def fetch_tx(
        self,
        tx_hash: str,
        format: str = "json",  # noqa: A002
    ) -> Dict[str, Any]:
        """Fetch a transaction by hash from ``/rawtx``.

        Parameters
        ----------
        tx_hash:
            64-character hexadecimal transaction hash.
        format:
            ``"json"`` (default) returns parsed JSON.
            ``"hex"`` returns the raw serialised transaction as a plain
            hex string (the API still responds over HTTP, but the body is
            text, not JSON – handle accordingly).

        Returns
        -------
        dict
            Parsed transaction JSON (inputs, outputs, fees, block info).
        """
        validate_tx_hash(tx_hash)
        url = f"{BLOCKCHAIN_BASE}/rawtx/{tx_hash}"
        params: Optional[Dict[str, Any]] = {"format": "hex"} if format == "hex" else None
        return self.api._get(url, params=params)  # type: ignore[attr-defined]

    def get_transaction(self, tx_hash: str) -> TransactionInfo:
        """Fetch a transaction and return it as a typed :class:`TransactionInfo`."""
        data = self.fetch_tx(tx_hash)
        return TransactionInfo(
            hash=data.get("hash", tx_hash),
            ver=data.get("ver", 0),
            vin_sz=data.get("vin_sz", 0),
            vout_sz=data.get("vout_sz", 0),
            size=data.get("size", 0),
            weight=data.get("weight", 0),
            fee=data.get("fee", 0),
            relayed_by=data.get("relayed_by", ""),
            lock_time=data.get("lock_time", 0),
            tx_index=data.get("tx_index", 0),
            double_spend=data.get("double_spend", False),
            time=data.get("time", 0),
            block_index=data.get("block_index"),
            block_height=data.get("block_height"),
            inputs=data.get("inputs", []),
            outputs=data.get("out", []),
        )

    def fetch_unconfirmed_transactions(self) -> Dict[str, Any]:
        """Fetch unconfirmed (mempool) transactions from ``/unconfirmed-transactions``.

        Returns
        -------
        dict
            ``{"txs": [tx, …]}``
        """
        url = f"{BLOCKCHAIN_BASE}/unconfirmed-transactions"
        return self.api._get(url, params={"format": "json"})  # type: ignore[attr-defined]

    def get_mempool_transactions(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Return up to *limit* unconfirmed transactions from the mempool."""
        data = self.fetch_unconfirmed_transactions()
        txs = data.get("txs", [])
        return txs[:limit] if limit else txs
