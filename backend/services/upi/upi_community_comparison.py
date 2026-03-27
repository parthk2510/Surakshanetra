"""
Advanced UPI Community Detection Comparison and Fraud Analysis
========================================================
This module provides comprehensive comparison metrics for community detection algorithms
and advanced fraud detection capabilities including density, velocity, betweenness,
and weighted risk scoring for mule account detection.
"""

import logging
import numpy as np
from typing import Dict, List, Any, Tuple, Optional
from datetime import datetime, timedelta
import networkx as nx
from collections import defaultdict

logger = logging.getLogger('upi_community_comparison')


def _build_graph(graph_data):
    """Build a NetworkX graph from graph_data dict (shared helper)."""
    G = nx.Graph()
    for node in graph_data.get('nodes', []):
        G.add_node(node['id'], **node)
    for edge in graph_data.get('edges', []):
        G.add_edge(edge['source'], edge['target'], **edge)
    return G


class UPICommunityComparison:
    """Advanced community detection comparison and fraud analysis system."""

    def __init__(self):
        self.algorithms = ['louvain', 'leiden', 'label_propagation', 'infomap']
        self.risk_weights = {
            'density': 0.15,
            'velocity': 0.20,
            'in_out_ratio': 0.15,
            'betweenness': 0.20,
            'community_size': 0.10,
            'risk_score': 0.20
        }
        self.thresholds = {
            'high_risk': 70.0,
            'medium_risk': 50.0,
            'low_risk': 30.0,
            'suspicious_density': 0.8,
            'suspicious_velocity': 1000.0,
            'suspicious_ratio': 5.0,
            'suspicious_betweenness': 0.1
        }
    
    def calculate_graph_metrics(self, graph_data: Dict[str, Any], G: nx.Graph = None) -> Dict[str, Any]:
        """Calculate comprehensive graph-level metrics."""
        if G is None:
            G = _build_graph(graph_data)
        
        if len(G.nodes()) == 0:
            return {}
        
        # Basic metrics
        num_nodes = G.number_of_nodes()
        num_edges = G.number_of_edges()
        density = nx.density(G)
        
        # Centrality measures
        betweenness = nx.betweenness_centrality(G, weight='weight')
        closeness = nx.closeness_centrality(G)
        try:
            eigenvector = nx.eigenvector_centrality(G, weight='weight')
        except (nx.PowerIterationFailedConvergence, nx.NetworkXError):
            try:
                eigenvector = nx.eigenvector_centrality_numpy(G, weight='weight')
            except Exception:
                eigenvector = {n: 0.0 for n in G.nodes()}
        
        # Clustering
        clustering = nx.average_clustering(G, weight='weight')
        
        # Connected components
        components = list(nx.connected_components(G))
        largest_component_size = max(len(comp) for comp in components) if components else 0
        
        return {
            'num_nodes': num_nodes,
            'num_edges': num_edges,
            'density': density,
            'avg_betweenness': np.mean(list(betweenness.values())) if betweenness else 0,
            'avg_closeness': np.mean(list(closeness.values())) if closeness else 0,
            'avg_eigenvector': np.mean(list(eigenvector.values())) if eigenvector else 0,
            'clustering_coefficient': clustering,
            'largest_component_size': largest_component_size,
            'num_connected_components': len(components),
            'betweenness_centrality': betweenness,
            'closeness_centrality': closeness,
            'eigenvector_centrality': eigenvector
        }
    
    def calculate_community_metrics(self, graph_data: Dict[str, Any],
                               communities: Dict[int, List[str]], G: nx.Graph = None) -> Dict[int, Dict[str, Any]]:
        """Calculate detailed metrics for each community."""
        if G is None:
            G = _build_graph(graph_data)
        
        community_metrics = {}
        
        for comm_id, members in communities.items():
            if not members:
                continue
            
            # Create subgraph for this community
            subgraph = G.subgraph(members)
            
            # Basic metrics
            num_nodes = len(members)
            num_edges = subgraph.number_of_edges()
            density = nx.density(subgraph) if num_nodes > 1 else 0
            
            # Transaction metrics
            total_amount = 0
            total_transactions = 0
            in_amounts = defaultdict(float)
            out_amounts = defaultdict(float)
            in_counts = defaultdict(int)
            out_counts = defaultdict(int)
            
            for edge in graph_data.get('edges', []):
                source, target = edge['source'], edge['target']
                amount = edge.get('amount', 0)
                
                if source in members and target in members:
                    total_amount += amount
                    total_transactions += 1
                    out_amounts[source] += amount
                    in_amounts[target] += amount
                    out_counts[source] += 1
                    in_counts[target] += 1
            
            # Velocity metrics (transactions per time unit)
            timestamps = [edge.get('timestamp', 0) for edge in graph_data.get('edges', [])
                        if edge.get('source') in members and edge.get('target') in members]
            
            if timestamps:
                time_span = max(timestamps) - min(timestamps) if max(timestamps) != min(timestamps) else 1
                velocity = total_transactions / max(time_span, 1)  # transactions per second
                daily_velocity = velocity * 86400  # transactions per day
            else:
                velocity = 0
                daily_velocity = 0
            
            # In/Out ratios
            in_out_ratios = {}
            for member in members:
                in_val = in_amounts.get(member, 0)
                out_val = out_amounts.get(member, 0)
                ratio = out_val / max(in_val, 1) if in_val > 0 else float('inf') if out_val > 0 else 0
                in_out_ratios[member] = ratio
            
            avg_in_out_ratio = np.mean(list(in_out_ratios.values())) if in_out_ratios else 0
            
            # Betweenness centrality within community
            betweenness = nx.betweenness_centrality(subgraph, weight='weight')
            avg_betweenness = np.mean(list(betweenness.values())) if betweenness else 0
            
            # Risk aggregation
            node_risk_scores = []
            for node in graph_data.get('nodes', []):
                if node['id'] in members:
                    node_risk_scores.append(node.get('riskScore', 0))
            
            avg_risk_score = np.mean(node_risk_scores) if node_risk_scores else 0
            max_risk_score = max(node_risk_scores) if node_risk_scores else 0
            
            # Suspicion indicators
            suspicious_indicators = {
                'high_density': density > self.thresholds['suspicious_density'],
                'high_velocity': daily_velocity > self.thresholds['suspicious_velocity'],
                'high_ratio': avg_in_out_ratio > self.thresholds['suspicious_ratio'],
                'high_betweenness': avg_betweenness > self.thresholds['suspicious_betweenness'],
                'high_risk': avg_risk_score > self.thresholds['high_risk']
            }
            
            community_metrics[comm_id] = {
                'id': comm_id,
                'member_count': num_nodes,
                'edge_count': num_edges,
                'density': density,
                'total_amount': total_amount,
                'total_transactions': total_transactions,
                'avg_transaction_amount': total_amount / max(total_transactions, 1),
                'velocity': velocity,
                'daily_velocity': daily_velocity,
                'avg_in_out_ratio': avg_in_out_ratio,
                'max_in_out_ratio': max(in_out_ratios.values()) if in_out_ratios else 0,
                'avg_betweenness': avg_betweenness,
                'max_betweenness': max(betweenness.values()) if betweenness else 0,
                'avg_risk_score': avg_risk_score,
                'max_risk_score': max_risk_score,
                'suspicious_indicators': suspicious_indicators,
                'suspicion_score': sum(suspicious_indicators.values()),
                'members': members,
                'in_out_ratios': in_out_ratios,
                'betweenness_scores': betweenness
            }
        
        return community_metrics
    
    def calculate_stability_metrics(self, graph_data: Dict[str, Any], 
                                results: Dict[str, Dict[str, Any]]) -> Dict[str, float]:
        """Calculate stability metrics across different algorithms."""
        if len(results) < 2:
            return {}
        
        algorithms = list(results.keys())
        stability_scores = {}
        
        for i, alg1 in enumerate(algorithms):
            for j, alg2 in enumerate(algorithms[i+1:], i+1):
                # Calculate normalized mutual information between partitions
                partition1 = results[alg1].get('community_detection', {}).get('partition', {})
                partition2 = results[alg2].get('community_detection', {}).get('partition', {})
                
                nmi = self._calculate_nmi(partition1, partition2)
                stability_key = f"{alg1}_vs_{alg2}"
                stability_scores[stability_key] = nmi
        
        # Average stability for each algorithm
        avg_stability = {}
        for alg in algorithms:
            related_scores = [score for key, score in stability_scores.items() if alg in key]
            avg_stability[alg] = np.mean(related_scores) if related_scores else 0
        
        return avg_stability
    
    def _calculate_nmi(self, partition1: Dict[str, int], partition2: Dict[str, int]) -> float:
        """Calculate Normalized Mutual Information between two partitions."""
        if not partition1 or not partition2:
            return 0.0
        
        nodes = set(partition1.keys()) & set(partition2.keys())
        if not nodes:
            return 0.0
        
        # Create label mappings
        labels1 = [partition1[node] for node in nodes]
        labels2 = [partition2[node] for node in nodes]
        
        # Calculate contingency matrix
        n = len(nodes)
        contingency = defaultdict(lambda: defaultdict(int))
        
        for i in range(n):
            contingency[labels1[i]][labels2[i]] += 1
        
        # Calculate NMI
        mi = 0.0
        h1 = 0.0
        h2 = 0.0
        
        for i in contingency:
            row_sum = sum(contingency[i].values())
            h1 -= (row_sum / n) * np.log2(row_sum / n)
            for j in contingency[i]:
                if contingency[i][j] > 0:
                    mi -= (contingency[i][j] / n) * np.log2((contingency[i][j] * n) / (row_sum * sum(contingency[k][j] for k in contingency)))
        
        for j in set().union(*[set(contingency[i].keys()) for i in contingency]):
            col_sum = sum(contingency[i][j] for i in contingency)
            h2 -= (col_sum / n) * np.log2(col_sum / n)
        
        if h1 == 0 or h2 == 0:
            return 0.0
        
        return mi / np.sqrt(h1 * h2)
    
    def calculate_weighted_risk_score(self, community_metrics: Dict[str, Any]) -> float:
        """Calculate weighted risk score for a community."""
        if not community_metrics:
            return 0.0
        
        # Normalize metrics to 0-1 scale
        normalized_metrics = {
            'density': min(community_metrics.get('density', 0) / self.thresholds['suspicious_density'], 1.0),
            'velocity': min(community_metrics.get('daily_velocity', 0) / self.thresholds['suspicious_velocity'], 1.0),
            'in_out_ratio': min(community_metrics.get('avg_in_out_ratio', 0) / self.thresholds['suspicious_ratio'], 1.0),
            'betweenness': min(community_metrics.get('avg_betweenness', 0) / self.thresholds['suspicious_betweenness'], 1.0),
            'community_size': min(community_metrics.get('member_count', 0) / 50, 1.0),  # Normalize to 50 members
            'risk_score': community_metrics.get('avg_risk_score', 0) / 100
        }
        
        # Calculate weighted score
        weighted_score = sum(
            self.risk_weights[metric] * normalized_metrics[metric]
            for metric in self.risk_weights
        )
        
        return weighted_score * 100  # Scale to 0-100
    
    def rank_suspicious_accounts(self, graph_data: Dict[str, Any], 
                              community_metrics: Dict[int, Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Rank accounts by suspiciousness across all metrics."""
        account_scores = {}
        
        for comm_id, metrics in community_metrics.items():
            for member in metrics['members']:
                # Get account-specific metrics
                in_out_ratio = metrics['in_out_ratios'].get(member, 0)
                betweenness = metrics['betweenness_scores'].get(member, 0)
                
                # Get node risk score
                node_risk = 0
                for node in graph_data.get('nodes', []):
                    if node['id'] == member:
                        node_risk = node.get('riskScore', 0)
                        break
                
                # Calculate account-level weighted score
                account_score = (
                    self.risk_weights['in_out_ratio'] * min(in_out_ratio / self.thresholds['suspicious_ratio'], 1.0) +
                    self.risk_weights['betweenness'] * min(betweenness / self.thresholds['suspicious_betweenness'], 1.0) +
                    self.risk_weights['risk_score'] * (node_risk / 100)
                ) * 100
                
                account_scores[member] = {
                    'account_id': member,
                    'community_id': comm_id,
                    'weighted_score': account_score,
                    'risk_score': node_risk,
                    'in_out_ratio': in_out_ratio,
                    'betweenness': betweenness,
                    'community_risk': metrics['avg_risk_score'],
                    'community_size': metrics['member_count'],
                    'suspicious_indicators': {
                        'high_ratio': in_out_ratio > self.thresholds['suspicious_ratio'],
                        'high_betweenness': betweenness > self.thresholds['suspicious_betweenness'],
                        'high_risk': node_risk > self.thresholds['high_risk']
                    }
                }
        
        # Sort by weighted score
        ranked_accounts = sorted(account_scores.values(), key=lambda x: x['weighted_score'], reverse=True)
        
        return ranked_accounts
    
    def compare_algorithms(self, graph_data: Dict[str, Any], 
                        results: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """Compare all community detection algorithms comprehensively."""
        # Build graph once and reuse across all metric calculations
        G = _build_graph(graph_data)

        comparison = {
            'timestamp': datetime.utcnow().isoformat(),
            'graph_metrics': self.calculate_graph_metrics(graph_data, G=G),
            'algorithm_results': {},
            'stability_metrics': self.calculate_stability_metrics(graph_data, results),
            'ranking': {}
        }

        # Analyze each algorithm result
        for algorithm, result in results.items():
            communities = result.get('community_detection', {}).get('communities', {})
            community_metrics = self.calculate_community_metrics(graph_data, communities, G=G)
            
            # Calculate algorithm-level metrics
            modularity = result.get('community_detection', {}).get('modularity', 0)
            num_communities = len(communities)
            avg_community_size = np.mean([len(members) for members in communities.values()]) if communities else 0
            
            # Risk analysis
            suspicious_communities = [
                comm_id for comm_id, metrics in community_metrics.items()
                if self.calculate_weighted_risk_score(metrics) > self.thresholds['high_risk']
            ]
            
            # Top suspicious accounts
            ranked_accounts = self.rank_suspicious_accounts(graph_data, community_metrics)
            
            comparison['algorithm_results'][algorithm] = {
                'modularity': modularity,
                'num_communities': num_communities,
                'avg_community_size': avg_community_size,
                'suspicious_communities': len(suspicious_communities),
                'suspicious_community_ratio': len(suspicious_communities) / max(num_communities, 1),
                'community_metrics': community_metrics,
                'top_suspicious_accounts': ranked_accounts[:10],  # Top 10
                'weighted_risk_scores': {
                    comm_id: self.calculate_weighted_risk_score(metrics)
                    for comm_id, metrics in community_metrics.items()
                }
            }
        
        # Rank algorithms by overall performance
        algorithm_scores = {}
        for algorithm, metrics in comparison['algorithm_results'].items():
            score = (
                0.3 * metrics['modularity'] +  # Modularity importance
                0.2 * (1 - abs(metrics['avg_community_size'] - 10) / 10) +  # Ideal community size
                0.3 * metrics['suspicious_community_ratio'] +  # Fraud detection capability
                0.2 * comparison['stability_metrics'].get(algorithm, 0)  # Stability
            )
            algorithm_scores[algorithm] = score
        
        comparison['ranking'] = dict(sorted(algorithm_scores.items(), key=lambda x: x[1], reverse=True))
        
        return comparison
    
    def generate_manual_validation_data(self, comparison_results: Dict[str, Any], 
                                   top_n: int = 50) -> Dict[str, Any]:
        """Generate data for manual validation loop."""
        # Get top suspicious accounts across all algorithms
        all_suspicious = []
        for algorithm, results in comparison_results['algorithm_results'].items():
            for account in results['top_suspicious_accounts']:
                account['algorithm'] = algorithm
                all_suspicious.append(account)
        
        # Remove duplicates and sort by weighted score
        unique_accounts = {}
        for account in all_suspicious:
            account_id = account['account_id']
            if account_id not in unique_accounts or account['weighted_score'] > unique_accounts[account_id]['weighted_score']:
                unique_accounts[account_id] = account
        
        top_accounts = sorted(unique_accounts.values(), key=lambda x: x['weighted_score'], reverse=True)[:top_n]
        
        return {
            'validation_batch': {
                'batch_id': f"validation_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                'timestamp': datetime.utcnow().isoformat(),
                'total_accounts': len(top_accounts),
                'accounts': top_accounts,
                'validation_fields': [
                    'account_id',
                    'weighted_score',
                    'risk_score',
                    'in_out_ratio',
                    'betweenness',
                    'community_id',
                    'community_size',
                    'suspicious_indicators',
                    'algorithm'
                ]
            },
            'summary': {
                'high_risk_accounts': len([a for a in top_accounts if a['weighted_score'] > self.thresholds['high_risk']]),
                'medium_risk_accounts': len([a for a in top_accounts if self.thresholds['medium_risk'] <= a['weighted_score'] <= self.thresholds['high_risk']]),
                'low_risk_accounts': len([a for a in top_accounts if a['weighted_score'] < self.thresholds['medium_risk']]),
                'avg_weighted_score': np.mean([a['weighted_score'] for a in top_accounts]) if top_accounts else 0
            }
        }


def run_comprehensive_comparison(graph_data: Dict[str, Any], 
                            community_results: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """
    Run comprehensive community detection comparison and fraud analysis.
    
    Args:
        graph_data: UPI transaction graph data
        community_results: Results from different community detection algorithms
        
    Returns:
        Comprehensive comparison results with fraud analysis
    """
    comparator = UPICommunityComparison()
    return comparator.compare_algorithms(graph_data, community_results)


def generate_validation_batch(comparison_results: Dict[str, Any], 
                         top_n: int = 50) -> Dict[str, Any]:
    """Generate manual validation batch data."""
    comparator = UPICommunityComparison()
    return comparator.generate_manual_validation_data(comparison_results, top_n)
