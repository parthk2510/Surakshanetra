"""
Anomaly Detection Engine for ChainBreak
Implements algorithms for detecting suspicious transaction patterns
"""

from neo4j import GraphDatabase
import numpy as np
from sklearn.ensemble import IsolationForest
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class LayeringDetector:
    """Detects layering patterns in transaction chains"""

    def __init__(self, neo4j_driver):
        self.driver = neo4j_driver

    def detect_layering_patterns(self, address: str, time_window_hours: int = 24) -> List[Dict[str, Any]]:
        """Detect multiple exchanges/mixing services used in single transaction chain"""
        try:
            query = """
            MATCH (a:Address {address: $address})-[:PARTICIPATED_IN]->(t1:Transaction),
                  (intermediate:Address)-[:PARTICIPATED_IN]->(t1),
                  (intermediate)-[:PARTICIPATED_IN]->(t2:Transaction),
                  (final:Address)-[:PARTICIPATED_IN]->(t2)
            WHERE t1.timestamp > datetime() - duration({hours: $time_window})
            AND t2.timestamp > datetime() - duration({hours: $time_window})
            AND intermediate <> final
            AND intermediate <> a
            RETURN a.address as source, 
                   intermediate.address as intermediate, 
                   final.address as final, 
                   t1.value as value1, 
                   t2.value as value2,
                   t1.timestamp as timestamp1,
                   t2.timestamp as timestamp2
            ORDER BY t1.timestamp DESC
            """

            with self.driver.session() as session:
                result = session.run(query, address=address,
                                     time_window=time_window_hours)
                patterns = [dict(record) for record in result]

            logger.info(
                f"Found {len(patterns)} layering patterns for address {address}")
            return patterns

        except Exception as e:
            logger.error(f"Error detecting layering patterns: {str(e)}")
            return []

    def detect_complex_layering(self, address: str, min_layers: int = 3, time_window_hours: int = 48) -> List[Dict[str, Any]]:
        """Detect complex layering with multiple intermediate addresses"""
        try:
            query = """
            MATCH path = (a:Address {address: $address})-[:PARTICIPATED_IN]->(t1:Transaction),
                  (intermediate:Address)-[:PARTICIPATED_IN]->(t1)
            WHERE t1.timestamp > datetime() - duration({hours: $time_window})
            WITH a, intermediate, t1
            MATCH (intermediate)-[:PARTICIPATED_IN]->(t2:Transaction),
                  (final:Address)-[:PARTICIPATED_IN]->(t2)
            WHERE t2.timestamp > t1.timestamp
            AND t2.timestamp < t1.timestamp + duration({hours: 2})
            WITH a, intermediate, final, t1, t2
            MATCH (final)-[:PARTICIPATED_IN]->(t3:Transaction),
                  (final2:Address)-[:PARTICIPATED_IN]->(t3)
            WHERE t3.timestamp > t2.timestamp
            AND t3.timestamp < t2.timestamp + duration({hours: 2})
            RETURN a.address as source,
                   [intermediate.address, final.address] as intermediates,
                   final2.address as final_destination,
                   [t1.value, t2.value, t3.value] as values,
                   [t1.timestamp, t2.timestamp, t3.timestamp] as timestamps
            """

            with self.driver.session() as session:
                result = session.run(query, address=address,
                                     time_window=time_window_hours)
                patterns = [dict(record) for record in result]

            logger.info(
                f"Found {len(patterns)} complex layering patterns for address {address}")
            return patterns

        except Exception as e:
            logger.error(f"Error detecting complex layering: {str(e)}")
            return []


