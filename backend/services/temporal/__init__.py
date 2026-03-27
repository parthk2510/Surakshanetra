"""
Temporal Community Evolution Analysis Module

This module provides tools for analyzing community evolution in Bitcoin transaction
networks across multiple temporal snapshots. It quantifies community-level and 
node-level changes using Normalized Mutual Information (NMI) and community overlap matrices.

Key Components:
    - data_loader: Loading and validating transaction graph snapshots
    - graph_builder: Constructing NetworkX graphs from transaction data
    - community_detector: Wrapper for various community detection algorithms
    - temporal_comparator: Computing NMI and overlap matrices between snapshots
    - transition_detector: Identifying splits, merges, emergence, and dissolution
    - reporter: Generating structured output reports
"""

from .data_loader import TemporalDataLoader, TransactionSnapshot
from .graph_builder import TemporalGraphBuilder
from .community_detector import CommunityDetector
from .temporal_comparator import TemporalComparator
from .transition_detector import TransitionDetector
from .reporter import EvolutionReporter
from .pipeline import TemporalAnalysisPipeline

__version__ = "1.0.0"
__all__ = [
    "TemporalDataLoader",
    "TransactionSnapshot", 
    "TemporalGraphBuilder",
    "CommunityDetector",
    "TemporalComparator",
    "TransitionDetector",
    "EvolutionReporter",
    "TemporalAnalysisPipeline",
]
