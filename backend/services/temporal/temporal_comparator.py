"""
Temporal Comparator Module for Community Evolution Analysis

This module provides tools for comparing community structures between two 
temporal snapshots using Normalized Mutual Information (NMI) and community
overlap matrices.

Mathematical Context:
    Given two partitions C1 and C2 of a common node set V:
    
    NMI (Normalized Mutual Information):
        NMI(C1, C2) = 2 * I(C1; C2) / (H(C1) + H(C2))
    
    where:
    - I(C1; C2) is the mutual information between partitions
    - H(C1), H(C2) are the entropies of individual partitions
    
    NMI ∈ [0, 1]:
    - NMI = 1: Partitions are identical
    - NMI = 0: Partitions are completely independent
    
    Overlap Matrix M:
        M[i][j] = |C1_i ∩ C2_j|
    
    The normalized overlap matrix provides transition probabilities between
    communities across time points.
"""

import logging
from typing import Dict, List, Any, Optional, Tuple, Set
from dataclasses import dataclass, field
import numpy as np

from .community_detector import CommunityResult

logger = logging.getLogger(__name__)


@dataclass
class TemporalComparisonResult:
    """
    Result of comparing community structures between two snapshots.
    
    Attributes:
        nmi_score: Normalized Mutual Information between partitions
        overlap_matrix: Raw overlap matrix M[i][j] = |C1_i ∩ C2_j|
        normalized_overlap_matrix: Row-normalized overlap matrix
        num_communities_t1: Number of communities at T1
        num_communities_t2: Number of communities at T2
        delta_communities: Change in number of communities (T2 - T1)
        common_nodes: Set of node IDs present in both partitions
        total_common_nodes: Count of common nodes
        nodes_unchanged: Nodes that stayed in equivalent communities
        nodes_changed: Nodes that changed communities
        percentage_unchanged: Percentage of nodes with stable community membership
        percentage_changed: Percentage of nodes that changed communities
        community_mapping_t1: Maps T1 community ID to original community ID
        community_mapping_t2: Maps T2 community ID to original community ID
    """
    nmi_score: float
    overlap_matrix: np.ndarray
    normalized_overlap_matrix: np.ndarray
    num_communities_t1: int
    num_communities_t2: int
    delta_communities: int
    common_nodes: Set[str]
    total_common_nodes: int
    nodes_unchanged: int
    nodes_changed: int
    percentage_unchanged: float
    percentage_changed: float
    community_mapping_t1: Dict[int, int] = field(default_factory=dict)
    community_mapping_t2: Dict[int, int] = field(default_factory=dict)
    
    def get_overlap_for_communities(
        self, 
        t1_community: int, 
        t2_community: int
    ) -> int:
        """Get the overlap count between specific communities."""
        if t1_community >= self.overlap_matrix.shape[0]:
            return 0
        if t2_community >= self.overlap_matrix.shape[1]:
            return 0
        return int(self.overlap_matrix[t1_community][t2_community])
    
    def get_transition_probability(
        self,
        t1_community: int,
        t2_community: int
    ) -> float:
        """Get the probability that a node from T1 community transitions to T2 community."""
        if t1_community >= self.normalized_overlap_matrix.shape[0]:
            return 0.0
        if t2_community >= self.normalized_overlap_matrix.shape[1]:
            return 0.0
        return float(self.normalized_overlap_matrix[t1_community][t2_community])