class SmurfingDetector:
    """Detects smurfing patterns (rapid movement across multiple accounts)"""

    def __init__(self, neo4j_driver):
        self.driver = neo4j_driver

    def detect_smurfing_patterns(self, min_transactions: int = 5, time_window_hours: int = 1) -> List[Dict[str, Any]]:
        """Detect rapid movement across multiple accounts (smurfing)"""
        try:
            query = """
            MATCH (sender:Address)-[:PARTICIPATED_IN]->(t:Transaction),
                  (receiver:Address)-[:PARTICIPATED_IN]->(t)
            WITH sender, count(t) as transaction_count, 
                 avg(t.value) as avg_amount, 
                 min(t.timestamp) as first_tx, 
                 max(t.timestamp) as last_tx,
                 collect(DISTINCT receiver.address) as receivers
            WHERE transaction_count >= $min_tx_count
            AND duration({milliseconds: last_tx - first_tx}).hours <= $time_window
            AND size(receivers) >= $min_tx_count * 0.8  // At least 80% unique receivers
            RETURN sender.address as source,
                   transaction_count,
                   avg_amount,
                   first_tx,
                   last_tx,
                   receivers,
                   duration({milliseconds: last_tx - first_tx}).hours as duration_hours
            ORDER BY transaction_count DESC
            """

            with self.driver.session() as session:
                result = session.run(query,
                                     min_tx_count=min_transactions,
                                     time_window=time_window_hours)
                patterns = [dict(record) for record in result]

            logger.info(f"Found {len(patterns)} smurfing patterns")
            return patterns

        except Exception as e:
            logger.error(f"Error detecting smurfing patterns: {str(e)}")
            return []

    def detect_structured_smurfing(self, address: str, time_window_hours: int = 24) -> List[Dict[str, Any]]:
        """Detect structured smurfing with specific patterns"""
        try:
            query = """
            MATCH (a:Address {address: $address})-[:PARTICIPATED_IN]->(t:Transaction),
                  (receiver:Address)-[:PARTICIPATED_IN]->(t)
            WHERE t.timestamp > datetime() - duration({hours: $time_window})
            WITH a, receiver, t
            MATCH (receiver)-[:PARTICIPATED_IN]->(t2:Transaction),
                  (final:Address)-[:PARTICIPATED_IN]->(t2)
            WHERE t2.timestamp > t.timestamp
            AND t2.timestamp < t.timestamp + duration({hours: 1})
            WITH a, receiver, final, t, t2
            RETURN a.address as source,
                   receiver.address as intermediate,
                   final.address as final_destination,
                   t.value as value1,
                   t2.value as value2,
                   t.timestamp as timestamp1,
                   t2.timestamp as timestamp2
            ORDER BY t.timestamp DESC
            """

            with self.driver.session() as session:
                result = session.run(query, address=address,
                                     time_window=time_window_hours)
                patterns = [dict(record) for record in result]

            logger.info(
                f"Found {len(patterns)} structured smurfing patterns for address {address}")
            return patterns

        except Exception as e:
            logger.error(f"Error detecting structured smurfing: {str(e)}")
            return []


class VolumeAnomalyDetector:
    """Detects transactions with unusual volumes using machine learning"""

    def __init__(self, neo4j_driver):
        self.driver = neo4j_driver
        self.isolation_forest = IsolationForest(
            contamination=0.1, random_state=42)

    def detect_volume_anomalies(self, time_window_hours: int = 24) -> List[Dict[str, Any]]:
        """Detect transactions with unusual volumes using Isolation Forest"""
        try:
            # Get transaction data from the specified time window
            query = """
            MATCH (t:Transaction)
            WHERE t.timestamp > datetime() - duration({hours: $time_window})
            RETURN t.tx_hash as tx_hash,
                   t.value as value, 
                   t.timestamp as timestamp
            """

            with self.driver.session() as session:
                result = session.run(query, time_window=time_window_hours)
                data = list(result)

            if len(data) < 10:  # Need minimum data for anomaly detection
                logger.warning(
                    "Insufficient data for volume anomaly detection")
                return []

            # Prepare data for anomaly detection
            values = np.array([record['value']
                              for record in data]).reshape(-1, 1)

            # Fit and predict
            self.isolation_forest.fit(values)
            anomaly_scores = self.isolation_forest.decision_function(values)
            predictions = self.isolation_forest.predict(values)

            # Return anomalous transactions
            anomalous_indices = np.where(predictions == -1)[0]
            anomalous_transactions = []

            for idx in anomalous_indices:
                record = data[idx]
                record['anomaly_score'] = float(anomaly_scores[idx])
                anomalous_transactions.append(record)

            logger.info(
                f"Found {len(anomalous_transactions)} volume anomalies")
            return anomalous_transactions

        except Exception as e:
            logger.error(f"Error detecting volume anomalies: {str(e)}")
            return []

    def detect_value_pattern_anomalies(self, address: str, time_window_hours: int = 24) -> List[Dict[str, Any]]:
        """Detect unusual value patterns for a specific address"""
        try:
            query = """
            MATCH (a:Address {address: $address})-[:PARTICIPATED_IN]->(t:Transaction)
            WHERE t.timestamp > datetime() - duration({hours: $time_window})
            RETURN t.tx_hash as tx_hash,
                   t.value as value,
                   t.timestamp as timestamp
            ORDER BY t.timestamp DESC
            """

            with self.driver.session() as session:
                result = session.run(query, address=address,
                                     time_window=time_window_hours)
                transactions = list(result)

            if len(transactions) < 5:
                return []

            # Calculate statistical measures
            values = [tx['value'] for tx in transactions]
            mean_value = np.mean(values)
            std_value = np.std(values)

            # Detect transactions that deviate significantly from the mean
            anomalies = []
            threshold = 2.0  # 2 standard deviations

            for tx in transactions:
                z_score = abs((tx['value'] - mean_value) /
                              std_value) if std_value > 0 else 0
                if z_score > threshold:
                    tx['z_score'] = z_score
                    tx['mean_value'] = mean_value
                    tx['std_value'] = std_value
                    anomalies.append(tx)

            logger.info(
                f"Found {len(anomalies)} value pattern anomalies for address {address}")
            return anomalies

        except Exception as e:
            logger.error(f"Error detecting value pattern anomalies: {str(e)}")
            return []


