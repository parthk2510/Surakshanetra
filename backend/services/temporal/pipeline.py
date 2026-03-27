"""
Pipeline Module for Temporal Community Evolution Analysis

This module provides a high-level orchestration layer that combines all
analysis components into a unified pipeline for end-to-end analysis.

The pipeline handles:
    1. Data loading and validation
    2. Graph construction
    3. Community detection on both snapshots
    4. Temporal comparison
    5. Transition detection
    6. Report generation

Usage:
    pipeline = TemporalAnalysisPipeline(
        algorithm="louvain",
        resolution=1.0,
        seed=42
    )
    
    result = pipeline.run(
        snapshot_t1_path="day1_graph.json",
        snapshot_t2_path="day3_graph.json"
    )
    
    pipeline.export_results(result, "output/")
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Union, Tuple
from dataclasses import dataclass

from .data_loader import TemporalDataLoader, TransactionSnapshot
from .graph_builder import TemporalGraphBuilder
from .community_detector import CommunityDetector, CommunityResult
from .temporal_comparator import TemporalComparator, TemporalComparisonResult
from .transition_detector import TransitionDetector, TransitionAnalysisResult
from .reporter import EvolutionReporter

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    """
    Complete result from the temporal analysis pipeline.
    
    Contains all intermediate results and the final report.
    """
    snapshot_t1: TransactionSnapshot
    snapshot_t2: TransactionSnapshot
    community_t1: CommunityResult
    community_t2: CommunityResult
    comparison: TemporalComparisonResult
    transitions: TransitionAnalysisResult
    report: Dict[str, Any]
    
    @property
    def nmi_score(self) -> float:
        """Shortcut to NMI score."""
        return self.comparison.nmi_score
    
    @property
    def num_transitions(self) -> int:
        """Total number of detected transitions."""
        return self.transitions.transition_summary['total_transitions']
    
    @property
    def is_stable(self) -> bool:
        """True if community structure is relatively stable (NMI > 0.8)."""
        return self.comparison.nmi_score > 0.8


class TemporalAnalysisPipeline:
    """
    Orchestrates the complete temporal community evolution analysis.
    
    This class provides a high-level interface for:
    - Loading and validating snapshot data
    - Running community detection
    - Comparing community structures
    - Detecting transitions
    - Generating reports
    
    Usage:
        # Create pipeline with configuration
        pipeline = TemporalAnalysisPipeline(
            algorithm="louvain",
            resolution=1.0,
            directed=False,
            weighted=True
        )
        
        # Run analysis
        result = pipeline.run(
            snapshot_t1_path="graphs/day1.json",
            snapshot_t2_path="graphs/day3.json"
        )
        
        # Access results
        print(f"NMI: {result.nmi_score:.4f}")
        print(f"Transitions: {result.num_transitions}")
        
        # Export
        pipeline.export_results(result, "output/")
    """
    
    def __init__(
        self,
        algorithm: str = "louvain",
        resolution: float = 1.0,
        seed: Optional[int] = 42,
        directed: bool = False,
        weighted: bool = True,
        weight_attribute: str = "weight",
        strict_validation: bool = False,
        split_threshold: float = 0.25,
        merge_threshold: float = 0.25,
        emergence_threshold: float = 0.5,
        dissolution_threshold: float = 0.5,
        use_address_graph: bool = False
    ):
        """
        Initialize the analysis pipeline.
        
        Args:
            algorithm: Community detection algorithm 
                      ('louvain', 'leiden', 'label_propagation', 'infomap')
            resolution: Resolution parameter for Louvain/Leiden
            seed: Random seed for reproducibility
            directed: Build directed or undirected graphs
            weighted: Include edge weights
            weight_attribute: Edge attribute to use as weight
            strict_validation: Raise errors on validation issues
            split_threshold: Threshold for detecting splits
            merge_threshold: Threshold for detecting merges
            emergence_threshold: Threshold for detecting new communities
            dissolution_threshold: Threshold for detecting dissolved communities
            use_address_graph: If True, analyze only address nodes 
                              (project bipartite graph)
        """
        self.algorithm = algorithm
        self.resolution = resolution
        self.seed = seed
        self.directed = directed
        self.weighted = weighted
        self.weight_attribute = weight_attribute
        self.strict_validation = strict_validation
        self.use_address_graph = use_address_graph
        
        # Initialize components
        self.data_loader = TemporalDataLoader(strict_validation=strict_validation)
        self.graph_builder = TemporalGraphBuilder(
            directed=directed,
            weighted=weighted,
            weight_attribute=weight_attribute
        )
        self.community_detector = CommunityDetector(
            algorithm=algorithm,
            seed=seed,
            resolution=resolution,
            weight_attribute=weight_attribute
        )
        self.comparator = TemporalComparator()
        self.transition_detector = TransitionDetector(
            split_threshold=split_threshold,
            merge_threshold=merge_threshold,
            emergence_threshold=emergence_threshold,
            dissolution_threshold=dissolution_threshold
        )
        self.reporter = EvolutionReporter()
        
        logger.info(f"Initialized TemporalAnalysisPipeline with algorithm={algorithm}")
    
    def run(
        self,
        snapshot_t1_path: Union[str, Path],
        snapshot_t2_path: Union[str, Path],
        timestamp_t1: Optional[datetime] = None,
        timestamp_t2: Optional[datetime] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> PipelineResult:
        """
        Run the complete analysis pipeline.
        
        Args:
            snapshot_t1_path: Path to first snapshot JSON file
            snapshot_t2_path: Path to second snapshot JSON file
            timestamp_t1: Optional timestamp for T1 (uses file mtime if not provided)
            timestamp_t2: Optional timestamp for T2
            metadata: Optional metadata to include in report
            
        Returns:
            PipelineResult containing all analysis results
        """
        logger.info("=" * 60)
        logger.info("STARTING TEMPORAL COMMUNITY EVOLUTION ANALYSIS")
        logger.info("=" * 60)
        
        # Step 1: Load and validate snapshots
        logger.info("Step 1: Loading snapshots...")
        snapshot_t1 = self.data_loader.load_from_json(
            snapshot_t1_path, timestamp=timestamp_t1
        )
        snapshot_t2 = self.data_loader.load_from_json(
            snapshot_t2_path, timestamp=timestamp_t2
        )
        
        is_valid, errors = self.data_loader.validate_snapshots([snapshot_t1, snapshot_t2])
        if not is_valid:
            logger.warning(f"Validation issues: {errors}")
        
        # Step 2: Build graphs
        logger.info("Step 2: Building graphs...")
        if self.use_address_graph:
            G1 = self.graph_builder.build_address_graph(snapshot_t1)
            G2 = self.graph_builder.build_address_graph(snapshot_t2)
        else:
            G1 = self.graph_builder.build_graph(snapshot_t1)
            G2 = self.graph_builder.build_graph(snapshot_t2)
        
        # Log graph statistics
        stats_t1 = self.graph_builder.get_graph_statistics(G1)
        stats_t2 = self.graph_builder.get_graph_statistics(G2)
        logger.info(f"  T1 Graph: {stats_t1['num_nodes']} nodes, {stats_t1['num_edges']} edges")
        logger.info(f"  T2 Graph: {stats_t2['num_nodes']} nodes, {stats_t2['num_edges']} edges")
        
        # Step 3: Run community detection
        logger.info("Step 3: Detecting communities...")
        community_t1 = self.community_detector.detect(G1)
        community_t2 = self.community_detector.detect(G2)
        
        logger.info(f"  T1: {community_t1.num_communities} communities "
                   f"(modularity: {community_t1.modularity:.4f})")
        logger.info(f"  T2: {community_t2.num_communities} communities "
                   f"(modularity: {community_t2.modularity:.4f})")
        
        # Step 4: Compare community structures
        logger.info("Step 4: Comparing community structures...")
        comparison = self.comparator.compare(community_t1, community_t2)
        
        logger.info(f"  NMI Score: {comparison.nmi_score:.4f}")
        logger.info(f"  Common nodes: {comparison.total_common_nodes}")
        logger.info(f"  Nodes unchanged: {comparison.nodes_unchanged} "
                   f"({comparison.percentage_unchanged:.1f}%)")
        
        # Step 5: Detect transitions
        logger.info("Step 5: Detecting transitions...")
        transitions = self.transition_detector.detect(
            comparison, community_t1, community_t2
        )
        
        logger.info(f"  Splits: {len(transitions.splits)}")
        logger.info(f"  Merges: {len(transitions.merges)}")
        logger.info(f"  Emergences: {len(transitions.emergences)}")
        logger.info(f"  Dissolutions: {len(transitions.dissolutions)}")
        logger.info(f"  Stable: {len(transitions.stable_communities)}")
        
        # Step 6: Generate report
        logger.info("Step 6: Generating report...")
        report = self.reporter.generate_full_report(
            snapshot_t1=snapshot_t1,
            snapshot_t2=snapshot_t2,
            community_t1=community_t1,
            community_t2=community_t2,
            comparison=comparison,
            transitions=transitions,
            metadata=metadata
        )
        
        logger.info("=" * 60)
        logger.info("ANALYSIS COMPLETE")
        logger.info("=" * 60)
        
        return PipelineResult(
            snapshot_t1=snapshot_t1,
            snapshot_t2=snapshot_t2,
            community_t1=community_t1,
            community_t2=community_t2,
            comparison=comparison,
            transitions=transitions,
            report=report
        )
    
    def run_from_data(
        self,
        data_t1: Dict[str, Any],
        data_t2: Dict[str, Any],
        timestamp_t1: datetime,
        timestamp_t2: datetime,
        metadata: Optional[Dict[str, Any]] = None
    ) -> PipelineResult:
        """
        Run the pipeline on in-memory data dictionaries.
        
        Useful for testing or when data is already loaded.
        
        Args:
            data_t1: Graph data dict for T1 with 'nodes' and 'edges'
            data_t2: Graph data dict for T2
            timestamp_t1: Timestamp for T1
            timestamp_t2: Timestamp for T2
            metadata: Optional metadata
            
        Returns:
            PipelineResult
        """
        snapshot_t1 = self.data_loader.load_from_dict(
            data_t1, timestamp_t1, snapshot_id="T1"
        )
        snapshot_t2 = self.data_loader.load_from_dict(
            data_t2, timestamp_t2, snapshot_id="T2"
        )
        
        # Build graphs
        if self.use_address_graph:
            G1 = self.graph_builder.build_address_graph(snapshot_t1)
            G2 = self.graph_builder.build_address_graph(snapshot_t2)
        else:
            G1 = self.graph_builder.build_graph(snapshot_t1)
            G2 = self.graph_builder.build_graph(snapshot_t2)
        
        # Run analysis
        community_t1 = self.community_detector.detect(G1)
        community_t2 = self.community_detector.detect(G2)
        comparison = self.comparator.compare(community_t1, community_t2)
        transitions = self.transition_detector.detect(
            comparison, community_t1, community_t2
        )
        report = self.reporter.generate_full_report(
            snapshot_t1=snapshot_t1,
            snapshot_t2=snapshot_t2,
            community_t1=community_t1,
            community_t2=community_t2,
            comparison=comparison,
            transitions=transitions,
            metadata=metadata
        )
        
        return PipelineResult(
            snapshot_t1=snapshot_t1,
            snapshot_t2=snapshot_t2,
            community_t1=community_t1,
            community_t2=community_t2,
            comparison=comparison,
            transitions=transitions,
            report=report
        )
    
    def export_results(
        self,
        result: PipelineResult,
        output_dir: Union[str, Path],
        formats: Optional[list] = None
    ) -> Dict[str, Path]:
        """
        Export analysis results to files.
        
        Args:
            result: PipelineResult from run()
            output_dir: Directory to save output files
            formats: List of formats to export ('json', 'text', 'markdown')
                    Defaults to all formats.
                    
        Returns:
            Dict mapping format to output file path
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        if formats is None:
            formats = ['json', 'text', 'markdown']
        
        exported = {}
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        if 'json' in formats:
            json_path = output_dir / f"evolution_report_{timestamp}.json"
            self.reporter.export_json(result.report, json_path)
            exported['json'] = json_path
        
        if 'text' in formats:
            text_path = output_dir / f"evolution_summary_{timestamp}.txt"
            self.reporter.export_text(result.report, text_path)
            exported['text'] = text_path
        
        if 'markdown' in formats:
            md_path = output_dir / f"evolution_report_{timestamp}.md"
            self.reporter.export_markdown(result.report, md_path)
            exported['markdown'] = md_path
        
        logger.info(f"Results exported to: {output_dir}")
        return exported
    
    def print_summary(self, result: PipelineResult) -> None:
        """Print a text summary of the results."""
        print(self.reporter.generate_text_summary(result.report))
    
    def get_configuration(self) -> Dict[str, Any]:
        """Get the current pipeline configuration."""
        return {
            'algorithm': self.algorithm,
            'resolution': self.resolution,
            'seed': self.seed,
            'directed': self.directed,
            'weighted': self.weighted,
            'weight_attribute': self.weight_attribute,
            'use_address_graph': self.use_address_graph
        }


