"""
Transition Detector Module for Community Evolution Analysis

This module identifies community-level transitions between temporal snapshots:
- Community splits (one T1 community → multiple T2 communities)
- Community merges (multiple T1 communities → one T2 community)
- Community emergence (new T2 communities with no T1 antecedent)
- Community dissolution (T1 communities with no T2 successor)

Mathematical Context:
    Given overlap matrix M where M[i][j] = |C1_i ∩ C2_j|:
    
    Split Detection:
        Community i at T1 splits if argmax_j(M[i][j]) is not unique
        and multiple T2 communities share significant overlap with i.
    
    Merge Detection:
        Community j at T2 is a merge if argmax_i(M[i][j]) is not unique
        and multiple T1 communities share significant overlap with j.
    
    Emergence:
        T2 community j emerged if max_i(M[i][j]) / |C2_j| < threshold
        (i.e., most of its members are new or from multiple small sources)
    
    Dissolution:
        T1 community i dissolved if max_j(M[i][j]) / |C1_i| < threshold
        (i.e., its members dispersed across T2 or departed)
"""

import logging
from typing import Dict, List, Any, Optional, Set, Tuple
from dataclasses import dataclass, field
import numpy as np

from .temporal_comparator import TemporalComparisonResult
from .community_detector import CommunityResult

logger = logging.getLogger(__name__)


@dataclass
class CommunitySplit:
    """
    Represents a community split event.
    
    Attributes:
        source_community: The T1 community that split
        target_communities: List of T2 communities formed from the split
        overlap_counts: Number of nodes from source that went to each target
        split_ratio: Proportion of source community that split off
    """
    source_community: int
    target_communities: List[int]
    overlap_counts: Dict[int, int]
    split_ratio: float
    
    @property
    def num_splits(self) -> int:
        """Number of resulting communities."""
        return len(self.target_communities)


@dataclass
class CommunityMerge:
    """
    Represents a community merge event.
    
    Attributes:
        source_communities: The T1 communities that merged
        target_community: The T2 community formed from the merge
        overlap_counts: Number of nodes from each source that joined target
        merge_ratio: Proportion of target made up from merging sources
    """
    source_communities: List[int]
    target_community: int
    overlap_counts: Dict[int, int]
    merge_ratio: float
    
    @property
    def num_merged(self) -> int:
        """Number of communities that merged."""
        return len(self.source_communities)


@dataclass
class CommunityEmergence:
    """
    Represents a new community that emerged at T2.
    
    Attributes:
        community_id: The new T2 community ID
        size: Number of nodes in the new community
        sources: Dict mapping source T1 communities to overlap counts
        emergence_ratio: Proportion of members that are "new" (not from any dominant source)
    """
    community_id: int
    size: int
    sources: Dict[int, int]
    emergence_ratio: float
    
    @property
    def is_completely_new(self) -> bool:
        """True if no nodes from T1 are in this community."""
        return sum(self.sources.values()) == 0


@dataclass
class CommunityDissolution:
    """
    Represents a community that dissolved from T1.
    
    Attributes:
        community_id: The dissolved T1 community ID
        size: Original size of the community
        destinations: Dict mapping destination T2 communities to overlap counts
        dissolution_ratio: Proportion of members that "dispersed"
    """
    community_id: int
    size: int
    destinations: Dict[int, int]
    dissolution_ratio: float
    
    @property
    def is_completely_dissolved(self) -> bool:
        """True if all nodes left the snapshot (not just moved to other communities)."""
        return sum(self.destinations.values()) == 0