class TemporalAnomalyDetector:
    """Detects temporal anomalies in transaction patterns"""

    def __init__(self, neo4j_driver):
        self.driver = neo4j_driver

    def detect_timing_anomalies(self, address: str, time_window_hours: int = 24) -> List[Dict[str, Any]]:
        """Detect unusual timing patterns in transactions"""
        try:
            query = """
            MATCH (a:Address {address: $address})-[:PARTICIPATED_IN]->(t:Transaction)
            WHERE t.timestamp > datetime() - duration({hours: $time_window})
            RETURN t.tx_hash as tx_hash,
                   t.timestamp as timestamp,
                   t.value as value
            ORDER BY t.timestamp ASC
            """

            with self.driver.session() as session:
                result = session.run(query, address=address,
                                     time_window=time_window_hours)
                transactions = list(result)

            if len(transactions) < 3:
                return []

            # Calculate time intervals between consecutive transactions
            intervals = []
            anomalies = []

            for i in range(1, len(transactions)):
                prev_time = transactions[i-1]['timestamp']
                curr_time = transactions[i]['timestamp']

                if hasattr(prev_time, 'timestamp') and hasattr(curr_time, 'timestamp'):
                    interval = (curr_time.timestamp() -
                                prev_time.timestamp()) / 60  # in minutes
                    intervals.append(interval)

                    # Detect very rapid transactions (less than 1 minute apart)
                    if interval < 1:
                        anomaly = {
                            'tx_hash': transactions[i]['tx_hash'],
                            'value': transactions[i]['value'],
                            'timestamp': transactions[i]['timestamp'],
                            'interval_minutes': interval,
                            'anomaly_type': 'rapid_transaction'
                        }
                        anomalies.append(anomaly)

            # Detect unusual patterns in intervals
            if len(intervals) > 0:
                mean_interval = np.mean(intervals)
                std_interval = np.std(intervals)

                for i, interval in enumerate(intervals):
                    if std_interval > 0:
                        z_score = abs(
                            (interval - mean_interval) / std_interval)
                        if z_score > 3:  # Very unusual timing
                            anomaly = {
                                'tx_hash': transactions[i+1]['tx_hash'],
                                'value': transactions[i+1]['value'],
                                'timestamp': transactions[i+1]['timestamp'],
                                'interval_minutes': interval,
                                'expected_interval': mean_interval,
                                'z_score': z_score,
                                'anomaly_type': 'timing_anomaly'
                            }
                            anomalies.append(anomaly)

            logger.info(
                f"Found {len(anomalies)} timing anomalies for address {address}")
            return anomalies

        except Exception as e:
            logger.error(f"Error detecting timing anomalies: {str(e)}")
            return []
