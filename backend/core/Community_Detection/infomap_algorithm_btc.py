"""
Infomap community detection algorithm for Bitcoin transaction graphs.

Infomap is a flow-based community detection algorithm that:
- Treats the network as a flow of information (random walks)
- Minimizes the description length of the random walk using the Map Equation
- Particularly effective for detecting communities in directed networks
- Well-suited for Bitcoin transaction graphs as it captures flow patterns

This module provides a backend implementation consistent with other algorithms
(Louvain, Leiden, Label Propagation) in the ChainBreak system.
"""

from typing import Dict, List, Any, Optional
import logging

try:
    import infomap
    INFOMAP_AVAILABLE = True
except ImportError:
    INFOMAP_AVAILABLE = False

import networkx as nx

logger = logging.getLogger(__name__)


def run_infomap_algorithm(
    graph_data: Dict[str, Any],
    weight_attribute: str = "weight",
    num_trials: int = 10,
    two_level: bool = False,
    directed: bool = True,
) -> Dict[str, Any]:
    """
    Run Infomap community detection algorithm on graph data.
    
    Infomap uses the Map Equation to detect communities based on information flow.
    This makes it especially useful for transaction networks where flow patterns
    are important for identifying entities and services.
    
    Args:
        graph_data: dict with 'nodes' (list of objects with 'id') and 'edges'
                    (list with 'source', 'target', and optional weight/value).
        weight_attribute: name of the weight attribute to use (default: weight).
        num_trials: number of optimization trials for consistent results (default: 10).
        two_level: if True, only detect two-level community structure (default: False).
        directed: if True, treat graph as directed (default: True for Bitcoin flows).
    
    Returns:
        dict containing:
            - partition: {node_id: community_id}
            - communities: {community_id: [node_ids]}
            - codelength: the codelength of the partition (quality metric)
            - num_communities: total number of communities found
            - hierarchical_structure: optional nested community structure if multi-level
            - flow_distribution: flow-based metrics per community
    
    Raises:
        ImportError: if infomap package is not installed
        ValueError: if graph data is invalid
    """
    
    if not INFOMAP_AVAILABLE:
        raise ImportError(
            "Infomap package is not installed. "
            "Install it with: pip install infomap"
        )
    
    nodes: List[Dict[str, Any]] = graph_data.get("nodes", [])
    edges: List[Dict[str, Any]] = graph_data.get("edges", [])
    
    if not nodes:
        raise ValueError("Graph must have at least one node")
    if not edges:
        raise ValueError("Graph must have at least one edge")
    
    # Create node ID to integer index mapping (Infomap requires integer node IDs)
    node_id_to_idx: Dict[str, int] = {}
    idx_to_node_id: Dict[int, str] = {}
    node_metadata: Dict[str, Dict[str, Any]] = {}
    
    for idx, node in enumerate(nodes):
        node_id = node.get("id")
        if node_id is None:
            raise ValueError("Each node must have an 'id'")
        node_id_to_idx[node_id] = idx
        idx_to_node_id[idx] = node_id
        node_metadata[node_id] = {
            "label": node.get("label", node_id),
            "type": node.get("type", "unknown"),
        }
    
    # Initialize Infomap with optimization settings
    flags = []
    if two_level:
        flags.append('--two-level')
    if directed:
        flags.append('--directed')
    flags.append(f'--num-trials {num_trials}')
    flags.append('--silent')
    im = infomap.Infomap(' '.join(flags))
    
    # Add nodes explicitly
    for idx in range(len(nodes)):
        im.add_node(idx)
    
    # Add edges with weights
    valid_edge_count = 0
    for edge in edges:
        source = edge.get("source")
        target = edge.get("target")
        
        if source not in node_id_to_idx or target not in node_id_to_idx:
            # Skip edges that reference missing nodes
            continue
        
        source_idx = node_id_to_idx[source]
        target_idx = node_id_to_idx[target]
        
        # Get edge weight
        weight = edge.get(weight_attribute, edge.get("value", edge.get("weight", 1.0)))
        if weight is None:
            weight = 1.0
        
        # For transaction networks, we can use the value as weight
        # Normalize large values to prevent numerical issues
        if weight > 1e10:
            weight = float(weight) / 1e8  # Convert satoshis to BTC if needed
        
        im.add_link(source_idx, target_idx, float(weight))
        valid_edge_count += 1
    
    if valid_edge_count == 0:
        raise ValueError("No valid edges after filtering missing nodes")
    
    logger.info(f"Infomap: Processing graph with {len(nodes)} nodes and {valid_edge_count} edges")
    
    # Run the Infomap algorithm
    im.run()
    
    # Extract results
    partition: Dict[str, int] = {}
    communities: Dict[int, List[str]] = {}
    flow_distribution: Dict[int, float] = {}
    
    # Process nodes with their community assignments
    for node in im.nodes:
        node_idx = node.node_id
        if node_idx in idx_to_node_id:
            node_id = idx_to_node_id[node_idx]
            module_id = node.module_id
            
            partition[node_id] = module_id
            communities.setdefault(module_id, []).append(node_id)
            
            # Track flow per community
            flow_distribution[module_id] = flow_distribution.get(module_id, 0) + node.flow
    
    # Get codelength (the Map Equation optimization metric)
    codelength = im.codelength
    
    # Calculate modularity equivalent for comparison with other algorithms
    # Build NetworkX graph for modularity calculation
    G = nx.DiGraph() if directed else nx.Graph()
    for node in nodes:
        G.add_node(node["id"])
    
    for edge in edges:
        source = edge.get("source")
        target = edge.get("target")
        if source in node_id_to_idx and target in node_id_to_idx:
            weight = edge.get(weight_attribute, edge.get("value", edge.get("weight", 1.0)))
            G.add_edge(source, target, weight=weight if weight else 1.0)
    
    # Calculate modularity using NetworkX (for comparison)
    try:
        communities_as_sets = [set(nodes) for nodes in communities.values()]
        if directed:
            # Convert to undirected for modularity calculation
            G_undirected = G.to_undirected()
            modularity = nx.algorithms.community.modularity(G_undirected, communities_as_sets)
        else:
            modularity = nx.algorithms.community.modularity(G, communities_as_sets)
    except Exception as e:
        logger.warning(f"Could not calculate modularity: {e}")
        modularity = 0.0
    
    # Ensure modularity is in valid range
    modularity = max(-0.5, min(1.0, modularity))
    
    # Build hierarchical structure if available
    hierarchical_structure = None
    if not two_level and im.num_top_modules > 0:
        hierarchical_structure = {
            "num_levels": im.num_levels,
            "num_top_modules": im.num_top_modules,
            "num_leaf_modules": im.num_leaf_modules,
        }
    
    # Calculate community statistics
    community_stats = {}
    for comm_id, member_list in communities.items():
        comm_node_types = {}
        for node_id in member_list:
            node_type = node_metadata.get(node_id, {}).get("type", "unknown")
            comm_node_types[node_type] = comm_node_types.get(node_type, 0) + 1
        
        community_stats[comm_id] = {
            "size": len(member_list),
            "flow": flow_distribution.get(comm_id, 0),
            "node_types": comm_node_types,
        }
    
    logger.info(
        f"Infomap completed: {len(communities)} communities, "
        f"codelength={codelength:.4f}, modularity={modularity:.4f}"
    )
    
    return {
        "partition": partition,
        "communities": communities,
        "modularity": modularity,
        "codelength": codelength,
        "num_communities": len(communities),
        "flow_distribution": flow_distribution,
        "community_stats": community_stats,
        "hierarchical_structure": hierarchical_structure,
        "algorithm_info": {
            "name": "Infomap",
            "description": "Flow-based community detection using the Map Equation",
            "directed": directed,
            "num_trials": num_trials,
            "two_level": two_level,
        },
    }


