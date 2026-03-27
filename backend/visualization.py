"""
Visualization Components for ChainBreak
Network visualization using Matplotlib and Gephi integration
"""

import matplotlib.pyplot as plt
import networkx as nx
from neo4j import GraphDatabase
import logging
from typing import Dict, Any, List, Optional
import os

logger = logging.getLogger(__name__)


class NetworkVisualizer:
    """Creates network visualizations for transaction networks"""
    
    def __init__(self, neo4j_driver):
        self.driver = neo4j_driver
        
    def visualize_address_network(self, address: str, depth: int = 2, max_nodes: int = 100) -> nx.DiGraph:
        """Create network visualization for address transactions"""
        try:
            logger.info(f"Creating network visualization for address: {address}")
            
            # Build network graph from Neo4j
            G = self._build_network_graph(address, depth, max_nodes)
            
            if len(G.nodes()) == 0:
                logger.warning(f"No network data found for address {address}")
                return G
            
            # Create visualization
            plt.figure(figsize=(16, 12))
            
            # Use spring layout for better visualization
            pos = nx.spring_layout(G, k=1.0, iterations=50, seed=42)
            
            # Color nodes based on type
            node_colors = []
            node_sizes = []
            
            for node in G.nodes():
                if node == address:
                    node_colors.append('red')  # Source address
                    node_sizes.append(500)
                elif G.nodes[node].get('type') == 'Transaction':
                    node_colors.append('lightblue')  # Transactions
                    node_sizes.append(500)
                else:
                    node_colors.append('lightgreen')  # Other addresses
                    node_sizes.append(500)
            
            # Draw nodes
            nx.draw_networkx_nodes(G, pos, 
                                  node_color=node_colors,
                                  node_size=node_sizes,
                                  alpha=0.8)
            
            # Draw edges with different colors based on relationship type
            edge_colors = []
            edge_widths = []
            
            for u, v, data in G.edges(data=True):
                if data.get('type') == 'PARTICIPATED_IN':
                    edge_colors.append('red')
                    edge_widths.append(2)
                elif data.get('type') == 'PARTICIPATED_IN':
                    edge_colors.append('blue')
                    edge_widths.append(2)
                else:
                    edge_colors.append('gray')
                    edge_widths.append(1)
            
            nx.draw_networkx_edges(G, pos, 
                                  edge_color=edge_colors,
                                  width=edge_widths,
                                  alpha=0.6,
                                  arrows=True,
                                  arrowsize=15)
            
            # Add labels (shortened for readability)
            labels = {}
            for node in G.nodes():
                if node == address:
                    labels[node] = f"SOURCE\n{node[:8]}..."
                elif len(node) > 10:
                    labels[node] = f"{node[:8]}..."
                else:
                    labels[node] = node
            
            nx.draw_networkx_labels(G, pos, labels, font_size=8, font_weight='bold')
            
            plt.title(f"Transaction Network for Address: {address[:10]}...\nDepth: {depth}, Nodes: {len(G.nodes())}", 
                     fontsize=14, fontweight='bold')
            plt.axis('off')
            plt.tight_layout()
            
            # Save the plot
            output_file = f"network_{address[:8]}_{depth}.png"
            plt.savefig(output_file, dpi=300, bbox_inches='tight')
            logger.info(f"Network visualization saved to {output_file}")
            
            # Close the plot to prevent GUI from opening
            plt.close()
            return G
            
        except Exception as e:
            logger.error(f"Error creating network visualization: {str(e)}")
            return nx.DiGraph()
        
    def _build_network_graph(self, address: str, depth: int, max_nodes: int) -> nx.DiGraph:
        """Build NetworkX graph from Neo4j data"""
        G = nx.DiGraph()
        
        # Add source address
        G.add_node(address, type='Address')
        
        # Get transaction network data
        query = """
        MATCH (a:Address {address: $address})-[:PARTICIPATED_IN]->(t:Transaction),
              (receiver:Address)-[:PARTICIPATED_IN]->(t)
        RETURN a.address as source, receiver.address as target, t.tx_hash as tx_hash, t.value as value
        LIMIT $max_nodes
        """
        
        try:
            with self.driver.session() as session:
                result = session.run(query, address=address, max_nodes=max_nodes)
                
            # Alternative query if apoc is not available
            if not result.peek():
                query = """
                MATCH (a:Address {address: $address})-[:PARTICIPATED_IN]->(t:Transaction),
                      (receiver:Address)-[:PARTICIPATED_IN]->(t)
                RETURN a.address as source, receiver.address as target, t.tx_hash as tx_hash, t.value as value
                LIMIT $max_nodes
                """
                
                with self.driver.session() as session:
                    result = session.run(query, address=address, max_nodes=max_nodes)
            
            # Build graph from results
            for record in result:
                if 'node' in record:  # apoc result
                    node_data = record['node']
                    if 'address' in node_data:
                        G.add_node(node_data['address'], type='Address', **node_data)
                    elif 'tx_hash' in node_data:
                        G.add_node(node_data['tx_hash'], type='Transaction', **node_data)
                else:  # direct query result
                    source = record['source']
                    target = record['target']
                    tx_hash = record['tx_hash']
                    value = record['value']
                    
                    G.add_node(source, type='Address')
                    G.add_node(target, type='Address')
                    G.add_node(tx_hash, type='Transaction', value=value)
                    
                    G.add_edge(source, tx_hash, type='PARTICIPATED_IN', value=value)
                    G.add_edge(tx_hash, target, type='PARTICIPATED_IN', value=value)
                    
        except Exception as e:
            logger.warning(f"Error with complex query, using simple approach: {str(e)}")
            # Fallback to simple approach
            self._build_simple_network_graph(G, address, depth, max_nodes)
            
        return G
    
    def _build_simple_network_graph(self, G: nx.DiGraph, address: str, depth: int, max_nodes: int):
        """Build network graph using simple queries"""
        try:
            # Get outgoing transactions
            query = """
            MATCH (a:Address {address: $address})-[:PARTICIPATED_IN]->(t:Transaction),
                  (receiver:Address)-[:PARTICIPATED_IN]->(t)
            RETURN a.address as source, receiver.address as target, t.tx_hash as tx_hash, t.value as value
            LIMIT $max_nodes
            """
            
            with self.driver.session() as session:
                result = session.run(query, address=address, max_nodes=max_nodes)
                records = list(result)  # Convert to list to avoid consume error
                
                for record in records:
                    source = record['source']
                    target = record['target']
                    tx_hash = record['tx_hash']
                    value = record['value']
                    
                    G.add_node(source, type='Address')
                    G.add_node(target, type='Address')
                    G.add_node(tx_hash, type='Transaction', value=value)
                    
                    G.add_edge(source, tx_hash, type='PARTICIPATED_IN', value=value)
                    G.add_edge(tx_hash, target, type='PARTICIPATED_IN', value=value)
                
        except Exception as e:
            logger.error(f"Error building simple network graph: {str(e)}")
    
    def create_risk_heatmap(self, addresses: List[str], risk_scores: List[float]) -> None:
        """Create a heatmap visualization of risk scores"""
        try:
            plt.figure(figsize=(12, 8))
            
            # Create heatmap data
            import numpy as np
            risk_matrix = np.array(risk_scores).reshape(1, -1)
            
            # Create heatmap
            plt.imshow(risk_matrix, cmap='RdYlGn_r', aspect='auto')
            plt.colorbar(label='Risk Score')
            
            # Set labels
            plt.xticks(range(len(addresses)), [addr[:8] + '...' for addr in addresses], rotation=45)
            plt.yticks([])
            plt.xlabel('Addresses')
            plt.title('Risk Score Heatmap', fontsize=14, fontweight='bold')
            
            # Add value annotations
            for i, score in enumerate(risk_scores):
                plt.text(i, 0, f'{score:.3f}', ha='center', va='center', fontweight='bold')
            
            plt.tight_layout()
            plt.close()
            
        except Exception as e:
            logger.error(f"Error creating risk heatmap: {str(e)}")
    
    def create_transaction_timeline(self, address: str, time_window_hours: int = 24) -> None:
        """Create a timeline visualization of transactions"""
        try:
            query = """
            MATCH (a:Address {address: $address})-[:PARTICIPATED_IN]->(t:Transaction)
            WHERE t.timestamp > datetime() - duration({hours: $time_window})
            RETURN t.tx_hash as tx_hash, t.value as value, t.timestamp as timestamp
            ORDER BY t.timestamp ASC
            """
            
            with self.driver.session() as session:
                result = session.run(query, address=address, time_window=time_window_hours)
                transactions = list(result)
            
            if not transactions:
                logger.warning(f"No transactions found for address {address}")
                return
            
            # Prepare data for plotting
            timestamps = []
            values = []
            tx_hashes = []
            
            for tx in transactions:
                if tx['timestamp']:
                    timestamps.append(tx['timestamp'])
                    values.append(tx['value'])
                    tx_hashes.append(tx['tx_hash'][:8] + '...')
            
            if not timestamps:
                return
            
            # Create timeline plot
            plt.figure(figsize=(14, 8))
            
            plt.scatter(timestamps, values, s=100, alpha=0.7, c='red')
            
            # Connect points with lines
            plt.plot(timestamps, values, 'b-', alpha=0.3)
            
            # Add labels
            for i, (ts, val, tx_hash) in enumerate(zip(timestamps, values, tx_hashes)):
                plt.annotate(tx_hash, (ts, val), xytext=(5, 5), 
                            textcoords='offset points', fontsize=8)
            
            plt.xlabel('Time', fontsize=12)
            plt.ylabel('Transaction Value (satoshi)', fontsize=12)
            plt.title(f'Transaction Timeline for {address[:10]}...', fontsize=14, fontweight='bold')
            plt.grid(True, alpha=0.3)
            plt.xticks(rotation=45)
            
            plt.tight_layout()
            plt.close()
            
        except Exception as e:
            logger.error(f"Error creating transaction timeline: {str(e)}")


