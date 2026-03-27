"""
Reporter Module for Community Evolution Analysis

This module generates structured output reports in both JSON format and
human-readable summaries. It consolidates all analysis results into 
comprehensive reports.

Output Formats:
    - JSON: Machine-readable structured data
    - Text: Human-readable summary with formatting
    - Markdown: Documentation-ready formatted output
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Union, List
from dataclasses import asdict

import numpy as np

from .data_loader import TransactionSnapshot
from .community_detector import CommunityResult
from .temporal_comparator import TemporalComparisonResult
from .transition_detector import TransitionAnalysisResult

logger = logging.getLogger(__name__)


class NumpyEncoder(json.JSONEncoder):
    """JSON encoder that handles NumPy types."""
    
    def default(self, obj):
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, set):
            return list(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


class EvolutionReporter:
    """
    Generates comprehensive reports for community evolution analysis.
    
    This class provides methods to:
    - Generate JSON reports with all metrics
    - Generate human-readable text summaries
    - Generate Markdown documentation
    - Export results to files
    
    Usage:
        reporter = EvolutionReporter()
        
        # Generate full report
        report = reporter.generate_full_report(
            snapshot_t1=snapshot_t1,
            snapshot_t2=snapshot_t2,
            community_t1=result_t1,
            community_t2=result_t2,
            comparison=comparison,
            transitions=transitions
        )
        
        # Export to JSON
        reporter.export_json(report, "evolution_report.json")
        
        # Print summary
        print(reporter.generate_text_summary(report))
    """
    
    def __init__(self, include_raw_data: bool = False):
        """
        Initialize the reporter.
        
        Args:
            include_raw_data: If True, include full node/edge lists in reports.
                            Increases file size significantly.
        """
        self.include_raw_data = include_raw_data
    
    def generate_full_report(
        self,
        snapshot_t1: TransactionSnapshot,
        snapshot_t2: TransactionSnapshot,
        community_t1: CommunityResult,
        community_t2: CommunityResult,
        comparison: TemporalComparisonResult,
        transitions: TransitionAnalysisResult,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Generate a comprehensive report containing all analysis results.
        
        Args:
            snapshot_t1: First temporal snapshot
            snapshot_t2: Second temporal snapshot
            community_t1: Community detection result at T1
            community_t2: Community detection result at T2
            comparison: Temporal comparison result
            transitions: Transition analysis result
            metadata: Optional additional metadata
            
        Returns:
            Dictionary containing the full report
        """
        logger.info("Generating full evolution report")
        
        report = {
            'report_metadata': {
                'generated_at': datetime.now().isoformat(),
                'report_version': '1.0.0',
                'analysis_type': 'temporal_community_evolution'
            },
            
            'summary_metrics': self._generate_summary_metrics(
                snapshot_t1, snapshot_t2, community_t1, community_t2, comparison
            ),
            
            'node_level_metrics': self._generate_node_metrics(comparison),
            
            'community_metrics_t1': self._generate_community_metrics(community_t1, 'T1'),
            'community_metrics_t2': self._generate_community_metrics(community_t2, 'T2'),
            
            'overlap_matrix': self._generate_overlap_report(comparison),
            
            'detected_transitions': self._generate_transition_report(transitions),
            
            'snapshot_info': {
                'T1': {
                    'snapshot_id': snapshot_t1.snapshot_id,
                    'timestamp': snapshot_t1.timestamp.isoformat(),
                    'num_nodes': snapshot_t1.num_nodes,
                    'num_edges': snapshot_t1.num_edges,
                    'num_addresses': len(snapshot_t1.address_nodes),
                    'num_transactions': len(snapshot_t1.transaction_nodes)
                },
                'T2': {
                    'snapshot_id': snapshot_t2.snapshot_id,
                    'timestamp': snapshot_t2.timestamp.isoformat(),
                    'num_nodes': snapshot_t2.num_nodes,
                    'num_edges': snapshot_t2.num_edges,
                    'num_addresses': len(snapshot_t2.address_nodes),
                    'num_transactions': len(snapshot_t2.transaction_nodes)
                }
            }
        }
        
        if metadata:
            report['custom_metadata'] = metadata
        
        if self.include_raw_data:
            report['raw_data'] = {
                'partition_t1': community_t1.partition,
                'partition_t2': community_t2.partition,
                'communities_t1': community_t1.communities,
                'communities_t2': community_t2.communities
            }
        
        return report
    
    def _generate_summary_metrics(
        self,
        snapshot_t1: TransactionSnapshot,
        snapshot_t2: TransactionSnapshot,
        community_t1: CommunityResult,
        community_t2: CommunityResult,
        comparison: TemporalComparisonResult
    ) -> Dict[str, Any]:
        """Generate summary metrics section."""
        return {
            'num_communities_t1': community_t1.num_communities,
            'num_communities_t2': community_t2.num_communities,
            'delta_communities': comparison.delta_communities,
            'nmi_score': round(comparison.nmi_score, 6),
            'modularity_t1': round(community_t1.modularity, 6),
            'modularity_t2': round(community_t2.modularity, 6),
            'delta_modularity': round(community_t2.modularity - community_t1.modularity, 6),
            'algorithm_used': community_t1.algorithm
        }
    
    def _generate_node_metrics(
        self,
        comparison: TemporalComparisonResult
    ) -> Dict[str, Any]:
        """Generate node-level metrics section."""
        return {
            'total_common_nodes': comparison.total_common_nodes,
            'nodes_changed_community': comparison.nodes_changed,
            'nodes_unchanged_community': comparison.nodes_unchanged,
            'percentage_changed': round(comparison.percentage_changed, 2),
            'percentage_unchanged': round(comparison.percentage_unchanged, 2)
        }
    
    def _generate_community_metrics(
        self,
        result: CommunityResult,
        label: str
    ) -> Dict[str, Any]:
        """Generate community-level metrics for a single snapshot."""
        sizes = list(result.community_sizes.values())
        
        return {
            'snapshot': label,
            'num_communities': result.num_communities,
            'modularity': round(result.modularity, 6),
            'avg_community_size': round(result.avg_community_size, 2),
            'min_community_size': min(sizes) if sizes else 0,
            'max_community_size': max(sizes) if sizes else 0,
            'community_size_distribution': {
                str(k): v for k, v in result.community_sizes.items()
            }
        }
    
    def _generate_overlap_report(
        self,
        comparison: TemporalComparisonResult
    ) -> Dict[str, Any]:
        """Generate overlap matrix report."""
        raw_matrix = comparison.overlap_matrix
        norm_matrix = comparison.normalized_overlap_matrix
        
        # Convert to lists for JSON serialization
        return {
            'raw_matrix': raw_matrix.tolist(),
            'normalized_matrix': norm_matrix.tolist(),
            'matrix_shape': list(raw_matrix.shape),
            't1_community_mapping': comparison.community_mapping_t1,
            't2_community_mapping': comparison.community_mapping_t2
        }
    
    def _generate_transition_report(
        self,
        transitions: TransitionAnalysisResult
    ) -> Dict[str, Any]:
        """Generate transition detection report."""
        return {
            'summary': transitions.transition_summary,
            
            'splits': [
                {
                    'source_community': s.source_community,
                    'target_communities': s.target_communities,
                    'overlap_counts': s.overlap_counts,
                    'split_ratio': round(s.split_ratio, 4),
                    'num_splits': s.num_splits
                }
                for s in transitions.splits
            ],
            
            'merges': [
                {
                    'source_communities': m.source_communities,
                    'target_community': m.target_community,
                    'overlap_counts': m.overlap_counts,
                    'merge_ratio': round(m.merge_ratio, 4),
                    'num_merged': m.num_merged
                }
                for m in transitions.merges
            ],
            
            'emergences': [
                {
                    'community_id': e.community_id,
                    'size': e.size,
                    'sources': e.sources,
                    'emergence_ratio': round(e.emergence_ratio, 4),
                    'is_completely_new': e.is_completely_new
                }
                for e in transitions.emergences
            ],
            
            'dissolutions': [
                {
                    'community_id': d.community_id,
                    'size': d.size,
                    'destinations': d.destinations,
                    'dissolution_ratio': round(d.dissolution_ratio, 4),
                    'is_completely_dissolved': d.is_completely_dissolved
                }
                for d in transitions.dissolutions
            ],
            
            'stable_communities': [
                {'t1_id': t1, 't2_id': t2}
                for t1, t2 in transitions.stable_communities
            ]
        }
    
    def generate_text_summary(self, report: Dict[str, Any]) -> str:
        """
        Generate a human-readable text summary of the report.
        
        Args:
            report: The full report dictionary
            
        Returns:
            Formatted text summary string
        """
        lines = []
        lines.append("=" * 70)
        lines.append("TEMPORAL COMMUNITY EVOLUTION ANALYSIS REPORT")
        lines.append("=" * 70)
        lines.append("")
        
        # Summary Metrics
        summary = report['summary_metrics']
        lines.append("📊 SUMMARY METRICS")
        lines.append("-" * 40)
        lines.append(f"  Communities at T1:     {summary['num_communities_t1']}")
        lines.append(f"  Communities at T2:     {summary['num_communities_t2']}")
        lines.append(f"  Delta Communities:     {summary['delta_communities']:+d}")
        lines.append(f"  NMI Score:             {summary['nmi_score']:.4f}")
        lines.append(f"  Modularity T1:         {summary['modularity_t1']:.4f}")
        lines.append(f"  Modularity T2:         {summary['modularity_t2']:.4f}")
        lines.append(f"  Algorithm:             {summary['algorithm_used']}")
        lines.append("")
        
        # Node-Level Metrics
        node_metrics = report['node_level_metrics']
        lines.append("👥 NODE-LEVEL STABILITY")
        lines.append("-" * 40)
        lines.append(f"  Common Nodes:          {node_metrics['total_common_nodes']}")
        lines.append(f"  Nodes Unchanged:       {node_metrics['nodes_unchanged_community']} "
                    f"({node_metrics['percentage_unchanged']:.1f}%)")
        lines.append(f"  Nodes Changed:         {node_metrics['nodes_changed_community']} "
                    f"({node_metrics['percentage_changed']:.1f}%)")
        lines.append("")
        
        # Transitions
        transitions = report['detected_transitions']
        trans_summary = transitions['summary']
        lines.append("🔄 DETECTED TRANSITIONS")
        lines.append("-" * 40)
        lines.append(f"  Splits:                {trans_summary['num_splits']}")
        lines.append(f"  Merges:                {trans_summary['num_merges']}")
        lines.append(f"  Emergences:            {trans_summary['num_emergences']}")
        lines.append(f"  Dissolutions:          {trans_summary['num_dissolutions']}")
        lines.append(f"  Stable Communities:    {trans_summary['num_stable']}")
        lines.append("")
        
        # Detailed Transitions
        if transitions['splits']:
            lines.append("  📤 SPLITS:")
            for split in transitions['splits']:
                lines.append(f"    - Community {split['source_community']} → "
                           f"{split['target_communities']} "
                           f"(ratio: {split['split_ratio']:.2f})")
            lines.append("")
        
        if transitions['merges']:
            lines.append("  📥 MERGES:")
            for merge in transitions['merges']:
                lines.append(f"    - Communities {merge['source_communities']} → "
                           f"{merge['target_community']} "
                           f"(ratio: {merge['merge_ratio']:.2f})")
            lines.append("")
        
        if transitions['emergences']:
            lines.append("  🆕 EMERGENCES:")
            for emergence in transitions['emergences']:
                new_label = " [NEW]" if emergence['is_completely_new'] else ""
                lines.append(f"    - Community {emergence['community_id']} "
                           f"(size: {emergence['size']}){new_label}")
            lines.append("")
        
        if transitions['dissolutions']:
            lines.append("  💨 DISSOLUTIONS:")
            for dissolution in transitions['dissolutions']:
                dissolved_label = " [GONE]" if dissolution['is_completely_dissolved'] else ""
                lines.append(f"    - Community {dissolution['community_id']} "
                           f"(was: {dissolution['size']}){dissolved_label}")
            lines.append("")
        
        # Snapshot Info
        snap_info = report['snapshot_info']
        lines.append("📁 SNAPSHOT INFORMATION")
        lines.append("-" * 40)
        lines.append(f"  T1 Snapshot: {snap_info['T1']['snapshot_id']}")
        lines.append(f"    Timestamp: {snap_info['T1']['timestamp']}")
        lines.append(f"    Nodes: {snap_info['T1']['num_nodes']} | "
                    f"Edges: {snap_info['T1']['num_edges']}")
        lines.append("")
        lines.append(f"  T2 Snapshot: {snap_info['T2']['snapshot_id']}")
        lines.append(f"    Timestamp: {snap_info['T2']['timestamp']}")
        lines.append(f"    Nodes: {snap_info['T2']['num_nodes']} | "
                    f"Edges: {snap_info['T2']['num_edges']}")
        lines.append("")
        
        lines.append("=" * 70)
        lines.append(f"Report generated: {report['report_metadata']['generated_at']}")
        lines.append("=" * 70)
        
        return "\n".join(lines)
    
    def generate_markdown_report(self, report: Dict[str, Any]) -> str:
        """
        Generate a Markdown-formatted report.
        
        Args:
            report: The full report dictionary
            
        Returns:
            Markdown string
        """
        lines = []
        
        lines.append("# Temporal Community Evolution Analysis Report")
        lines.append("")
        lines.append(f"*Generated: {report['report_metadata']['generated_at']}*")
        lines.append("")
        
        # Summary
        summary = report['summary_metrics']
        lines.append("## Summary Metrics")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| Communities at T1 | {summary['num_communities_t1']} |")
        lines.append(f"| Communities at T2 | {summary['num_communities_t2']} |")
        lines.append(f"| Delta Communities | {summary['delta_communities']:+d} |")
        lines.append(f"| NMI Score | {summary['nmi_score']:.4f} |")
        lines.append(f"| Modularity T1 | {summary['modularity_t1']:.4f} |")
        lines.append(f"| Modularity T2 | {summary['modularity_t2']:.4f} |")
        lines.append(f"| Algorithm | {summary['algorithm_used']} |")
        lines.append("")
        
        # Node Metrics
        node_metrics = report['node_level_metrics']
        lines.append("## Node-Level Stability")
        lines.append("")
        lines.append("| Metric | Count | Percentage |")
        lines.append("|--------|-------|------------|")
        lines.append(f"| Common Nodes | {node_metrics['total_common_nodes']} | - |")
        lines.append(f"| Unchanged | {node_metrics['nodes_unchanged_community']} | "
                    f"{node_metrics['percentage_unchanged']:.1f}% |")
        lines.append(f"| Changed | {node_metrics['nodes_changed_community']} | "
                    f"{node_metrics['percentage_changed']:.1f}% |")
        lines.append("")
        
        # Transitions
        transitions = report['detected_transitions']
        lines.append("## Detected Transitions")
        lines.append("")
        
        trans_summary = transitions['summary']
        lines.append("### Overview")
        lines.append("")
        lines.append(f"- **Splits:** {trans_summary['num_splits']}")
        lines.append(f"- **Merges:** {trans_summary['num_merges']}")
        lines.append(f"- **Emergences:** {trans_summary['num_emergences']}")
        lines.append(f"- **Dissolutions:** {trans_summary['num_dissolutions']}")
        lines.append(f"- **Stable:** {trans_summary['num_stable']}")
        lines.append("")
        
        if transitions['splits']:
            lines.append("### Splits")
            lines.append("")
            for split in transitions['splits']:
                lines.append(f"- Community **{split['source_community']}** → "
                           f"{split['target_communities']} "
                           f"(split ratio: {split['split_ratio']:.2%})")
            lines.append("")
        
        if transitions['merges']:
            lines.append("### Merges")
            lines.append("")
            for merge in transitions['merges']:
                lines.append(f"- Communities {merge['source_communities']} → "
                           f"**{merge['target_community']}** "
                           f"(merge ratio: {merge['merge_ratio']:.2%})")
            lines.append("")
        
        return "\n".join(lines)
    
    def export_json(
        self,
        report: Dict[str, Any],
        filepath: Union[str, Path],
        indent: int = 2
    ) -> None:
        """
        Export report to JSON file.
        
        Args:
            report: The report dictionary
            filepath: Output file path
            indent: JSON indentation level
        """
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=indent, cls=NumpyEncoder)
        
        logger.info(f"Report exported to: {filepath}")
    
    def export_text(
        self,
        report: Dict[str, Any],
        filepath: Union[str, Path]
    ) -> None:
        """Export text summary to file."""
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(self.generate_text_summary(report))
        
        logger.info(f"Text summary exported to: {filepath}")
    
    def export_markdown(
        self,
        report: Dict[str, Any],
        filepath: Union[str, Path]
    ) -> None:
        """Export Markdown report to file."""
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(self.generate_markdown_report(report))
        
        logger.info(f"Markdown report exported to: {filepath}")