def identify_entity_types(
    community_result: Dict[str, Any],
    graph_data: Dict[str, Any],
) -> Dict[int, Dict[str, Any]]:
    """
    Analyze detected communities to identify likely entity types (exchanges, services, etc.)
    based on transaction patterns within each community.
    
    Args:
        community_result: Result from run_infomap_algorithm
        graph_data: Original graph data with node/edge details
    
    Returns:
        dict mapping community_id to entity analysis
    """
    
    communities = community_result.get("communities", {})
    community_stats = community_result.get("community_stats", {})
    
    # Create edge lookup for analysis
    edges = graph_data.get("edges", [])
    edge_lookup: Dict[str, List[Dict]] = {}
    
    for edge in edges:
        source = edge.get("source")
        target = edge.get("target")
        if source:
            edge_lookup.setdefault(source, []).append(edge)
        if target:
            edge_lookup.setdefault(target + "_incoming", []).append(edge)
    
    entity_analysis = {}
    
    for comm_id, members in communities.items():
        stats = community_stats.get(comm_id, {})
        
        # Calculate transaction patterns
        total_incoming = 0
        total_outgoing = 0
        unique_external_sources = set()
        unique_external_targets = set()
        member_set = set(members)
        
        for member in members:
            # Outgoing edges
            for edge in edge_lookup.get(member, []):
                target = edge.get("target")
                value = edge.get("value", edge.get("weight", 0))
                if target not in member_set:
                    total_outgoing += value if value else 0
                    unique_external_targets.add(target)
            
            # Incoming edges
            for edge in edge_lookup.get(member + "_incoming", []):
                source = edge.get("source")
                value = edge.get("value", edge.get("weight", 0))
                if source not in member_set:
                    total_incoming += value if value else 0
                    unique_external_sources.add(source)
        
        # Determine likely entity type based on patterns
        entity_type = "unknown"
        confidence = 0.0
        
        size = stats.get("size", 0)
        flow = stats.get("flow", 0)
        
        # Heuristics for entity type detection
        if size == 1:
            if len(unique_external_sources) > 10 and len(unique_external_targets) > 10:
                entity_type = "exchange_hot_wallet"
                confidence = 0.7
            elif total_incoming > total_outgoing * 10:
                entity_type = "collection_address"
                confidence = 0.6
            elif total_outgoing > total_incoming * 10:
                entity_type = "distribution_address"
                confidence = 0.6
            else:
                entity_type = "individual_address"
                confidence = 0.5
        elif size <= 5:
            if len(unique_external_sources) > 50:
                entity_type = "service_cluster"
                confidence = 0.65
            else:
                entity_type = "related_addresses"
                confidence = 0.55
        elif size <= 20:
            entity_type = "entity_cluster"
            confidence = 0.6
        else:
            entity_type = "large_service"
            confidence = 0.55
        
        entity_analysis[comm_id] = {
            "likely_entity_type": entity_type,
            "confidence": confidence,
            "size": size,
            "flow": flow,
            "external_connections": {
                "unique_sources": len(unique_external_sources),
                "unique_targets": len(unique_external_targets),
                "total_incoming_value": total_incoming,
                "total_outgoing_value": total_outgoing,
            },
            "patterns": {
                "is_hub": len(unique_external_sources) + len(unique_external_targets) > 50,
                "is_sink": total_incoming > 0 and total_outgoing == 0,
                "is_source": total_outgoing > 0 and total_incoming == 0,
                "is_pass_through": total_incoming > 0 and total_outgoing > 0 and abs(total_incoming - total_outgoing) < total_incoming * 0.1,
            },
        }
    
    return entity_analysis