class GephiExporter:
    """Exports transaction networks to Gephi format"""
    
    def __init__(self, neo4j_driver):
        self.driver = neo4j_driver
        
    def export_to_gephi(self, output_file: str = 'transaction_network.gexf', 
                        max_transactions: int = 1000) -> str:
        """Export transaction network to Gephi format"""
        try:
            logger.info(f"Exporting network to Gephi format: {output_file}")
            
            # Get comprehensive transaction data
            query = """
            MATCH (sender:Address)-[:PARTICIPATED_IN]->(t:Transaction)-[:PARTICIPATED_IN]->(receiver:Address)
            RETURN sender.address as source, receiver.address as target, 
                   t.value as value, t.timestamp as timestamp, t.tx_hash as tx_hash
            LIMIT $max_transactions
            """
            
            with self.driver.session() as session:
                result = session.run(query, max_transactions=max_transactions)
                
            # Build NetworkX graph
            G = nx.DiGraph()
            
            for record in result:
                source = record['source']
                target = record['target']
                value = record['value']
                timestamp = record['timestamp']
                tx_hash = record['tx_hash']
                
                G.add_node(source, type='Address', label=source)
                G.add_node(target, type='Address', label=target)
                G.add_node(tx_hash, type='Transaction', label=tx_hash[:8] + '...')
                
                G.add_edge(source, tx_hash, type='PARTICIPATED_IN', value=value, timestamp=timestamp)
                G.add_edge(tx_hash, target, type='PARTICIPATED_IN', value=value, timestamp=timestamp)
            
            # Export to GEXF format for Gephi
            nx.write_gexf(G, output_file)
            logger.info(f"Network exported to {output_file} with {len(G.nodes())} nodes and {len(G.edges())} edges")
            
            return output_file
            
        except Exception as e:
            logger.error(f"Error exporting to Gephi: {str(e)}")
            return ""
    
    def export_address_subgraph(self, address: str, depth: int = 2, 
                               output_file: str = None) -> str:
        """Export a specific address subgraph to Gephi"""
        try:
            if not output_file:
                output_file = f"subgraph_{address[:8]}_{depth}.gexf"
            
            logger.info(f"Exporting subgraph for {address} to {output_file}")
            
            # Build the subgraph
            visualizer = NetworkVisualizer(self.driver)
            G = visualizer._build_network_graph(address, depth, 1000)
            
            if len(G.nodes()) == 0:
                logger.warning(f"No data found for address {address}")
                return ""
            
            # Export to GEXF
            nx.write_gexf(G, output_file)
            logger.info(f"Subgraph exported to {output_file}")
            
            return output_file
            
        except Exception as e:
            logger.error(f"Error exporting subgraph: {str(e)}")


