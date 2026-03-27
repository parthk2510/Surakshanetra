"""
Test script for Louvain Community Detection Algorithm (No Visualization)
This script tests the Louvain algorithm on Bitcoin transaction graphs
and can be used as a reference for backend integration.
"""

import json
import os
import networkx as nx
import community.community_louvain as community_louvain
from pathlib import Path


def load_graph_from_json(file_path):
    """
    Load graph data from a JSON file.
    
    Args:
        file_path (str): Path to the JSON file containing graph data
        
    Returns:
        dict: Graph data with nodes and edges
    """
    with open(file_path, 'r') as f:
        return json.load(f)


def run_louvain_algorithm(graph_data, resolution=1.0, weight_attribute='weight'):
    """
    Run Louvain community detection algorithm on graph data.
    
    Args:
        graph_data (dict): Dictionary containing 'nodes' and 'edges' lists
        resolution (float): Resolution parameter (1.0 = standard, >1.0 = smaller communities)
        weight_attribute (str): Edge attribute to use as weight
        
    Returns:
        dict: Results containing:
            - partition: {node_id: community_id}
            - communities: {community_id: [node_ids]}
            - modularity: Quality metric of the partition
            - num_communities: Total number of communities found
            - graph: NetworkX graph object
    """
    # Build NetworkX graph (undirected for Louvain)
    G = nx.Graph()
    
    # Add nodes with attributes
    for node in graph_data.get('nodes', []):
        G.add_node(
            node['id'],
            label=node.get('label', node['id']),
            node_type=node.get('type', 'unknown')
        )
    
    # Add edges with weights
    for edge in graph_data.get('edges', []):
        # Use 'value' or 'weight' from edge data
        weight = edge.get('value', edge.get('weight', 1))
        G.add_edge(
            edge['source'],
            edge['target'],
            weight=weight
        )
    
    # Apply Louvain algorithm
    partition = community_louvain.best_partition(G, weight=weight_attribute, resolution=resolution)
    
    # Calculate modularity (quality metric)
    modularity = community_louvain.modularity(partition, G, weight=weight_attribute)
    
    # Organize nodes by community
    communities = {}
    for node_id, comm_id in partition.items():
        if comm_id not in communities:
            communities[comm_id] = []
        communities[comm_id].append(node_id)
    
    return {
        'partition': partition,
        'communities': communities,
        'modularity': modularity,
        'num_communities': len(communities),
    }


def print_community_results(results, graph=None):
    """
    Print community detection results in a readable format.

    Args:
        results (dict): Results from run_louvain_algorithm
        graph: Optional NetworkX graph. Falls back to results['_graph'] if not provided.
    """
    print("=" * 60)
    print("LOUVAIN COMMUNITY DETECTION RESULTS")
    print("=" * 60)
    print(f"Total Communities Found: {results['num_communities']}")
    print(f"Modularity Score: {results['modularity']:.4f}")
    print(f"(Higher modularity = better community structure)")
    print("=" * 60)
    print()

    G = graph or results.get('_graph')
    
    for comm_id, members in sorted(results['communities'].items()):
        print(f"┌─ Community {comm_id} ({len(members)} nodes)")
        print("│")
        
        for member in members:
            if G is not None:
                node_type = G.nodes[member].get('node_type', 'unknown')
                label = G.nodes[member].get('label', member[:15])
            else:
                node_type = 'unknown'
                label = str(member)[:15]
            
            # Truncate long labels
            if len(label) > 15:
                label = label[:12] + "..."
            
            print(f"│  [{node_type.upper():12}] {label}")
        
        print("└" + "─" * 58)
        print()


def export_results_to_json(results, output_path):
    """
    Export community detection results to JSON format.
    This format can be used by the frontend to visualize communities.
    
    Args:
        results (dict): Results from run_louvain_algorithm
        output_path (str): Path to save the JSON output
    """
    # Prepare data for JSON export (exclude NetworkX graph object)
    export_data = {k: v for k, v in results.items() if k != '_graph'}
    export_data['communities'] = {str(k): v for k, v in results['communities'].items()}
    
    with open(output_path, 'w') as f:
        json.dump(export_data, f, indent=2)
    
    print(f"Results exported to: {output_path}")


def main():
    """Main test function"""
    # Get the project root directory
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    
    # Path to test graph
    graph_file = project_root / 'data' / 'graph' / 'graph_1A1zP1eP5QGe.json'
    
    print(f"Loading graph from: {graph_file}")
    print()
    
    if not graph_file.exists():
        print(f"ERROR: Graph file not found at {graph_file}")
        return
    
    # Load graph data
    graph_data = load_graph_from_json(graph_file)
    
    print(f"Graph loaded: {len(graph_data.get('nodes', []))} nodes, "
          f"{len(graph_data.get('edges', []))} edges\n")
    
    # Run Louvain algorithm
    print("Running Louvain algorithm...")
    results = run_louvain_algorithm(graph_data, resolution=1.0)
    print()
    
    # Print results
    print_community_results(results)
    
    # Optional: Export results to JSON (commented out by default)
    # Uncomment the lines below if you want to save results to a file
    # output_file = project_root / 'data' / 'graph' / 'louvain_results.json'
    # export_results_to_json(results, output_file)
    
    # Return results for potential further processing
    return results


if __name__ == "__main__":
    results = main()
