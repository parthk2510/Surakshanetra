"""
Risk Scoring System for ChainBreak
Calculates comprehensive risk scores for wallet addresses
"""

from neo4j import GraphDatabase
import logging
from typing import Dict, Any, Optional, List
import math
from datetime import datetime

logger = logging.getLogger(__name__)


class RiskScorer:
    """Calculates comprehensive risk scores for addresses"""
    
    def __init__(self, neo4j_driver, config: Dict[str, Any]):
        self.driver = neo4j_driver
        self.config = config
        self.risk_weights = config.get('risk_scoring', {})
        
    def calculate_address_risk_score(self, address: str) -> Dict[str, Any]:
        """Calculate comprehensive risk score for an address"""
        try:
            logger.info(f"Calculating risk score for address: {address}")
            
            # Get address characteristics
            address_info = self._get_address_info(address)
            if not address_info:
                logger.warning(f"No address info found for {address}")
                return self._get_default_risk_score(address)
                
            # Calculate individual risk factors
            volume_score = self._calculate_volume_risk(address_info)
            frequency_score = self._calculate_frequency_risk(address_info)
            layering_score = self._calculate_layering_risk(address)
            smurfing_score = self._calculate_smurfing_risk(address)
            temporal_score = self._calculate_temporal_risk(address)
            
            # Weighted risk calculation
            risk_factors = {
                'volume': volume_score * self.risk_weights.get('volume_weight', 0.3),
                'frequency': frequency_score * self.risk_weights.get('frequency_weight', 0.2),
                'layering': layering_score * self.risk_weights.get('layering_weight', 0.3),
                'smurfing': smurfing_score * self.risk_weights.get('smurfing_weight', 0.2)
            }
            
            # Add temporal risk if available
            if temporal_score > 0:
                risk_factors['temporal'] = temporal_score * 0.1
                # Adjust other weights proportionally
                total_weight = sum(risk_factors.values())
                for key in risk_factors:
                    if key != 'temporal':
                        risk_factors[key] = risk_factors[key] * (0.9 / (total_weight - risk_factors['temporal']))
            
            total_risk_score = sum(risk_factors.values())
            
            # Ensure score is between 0 and 1
            total_risk_score = max(0.0, min(1.0, total_risk_score))
            
            risk_result = {
                'address': address,
                'total_risk_score': total_risk_score,
                'risk_factors': risk_factors,
                'risk_level': self._classify_risk_level(total_risk_score),
                'address_info': address_info,
                'risk_details': {
                    'volume_risk': volume_score,
                    'frequency_risk': frequency_score,
                    'layering_risk': layering_score,
                    'smurfing_risk': smurfing_score,
                    'temporal_risk': temporal_score
                }
            }
            
            logger.info(f"Risk score calculated for {address}: {total_risk_score:.3f} ({risk_result['risk_level']})")
            return risk_result
            
        except Exception as e:
            logger.error(f"Error calculating risk score for {address}: {str(e)}")
            return self._get_default_risk_score(address)
    
    def _get_address_info(self, address: str) -> Optional[Dict[str, Any]]:
        """Get comprehensive address information from Neo4j"""
        query = """
        MATCH (a:Address {address: $address})
        OPTIONAL MATCH (a)-[:PARTICIPATED_IN]->(t:Transaction)
        WITH a, 
             count(t) as outgoing_tx_count,
             sum(t.value) as total_outgoing,
             avg(t.value) as avg_outgoing,
             min(t.timestamp) as first_outgoing,
             max(t.timestamp) as last_outgoing
        OPTIONAL MATCH (a)<-[:PARTICIPATED_IN]-(t2:Transaction)
        WITH a, outgoing_tx_count, total_outgoing, avg_outgoing, first_outgoing, last_outgoing,
             count(t2) as incoming_tx_count,
             sum(t2.value) as total_incoming,
             avg(t2.value) as avg_incoming,
             min(t2.timestamp) as first_incoming,
             max(t2.timestamp) as last_incoming
        RETURN a.address as address,
               a.balance as balance,
               a.total_received as total_received,
               a.total_sent as total_sent,
               outgoing_tx_count,
               total_outgoing,
               avg_outgoing,
               first_outgoing,
               last_outgoing,
               incoming_tx_count,
               total_incoming,
               avg_incoming,
               first_incoming,
               last_incoming
        """
        
        with self.driver.session() as session:
            result = session.run(query, address=address)
            return result.single()
    
    def _calculate_volume_risk(self, address_info: Dict[str, Any]) -> float:
        """Calculate risk based on transaction volumes"""
        if not address_info:
            return 0.5
        
        balance = address_info.get('balance', 0) or 0
        total_received = address_info.get('total_received', 0) or 0
        total_sent = address_info.get('total_sent', 0) or 0
        
        # High volume relative to balance is risky
        if balance > 0:
            volume_ratio = total_received / balance
            if volume_ratio > 20:
                return 0.95  # Very high risk
            elif volume_ratio > 10:
                return 0.85  # High risk
            elif volume_ratio > 5:
                return 0.7   # Medium-high risk
            elif volume_ratio > 2:
                return 0.5   # Medium risk
            else:
                return 0.3   # Low risk
        
        # If no balance, consider absolute volumes
        if total_received > 1000000000:  # 10 BTC
            return 0.8
        elif total_received > 100000000:  # 1 BTC
            return 0.6
        elif total_received > 10000000:   # 0.1 BTC
            return 0.4
        else:
            return 0.2
    
    def _calculate_frequency_risk(self, address_info: Dict[str, Any]) -> float:
        """Calculate risk based on transaction frequency patterns"""
        if not address_info:
            return 0.5
        
        outgoing_tx_count = address_info.get('outgoing_tx_count', 0) or 0
        incoming_tx_count = address_info.get('incoming_tx_count', 0) or 0
        total_tx_count = address_info.get('transaction_count', 0) or 0
        
        # Very high transaction count is suspicious
        if total_tx_count > 1000:
            return 0.9
        elif total_tx_count > 500:
            return 0.8
        elif total_tx_count > 100:
            return 0.6
        elif total_tx_count > 50:
            return 0.4
        else:
            return 0.2
        
        # Consider ratio of incoming vs outgoing
        if outgoing_tx_count > 0 and incoming_tx_count > 0:
            ratio = outgoing_tx_count / incoming_tx_count
            if ratio > 10 or ratio < 0.1:  # Very imbalanced
                return min(0.9, risk_score + 0.2)
        
        return risk_score
    
    def _calculate_layering_risk(self, address: str) -> float:
        """Calculate risk based on layering patterns"""
        try:
            # Count layering patterns
            query = """
            MATCH (a:Address {address: $address})-[:PARTICIPATED_IN]->(t1:Transaction),
                  (intermediate:Address)-[:PARTICIPATED_IN]->(t1),
                  (intermediate)-[:PARTICIPATED_IN]->(t2:Transaction),
                  (final:Address)-[:PARTICIPATED_IN]->(t2)
            WHERE t1.timestamp > datetime() - duration({hours: 24})
            AND t2.timestamp > datetime() - duration({hours: 24})
            AND intermediate <> final
            AND intermediate <> a
            RETURN count(*) as layering_count
            """
            
            with self.driver.session() as session:
                result = session.run(query, address=address)
                layering_count = result.single()['layering_count'] or 0
            
            # Calculate risk based on layering count
            if layering_count > 10:
                return 0.95
            elif layering_count > 5:
                return 0.8
            elif layering_count > 2:
                return 0.6
            elif layering_count > 0:
                return 0.4
            else:
                return 0.1
                
        except Exception as e:
            logger.warning(f"Error calculating layering risk: {str(e)}")
            return 0.3
    
    def _calculate_smurfing_risk(self, address: str) -> float:
        """Calculate risk based on smurfing patterns"""
        try:
            # Count rapid transactions to multiple addresses
            query = """
            MATCH (a:Address {address: $address})-[:PARTICIPATED_IN]->(t:Transaction),
                  (receiver:Address)-[:PARTICIPATED_IN]->(t)
            WHERE t.timestamp > datetime() - duration({hours: 1})
            WITH a, count(t) as tx_count, count(DISTINCT receiver) as unique_receivers
            WHERE tx_count >= 5 AND unique_receivers >= tx_count * 0.8
            RETURN tx_count, unique_receivers
            """
            
            with self.driver.session() as session:
                result = session.run(query, address=address)
                smurfing_data = result.single()
            
            if smurfing_data:
                tx_count = smurfing_data['tx_count'] or 0
                if tx_count > 20:
                    return 0.9
                elif tx_count > 10:
                    return 0.7
                elif tx_count >= 5:
                    return 0.5
            else:
                return 0.1
                
        except Exception as e:
            logger.warning(f"Error calculating smurfing risk: {str(e)}")
            return 0.3
    
    def _calculate_temporal_risk(self, address: str) -> float:
        """Calculate risk based on temporal patterns"""
        try:
            # Check for rapid transaction sequences
            query = """
            MATCH (a:Address {address: $address})-[:PARTICIPATED_IN]->(t:Transaction)
            WHERE t.timestamp > datetime() - duration({hours: 24})
            WITH a, t
            ORDER BY t.timestamp ASC
            WITH a, collect(t) as transactions
            UNWIND range(0, size(transactions)-2) as i
            WITH a, transactions[i] as tx1, transactions[i+1] as tx2
            WHERE duration({milliseconds: tx2.timestamp - tx1.timestamp}).minutes < 1
            RETURN count(*) as rapid_sequences
            """
            
            with self.driver.session() as session:
                result = session.run(query, address=address)
                rapid_sequences = result.single()['rapid_sequences'] or 0
            
            # Calculate risk based on rapid sequences
            if rapid_sequences > 10:
                return 0.8
            elif rapid_sequences > 5:
                return 0.6
            elif rapid_sequences > 0:
                return 0.4
            else:
                return 0.1
                
        except Exception as e:
            logger.warning(f"Error calculating temporal risk: {str(e)}")
            return 0.3
    
    def _classify_risk_level(self, score: float) -> str:
        """Classify risk score into levels"""
        if score >= 0.8:
            return "CRITICAL"
        elif score >= 0.6:
            return "HIGH"
        elif score >= 0.4:
            return "MEDIUM"
        elif score >= 0.2:
            return "LOW"
        else:
            return "VERY_LOW"
    
    def _get_default_risk_score(self, address: str) -> Dict[str, Any]:
        """Return default risk score when calculation fails"""
        return {
            'address': address,
            'total_risk_score': 0.5,
            'risk_factors': {'default': 0.5},
            'risk_level': 'MEDIUM',
            'address_info': None,
            'risk_details': {},
            'error': 'Failed to calculate risk score'
        }
    
    def get_risk_summary(self, addresses: List[str]) -> Dict[str, Any]:
        """Get risk summary for multiple addresses"""
        risk_scores = []
        risk_distribution = {
            'CRITICAL': 0,
            'HIGH': 0,
            'MEDIUM': 0,
            'LOW': 0,
            'VERY_LOW': 0
        }
        
        for address in addresses:
            risk_score = self.calculate_address_risk_score(address)
            risk_scores.append(risk_score)
            risk_distribution[risk_score['risk_level']] += 1
        
        # Calculate aggregate statistics
        total_scores = [rs['total_risk_score'] for rs in risk_scores]
        avg_risk = sum(total_scores) / len(total_scores) if total_scores else 0
        
        return {
            'total_addresses': len(addresses),
            'average_risk_score': avg_risk,
            'risk_distribution': risk_distribution,
            'high_risk_addresses': [rs for rs in risk_scores if rs['risk_level'] in ['HIGH', 'CRITICAL']],
            'risk_scores': risk_scores
        }
    
    def export_risk_report(self, addresses: List[str], output_file: str = None) -> str:
        """Export risk analysis report to file"""
        risk_summary = self.get_risk_summary(addresses)
        
        report_lines = [
            "ChainBreak Risk Analysis Report",
            "=" * 50,
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"Total Addresses Analyzed: {risk_summary['total_addresses']}",
            f"Average Risk Score: {risk_summary['average_risk_score']:.3f}",
            "",
            "Risk Level Distribution:",
            "-" * 25
        ]
        
        for level, count in risk_summary['risk_distribution'].items():
            report_lines.append(f"{level}: {count}")
        
        report_lines.extend([
            "",
            "High Risk Addresses:",
            "-" * 25
        ])
        
        for high_risk in risk_summary['high_risk_addresses']:
            report_lines.append(
                f"Address: {high_risk['address']} | "
                f"Risk Score: {high_risk['total_risk_score']:.3f} | "
                f"Level: {high_risk['risk_level']}"
            )
        
        report_content = "\n".join(report_lines)
        
        if output_file:
            try:
                with open(output_file, 'w') as f:
                    f.write(report_content)
                logger.info(f"Risk report exported to {output_file}")
            except Exception as e:
                logger.error(f"Error exporting report: {str(e)}")
        
        return report_content