class ChartGenerator:
    """Generates various charts and statistics"""
    
    def __init__(self, neo4j_driver):
        self.driver = neo4j_driver
    
    def create_risk_distribution_chart(self, risk_summary: Dict[str, Any]) -> None:
        """Create a pie chart of risk distribution"""
        try:
            risk_distribution = risk_summary['risk_distribution']
            
            # Filter out zero counts
            labels = [level for level, count in risk_distribution.items() if count > 0]
            sizes = [risk_distribution[level] for level in labels]
            colors = ['#ff4444', '#ff8800', '#ffcc00', '#88cc00', '#44cc44']
            
            plt.figure(figsize=(10, 8))
            plt.pie(sizes, labels=labels, colors=colors[:len(labels)], autopct='%1.1f%%', startangle=90)
            plt.title('Risk Level Distribution', fontsize=14, fontweight='bold')
            plt.axis('equal')
            
            plt.tight_layout()
            plt.close()
            
        except Exception as e:
            logger.error(f"Error creating risk distribution chart: {str(e)}")
    
    def create_transaction_volume_chart(self, address: str, time_window_hours: int = 24) -> None:
        """Create a bar chart of transaction volumes"""
        try:
            query = """
            MATCH (a:Address {address: $address})-[:PARTICIPATED_IN]->(t:Transaction)
            WHERE t.timestamp > datetime() - duration({hours: $time_window})
            RETURN t.tx_hash as tx_hash, t.value as value, t.timestamp as timestamp
            ORDER BY t.timestamp ASC
            """
            
            with self.driver.session() as session:
                result = session.run(query, address=address, time_window=time_window_hours)
                transactions = list(result)
            
            if not transactions:
                logger.warning(f"No transactions found for address {address}")
                return
            
            # Prepare data
            tx_hashes = [tx['tx_hash'][:8] + '...' for tx in transactions]
            values = [tx['value'] for tx in transactions]
            
            # Create bar chart
            plt.figure(figsize=(14, 8))
            bars = plt.bar(range(len(values)), values, color='skyblue', alpha=0.7)
            
            # Color bars based on value (higher values = darker)
            max_val = max(values) if values else 1
            for bar, value in zip(bars, values):
                intensity = value / max_val
                bar.set_color(plt.cm.Reds(intensity))
            
            plt.xlabel('Transaction', fontsize=12)
            plt.ylabel('Value (satoshi)', fontsize=12)
            plt.title(f'Transaction Volumes for {address[:10]}...', fontsize=14, fontweight='bold')
            plt.xticks(range(len(tx_hashes)), tx_hashes, rotation=45)
            plt.grid(True, alpha=0.3)
            
            plt.tight_layout()
            plt.close()
            
        except Exception as e:
            logger.error(f"Error creating transaction volume chart: {str(e)}")
