"""
UPI Community Detection Integration
====================================
This module integrates UPI transaction analysis with community detection algorithms
to identify fraud networks and suspicious transaction patterns.
"""

import logging
import traceback
from typing import Dict, List, Any, Optional
from datetime import datetime

# Import community detection algorithms
try:
    from ...core.Community_Detection.louvain_simple_btc import run_louvain_algorithm
    from ...core.Community_Detection.leiden_algorithm_btc import run_leiden_algorithm
    from ...core.Community_Detection.label_propagation_btc import run_label_propagation
    from ...core.Community_Detection.infomap_algorithm_btc import run_infomap_algorithm
    HAS_COMMUNITY_DETECTION = True
except ImportError as e:
    logging.warning(f"Community detection modules not available: {e}")
    HAS_COMMUNITY_DETECTION = False

logger = logging.getLogger('upi_community_detection')


def prepare_upi_graph_for_community_detection(upi_analysis_result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert UPI analysis result to format suitable for community detection algorithms.
    
    Args:
        upi_analysis_result: Result from analyze_upi_transactions()
        
    Returns:
        Graph data in format expected by community detection algorithms
    """
    if not upi_analysis_result or 'graph' not in upi_analysis_result:
        raise ValueError("Invalid UPI analysis result")
    
    graph_data = upi_analysis_result['graph']
    
    # Enhance nodes with risk information for community analysis
    enhanced_nodes = []
    for node in graph_data.get('nodes', []):
        enhanced_node = {
            'id': node.get('id'),
            'label': node.get('upiId', node.get('id')),
            'type': 'upi_address',
            'riskScore': node.get('riskScore', 0),
            'riskBand': node.get('riskBand', 'unknown'),
            'inTxCount': node.get('inTxCount', 0),
            'outTxCount': node.get('outTxCount', 0),
            'totalInAmount': node.get('totalInAmount', 0),
            'totalOutAmount': node.get('totalOutAmount', 0),
            'inCounterparties': node.get('inCounterparties', 0),
            'outCounterparties': node.get('outCounterparties', 0),
            'reasonCodes': node.get('reasonCodes', [])
        }
        enhanced_nodes.append(enhanced_node)
    
    # Enhance edges with transaction frequency and amount information
    enhanced_edges = []
    edge_frequency = {}
    edge_amounts = {}
    
    for edge in graph_data.get('edges', []):
        source = edge.get('source')
        target = edge.get('target')
        amount = edge.get('amount', 0)
        
        # Track frequency and total amounts for edge weights
        edge_key = f"{source}->{target}"
        edge_frequency[edge_key] = edge_frequency.get(edge_key, 0) + 1
        edge_amounts[edge_key] = edge_amounts.get(edge_key, 0) + amount
    
    # Create one enhanced edge per unique pair using aggregated data
    for edge_key in edge_frequency:
        parts = edge_key.split('->')
        source = parts[0]
        target = parts[1]
        frequency = edge_frequency[edge_key]
        total_amount = edge_amounts[edge_key]

        enhanced_edge = {
            'source': source,
            'target': target,
            'amount': total_amount,
            'frequency': frequency,
            'totalAmount': total_amount,
            'avgAmount': total_amount / frequency if frequency > 0 else 0,
            'weight': frequency,  # Primary weight for community detection
            'value': frequency    # Alternative weight field
        }
        enhanced_edges.append(enhanced_edge)
    
    return {
        'nodes': enhanced_nodes,
        'edges': enhanced_edges
    }


def analyze_community_risk_patterns(communities: Dict, node_risk_scores: Dict) -> Dict:
    """
    Analyze risk patterns within communities.
    
    Args:
        communities: Dictionary mapping community_id -> list of node_ids
        node_risk_scores: Dictionary mapping node_id -> risk_score
        
    Returns:
        Dictionary with risk analysis per community
    """
    community_risk_analysis = {}
    
    for community_id, members in communities.items():
        total_risk_score = 0
        high_risk_count = 0
        valid_members = 0
        max_risk = 0
        min_risk = float('inf')
        
        for member in members:
            # Get risk score and handle None values
            risk_score = node_risk_scores.get(member)
            
            # Skip None values
            if risk_score is None:
                continue
                
            # Convert to float if it's not already
            try:
                risk_score = float(risk_score)
            except (TypeError, ValueError):
                continue
                
            total_risk_score += risk_score
            valid_members += 1
            max_risk = max(max_risk, risk_score)
            min_risk = min(min_risk, risk_score)
            
            if risk_score > 70:
                high_risk_count += 1
        
        # Handle case where no valid risk scores found
        if valid_members == 0:
            community_risk_analysis[community_id] = {
                'avg_risk': 0.0,
                'max_risk': 0.0,
                'min_risk': 0.0,
                'high_risk_count': 0,
                'total_members': len(members),
                'valid_risk_count': 0
            }
        else:
            community_risk_analysis[community_id] = {
                'avg_risk': round(total_risk_score / valid_members, 2),
                'max_risk': round(max_risk, 2),
                'min_risk': round(min_risk, 2),
                'high_risk_count': high_risk_count,
                'total_members': len(members),
                'valid_risk_count': valid_members
            }
    
    return community_risk_analysis


def detect_upi_communities(upi_analysis_result: Dict[str, Any], 
                          algorithm: str = 'louvain',
                          resolution: float = 1.0,
                          **kwargs) -> Dict[str, Any]:
    """
    Run community detection on UPI transaction analysis results.
    
    Args:
        upi_analysis_result: Result from analyze_upi_transactions()
        algorithm: Community detection algorithm ('louvain', 'leiden', 'label_propagation', 'infomap')
        resolution: Resolution parameter for algorithm
        **kwargs: Additional algorithm-specific parameters
        
    Returns:
        Enhanced community detection results with UPI-specific analysis
    """
    if not HAS_COMMUNITY_DETECTION:
        raise ImportError("Community detection algorithms not available")
    
    if not upi_analysis_result:
        raise ValueError("UPI analysis result is required")
    
    logger.info(f"Starting UPI community detection with {algorithm} algorithm")
    
    try:
        # Prepare graph data for community detection
        graph_data = prepare_upi_graph_for_community_detection(upi_analysis_result)
        
        if not graph_data.get('nodes') or not graph_data.get('edges'):
            logger.warning(f"Graph is empty (nodes: {len(graph_data.get('nodes', []))}, edges: {len(graph_data.get('edges', []))}). Skipping community detection.")
            return {
                'algorithm': algorithm,
                'resolution': resolution,
                'timestamp': datetime.utcnow().isoformat(),
                'community_detection': {'partition': {}, 'communities': {}, 'modularity': 0, 'num_communities': 0},
                'community_risk_analysis': {},
                'summary': {'total_communities': 0, 'modularity': 0, 'high_risk_communities': 0, 'total_nodes_analyzed': 0, 'total_edges_analyzed': 0}
            }
            
        # Run selected community detection algorithm
        if algorithm == 'louvain':
            community_results = run_louvain_algorithm(graph_data, resolution=resolution, **kwargs)
        elif algorithm == 'leiden':
            community_results = run_leiden_algorithm(graph_data, resolution=resolution, **kwargs)
        elif algorithm == 'label_propagation':
            community_results = run_label_propagation(graph_data, **kwargs)
        elif algorithm == 'infomap':
            community_results = run_infomap_algorithm(graph_data, **kwargs)
        else:
            raise ValueError(f"Unknown algorithm: {algorithm}")
        
        # Convert node list to risk score dictionary for analysis
        node_risk_dict = {}
        for node in graph_data['nodes']:
            node_id = node.get('id')
            risk_score = node.get('riskScore', 0)
            if node_id:
                node_risk_dict[node_id] = risk_score
        
        # Build communities dictionary in the format {community_id: [list of member nodes]}
        communities_dict = {}
        
        # Check different possible formats from community detection algorithms
        if 'communities' in community_results and isinstance(community_results['communities'], dict):
            # Format: {'communities': {0: ['node1', 'node2'], 1: ['node3', 'node4']}}
            communities_dict = community_results['communities']
        elif 'partition' in community_results:
            # Format: {'partition': {'node1': 0, 'node2': 0, 'node3': 1}}
            partition = community_results['partition']
            for node_id, comm_id in partition.items():
                if comm_id not in communities_dict:
                    communities_dict[comm_id] = []
                communities_dict[comm_id].append(node_id)
        elif isinstance(community_results, dict) and all(isinstance(k, (int, str)) for k in community_results.keys()):
            # Assume the whole result is a partition dict
            for node_id, comm_id in community_results.items():
                if isinstance(comm_id, (int, str)) and not isinstance(node_id, (int, str)):  # Simple check
                    if comm_id not in communities_dict:
                        communities_dict[comm_id] = []
                    communities_dict[comm_id].append(node_id)
                else:
                    # Maybe it's already in communities format
                    communities_dict = community_results
                    break
        
        # If we still don't have communities, try to extract from the result
        if not communities_dict:
            # Try to get from the main result structure
            for key, value in community_results.items():
                if isinstance(value, dict) and all(isinstance(v, list) for v in value.values()):
                    communities_dict = value
                    break
        
        # Log the structure for debugging
        logger.debug(f"Communities dict type: {type(communities_dict)}")
        if communities_dict:
            sample_key = next(iter(communities_dict))
            logger.debug(f"Sample community format: {sample_key} -> {type(communities_dict[sample_key])}")
        
        # Analyze risk patterns within communities
        community_risk_analysis = analyze_community_risk_patterns(
            communities_dict,  # Pass the communities dict with lists of members
            node_risk_dict  # Pass the risk score dict
        )
        
        # Create enhanced results
        enhanced_results = {
            'algorithm': algorithm,
            'resolution': resolution,
            'timestamp': datetime.utcnow().isoformat(),
            'community_detection': {
                'partition': community_results.get('partition', {}),
                'communities': communities_dict,
                'modularity': community_results.get('modularity', 0),
                'num_communities': len(communities_dict)
            },
            'community_risk_analysis': community_risk_analysis,
            'summary': {
                'total_communities': len(communities_dict),
                'modularity': community_results.get('modularity', 0),
                'high_risk_communities': len([
                    c for c in community_risk_analysis.values() 
                    if c.get('avg_risk', 0) >= 50 or c.get('high_risk_count', 0) > 0
                ]),
                'total_nodes_analyzed': len(graph_data['nodes']),
                'total_edges_analyzed': len(graph_data['edges'])
            }
        }
        
        logger.info(f"UPI community detection completed: {enhanced_results['summary']['total_communities']} communities, "
                   f"modularity={enhanced_results['community_detection']['modularity']:.4f}, "
                   f"high_risk_communities={enhanced_results['summary']['high_risk_communities']}")
        
        return enhanced_results
        
    except Exception as e:
        logger.error(f"UPI community detection failed: {str(e)}")
        logger.error(traceback.format_exc())
        raise


def get_suspicious_communities(community_results: Dict[str, Any], 
                             min_risk_score: float = 60.0,
                             min_members: int = 3) -> List[Dict[str, Any]]:
    """
    Extract suspicious communities based on risk criteria.
    
    Args:
        community_results: Results from detect_upi_communities()
        min_risk_score: Minimum average risk score for suspicious communities
        min_members: Minimum number of members for suspicious communities
        
    Returns:
        List of suspicious communities sorted by risk score
    """
    if not community_results or 'community_risk_analysis' not in community_results:
        return []
    
    suspicious_communities = []
    
    for comm_id, comm_data in community_results['community_risk_analysis'].items():
        if (comm_data.get('avgRiskScore', 0) >= min_risk_score and 
            comm_data.get('memberCount', 0) >= min_members):
            
            suspicious_communities.append({
                'communityId': comm_id,
                'riskLevel': comm_data.get('riskLevel'),
                'avgRiskScore': comm_data.get('avgRiskScore'),
                'memberCount': comm_data.get('memberCount'),
                'highRiskCount': comm_data.get('highRiskCount'),
                'criticalRiskCount': comm_data.get('criticalRiskCount'),
                'totalAmount': comm_data.get('totalAmount'),
                'members': comm_data.get('members', [])
            })
    
    # Sort by average risk score (highest first)
    suspicious_communities.sort(key=lambda x: x['avgRiskScore'], reverse=True)
    
    return suspicious_communities


def export_community_analysis_to_json(community_results: Dict[str, Any], 
                                  output_path: str) -> bool:
    """
    Export community analysis results to JSON file.
    
    Args:
        community_results: Results from detect_upi_communities()
        output_path: Path to save the JSON file
        
    Returns:
        True if successful, False otherwise
    """
    try:
        import json
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(community_results, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Community analysis exported to: {output_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to export community analysis: {str(e)}")
        return False
