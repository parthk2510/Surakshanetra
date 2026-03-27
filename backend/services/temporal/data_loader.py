"""
Data Loader Module for Temporal Community Analysis

This module handles the ingestion and validation of Bitcoin transaction graph
snapshots at different time points. It ensures data schema consistency and
handles edge cases gracefully.

Mathematical Context:
    Given a temporal series of transaction graphs G_t1, G_t2, ..., G_tn,
    each snapshot contains:
    - V_t: Set of wallet addresses (nodes) at time t
    - E_t: Set of transactions (edges) at time t
    
    The loader validates that node identifiers are consistent across snapshots
    to enable meaningful temporal comparisons.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Set, Union, Tuple

logger = logging.getLogger(__name__)


@dataclass
class TransactionSnapshot:
    """
    Represents a single temporal snapshot of a Bitcoin transaction graph.
    
    Attributes:
        timestamp: The datetime when this snapshot was captured
        nodes: List of node dictionaries with 'id', 'label', 'type' keys
        edges: List of edge dictionaries with 'source', 'target' keys
        metadata: Optional additional metadata about the snapshot
        snapshot_id: Unique identifier for this snapshot
    """
    timestamp: datetime
    nodes: List[Dict[str, Any]]
    edges: List[Dict[str, Any]]
    snapshot_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate the snapshot after initialization."""
        if not self.snapshot_id:
            self.snapshot_id = f"snapshot_{self.timestamp.strftime('%Y%m%d_%H%M%S')}"
    
    @property
    def num_nodes(self) -> int:
        """Return the number of nodes in this snapshot."""
        return len(self.nodes)
    
    @property
    def num_edges(self) -> int:
        """Return the number of edges in this snapshot."""
        return len(self.edges)
    
    @property
    def node_ids(self) -> Set[str]:
        """Return set of all node IDs in this snapshot."""
        return {node['id'] for node in self.nodes if 'id' in node}
    
    @property
    def address_nodes(self) -> List[Dict[str, Any]]:
        """Return only address-type nodes (excluding transactions)."""
        return [n for n in self.nodes if n.get('type') == 'address']
    
    @property  
    def transaction_nodes(self) -> List[Dict[str, Any]]:
        """Return only transaction-type nodes."""
        return [n for n in self.nodes if n.get('type') == 'transaction']


