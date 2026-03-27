"""
Community Detection Module for Temporal Community Analysis

This module provides a unified interface for community detection algorithms.
It wraps various algorithms (Louvain, Leiden, Label Propagation, Infomap)
to ensure consistent output format for temporal comparison.

Mathematical Context:
    Given graph G = (V, E), community detection partitions V into k disjoint
    communities C = {C_1, C_2, ..., C_k} such that the modularity Q is maximized:
    
    Q = (1/2m) * Σ_{ij} [A_ij - (k_i * k_j)/(2m)] * δ(c_i, c_j)
    
    where:
    - A_ij is the adjacency matrix
    - k_i is the degree of node i  
    - m is the total number of edges
    - c_i is the community of node i
    - δ is the Kronecker delta
    
    The output partition π: V → {1, 2, ..., k} maps each node to its community.
"""

import logging
from typing import Dict, List, Any, Optional, Literal
from enum import Enum
from dataclasses import dataclass

import networkx as nx

logger = logging.getLogger(__name__)


class CommunityAlgorithm(str, Enum):
    """Supported community detection algorithms."""
    LOUVAIN = "louvain"
    LEIDEN = "leiden"
    LABEL_PROPAGATION = "label_propagation"
    INFOMAP = "infomap"


@dataclass
class CommunityResult:
    """
    Standardized result from community detection.
    
    Attributes:
        partition: Dict mapping node_id -> community_id
        communities: Dict mapping community_id -> list of node_ids
        modularity: Quality metric (higher = better community structure)
        num_communities: Total number of communities detected
        algorithm: Name of the algorithm used
        parameters: Parameters used for the algorithm
    """
    partition: Dict[str, int]
    communities: Dict[int, List[str]]
    modularity: float
    num_communities: int
    algorithm: str
    parameters: Dict[str, Any]
    
    @property
    def community_sizes(self) -> Dict[int, int]:
        """Return dictionary of community ID -> size."""
        return {k: len(v) for k, v in self.communities.items()}
    
    @property
    def avg_community_size(self) -> float:
        """Return average community size."""
        if not self.communities:
            return 0.0
        return sum(len(c) for c in self.communities.values()) / len(self.communities)
    
    def get_community_of_node(self, node_id: str) -> Optional[int]:
        """Get the community ID for a specific node."""
        return self.partition.get(node_id)
    
    def get_nodes_in_community(self, community_id: int) -> List[str]:
        """Get all nodes in a specific community."""
        return self.communities.get(community_id, [])


