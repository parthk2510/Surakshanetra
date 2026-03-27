"""
coordinator.py
``MultiAddressCoordinator`` – in-memory graph of co-spending address clusters.

Builds an undirected adjacency structure from transaction data so that the
fetcher can answer questions like "which addresses have collectively appeared
in the same transaction inputs as this address?" without an external graph DB.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Dict, List, Set

__all__ = ["MultiAddressCoordinator"]

log = logging.getLogger(__name__)


class MultiAddressCoordinator:
    """Thread-unsafe in-memory address-cluster tracker.

    Attributes
    ----------
    address_graph:
        Adjacency map: ``address → {related_addresses}``.
    address_metadata:
        Per-address summary dict (balance, tx_count, …).
    shared_transactions:
        ``"addr1:addr2" → [tx_hash, …]`` for every edge in the graph.
    """

    def __init__(self, max_workers: int = 5) -> None:
        self.max_workers = max_workers
        self.address_graph: Dict[str, Set[str]] = defaultdict(set)
        self.address_metadata: Dict[str, Dict[str, Any]] = {}
        self.shared_transactions: Dict[str, List[str]] = defaultdict(list)

    # ------------------------------------------------------------------ #
    # Mutation
    # ------------------------------------------------------------------ #

    def add_address_relationship(self, addr1: str, addr2: str, tx_hash: str) -> None:
        """Record that *addr1* and *addr2* co-appear in *tx_hash*."""
        self.address_graph[addr1].add(addr2)
        self.address_graph[addr2].add(addr1)
        key = f"{addr1}:{addr2}"
        if tx_hash not in self.shared_transactions[key]:
            self.shared_transactions[key].append(tx_hash)

    # ------------------------------------------------------------------ #
    # Query
    # ------------------------------------------------------------------ #

    def get_connected_addresses(self, address: str, max_depth: int = 2) -> Set[str]:
        """BFS expansion up to *max_depth* hops from *address*.

        Parameters
        ----------
        address:
            Starting address.
        max_depth:
            Maximum graph hops to traverse.

        Returns
        -------
        set
            All reachable addresses including *address* itself.
        """
        visited: Set[str] = set()
        queue: List[tuple] = [(address, 0)]
        while queue:
            current, depth = queue.pop(0)
            if current in visited or depth > max_depth:
                continue
            visited.add(current)
            if depth < max_depth:
                for neighbour in self.address_graph.get(current, set()):
                    if neighbour not in visited:
                        queue.append((neighbour, depth + 1))
        return visited

    def get_address_cluster(self, address: str, max_depth: int = 2) -> Dict[str, Any]:
        """Return a cluster summary rooted at *address*.

        Returns
        -------
        dict
            Keys: ``root_address``, ``cluster_size``, ``addresses``,
            ``metadata`` (maps address → stored metadata dict).
        """
        connected = self.get_connected_addresses(address, max_depth=max_depth)
        return {
            "root_address": address,
            "cluster_size": len(connected),
            "addresses": sorted(connected),
            "metadata": {
                addr: self.address_metadata.get(addr, {}) for addr in connected
            },
        }

    # ------------------------------------------------------------------ #
    # Housekeeping
    # ------------------------------------------------------------------ #

    def reset(self) -> None:
        """Clear all stored state (useful between investigations)."""
        self.address_graph.clear()
        self.address_metadata.clear()
        self.shared_transactions.clear()
        log.debug("MultiAddressCoordinator state reset")