class TemporalDataLoader:
    """
    Handles loading and validation of temporal graph snapshots.
    
    This class provides methods to:
    - Load graph data from JSON files
    - Validate data schema consistency
    - Handle missing or malformed data gracefully
    - Create TransactionSnapshot objects for analysis
    
    Usage:
        loader = TemporalDataLoader()
        snapshot_t1 = loader.load_from_json("day1_graph.json", timestamp=datetime(2024, 1, 1))
        snapshot_t2 = loader.load_from_json("day3_graph.json", timestamp=datetime(2024, 1, 3))
        
        # Validate schema consistency
        is_valid, errors = loader.validate_snapshots([snapshot_t1, snapshot_t2])
    """
    
    # Required keys for node and edge validation
    REQUIRED_NODE_KEYS = {'id'}
    REQUIRED_EDGE_KEYS = {'source', 'target'}
    OPTIONAL_NODE_KEYS = {'label', 'type', 'value'}
    OPTIONAL_EDGE_KEYS = {'weight', 'value', 'timestamp'}
    
    def __init__(self, strict_validation: bool = False):
        """
        Initialize the data loader.
        
        Args:
            strict_validation: If True, raise exceptions on validation errors.
                             If False, log warnings and continue.
        """
        self.strict_validation = strict_validation
        self._validation_errors: List[str] = []
        
    def load_from_json(
        self, 
        file_path: Union[str, Path], 
        timestamp: Optional[datetime] = None,
        snapshot_id: Optional[str] = None
    ) -> TransactionSnapshot:
        """
        Load a graph snapshot from a JSON file.
        
        Args:
            file_path: Path to the JSON file containing graph data
            timestamp: Optional timestamp for the snapshot. If not provided,
                      uses file modification time or current time.
            snapshot_id: Optional unique identifier for this snapshot
                      
        Returns:
            TransactionSnapshot object containing the loaded data
            
        Raises:
            FileNotFoundError: If the file doesn't exist
            json.JSONDecodeError: If the file contains invalid JSON
            ValueError: If strict validation is enabled and data is invalid
        """
        file_path = Path(file_path)
        
        if not file_path.exists():
            raise FileNotFoundError(f"Graph file not found: {file_path}")
        
        logger.info(f"Loading graph snapshot from: {file_path}")
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in file {file_path}: {e}")
            raise
        
        # Extract nodes and edges
        nodes = data.get('nodes', [])
        edges = data.get('edges', [])
        metadata = data.get('metadata', {})
        
        # Determine timestamp
        if timestamp is None:
            # Try to get from metadata, then file modification time
            if 'timestamp' in metadata:
                try:
                    timestamp = datetime.fromisoformat(metadata['timestamp'])
                except (ValueError, TypeError):
                    timestamp = datetime.fromtimestamp(file_path.stat().st_mtime)
            else:
                timestamp = datetime.fromtimestamp(file_path.stat().st_mtime)
        
        # Create snapshot
        snapshot = TransactionSnapshot(
            timestamp=timestamp,
            nodes=nodes,
            edges=edges,
            snapshot_id=snapshot_id or file_path.stem,
            metadata=metadata
        )
        
        # Validate the snapshot
        is_valid, errors = self._validate_snapshot(snapshot)
        
        if not is_valid:
            error_msg = f"Validation errors in {file_path}: {errors}"
            if self.strict_validation:
                raise ValueError(error_msg)
            else:
                logger.warning(error_msg)
        
        logger.info(f"Loaded snapshot '{snapshot.snapshot_id}': "
                   f"{snapshot.num_nodes} nodes, {snapshot.num_edges} edges")
        
        return snapshot
    
    def load_from_dict(
        self,
        data: Dict[str, Any],
        timestamp: datetime,
        snapshot_id: str = ""
    ) -> TransactionSnapshot:
        """
        Create a snapshot from a dictionary (useful for testing or in-memory data).
        
        Args:
            data: Dictionary with 'nodes' and 'edges' keys
            timestamp: Timestamp for this snapshot
            snapshot_id: Optional identifier
            
        Returns:
            TransactionSnapshot object
        """
        nodes = data.get('nodes', [])
        edges = data.get('edges', [])
        metadata = data.get('metadata', {})
        
        snapshot = TransactionSnapshot(
            timestamp=timestamp,
            nodes=nodes,
            edges=edges,
            snapshot_id=snapshot_id,
            metadata=metadata
        )
        
        is_valid, errors = self._validate_snapshot(snapshot)
        
        if not is_valid and self.strict_validation:
            raise ValueError(f"Validation errors: {errors}")
        
        return snapshot
    
    def _validate_snapshot(self, snapshot: TransactionSnapshot) -> Tuple[bool, List[str]]:
        """
        Validate a single snapshot's data schema.
        
        Args:
            snapshot: The snapshot to validate
            
        Returns:
            Tuple of (is_valid, list_of_error_messages)
        """
        errors = []
        
        # Check for empty data
        if not snapshot.nodes:
            errors.append("Snapshot contains no nodes")
            
        if not snapshot.edges:
            errors.append("Snapshot contains no edges")
        
        # Validate nodes
        node_ids = set()
        for i, node in enumerate(snapshot.nodes):
            # Check required keys
            missing_keys = self.REQUIRED_NODE_KEYS - set(node.keys())
            if missing_keys:
                errors.append(f"Node {i} missing required keys: {missing_keys}")
                continue
            
            node_id = node.get('id')
            
            # Check for duplicate IDs
            if node_id in node_ids:
                errors.append(f"Duplicate node ID: {node_id}")
            else:
                node_ids.add(node_id)
            
            # Check for empty/null IDs
            if not node_id:
                errors.append(f"Node {i} has empty or null ID")
        
        # Validate edges
        for i, edge in enumerate(snapshot.edges):
            # Check required keys
            missing_keys = self.REQUIRED_EDGE_KEYS - set(edge.keys())
            if missing_keys:
                errors.append(f"Edge {i} missing required keys: {missing_keys}")
                continue
            
            source = edge.get('source')
            target = edge.get('target')
            
            # Check if source and target exist in nodes
            if source not in node_ids:
                errors.append(f"Edge {i} references unknown source node: {source}")
            if target not in node_ids:
                errors.append(f"Edge {i} references unknown target node: {target}")
        
        self._validation_errors = errors
        return len(errors) == 0, errors
    
    def validate_snapshots(
        self, 
        snapshots: List[TransactionSnapshot]
    ) -> Tuple[bool, Dict[str, List[str]]]:
        """
        Validate multiple snapshots for temporal comparison compatibility.
        
        This checks:
        - Individual snapshot validity
        - Node ID format consistency across snapshots
        - Temporal ordering
        
        Args:
            snapshots: List of snapshots to validate
            
        Returns:
            Tuple of (is_valid, dict_of_errors_per_snapshot)
        """
        all_errors = {}
        
        # Validate each snapshot individually
        for snapshot in snapshots:
            is_valid, errors = self._validate_snapshot(snapshot)
            if errors:
                all_errors[snapshot.snapshot_id] = errors
        
        # Check temporal ordering
        sorted_snapshots = sorted(snapshots, key=lambda s: s.timestamp)
        for i in range(len(sorted_snapshots) - 1):
            if sorted_snapshots[i].timestamp >= sorted_snapshots[i + 1].timestamp:
                all_errors.setdefault('temporal_ordering', []).append(
                    f"Snapshot {sorted_snapshots[i].snapshot_id} has timestamp >= "
                    f"snapshot {sorted_snapshots[i + 1].snapshot_id}"
                )
        
        return len(all_errors) == 0, all_errors
    
    def get_common_nodes(
        self, 
        snapshot_t1: TransactionSnapshot, 
        snapshot_t2: TransactionSnapshot,
        node_type: Optional[str] = None
    ) -> Set[str]:
        """
        Find nodes that exist in both snapshots.
        
        Args:
            snapshot_t1: First temporal snapshot
            snapshot_t2: Second temporal snapshot
            node_type: Optional filter for node type ('address' or 'transaction')
            
        Returns:
            Set of node IDs present in both snapshots
        """
        if node_type:
            nodes_t1 = {n['id'] for n in snapshot_t1.nodes if n.get('type') == node_type}
            nodes_t2 = {n['id'] for n in snapshot_t2.nodes if n.get('type') == node_type}
        else:
            nodes_t1 = snapshot_t1.node_ids
            nodes_t2 = snapshot_t2.node_ids
        
        return nodes_t1 & nodes_t2
    
    def get_node_changes(
        self,
        snapshot_t1: TransactionSnapshot,
        snapshot_t2: TransactionSnapshot,
        node_type: Optional[str] = None
    ) -> Dict[str, Set[str]]:
        """
        Compute node-level changes between two snapshots.
        
        Args:
            snapshot_t1: First temporal snapshot
            snapshot_t2: Second temporal snapshot  
            node_type: Optional filter for node type
            
        Returns:
            Dictionary with keys:
            - 'common': Nodes in both snapshots
            - 'added': Nodes only in T2 (new nodes)
            - 'removed': Nodes only in T1 (departed nodes)
        """
        if node_type:
            nodes_t1 = {n['id'] for n in snapshot_t1.nodes if n.get('type') == node_type}
            nodes_t2 = {n['id'] for n in snapshot_t2.nodes if n.get('type') == node_type}
        else:
            nodes_t1 = snapshot_t1.node_ids
            nodes_t2 = snapshot_t2.node_ids
        
        return {
            'common': nodes_t1 & nodes_t2,
            'added': nodes_t2 - nodes_t1,
            'removed': nodes_t1 - nodes_t2
        }
    
    @staticmethod
    def create_empty_snapshot(
        timestamp: datetime,
        snapshot_id: str = "empty"
    ) -> TransactionSnapshot:
        """
        Create an empty snapshot for handling edge cases.
        
        Args:
            timestamp: Timestamp for the empty snapshot
            snapshot_id: Identifier for the snapshot
            
        Returns:
            Empty TransactionSnapshot object
        """
        return TransactionSnapshot(
            timestamp=timestamp,
            nodes=[],
            edges=[],
            snapshot_id=snapshot_id,
            metadata={'is_empty': True}
        )