def create_mock_snapshots() -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Create mock snapshot data for testing.
    
    Returns:
        Tuple of (T1 data, T2 data) dictionaries
    """
    # T1: Initial community structure
    # Community 1: A, B, C (tightly connected)
    # Community 2: D, E, F (tightly connected)
    # Community 3: G, H, I (tightly connected)
    
    nodes_t1 = [
        {"id": "A", "label": "A", "type": "address"},
        {"id": "B", "label": "B", "type": "address"},
        {"id": "C", "label": "C", "type": "address"},
        {"id": "D", "label": "D", "type": "address"},
        {"id": "E", "label": "E", "type": "address"},
        {"id": "F", "label": "F", "type": "address"},
        {"id": "G", "label": "G", "type": "address"},
        {"id": "H", "label": "H", "type": "address"},
        {"id": "I", "label": "I", "type": "address"},
    ]
    
    edges_t1 = [
        # Community 1
        {"source": "A", "target": "B", "weight": 5},
        {"source": "B", "target": "C", "weight": 5},
        {"source": "A", "target": "C", "weight": 5},
        # Community 2
        {"source": "D", "target": "E", "weight": 5},
        {"source": "E", "target": "F", "weight": 5},
        {"source": "D", "target": "F", "weight": 5},
        # Community 3
        {"source": "G", "target": "H", "weight": 5},
        {"source": "H", "target": "I", "weight": 5},
        {"source": "G", "target": "I", "weight": 5},
        # Weak inter-community links
        {"source": "C", "target": "D", "weight": 1},
        {"source": "F", "target": "G", "weight": 1},
    ]
    
    # T2: Evolution
    # - Community 1 stays mostly stable
    # - Community 2 and 3 merge
    # - New node J appears with Community 1
    
    nodes_t2 = [
        {"id": "A", "label": "A", "type": "address"},
        {"id": "B", "label": "B", "type": "address"},
        {"id": "C", "label": "C", "type": "address"},
        {"id": "D", "label": "D", "type": "address"},
        {"id": "E", "label": "E", "type": "address"},
        {"id": "F", "label": "F", "type": "address"},
        {"id": "G", "label": "G", "type": "address"},
        {"id": "H", "label": "H", "type": "address"},
        {"id": "I", "label": "I", "type": "address"},
        {"id": "J", "label": "J", "type": "address"},  # New node
    ]
    
    edges_t2 = [
        # Community 1 (stable) + new member J
        {"source": "A", "target": "B", "weight": 5},
        {"source": "B", "target": "C", "weight": 5},
        {"source": "A", "target": "C", "weight": 5},
        {"source": "A", "target": "J", "weight": 5},
        {"source": "B", "target": "J", "weight": 5},
        # Merged Community (D,E,F,G,H,I)
        {"source": "D", "target": "E", "weight": 5},
        {"source": "E", "target": "F", "weight": 5},
        {"source": "D", "target": "F", "weight": 5},
        {"source": "G", "target": "H", "weight": 5},
        {"source": "H", "target": "I", "weight": 5},
        {"source": "G", "target": "I", "weight": 5},
        # Strong links between former communities 2 and 3 (merge)
        {"source": "F", "target": "G", "weight": 5},
        {"source": "E", "target": "H", "weight": 5},
        {"source": "D", "target": "I", "weight": 5},
        # Weak link to community 1
        {"source": "C", "target": "D", "weight": 1},
    ]
    
    data_t1 = {"nodes": nodes_t1, "edges": edges_t1}
    data_t2 = {"nodes": nodes_t2, "edges": edges_t2}
    
    return data_t1, data_t2