class TemporalComparator:
    """
    Compares community structures between two temporal snapshots.
    
    This class computes:
    - Normalized Mutual Information (NMI) for global similarity
    - Community overlap matrix for detailed comparison
    - Node-level stability metrics
    
    Usage:
        comparator = TemporalComparator()
        result = comparator.compare(result_t1, result_t2)
        
        print(f"NMI Score: {result.nmi_score:.4f}")
        print(f"Nodes changed: {result.percentage_changed:.1f}%")
    """
    
    def __init__(self, nmi_method: str = "arithmetic"):
        """
        Initialize the temporal comparator.
        
        Args:
            nmi_method: Normalization method for NMI ('arithmetic', 'geometric', 'min', 'max')
        """
        self.nmi_method = nmi_method
    
    def compare(
        self,
        result_t1: CommunityResult,
        result_t2: CommunityResult,
        common_nodes: Optional[Set[str]] = None
    ) -> TemporalComparisonResult:
        """
        Compare two community detection results.
        
        Args:
            result_t1: Community detection result at time T1
            result_t2: Community detection result at time T2
            common_nodes: Optional set of nodes to compare. If None, uses intersection.
            
        Returns:
            TemporalComparisonResult with all comparison metrics
        """
        logger.info("Comparing community structures between T1 and T2")
        
        # Determine common nodes
        if common_nodes is None:
            nodes_t1 = set(result_t1.partition.keys())
            nodes_t2 = set(result_t2.partition.keys())
            common_nodes = nodes_t1 & nodes_t2
        
        if not common_nodes:
            logger.warning("No common nodes between snapshots")
            return self._empty_comparison_result(result_t1, result_t2)
        
        total_common = len(common_nodes)
        logger.info(f"Comparing partitions on {total_common} common nodes")
        
        # Build label vectors for common nodes only
        partition_t1 = {n: result_t1.partition[n] for n in common_nodes 
                       if n in result_t1.partition}
        partition_t2 = {n: result_t2.partition[n] for n in common_nodes 
                       if n in result_t2.partition}
        
        # Compute NMI
        nmi_score = self._compute_nmi(partition_t1, partition_t2)
        
        # Build overlap matrix
        overlap_matrix, normalized_matrix, mapping_t1, mapping_t2 = (
            self._build_overlap_matrix(partition_t1, partition_t2)
        )
        
        # Compute node-level stability
        nodes_unchanged, nodes_changed = self._compute_node_stability(
            partition_t1, partition_t2, mapping_t1, mapping_t2
        )
        
        percentage_unchanged = (nodes_unchanged / total_common * 100) if total_common > 0 else 0.0
        percentage_changed = (nodes_changed / total_common * 100) if total_common > 0 else 0.0
        
        num_communities_t1 = len(set(partition_t1.values()))
        num_communities_t2 = len(set(partition_t2.values()))
        
        return TemporalComparisonResult(
            nmi_score=nmi_score,
            overlap_matrix=overlap_matrix,
            normalized_overlap_matrix=normalized_matrix,
            num_communities_t1=num_communities_t1,
            num_communities_t2=num_communities_t2,
            delta_communities=num_communities_t2 - num_communities_t1,
            common_nodes=common_nodes,
            total_common_nodes=total_common,
            nodes_unchanged=nodes_unchanged,
            nodes_changed=nodes_changed,
            percentage_unchanged=percentage_unchanged,
            percentage_changed=percentage_changed,
            community_mapping_t1=mapping_t1,
            community_mapping_t2=mapping_t2
        )
    
    def _compute_nmi(
        self,
        partition_t1: Dict[str, int],
        partition_t2: Dict[str, int]
    ) -> float:
        """
        Compute Normalized Mutual Information between two partitions.
        
        Uses sklearn's normalized_mutual_info_score for accurate computation.
        
        Args:
            partition_t1: Node -> community mapping at T1
            partition_t2: Node -> community mapping at T2
            
        Returns:
            NMI score in [0, 1]
        """
        from sklearn.metrics import normalized_mutual_info_score
        
        # Get common nodes (should already be common, but double-check)
        common_nodes = set(partition_t1.keys()) & set(partition_t2.keys())
        
        if len(common_nodes) < 2:
            logger.warning("Less than 2 common nodes, NMI undefined")
            return 0.0
        
        # Create aligned label arrays
        nodes = sorted(common_nodes)
        labels_t1 = [partition_t1[n] for n in nodes]
        labels_t2 = [partition_t2[n] for n in nodes]
        
        # Handle single-community edge case
        if len(set(labels_t1)) == 1 and len(set(labels_t2)) == 1:
            # Both partitions have single community (perfect match)
            return 1.0
        
        if len(set(labels_t1)) == 1 or len(set(labels_t2)) == 1:
            # One partition has single community (degenerate case)
            logger.warning("One partition has only one community, NMI may be misleading")
        
        # Compute NMI
        nmi = normalized_mutual_info_score(
            labels_t1, 
            labels_t2, 
            average_method=self.nmi_method
        )
        
        return float(nmi)
    
    def _build_overlap_matrix(
        self,
        partition_t1: Dict[str, int],
        partition_t2: Dict[str, int]
    ) -> Tuple[np.ndarray, np.ndarray, Dict[int, int], Dict[int, int]]:
        """
        Build the community overlap matrix.
        
        M[i][j] = number of nodes in community i at T1 AND community j at T2
        
        Args:
            partition_t1: Node -> community mapping at T1
            partition_t2: Node -> community mapping at T2
            
        Returns:
            Tuple of (raw_matrix, normalized_matrix, t1_mapping, t2_mapping)
            where mappings convert internal indices to original community IDs
        """
        # Get unique community IDs and create consecutive index mappings
        communities_t1 = sorted(set(partition_t1.values()))
        communities_t2 = sorted(set(partition_t2.values()))
        
        # Map original community IDs to matrix indices
        t1_to_idx = {c: i for i, c in enumerate(communities_t1)}
        t2_to_idx = {c: i for i, c in enumerate(communities_t2)}
        
        # Reverse mappings for output
        idx_to_t1 = {i: c for c, i in t1_to_idx.items()}
        idx_to_t2 = {i: c for c, i in t2_to_idx.items()}
        
        n_t1 = len(communities_t1)
        n_t2 = len(communities_t2)
        
        # Initialize overlap matrix
        overlap = np.zeros((n_t1, n_t2), dtype=np.int32)
        
        # Compute overlaps
        common_nodes = set(partition_t1.keys()) & set(partition_t2.keys())
        
        for node in common_nodes:
            c1 = partition_t1[node]
            c2 = partition_t2[node]
            i = t1_to_idx[c1]
            j = t2_to_idx[c2]
            overlap[i][j] += 1
        
        # Create row-normalized matrix (probability of T1->T2 transition)
        row_sums = overlap.sum(axis=1, keepdims=True)
        row_sums = np.where(row_sums == 0, 1, row_sums)  # Avoid division by zero
        normalized = overlap.astype(np.float64) / row_sums
        
        return overlap, normalized, idx_to_t1, idx_to_t2
    
    def _compute_node_stability(
        self,
        partition_t1: Dict[str, int],
        partition_t2: Dict[str, int],
        mapping_t1: Dict[int, int],
        mapping_t2: Dict[int, int]
    ) -> Tuple[int, int]:
        """
        Compute how many nodes stayed in "equivalent" communities.
        
        Since community IDs may not be comparable across time, we use the
        overlap matrix to find maximum-overlap correspondence.
        
        Args:
            partition_t1: Node -> community mapping at T1
            partition_t2: Node -> community mapping at T2
            mapping_t1: Matrix index -> T1 community ID
            mapping_t2: Matrix index -> T2 community ID
            
        Returns:
            Tuple of (nodes_unchanged, nodes_changed)
        """
        common_nodes = set(partition_t1.keys()) & set(partition_t2.keys())
        
        if not common_nodes:
            return 0, 0
        
        # Build a simple stability measure:
        # A node is "unchanged" if it's in the same set of nodes as before
        # This is determined by checking if the majority of its T1 community
        # members are also in its T2 community
        
        # Group nodes by T1 community
        t1_communities = {}
        for node, comm in partition_t1.items():
            if node in common_nodes:
                t1_communities.setdefault(comm, set()).add(node)
        
        # Group nodes by T2 community
        t2_communities = {}
        for node, comm in partition_t2.items():
            if node in common_nodes:
                t2_communities.setdefault(comm, set()).add(node)
        
        # Find best T2 match for each T1 community (maximum overlap)
        t1_to_t2_best = {}
        for t1_comm, t1_nodes in t1_communities.items():
            best_overlap = 0
            best_t2 = None
            for t2_comm, t2_nodes in t2_communities.items():
                overlap = len(t1_nodes & t2_nodes)
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_t2 = t2_comm
            t1_to_t2_best[t1_comm] = best_t2
        
        # Count nodes that stayed with their community's best match
        nodes_unchanged = 0
        nodes_changed = 0
        
        for node in common_nodes:
            t1_comm = partition_t1[node]
            t2_comm = partition_t2[node]
            expected_t2 = t1_to_t2_best.get(t1_comm)
            
            if expected_t2 is not None and t2_comm == expected_t2:
                nodes_unchanged += 1
            else:
                nodes_changed += 1
        
        return nodes_unchanged, nodes_changed
    
    def _empty_comparison_result(
        self,
        result_t1: CommunityResult,
        result_t2: CommunityResult
    ) -> TemporalComparisonResult:
        """Return empty comparison result for edge cases."""
        return TemporalComparisonResult(
            nmi_score=0.0,
            overlap_matrix=np.array([[]]),
            normalized_overlap_matrix=np.array([[]]),
            num_communities_t1=result_t1.num_communities,
            num_communities_t2=result_t2.num_communities,
            delta_communities=result_t2.num_communities - result_t1.num_communities,
            common_nodes=set(),
            total_common_nodes=0,
            nodes_unchanged=0,
            nodes_changed=0,
            percentage_unchanged=0.0,
            percentage_changed=0.0
        )
    
    def compute_adjusted_rand_index(
        self,
        partition_t1: Dict[str, int],
        partition_t2: Dict[str, int]
    ) -> float:
        """
        Compute Adjusted Rand Index (ARI) as an alternative to NMI.
        
        ARI measures the similarity between two clusterings, adjusted for chance.
        ARI ∈ [-1, 1]:
        - ARI = 1: Perfect match
        - ARI = 0: Random clustering
        - ARI < 0: Worse than random
        
        Args:
            partition_t1: Node -> community mapping at T1
            partition_t2: Node -> community mapping at T2
            
        Returns:
            ARI score
        """
        from sklearn.metrics import adjusted_rand_score
        
        common_nodes = set(partition_t1.keys()) & set(partition_t2.keys())
        
        if len(common_nodes) < 2:
            return 0.0
        
        nodes = sorted(common_nodes)
        labels_t1 = [partition_t1[n] for n in nodes]
        labels_t2 = [partition_t2[n] for n in nodes]
        
        return float(adjusted_rand_score(labels_t1, labels_t2))
    
    def compute_variation_of_information(
        self,
        partition_t1: Dict[str, int],
        partition_t2: Dict[str, int]
    ) -> float:
        """
        Compute Variation of Information (VI) between partitions.
        
        VI = H(C1|C2) + H(C2|C1)
        
        Lower VI indicates more similar partitions.
        VI = 0 means identical partitions.
        
        Args:
            partition_t1: Node -> community mapping at T1
            partition_t2: Node -> community mapping at T2
            
        Returns:
            VI score (lower = more similar)
        """
        from sklearn.metrics import mutual_info_score
        from scipy.stats import entropy
        import numpy as np
        
        common_nodes = set(partition_t1.keys()) & set(partition_t2.keys())
        
        if len(common_nodes) < 2:
            return 0.0
        
        nodes = sorted(common_nodes)
        labels_t1 = [partition_t1[n] for n in nodes]
        labels_t2 = [partition_t2[n] for n in nodes]
        
        n = len(nodes)
        
        # Compute entropies
        _, counts_t1 = np.unique(labels_t1, return_counts=True)
        _, counts_t2 = np.unique(labels_t2, return_counts=True)
        
        h_t1 = entropy(counts_t1, base=2)
        h_t2 = entropy(counts_t2, base=2)
        
        # Compute mutual information
        mi = mutual_info_score(labels_t1, labels_t2) / np.log(2)  # Convert to bits
        
        # VI = H(C1) + H(C2) - 2*I(C1;C2)
        vi = h_t1 + h_t2 - 2 * mi
        
        return float(max(0, vi))  # Should be non-negative, but numerical errors possible