# Utility function for testing
def test_infomap():
    """Test function for Infomap algorithm"""
    if not INFOMAP_AVAILABLE:
        print("Infomap is not available. Install with: pip install infomap")
        return
    
    # Sample test data
    test_data = {
        "nodes": [
            {"id": "addr1", "type": "address", "label": "Address 1"},
            {"id": "addr2", "type": "address", "label": "Address 2"},
            {"id": "addr3", "type": "address", "label": "Address 3"},
            {"id": "tx1", "type": "transaction", "label": "TX 1"},
            {"id": "tx2", "type": "transaction", "label": "TX 2"},
        ],
        "edges": [
            {"source": "addr1", "target": "tx1", "value": 100000000},
            {"source": "tx1", "target": "addr2", "value": 50000000},
            {"source": "tx1", "target": "addr3", "value": 49000000},
            {"source": "addr2", "target": "tx2", "value": 30000000},
            {"source": "tx2", "target": "addr3", "value": 29000000},
        ],
    }
    
    result = run_infomap_algorithm(test_data)
    print("=" * 60)
    print("INFOMAP COMMUNITY DETECTION RESULTS")
    print("=" * 60)
    print(f"Number of communities: {result['num_communities']}")
    print(f"Codelength: {result['codelength']:.4f}")
    print(f"Modularity: {result['modularity']:.4f}")
    print("\nCommunities:")
    for comm_id, members in result["communities"].items():
        print(f"  Community {comm_id}: {members}")
    
    return result


if __name__ == "__main__":
    test_infomap()
