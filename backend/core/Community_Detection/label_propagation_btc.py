"""
Label Propagation Algorithm (LPA) community detection using NetworkX.
Provides a backend implementation similar in shape to the Louvain/Leiden helpers.
"""

from typing import Dict, Any, List

import networkx as nx


def run_label_propagation(graph_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Run Label Propagation community detection on the given graph.

    Args:
        graph_data: dict with 'nodes' and 'edges' lists.

    Returns:
        dict with:
          - partition: {node_id: community_id}
          - communities: {community_id: [node_ids]}
          - num_communities: int
    """
    nodes: List[Dict[str, Any]] = graph_data.get("nodes", [])
    edges: List[Dict[str, Any]] = graph_data.get("edges", [])

    if not nodes:
        raise ValueError("Graph must have at least one node")
    if not edges:
        raise ValueError("Graph must have at least one edge")

    G = nx.Graph()

    for node in nodes:
        node_id = node.get("id")
        if node_id is None:
            raise ValueError("Each node must have an 'id'")
        G.add_node(
            node_id,
            label=node.get("label", node_id),
            node_type=node.get("type", "unknown"),
        )

    for edge in edges:
        src = edge.get("source")
        tgt = edge.get("target")
        if src is None or tgt is None:
            continue
        if src not in G or tgt not in G:
            continue
        G.add_edge(src, tgt, weight=edge.get('weight', edge.get('value', 1.0)))

    # NetworkX async label propagation returns a generator of sets of nodes
    communities_iter = nx.algorithms.community.asyn_lpa_communities(G, weight='weight')
    communities_list = list(communities_iter)

    partition: Dict[str, int] = {}
    communities: Dict[int, List[str]] = {}

    for comm_id, community_nodes in enumerate(communities_list):
        node_ids = [n for n in community_nodes]
        communities[comm_id] = node_ids
        for n in node_ids:
            partition[n] = comm_id

    # Calculate modularity for quality metric
    try:
        modularity = nx.algorithms.community.modularity(G, communities_list)
    except Exception:
        # Fallback if modularity calculation fails
        modularity = 0.0

    return {
        "partition": partition,
        "communities": communities,
        "num_communities": len(communities),
        "modularity": modularity,  # Added quality metric
    }

