"""
Graph Builder Module for Temporal Community Analysis

This module handles the construction of NetworkX graphs from TransactionSnapshot
objects. It supports configurable graph types (directed/undirected) and 
weighted/unweighted edges.

Mathematical Context:
    Given snapshot data S = (V, E), we construct graph G = (V, E) where:
    - V is the set of wallet addresses/transactions
    - E is the set of edges representing transactions/relationships
    
    For community detection, we typically convert to undirected graphs
    since most algorithms (Louvain, Leiden) operate on undirected networks.
"""

import logging
from typing import Dict, Any, Optional, List, Set

import networkx as nx

from .data_loader import TransactionSnapshot

logger = logging.getLogger(__name__)


class TemporalGraphBuilder:
    """
    Constructs NetworkX graphs from transaction snapshots.
    
    This class provides methods to build graphs with various configurations:
    - Directed vs undirected
    - Weighted vs unweighted edges
    - Filtering by node types
    
    Usage:
        builder = TemporalGraphBuilder(directed=False, weighted=True)
        G = builder.build_graph(snapshot)
        
        # Build address-only graph (exclude transaction nodes)
        G_addresses = builder.build_address_graph(snapshot)
    """
    
    def __init__(
        self,
        directed: bool = False,
        weighted: bool = True,
        weight_attribute: str = 'weight',
        default_weight: float = 1.0
    ):
        """
        Initialize the graph builder.
        
        Args:
            directed: If True, create directed graphs. If False, create undirected.
            weighted: If True, include edge weights in the graph.
            weight_attribute: Name of the edge attribute to use as weight.
            default_weight: Default weight for edges without weight data.
        """
        self.directed = directed
        self.weighted = weighted
        self.weight_attribute = weight_attribute
        self.default_weight = default_weight
    
    def build_graph(
        self,
        snapshot: TransactionSnapshot,
        node_filter: Optional[Set[str]] = None
    ) -> nx.Graph:
        """
        Build a NetworkX graph from a transaction snapshot.
        
        Args:
            snapshot: The transaction snapshot to convert
            node_filter: Optional set of node IDs to include. If None, all nodes included.
            
        Returns:
            NetworkX Graph or DiGraph object
            
        Raises:
            ValueError: If snapshot is empty and strict mode is enabled
        """
        logger.info(f"Building graph from snapshot '{snapshot.snapshot_id}' "
                   f"(directed={self.directed}, weighted={self.weighted})")
        
        # Create appropriate graph type
        if self.directed:
            G = nx.DiGraph()
        else:
            G = nx.Graph()
        
        # Add nodes with attributes
        nodes_added = 0
        for node in snapshot.nodes:
            node_id = node.get('id')
            
            if node_id is None:
                continue
                
            # Apply node filter if provided
            if node_filter is not None and node_id not in node_filter:
                continue
            
            G.add_node(
                node_id,
                label=node.get('label', str(node_id)[:12]),
                node_type=node.get('type', 'unknown'),
                **{k: v for k, v in node.items() 
                   if k not in ['id', 'label', 'type']}
            )
            nodes_added += 1
        
        # Add edges with optional weights
        edges_added = 0
        edges_skipped = 0
        
        for edge in snapshot.edges:
            source = edge.get('source')
            target = edge.get('target')
            
            if source is None or target is None:
                edges_skipped += 1
                continue
            
            # Skip edges where nodes aren't in the graph
            if source not in G or target not in G:
                edges_skipped += 1
                continue
            
            # Prepare edge attributes
            edge_attrs = {}
            
            if self.weighted:
                # Try multiple weight attribute names
                weight = edge.get(self.weight_attribute)
                if weight is None:
                    weight = edge.get('value')
                if weight is None:
                    weight = edge.get('weight')
                if weight is None:
                    weight = self.default_weight
                    
                # Ensure weight is numeric
                try:
                    edge_attrs['weight'] = float(weight)
                except (TypeError, ValueError):
                    edge_attrs['weight'] = self.default_weight
            
            # Copy other edge attributes
            for k, v in edge.items():
                if k not in ['source', 'target', 'weight', 'value']:
                    edge_attrs[k] = v
            
            G.add_edge(source, target, **edge_attrs)
            edges_added += 1
        
        logger.info(f"Graph built: {nodes_added} nodes, {edges_added} edges "
                   f"({edges_skipped} edges skipped)")
        
        return G
    
    def build_address_graph(
        self,
        snapshot: TransactionSnapshot
    ) -> nx.Graph:
        """
        Build a graph containing only address nodes.
        
        This filters out transaction nodes and creates edges directly between
        addresses that are connected through transactions.
        
        For bipartite transaction graphs (address -> tx -> address), this
        creates a projection onto the address nodes.
        
        Args:
            snapshot: The transaction snapshot
            
        Returns:
            NetworkX graph with only address nodes
        """
        # First, build full graph
        full_graph = self.build_graph(snapshot)
        
        # Get address nodes
        address_nodes = {
            node for node, data in full_graph.nodes(data=True)
            if data.get('node_type') == 'address'
        }
        
        transaction_nodes = {
            node for node, data in full_graph.nodes(data=True)
            if data.get('node_type') == 'transaction'
        }
        
        # Create address-only graph
        if self.directed:
            address_graph = nx.DiGraph()
        else:
            address_graph = nx.Graph()
        
        # Add address nodes
        for node in address_nodes:
            address_graph.add_node(node, **full_graph.nodes[node])
        
        # For each transaction, connect its input and output addresses
        for tx_node in transaction_nodes:
            # Get all neighbors (addresses connected to this transaction)
            neighbors = list(full_graph.neighbors(tx_node))
            
            # In a bipartite graph, create edges between all pairs of addresses
            # connected through this transaction
            for i, addr1 in enumerate(neighbors):
                if addr1 not in address_nodes:
                    continue
                for addr2 in neighbors[i + 1:]:
                    if addr2 not in address_nodes:
                        continue
                    
                    # Combine weights if edge exists
                    if address_graph.has_edge(addr1, addr2):
                        if self.weighted:
                            current_weight = address_graph[addr1][addr2].get('weight', 0)
                            address_graph[addr1][addr2]['weight'] = current_weight + 1
                    else:
                        edge_attrs = {'weight': 1.0} if self.weighted else {}
                        address_graph.add_edge(addr1, addr2, **edge_attrs)
        
        # Also add direct address-to-address edges
        for u, v, data in full_graph.edges(data=True):
            if u in address_nodes and v in address_nodes:
                if address_graph.has_edge(u, v):
                    if self.weighted:
                        current_weight = address_graph[u][v].get('weight', 0)
                        new_weight = data.get('weight', 1.0)
                        address_graph[u][v]['weight'] = current_weight + new_weight
                else:
                    address_graph.add_edge(u, v, **data)
        
        logger.info(f"Address graph built: {address_graph.number_of_nodes()} nodes, "
                   f"{address_graph.number_of_edges()} edges")
        
        return address_graph
    
    def build_subgraph(
        self,
        snapshot: TransactionSnapshot,
        node_ids: Set[str]
    ) -> nx.Graph:
        """
        Build a subgraph containing only specified nodes.
        
        Args:
            snapshot: The transaction snapshot
            node_ids: Set of node IDs to include
            
        Returns:
            NetworkX graph containing only the specified nodes
        """
        return self.build_graph(snapshot, node_filter=node_ids)
    
    def get_graph_statistics(self, G: nx.Graph) -> Dict[str, Any]:
        """
        Compute basic statistics about a graph.
        
        Args:
            G: NetworkX graph
            
        Returns:
            Dictionary of graph statistics
        """
        stats = {
            'num_nodes': G.number_of_nodes(),
            'num_edges': G.number_of_edges(),
            'is_directed': G.is_directed(),
        }
        
        if G.number_of_nodes() > 0:
            stats['density'] = nx.density(G)
            
            if not G.is_directed():
                stats['is_connected'] = nx.is_connected(G)
                if stats['is_connected']:
                    stats['diameter'] = nx.diameter(G)
                stats['num_connected_components'] = nx.number_connected_components(G)
            else:
                stats['is_weakly_connected'] = nx.is_weakly_connected(G)
                stats['num_weakly_connected_components'] = (
                    nx.number_weakly_connected_components(G)
                )
            
            # Degree statistics
            degrees = [d for _, d in G.degree()]
            if degrees:
                stats['avg_degree'] = sum(degrees) / len(degrees)
                stats['max_degree'] = max(degrees)
                stats['min_degree'] = min(degrees)
        
        return stats
    
    def ensure_connected_for_community_detection(
        self,
        G: nx.Graph
    ) -> nx.Graph:
        """
        Return the largest connected component for community detection.
        
        Many community detection algorithms require connected graphs.
        This method extracts the largest connected component.
        
        Args:
            G: Input graph (may be disconnected)
            
        Returns:
            Largest connected component as a new graph
        """
        if G.is_directed():
            # Use weakly connected components for directed graphs
            largest_cc = max(nx.weakly_connected_components(G), key=len)
        else:
            largest_cc = max(nx.connected_components(G), key=len)
        
        subgraph = G.subgraph(largest_cc).copy()
        
        original_size = G.number_of_nodes()
        new_size = subgraph.number_of_nodes()
        
        if new_size < original_size:
            logger.warning(
                f"Extracted largest connected component: "
                f"{new_size}/{original_size} nodes ({100*new_size/original_size:.1f}%)"
            )
        
        return subgraph