class CommunityDetector:
    """
    Unified interface for community detection algorithms.
    
    This class wraps various community detection implementations to provide:
    - Consistent output format (CommunityResult)
    - Deterministic behavior through seed control
    - Graceful handling of edge cases
    
    Usage:
        detector = CommunityDetector(algorithm="louvain", seed=42)
        result = detector.detect(G)
        print(f"Found {result.num_communities} communities")
    """
    
    def __init__(
        self,
        algorithm: str = "louvain",
        seed: Optional[int] = 42,
        resolution: float = 1.0,
        weight_attribute: str = "weight"
    ):
        """
        Initialize the community detector.
        
        Args:
            algorithm: Algorithm to use ('louvain', 'leiden', 'label_propagation', 'infomap')
            seed: Random seed for reproducibility. Set to None for non-deterministic.
            resolution: Resolution parameter for Louvain/Leiden (higher = smaller communities)
            weight_attribute: Edge attribute to use as weight
        """
        self.algorithm = CommunityAlgorithm(algorithm.lower())
        self.seed = seed
        self.resolution = resolution
        self.weight_attribute = weight_attribute
        
        # Validate algorithm availability
        self._check_algorithm_availability()
    
    def _check_algorithm_availability(self) -> None:
        """Check if required libraries are available for the selected algorithm."""
        if self.algorithm == CommunityAlgorithm.LOUVAIN:
            try:
                import community.community_louvain
            except ImportError:
                raise ImportError(
                    "python-louvain package required for Louvain algorithm. "
                    "Install with: pip install python-louvain"
                )
        
        elif self.algorithm == CommunityAlgorithm.LEIDEN:
            try:
                import igraph
                import leidenalg
            except ImportError:
                raise ImportError(
                    "igraph and leidenalg packages required for Leiden algorithm. "
                    "Install with: pip install python-igraph leidenalg"
                )
        
        elif self.algorithm == CommunityAlgorithm.INFOMAP:
            try:
                import infomap
            except ImportError:
                raise ImportError(
                    "infomap package required for Infomap algorithm. "
                    "Install with: pip install infomap"
                )
    
    def detect(self, G: nx.Graph) -> CommunityResult:
        """
        Run community detection on the graph.
        
        Args:
            G: NetworkX graph (should be undirected for most algorithms)
            
        Returns:
            CommunityResult with partition and metrics
            
        Raises:
            ValueError: If graph is empty or has no edges
        """
        # Input validation
        if G.number_of_nodes() == 0:
            logger.warning("Empty graph provided for community detection")
            return self._empty_result()
        
        if G.number_of_edges() == 0:
            logger.warning("Graph has no edges, assigning each node to its own community")
            return self._singleton_communities(G)
        
        logger.info(f"Running {self.algorithm.value} community detection on graph "
                   f"with {G.number_of_nodes()} nodes and {G.number_of_edges()} edges")
        
        # Dispatch to appropriate algorithm
        if self.algorithm == CommunityAlgorithm.LOUVAIN:
            return self._detect_louvain(G)
        elif self.algorithm == CommunityAlgorithm.LEIDEN:
            return self._detect_leiden(G)
        elif self.algorithm == CommunityAlgorithm.LABEL_PROPAGATION:
            return self._detect_label_propagation(G)
        elif self.algorithm == CommunityAlgorithm.INFOMAP:
            return self._detect_infomap(G)
        else:
            raise ValueError(f"Unknown algorithm: {self.algorithm}")
    
    def _detect_louvain(self, G: nx.Graph) -> CommunityResult:
        """Run Louvain community detection."""
        import community.community_louvain as community_louvain
        
        # Louvain requires undirected graph
        if G.is_directed():
            G = G.to_undirected()
            logger.info("Converted directed graph to undirected for Louvain")
        
        # Run algorithm
        partition = community_louvain.best_partition(
            G,
            weight=self.weight_attribute,
            resolution=self.resolution,
            random_state=self.seed
        )
        
        # Calculate modularity
        modularity = community_louvain.modularity(
            partition, G, weight=self.weight_attribute
        )
        
        # Convert to standard format
        communities = self._partition_to_communities(partition)
        
        return CommunityResult(
            partition=partition,
            communities=communities,
            modularity=modularity,
            num_communities=len(communities),
            algorithm="louvain",
            parameters={
                'resolution': self.resolution,
                'weight_attribute': self.weight_attribute,
                'seed': self.seed
            }
        )
    
    def _detect_leiden(self, G: nx.Graph) -> CommunityResult:
        """Run Leiden community detection."""
        import igraph as ig
        import leidenalg
        
        # Convert NetworkX to igraph
        node_list = list(G.nodes())
        node_to_idx = {node: idx for idx, node in enumerate(node_list)}
        
        ig_graph = ig.Graph()
        ig_graph.add_vertices(len(node_list))
        
        # Add node names
        for idx, node in enumerate(node_list):
            ig_graph.vs[idx]['name'] = node
        
        # Add edges
        edges = []
        weights = []
        for u, v, data in G.edges(data=True):
            edges.append((node_to_idx[u], node_to_idx[v]))
            weight = data.get(self.weight_attribute, data.get('weight', 1.0))
            weights.append(float(weight) if weight is not None else 1.0)
        
        ig_graph.add_edges(edges)
        ig_graph.es['weight'] = weights
        
        # Run Leiden
        partition = leidenalg.find_partition(
            ig_graph,
            leidenalg.RBConfigurationVertexPartition,
            weights=weights,
            resolution_parameter=self.resolution,
            seed=self.seed
        )
        
        # Get membership
        membership = partition.membership
        
        # Calculate modularity using igraph
        try:
            modularity = ig_graph.modularity(membership, weights=weights)
        except Exception:
            modularity = partition.quality() / (2 * sum(weights)) if sum(weights) > 0 else 0.0
        
        modularity = max(-0.5, min(1.0, modularity))
        
        # Convert to node ID mappings
        partition_dict = {}
        communities = {}
        
        for idx, comm_id in enumerate(membership):
            node_id = node_list[idx]
            partition_dict[node_id] = comm_id
            communities.setdefault(comm_id, []).append(node_id)
        
        return CommunityResult(
            partition=partition_dict,
            communities=communities,
            modularity=modularity,
            num_communities=len(communities),
            algorithm="leiden",
            parameters={
                'resolution': self.resolution,
                'weight_attribute': self.weight_attribute,
                'seed': self.seed
            }
        )
    
    def _detect_label_propagation(self, G: nx.Graph) -> CommunityResult:
        """Run Label Propagation community detection."""
        import random
        
        # Set seed for reproducibility
        if self.seed is not None:
            random.seed(self.seed)
        
        # Undirected graph required
        if G.is_directed():
            G = G.to_undirected()
            logger.info("Converted directed graph to undirected for Label Propagation")
        
        # Run algorithm
        communities_iter = nx.algorithms.community.asyn_lpa_communities(G)
        communities_list = list(communities_iter)
        
        # Convert to standard format
        partition_dict = {}
        communities = {}
        
        for comm_id, community_nodes in enumerate(communities_list):
            node_list = list(community_nodes)
            communities[comm_id] = node_list
            for node in node_list:
                partition_dict[node] = comm_id
        
        # Calculate modularity
        try:
            modularity = nx.algorithms.community.modularity(G, communities_list)
        except Exception:
            modularity = 0.0
        
        return CommunityResult(
            partition=partition_dict,
            communities=communities,
            modularity=modularity,
            num_communities=len(communities),
            algorithm="label_propagation",
            parameters={'seed': self.seed}
        )
    
    def _detect_infomap(self, G: nx.Graph) -> CommunityResult:
        """Run Infomap community detection."""
        import infomap
        
        # Create Infomap instance
        im = infomap.Infomap(f"--seed {self.seed}" if self.seed else "")
        
        # Build node index mapping
        node_list = list(G.nodes())
        node_to_idx = {node: idx for idx, node in enumerate(node_list)}
        
        # Add edges
        for u, v, data in G.edges(data=True):
            weight = data.get(self.weight_attribute, data.get('weight', 1.0))
            weight = float(weight) if weight is not None else 1.0
            im.add_link(node_to_idx[u], node_to_idx[v], weight)
        
        # Run algorithm
        im.run()
        
        # Extract communities
        partition_dict = {}
        communities = {}
        
        for node in im.tree:
            if node.is_leaf:
                node_id = node_list[node.node_id]
                comm_id = node.module_id
                partition_dict[node_id] = comm_id
                communities.setdefault(comm_id, []).append(node_id)
        
        # Infomap uses code length as quality metric
        # Convert to approximate modularity scale
        try:
            modularity = nx.algorithms.community.modularity(
                G.to_undirected() if G.is_directed() else G,
                [set(nodes) for nodes in communities.values()]
            )
        except Exception:
            modularity = 0.0
        
        return CommunityResult(
            partition=partition_dict,
            communities=communities,
            modularity=modularity,
            num_communities=len(communities),
            algorithm="infomap",
            parameters={
                'seed': self.seed,
                'codelength': im.codelength
            }
        )
    
    def _partition_to_communities(
        self, 
        partition: Dict[str, int]
    ) -> Dict[int, List[str]]:
        """Convert node->community partition to community->nodes mapping."""
        communities = {}
        for node_id, comm_id in partition.items():
            communities.setdefault(comm_id, []).append(node_id)
        return communities
    
    def _empty_result(self) -> CommunityResult:
        """Return empty result for edge cases."""
        return CommunityResult(
            partition={},
            communities={},
            modularity=0.0,
            num_communities=0,
            algorithm=self.algorithm.value,
            parameters={}
        )
    
    def _singleton_communities(self, G: nx.Graph) -> CommunityResult:
        """Assign each node to its own community (for graphs with no edges)."""
        partition = {node: idx for idx, node in enumerate(G.nodes())}
        communities = {idx: [node] for idx, node in enumerate(G.nodes())}
        
        return CommunityResult(
            partition=partition,
            communities=communities,
            modularity=0.0,  # No structure = 0 modularity
            num_communities=G.number_of_nodes(),
            algorithm=self.algorithm.value,
            parameters={'note': 'singleton_communities_due_to_no_edges'}
        )