@dataclass
class TransitionAnalysisResult:
    """
    Complete result of transition detection analysis.
    
    Attributes:
        splits: List of detected community splits
        merges: List of detected community merges
        emergences: List of newly emerged communities
        dissolutions: List of dissolved communities
        stable_communities: List of communities that remained stable
        transition_summary: Dict with summary statistics
    """
    splits: List[CommunitySplit]
    merges: List[CommunityMerge]
    emergences: List[CommunityEmergence]
    dissolutions: List[CommunityDissolution]
    stable_communities: List[Tuple[int, int]]  # (T1_id, T2_id) pairs
    transition_summary: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Compute summary statistics."""
        self.transition_summary = {
            'num_splits': len(self.splits),
            'num_merges': len(self.merges),
            'num_emergences': len(self.emergences),
            'num_dissolutions': len(self.dissolutions),
            'num_stable': len(self.stable_communities),
            'total_transitions': (len(self.splits) + len(self.merges) + 
                                len(self.emergences) + len(self.dissolutions))
        }
    
    @property
    def has_changes(self) -> bool:
        """True if any transitions were detected."""
        return self.transition_summary['total_transitions'] > 0


class TransitionDetector:
    """
    Detects community-level transitions between temporal snapshots.
    
    This class analyzes the overlap matrix to identify:
    - Splits: One community dividing into multiple
    - Merges: Multiple communities combining into one
    - Emergences: New communities appearing
    - Dissolutions: Communities disappearing
    
    Usage:
        detector = TransitionDetector(
            split_threshold=0.3,
            merge_threshold=0.3,
            emergence_threshold=0.5,
            dissolution_threshold=0.5
        )
        result = detector.detect(comparison_result, result_t1, result_t2)
        
        print(f"Detected {len(result.splits)} splits")
        print(f"Detected {len(result.merges)} merges")
    """
    
    def __init__(
        self,
        split_threshold: float = 0.25,
        merge_threshold: float = 0.25,
        emergence_threshold: float = 0.5,
        dissolution_threshold: float = 0.5,
        min_community_size: int = 2
    ):
        """
        Initialize the transition detector.
        
        Args:
            split_threshold: Minimum proportion of a T1 community that must go
                           to a secondary T2 community to count as a split.
            merge_threshold: Minimum proportion of a T2 community that must come
                           from a secondary T1 community to count as a merge.
            emergence_threshold: Maximum overlap proportion with any T1 community
                               for a T2 community to be considered "emerged".
            dissolution_threshold: Maximum overlap proportion with any T2 community
                                  for a T1 community to be considered "dissolved".
            min_community_size: Minimum community size to consider for transitions.
        """
        self.split_threshold = split_threshold
        self.merge_threshold = merge_threshold
        self.emergence_threshold = emergence_threshold
        self.dissolution_threshold = dissolution_threshold
        self.min_community_size = min_community_size
    
    def detect(
        self,
        comparison: TemporalComparisonResult,
        result_t1: CommunityResult,
        result_t2: CommunityResult
    ) -> TransitionAnalysisResult:
        """
        Detect all community transitions between snapshots.
        
        Args:
            comparison: Result from TemporalComparator.compare()
            result_t1: Community detection result at T1
            result_t2: Community detection result at T2
            
        Returns:
            TransitionAnalysisResult with all detected transitions
        """
        logger.info("Detecting community transitions between T1 and T2")
        
        overlap_matrix = comparison.overlap_matrix
        mapping_t1 = comparison.community_mapping_t1
        mapping_t2 = comparison.community_mapping_t2
        
        # Get community sizes
        sizes_t1 = {i: overlap_matrix[i].sum() for i in range(overlap_matrix.shape[0])}
        sizes_t2 = {j: overlap_matrix[:, j].sum() for j in range(overlap_matrix.shape[1])}
        
        # Detect each type of transition
        splits = self._detect_splits(overlap_matrix, sizes_t1, mapping_t1, mapping_t2)
        merges = self._detect_merges(overlap_matrix, sizes_t2, mapping_t1, mapping_t2)
        emergences = self._detect_emergences(
            overlap_matrix, sizes_t2, mapping_t2, result_t2
        )
        dissolutions = self._detect_dissolutions(
            overlap_matrix, sizes_t1, mapping_t1, result_t1
        )
        stable = self._detect_stable_communities(
            overlap_matrix, sizes_t1, sizes_t2, mapping_t1, mapping_t2
        )
        
        result = TransitionAnalysisResult(
            splits=splits,
            merges=merges,
            emergences=emergences,
            dissolutions=dissolutions,
            stable_communities=stable
        )
        
        logger.info(f"Transition detection complete: {result.transition_summary}")
        
        return result
    
    def _detect_splits(
        self,
        overlap_matrix: np.ndarray,
        sizes_t1: Dict[int, int],
        mapping_t1: Dict[int, int],
        mapping_t2: Dict[int, int]
    ) -> List[CommunitySplit]:
        """
        Detect community splits.
        
        A split occurs when a T1 community maps to multiple T2 communities
        with significant overlap.
        """
        splits = []
        
        n_t1 = overlap_matrix.shape[0]
        n_t2 = overlap_matrix.shape[1]
        
        for i in range(n_t1):
            size_t1 = sizes_t1[i]
            
            if size_t1 < self.min_community_size:
                continue
            
            # Get overlaps with all T2 communities
            overlaps = overlap_matrix[i, :]
            
            # Find T2 communities with significant overlap
            significant_targets = []
            for j in range(n_t2):
                if size_t1 > 0 and overlaps[j] / size_t1 >= self.split_threshold:
                    significant_targets.append((j, overlaps[j]))
            
            # Split if more than one significant target
            if len(significant_targets) > 1:
                target_communities = [mapping_t2[j] for j, _ in significant_targets]
                overlap_counts = {mapping_t2[j]: int(count) 
                                for j, count in significant_targets}
                
                # Calculate split ratio (proportion that went to secondary targets)
                max_overlap = max(count for _, count in significant_targets)
                secondary_overlap = sum(count for _, count in significant_targets) - max_overlap
                split_ratio = secondary_overlap / size_t1 if size_t1 > 0 else 0
                
                splits.append(CommunitySplit(
                    source_community=mapping_t1[i],
                    target_communities=target_communities,
                    overlap_counts=overlap_counts,
                    split_ratio=split_ratio
                ))
        
        logger.debug(f"Detected {len(splits)} splits")
        return splits
    
    def _detect_merges(
        self,
        overlap_matrix: np.ndarray,
        sizes_t2: Dict[int, int],
        mapping_t1: Dict[int, int],
        mapping_t2: Dict[int, int]
    ) -> List[CommunityMerge]:
        """
        Detect community merges.
        
        A merge occurs when a T2 community receives significant nodes from
        multiple T1 communities.
        """
        merges = []
        
        n_t1 = overlap_matrix.shape[0]
        n_t2 = overlap_matrix.shape[1]
        
        for j in range(n_t2):
            size_t2 = sizes_t2[j]
            
            if size_t2 < self.min_community_size:
                continue
            
            # Get overlaps with all T1 communities
            overlaps = overlap_matrix[:, j]
            
            # Find T1 communities with significant overlap
            significant_sources = []
            for i in range(n_t1):
                if size_t2 > 0 and overlaps[i] / size_t2 >= self.merge_threshold:
                    significant_sources.append((i, overlaps[i]))
            
            # Merge if more than one significant source
            if len(significant_sources) > 1:
                source_communities = [mapping_t1[i] for i, _ in significant_sources]
                overlap_counts = {mapping_t1[i]: int(count) 
                                for i, count in significant_sources}
                
                # Calculate merge ratio (proportion from merging sources)
                total_merged = sum(count for _, count in significant_sources)
                merge_ratio = total_merged / size_t2 if size_t2 > 0 else 0
                
                merges.append(CommunityMerge(
                    source_communities=source_communities,
                    target_community=mapping_t2[j],
                    overlap_counts=overlap_counts,
                    merge_ratio=merge_ratio
                ))
        
        logger.debug(f"Detected {len(merges)} merges")
        return merges
    
    def _detect_emergences(
        self,
        overlap_matrix: np.ndarray,
        sizes_t2: Dict[int, int],
        mapping_t2: Dict[int, int],
        result_t2: CommunityResult
    ) -> List[CommunityEmergence]:
        """
        Detect newly emerged communities.
        
        A community emerged if it has no dominant T1 antecedent
        (max overlap proportion < emergence_threshold).
        """
        emergences = []
        
        n_t1 = overlap_matrix.shape[0]
        n_t2 = overlap_matrix.shape[1]
        
        for j in range(n_t2):
            actual_size = len(result_t2.communities.get(mapping_t2[j], []))
            
            if actual_size < self.min_community_size:
                continue
            
            # Get overlaps with all T1 communities
            overlaps = overlap_matrix[:, j]
            total_overlap = overlaps.sum()
            max_overlap = overlaps.max() if len(overlaps) > 0 else 0
            
            # Calculate emergence ratio (proportion of nodes NOT from dominant source)
            # Also consider nodes that weren't in T1 at all
            nodes_from_t1 = total_overlap
            new_nodes = actual_size - nodes_from_t1
            
            # Emergence if max overlap is small relative to community size
            if actual_size > 0:
                max_overlap_ratio = max_overlap / actual_size
                
                if max_overlap_ratio < self.emergence_threshold:
                    sources = {}
                    for i in range(n_t1):
                        if overlaps[i] > 0:
                            sources[mapping_t2.get(i, i)] = int(overlaps[i])
                    
                    emergence_ratio = 1.0 - max_overlap_ratio
                    
                    emergences.append(CommunityEmergence(
                        community_id=mapping_t2[j],
                        size=actual_size,
                        sources=sources,
                        emergence_ratio=emergence_ratio
                    ))
        
        logger.debug(f"Detected {len(emergences)} emergences")
        return emergences
    
    def _detect_dissolutions(
        self,
        overlap_matrix: np.ndarray,
        sizes_t1: Dict[int, int],
        mapping_t1: Dict[int, int],
        result_t1: CommunityResult
    ) -> List[CommunityDissolution]:
        """
        Detect dissolved communities.
        
        A community dissolved if it has no dominant T2 successor
        (max overlap proportion < dissolution_threshold).
        """
        dissolutions = []
        
        n_t1 = overlap_matrix.shape[0]
        n_t2 = overlap_matrix.shape[1]
        
        for i in range(n_t1):
            actual_size = len(result_t1.communities.get(mapping_t1[i], []))
            
            if actual_size < self.min_community_size:
                continue
            
            # Get overlaps with all T2 communities
            overlaps = overlap_matrix[i, :]
            total_overlap = overlaps.sum()
            max_overlap = overlaps.max() if len(overlaps) > 0 else 0
            
            # Calculate dissolution ratio
            if actual_size > 0:
                max_overlap_ratio = max_overlap / actual_size
                
                if max_overlap_ratio < self.dissolution_threshold:
                    destinations = {}
                    for j in range(n_t2):
                        if overlaps[j] > 0:
                            destinations[mapping_t1.get(j, j)] = int(overlaps[j])
                    
                    dissolution_ratio = 1.0 - max_overlap_ratio
                    
                    dissolutions.append(CommunityDissolution(
                        community_id=mapping_t1[i],
                        size=actual_size,
                        destinations=destinations,
                        dissolution_ratio=dissolution_ratio
                    ))
        
        logger.debug(f"Detected {len(dissolutions)} dissolutions")
        return dissolutions
    
    def _detect_stable_communities(
        self,
        overlap_matrix: np.ndarray,
        sizes_t1: Dict[int, int],
        sizes_t2: Dict[int, int],
        mapping_t1: Dict[int, int],
        mapping_t2: Dict[int, int]
    ) -> List[Tuple[int, int]]:
        """
        Detect stable communities that persisted with minimal change.
        
        A community is stable if there's a strong bidirectional correspondence:
        - Most of T1 community i went to T2 community j
        - Most of T2 community j came from T1 community i
        """
        stable = []
        stability_threshold = 0.7  # 70% overlap in both directions
        
        n_t1 = overlap_matrix.shape[0]
        n_t2 = overlap_matrix.shape[1]
        
        for i in range(n_t1):
            size_t1 = sizes_t1[i]
            if size_t1 < self.min_community_size:
                continue
            
            # Find best T2 match
            best_j = overlap_matrix[i, :].argmax() if n_t2 > 0 else -1
            
            if best_j < 0:
                continue
            
            overlap = overlap_matrix[i, best_j]
            size_t2 = sizes_t2[best_j]
            
            if size_t2 < self.min_community_size:
                continue
            
            # Check bidirectional stability
            forward_ratio = overlap / size_t1 if size_t1 > 0 else 0
            backward_ratio = overlap / size_t2 if size_t2 > 0 else 0
            
            # Also check that T1 community i is the best source for T2 community j
            best_i_for_j = overlap_matrix[:, best_j].argmax() if n_t1 > 0 else -1
            
            if (forward_ratio >= stability_threshold and 
                backward_ratio >= stability_threshold and
                best_i_for_j == i):
                stable.append((mapping_t1[i], mapping_t2[best_j]))
        
        logger.debug(f"Detected {len(stable)} stable communities")
        return stable
    
    def get_transition_graph(
        self,
        transitions: TransitionAnalysisResult
    ) -> Dict[str, Any]:
        """
        Generate a graph representation of community transitions.
        
        Useful for visualizing the evolution of communities.
        
        Args:
            transitions: Result from detect()
            
        Returns:
            Dict with 'nodes' and 'edges' for visualization
        """
        nodes = []
        edges = []
        
        # Track all community IDs
        t1_communities = set()
        t2_communities = set()
        
        # Add nodes and edges for splits
        for split in transitions.splits:
            t1_communities.add(split.source_community)
            for target in split.target_communities:
                t2_communities.add(target)
                overlap = split.overlap_counts.get(target, 0)
                edges.append({
                    'source': f"T1_{split.source_community}",
                    'target': f"T2_{target}",
                    'weight': overlap,
                    'type': 'split'
                })
        
        # Add nodes and edges for merges
        for merge in transitions.merges:
            t2_communities.add(merge.target_community)
            for source in merge.source_communities:
                t1_communities.add(source)
                overlap = merge.overlap_counts.get(source, 0)
                edges.append({
                    'source': f"T1_{source}",
                    'target': f"T2_{merge.target_community}",
                    'weight': overlap,
                    'type': 'merge'
                })
        
        # Add stable community edges
        for t1_id, t2_id in transitions.stable_communities:
            t1_communities.add(t1_id)
            t2_communities.add(t2_id)
            edges.append({
                'source': f"T1_{t1_id}",
                'target': f"T2_{t2_id}",
                'type': 'stable'
            })
        
        # Add emergence nodes
        for emergence in transitions.emergences:
            t2_communities.add(emergence.community_id)
        
        # Add dissolution nodes
        for dissolution in transitions.dissolutions:
            t1_communities.add(dissolution.community_id)
        
        # Create node list
        for c_id in t1_communities:
            nodes.append({
                'id': f"T1_{c_id}",
                'community_id': c_id,
                'snapshot': 'T1'
            })
        
        for c_id in t2_communities:
            nodes.append({
                'id': f"T2_{c_id}",
                'community_id': c_id,
                'snapshot': 'T2'
            })
        
        return {'nodes': nodes, 'edges': edges}
