"""
Leiden community detection using python-igraph + leidenalg.
This module provides a backend implementation to mirror the Louvain endpoint.
"""

from typing import Dict, List, Any

import igraph as ig
import leidenalg


def run_leiden_algorithm(
    graph_data: Dict[str, Any],
    weight_attribute: str = "weight",
    resolution: float = 1.0,
) -> Dict[str, Any]:
    """
    Run Leiden community detection.

    Args:
        graph_data: dict with 'nodes' (list of objects with 'id') and 'edges'
                    (list with 'source', 'target', and optional weight/value).
        weight_attribute: name of the weight attribute to use (default: weight).
        resolution: resolution parameter (higher -> more/smaller communities).

    Returns:
        dict containing partition map, communities, modularity, num_communities.
    """
    nodes: List[Dict[str, Any]] = graph_data.get("nodes", [])
    edges: List[Dict[str, Any]] = graph_data.get("edges", [])

    if not nodes:
        raise ValueError("Graph must have at least one node")
    if not edges:
        raise ValueError("Graph must have at least one edge")

    # Map node IDs to igraph vertex indices
    node_id_to_idx = {}
    ig_graph = ig.Graph()
    ig_graph.add_vertices(len(nodes))

    for idx, node in enumerate(nodes):
        node_id = node.get("id")
        if node_id is None:
            raise ValueError("Each node must have an 'id'")
        node_id_to_idx[node_id] = idx
        ig_graph.vs[idx]["name"] = node_id
        ig_graph.vs[idx]["label"] = node.get("label", node_id)
        ig_graph.vs[idx]["type"] = node.get("type", "unknown")

    # Build edges and weights
    ig_edges = []
    weights = []
    for edge in edges:
        source = edge.get("source")
        target = edge.get("target")
        if source not in node_id_to_idx or target not in node_id_to_idx:
            # Skip edges that reference missing nodes
            continue
        ig_edges.append((node_id_to_idx[source], node_id_to_idx[target]))
        weight_val = edge.get(weight_attribute, edge.get("value", edge.get("weight", 1.0)))
        weights.append(weight_val if weight_val is not None else 1.0)

    if not ig_edges:
        raise ValueError("No valid edges after filtering missing nodes")

    ig_graph.add_edges(ig_edges)
    ig_graph.es[weight_attribute] = weights

    # Run Leiden with RBConfigurationVertexPartition (supports resolution parameter)
    partition = leidenalg.find_partition(
        ig_graph,
        leidenalg.RBConfigurationVertexPartition,
        weights=weights,
        resolution_parameter=resolution,
    )

    membership = partition.membership

    # Calculate PROPER modularity (0 to 1 range) using igraph's modularity function
    # partition.quality() returns resolution-scaled quality, not standard modularity
    try:
        modularity = ig_graph.modularity(membership, weights=weights)
    except Exception:
        # Fallback: normalize quality() by total edge weight
        total_weight = sum(weights)
        modularity = partition.quality() / (2 * total_weight) if total_weight > 0 else 0.0
    
    # Ensure modularity is in valid range [-0.5, 1]
    modularity = max(-0.5, min(1.0, modularity))

    # Build partition mapping and communities
    partition_map: Dict[str, int] = {}
    communities: Dict[int, List[str]] = {}
    for idx, comm_id in enumerate(membership):
        node_id = ig_graph.vs[idx]["name"]
        partition_map[node_id] = comm_id
        communities.setdefault(comm_id, []).append(node_id)

    return {
        "partition": partition_map,
        "communities": communities,
        "modularity": modularity,
        "num_communities": len(communities),
    }

