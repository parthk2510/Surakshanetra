"""
Main ChainBreak Application Class
Integrates all components for comprehensive blockchain analysis
"""

import logging
import os
import yaml
from typing import Dict, Any, List, Optional
from pathlib import Path

from .core.data_ingestion_Neo4j import BaseDataIngestor, Neo4jDataIngestor
from .core.data_ingestion_json import JSONDataIngestor
from .services.analytics.anomaly_detection import (
    LayeringDetector,
    SmurfingDetector,
    VolumeAnomalyDetector,
    TemporalAnomalyDetector
)
from backend.services.analytics.risk_scoring import RiskScorer
from .visualization import NetworkVisualizer, GephiExporter, ChartGenerator
from .services.threat_intel.threat_intelligence import ThreatIntelligenceManager

logger = logging.getLogger(__name__)


class ChainBreak:
    """Main ChainBreak application class integrating all components"""

    def __init__(self, config_path: str = "config.yaml"):
        """Initialize ChainBreak with configuration"""
        self.config = self._load_config(config_path)
        self._setup_logging()

        # Initialize Neo4j connection parameters (env vars take priority over config.yaml)
        neo4j_config = self.config.get('neo4j', {})
        self.neo4j_uri = os.getenv('NEO4J_URI', neo4j_config.get('uri', 'bolt://localhost:7687'))
        self.neo4j_user = os.getenv('NEO4J_USERNAME', neo4j_config.get('username', 'neo4j'))
        self.neo4j_password = os.getenv('NEO4J_PASSWORD', neo4j_config.get('password', 'password'))

        # Backend mode tracking
        self.backend_mode = "unknown"
        self.use_json_backend = self.config.get('use_json_backend', False)

        # Initialize components with graceful fallback
        self._initialize_components()
        
        # Initialize threat intelligence manager
        self.threat_intel_manager = ThreatIntelligenceManager(self.config.get('threat_intelligence', {}))

        logger.info(
            f"ChainBreak initialized successfully in {self.backend_mode} mode")

    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load configuration from YAML file"""
        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            logger.info(f"Configuration loaded from {config_path}")
            return config
        except Exception as e:
            logger.warning(
                f"Error loading config from {config_path}: {str(e)}")
            logger.info("Using default configuration")
            return self._get_default_config()

    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration"""
        return {
            'neo4j': {
                'uri': os.getenv('NEO4J_URI', 'bolt://localhost:7687'),
                'username': os.getenv('NEO4J_USERNAME', 'neo4j'),
                'password': os.getenv('NEO4J_PASSWORD', 'password')
            },
            'blockcypher': {
                'api_key': 'your_api_key_here',
                'timeout': 30
            },
            'analysis': {
                'time_window_hours': 24,
                'min_transactions': 5,
                'volume_threshold': 1000000
            },
            'risk_scoring': {
                'volume_weight': 0.3,
                'frequency_weight': 0.2,
                'layering_weight': 0.3,
                'smurfing_weight': 0.2
            },
            'use_json_backend': False
        }

    def _setup_logging(self):
        """Setup logging configuration"""
        import pathlib
        log_file = pathlib.Path('logs/chainbreak.log')
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers = [logging.StreamHandler()]
        try:
            handlers.insert(0, logging.FileHandler(str(log_file)))
        except Exception:
            pass
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=handlers
        )

    def _initialize_components(self):
        """Initialize all ChainBreak components with enhanced Neo4j prioritization"""
        # Always try Neo4j first unless explicitly disabled
        if not self.use_json_backend:
            try:
                logger.info("Attempting to connect to Neo4j...")
                self._initialize_neo4j_backend()
                self.backend_mode = "neo4j"
                logger.info("[SUCCESS] Successfully initialized Neo4j backend")
                return
            except Exception as e:
                logger.warning(f"[ERROR] Neo4j connection failed: {str(e)}")
                logger.info("[RETRY] Attempting Neo4j connection retry...")
                
                # Retry Neo4j connection once
                try:
                    import time
                    time.sleep(2)  # Brief delay before retry
                    self._initialize_neo4j_backend()
                    self.backend_mode = "neo4j"
                    logger.info("[SUCCESS] Successfully initialized Neo4j backend on retry")
                    return
                except Exception as retry_e:
                    logger.warning(f"[ERROR] Neo4j retry failed: {str(retry_e)}")
        
        # Fallback to JSON backend
        logger.info("[FALLBACK] Falling back to JSON backend mode")
        self._initialize_json_backend()
        self.backend_mode = "json"
        logger.warning("[WARNING] Running in limited JSON backend mode - some features disabled")

    def _initialize_neo4j_backend(self):
        """Initialize Neo4j-based backend"""
        self.data_ingestor = Neo4jDataIngestor(
            self.neo4j_uri,
            self.neo4j_user,
            self.neo4j_password
        )

        # Initialize anomaly detectors with Neo4j driver
        self.layering_detector = LayeringDetector(self.data_ingestor.driver)
        self.smurfing_detector = SmurfingDetector(self.data_ingestor.driver)
        self.volume_detector = VolumeAnomalyDetector(self.data_ingestor.driver)
        self.temporal_detector = TemporalAnomalyDetector(
            self.data_ingestor.driver)

        # Initialize risk scorer with Neo4j driver
        self.risk_scorer = RiskScorer(self.data_ingestor.driver, self.config)

        # Initialize visualization components with Neo4j driver
        self.visualizer = NetworkVisualizer(self.data_ingestor.driver)
        self.gephi_exporter = GephiExporter(self.data_ingestor.driver)
        self.chart_generator = ChartGenerator(self.data_ingestor.driver)

        logger.info("All Neo4j components initialized successfully")

    def _initialize_json_backend(self):
        """Initialize JSON-based backend"""
        logger.info("Initializing JSON backend components...")

        self.data_ingestor = JSONDataIngestor()

        # Initialize lightweight components for JSON mode
        self.layering_detector = None
        self.smurfing_detector = None
        self.volume_detector = None
        self.temporal_detector = None

        self.risk_scorer = None
        self.visualizer = None
        self.gephi_exporter = None
        self.chart_generator = None

        logger.info(
            "JSON backend components initialized (limited functionality)")

    def get_backend_mode(self) -> str:
        """Get current backend mode"""
        return self.backend_mode

    def is_neo4j_available(self) -> bool:
        """Check if Neo4j backend is available"""
        return self.backend_mode == "neo4j" and self.data_ingestor.is_operational()

    def analyze_address(self, address: str, blockchain: str = 'btc',
                        generate_visualizations: bool = True) -> Dict[str, Any]:
        """Comprehensive analysis of a single address"""
        try:
            logger.info(
                f"Starting comprehensive analysis for address: {address}")
            logger.info(f"Using backend mode: {self.backend_mode}")

            # Step 1: Ingest data
            logger.info("Step 1: Ingesting blockchain data...")
            ingestion_success = self.data_ingestor.ingest_address_data(
                address, blockchain)

            if not ingestion_success:
                logger.warning(f"Data ingestion failed for address {address}")
                return self._get_analysis_error_result(address, "Data ingestion failed")

            # Step 2: Detect anomalies (only if Neo4j backend available)
            anomalies = {}
            if self.is_neo4j_available():
                logger.info("Step 2: Detecting anomalies...")

                # Layering detection
                layering_patterns = self.layering_detector.detect_layering_patterns(
                    address)
                complex_layering = self.layering_detector.detect_complex_layering(
                    address)

                # Smurfing detection
                smurfing_patterns = self.smurfing_detector.detect_smurfing_patterns()
                structured_smurfing = self.smurfing_detector.detect_structured_smurfing(
                    address)

                # Volume anomalies
                volume_anomalies = self.volume_detector.detect_volume_anomalies()
                value_pattern_anomalies = self.volume_detector.detect_value_pattern_anomalies(
                    address)

                # Temporal anomalies
                timing_anomalies = self.temporal_detector.detect_timing_anomalies(
                    address)

                anomalies = {
                    'layering_patterns': layering_patterns,
                    'complex_layering': complex_layering,
                    'smurfing_patterns': smurfing_patterns,
                    'structured_smurfing': structured_smurfing,
                    'volume_anomalies': volume_anomalies,
                    'value_pattern_anomalies': value_pattern_anomalies,
                    'timing_anomalies': timing_anomalies
                }
            else:
                logger.info(
                    "Step 2: Skipping anomaly detection (JSON backend mode)")
                anomalies = {
                    'layering_patterns': [],
                    'complex_layering': [],
                    'smurfing_patterns': [],
                    'structured_smurfing': [],
                    'volume_anomalies': [],
                    'value_pattern_anomalies': [],
                    'timing_anomalies': []
                }

            # Step 3: Calculate risk score (only if Neo4j backend available)
            risk_score = None
            if self.is_neo4j_available():
                logger.info("Step 3: Calculating risk score...")
                risk_score = self.risk_scorer.calculate_address_risk_score(
                    address)
            else:
                logger.info(
                    "Step 3: Skipping risk scoring (JSON backend mode)")
                risk_score = {
                    'overall_score': 0,
                    'risk_level': 'UNKNOWN',
                    'factors': {'message': 'Risk scoring not available in JSON mode'}
                }
            
            # Step 3.5: Enhance risk score with threat intelligence
            threat_intel_result = None
            if self.threat_intel_manager.is_available():
                logger.info("Step 3.5: Checking address against threat intelligence...")
                threat_intel_result = self.threat_intel_manager.check_address(address)
                
                if threat_intel_result.get("blacklisted", False):
                    logger.warning(f"Address {address} is blacklisted by threat intelligence!")
                    # Enhance risk score with threat intelligence
                    enhanced_risk = self.threat_intel_manager.enhance_risk_score(
                        address, 
                        risk_score.get('overall_score', 0) if risk_score else 0,
                        risk_score.get('risk_level', 'UNKNOWN') if risk_score else 'UNKNOWN'
                    )
                    risk_score = {
                        'overall_score': enhanced_risk.get('final_risk_score', 0),
                        'risk_level': enhanced_risk.get('final_risk_level', 'UNKNOWN'),
                        'threat_intel_enhanced': True,
                        'threat_intel_result': threat_intel_result,
                        'enhancement_details': enhanced_risk
                    }
                else:
                    logger.info(f"Address {address} is clean according to threat intelligence")
                    if risk_score:
                        risk_score['threat_intel_enhanced'] = True
                        risk_score['threat_intel_result'] = threat_intel_result
            else:
                logger.info("Step 3.5: Threat intelligence not available")

            # Step 4: Generate visualizations if requested and available
            visualizations = {}
            if generate_visualizations and self.is_neo4j_available():
                logger.info("Step 4: Generating visualizations...")
                try:
                    # Network visualization
                    network_graph = self.visualizer.visualize_address_network(
                        address)
                    visualizations['network_graph'] = network_graph

                    # Transaction timeline
                    self.visualizer.create_transaction_timeline(address)
                    visualizations['timeline_created'] = True

                    # Risk heatmap - get risk score for the address
                    risk_score = self.risk_scorer.calculate_risk_score(address)
                    self.visualizer.create_risk_heatmap([address], [risk_score])
                    visualizations['risk_heatmap_created'] = True

                except Exception as e:
                    logger.warning(
                        f"Visualization generation failed: {str(e)}")
                    visualizations['error'] = str(e)
            else:
                logger.info(
                    "Step 4: Skipping visualizations (JSON backend mode or not requested)")
                visualizations['message'] = 'Visualizations not available in JSON mode'

            # Step 5: Compile results
            logger.info("Step 5: Compiling analysis results...")

            analysis_results = {
                'address': address,
                'blockchain': blockchain,
                'backend_mode': self.backend_mode,
                'analysis_timestamp': self._get_current_timestamp(),
                'ingestion_success': ingestion_success,
                'anomalies': anomalies,
                'risk_score': risk_score,
                'threat_intelligence': threat_intel_result,
                'visualizations': visualizations,
                'summary': self._generate_analysis_summary(address, anomalies, risk_score, threat_intel_result)
            }

            logger.info(
                f"Analysis completed successfully for address: {address}")
            return analysis_results

        except Exception as e:
            logger.error(f"Analysis failed for address {address}: {str(e)}")
            return self._get_analysis_error_result(address, str(e))

    def analyze_multiple_addresses(self, addresses: List[str], blockchain: str = 'btc') -> Dict[str, Any]:
        """Analyze multiple addresses"""
        try:
            logger.info(
                f"Starting batch analysis for {len(addresses)} addresses")

            results = {}
            successful_analyses = 0
            failed_analyses = 0

            for address in addresses:
                try:
                    result = self.analyze_address(
                        address, blockchain, generate_visualizations=False)
                    if 'error' not in result:
                        results[address] = result
                        successful_analyses += 1
                    else:
                        results[address] = {'error': result['error']}
                        failed_analyses += 1
                except Exception as e:
                    logger.error(
                        f"Analysis failed for address {address}: {str(e)}")
                    results[address] = {'error': str(e)}
                    failed_analyses += 1

            batch_results = {
                'addresses_analyzed': len(addresses),
                'successful_analyses': successful_analyses,
                'failed_analyses': failed_analyses,
                'blockchain': blockchain,
                'backend_mode': self.backend_mode,
                'analysis_timestamp': self._get_current_timestamp(),
                'results': results,
                'summary': self._generate_comparative_analysis(results)
            }

            logger.info(
                f"Batch analysis completed: {successful_analyses} successful, {failed_analyses} failed")
            return batch_results

        except Exception as e:
            logger.error(f"Batch analysis failed: {str(e)}")
            return {'error': f'Batch analysis failed: {str(e)}'}

    def export_network_to_gephi(self, address: str, output_file: str = None) -> Optional[str]:
        """Export network to Gephi format"""
        if not self.is_neo4j_available():
            logger.warning("Gephi export not available in JSON backend mode")
            return None

        try:
            if not output_file:
                output_file = f"network_{address}_{self._get_current_timestamp()}.gexf"

            export_file = self.gephi_exporter.export_address_subgraph(
                address, output_file)
            logger.info(f"Network exported to Gephi format: {export_file}")
            return export_file

        except Exception as e:
            logger.error(f"Gephi export failed: {str(e)}")
            return None

    def generate_risk_report(self, addresses: List[str], output_file: str = None) -> str:
        """Generate comprehensive risk report"""
        if not self.is_neo4j_available():
            logger.warning(
                "Risk report generation not available in JSON backend mode")
            return "Risk report generation requires Neo4j backend"

        try:
            report_content = self.risk_scorer.export_risk_report(
                addresses, output_file)
            logger.info(f"Risk report generated: {output_file}")
            return report_content

        except Exception as e:
            logger.error(f"Risk report generation failed: {str(e)}")
            return f"Risk report generation failed: {str(e)}"

    def get_system_status(self) -> Dict[str, Any]:
        """Get comprehensive system status"""
        try:
            neo4j_status = "connected" if self.is_neo4j_available() else "disconnected"

            # Get database statistics if Neo4j is available
            db_stats = {}
            if self.is_neo4j_available():
                db_stats = self._get_database_statistics()

            status = {
                'system_status': 'operational' if self.data_ingestor.is_operational() else 'degraded',
                'backend_mode': self.backend_mode,
                'neo4j_connection': neo4j_status,
                'data_ingestor_status': 'operational' if self.data_ingestor.is_operational() else 'failed',
                'database_statistics': db_stats,
                'timestamp': self._get_current_timestamp(),
                'configuration': {
                    'neo4j_uri': self.neo4j_uri,
                    'use_json_backend': self.use_json_backend
                }
            }

            return status

        except Exception as e:
            logger.error(f"Error getting system status: {str(e)}")
            return {
                'system_status': 'error',
                'error': str(e),
                'timestamp': self._get_current_timestamp()
            }

    def _get_database_statistics(self) -> Dict[str, Any]:
        """Get database statistics from Neo4j"""
        if not self.is_neo4j_available():
            return {}

        try:
            with self.data_ingestor.driver.session() as session:
                # Count nodes by type
                node_counts = {}
                for node_type in ['Address', 'Transaction', 'Block']:
                    result = session.run(
                        f"MATCH (n:{node_type}) RETURN count(n) as count")
                    count = result.single()['count']
                    node_counts[f'{node_type.lower()}_count'] = count

                # Count relationships
                result = session.run(
                    "MATCH ()-[r]-() RETURN count(r) as count")
                relationship_count = result.single()['count']

                return {
                    'node_counts': node_counts,
                    'relationship_count': relationship_count
                }

        except Exception as e:
            logger.warning(f"Error getting database statistics: {str(e)}")
            return {}

    def _generate_analysis_summary(self, address: str, anomalies: Dict[str, Any],
                                   risk_score: Dict[str, Any], threat_intel_result: Dict[str, Any] = None) -> Dict[str, Any]:
        """Generate analysis summary"""
        summary = {
            'address': address,
            'anomaly_summary': {
                'layering_count': len(anomalies.get('layering_patterns', [])),
                'smurfing_count': len(anomalies.get('smurfing_patterns', [])),
                'volume_anomaly_count': len(anomalies.get('volume_anomalies', []))
            },
            'risk_summary': {
                'overall_score': risk_score.get('overall_score', 0) if risk_score else 0,
                'risk_level': risk_score.get('risk_level', 'UNKNOWN') if risk_score else 'UNKNOWN',
                'threat_intel_enhanced': risk_score.get('threat_intel_enhanced', False) if risk_score else False
            },
            'threat_intelligence_summary': {
                'available': threat_intel_result.get('available', False) if threat_intel_result else False,
                'blacklisted': threat_intel_result.get('blacklisted', False) if threat_intel_result else False,
                'confidence': threat_intel_result.get('confidence', 0.0) if threat_intel_result else 0.0,
                'risk_level': threat_intel_result.get('risk_level', 'unknown') if threat_intel_result else 'unknown',
                'sources': threat_intel_result.get('blacklisted_sources', []) if threat_intel_result else []
            },
            'recommendations': self._generate_recommendations(anomalies, risk_score, threat_intel_result)
        }

        return summary

    def _generate_comparative_analysis(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Generate comparative analysis for multiple addresses"""
        if not results:
            return {}

        risk_scores = []
        anomaly_counts = []

        for address, result in results.items():
            if 'error' not in result:
                risk_score = result.get('risk_score', {})
                if risk_score:
                    risk_scores.append(risk_score.get('overall_score', 0))

                anomalies = result.get('anomalies', {})
                total_anomalies = (
                    len(anomalies.get('layering_patterns', [])) +
                    len(anomalies.get('smurfing_patterns', [])) +
                    len(anomalies.get('volume_anomalies', []))
                )
                anomaly_counts.append(total_anomalies)

        if risk_scores:
            avg_risk = sum(risk_scores) / len(risk_scores)
            max_risk = max(risk_scores)
            min_risk = min(risk_scores)
        else:
            avg_risk = max_risk = min_risk = 0

        if anomaly_counts:
            avg_anomalies = sum(anomaly_counts) / len(anomaly_counts)
            total_anomalies = sum(anomaly_counts)
        else:
            avg_anomalies = total_anomalies = 0

        return {
            'risk_statistics': {
                'average_risk_score': avg_risk,
                'highest_risk_score': max_risk,
                'lowest_risk_score': min_risk
            },
            'anomaly_statistics': {
                'average_anomalies_per_address': avg_anomalies,
                'total_anomalies': total_anomalies
            },
            'address_count': len(results)
        }

    def _generate_recommendations(self, anomalies: Dict[str, Any],
                                  risk_score: Dict[str, Any], threat_intel_result: Dict[str, Any] = None) -> List[str]:
        """Generate recommendations based on analysis results"""
        recommendations = []

        if not risk_score:
            recommendations.append(
                "Enable Neo4j backend for comprehensive risk analysis")
            return recommendations

        risk_level = risk_score.get('risk_level', 'UNKNOWN')

        # Check threat intelligence results first
        if threat_intel_result and threat_intel_result.get('blacklisted', False):
            recommendations.append(
                "[CRITICAL] Address is blacklisted by threat intelligence sources")
            recommendations.append(
                "Immediate investigation required - address reported for illicit activity")
            recommendations.append(
                "Consider reporting to relevant authorities")
            recommendations.append(
                f"Blacklisted by sources: {', '.join(threat_intel_result.get('blacklisted_sources', []))}")
            return recommendations

        if risk_level in ['CRITICAL', 'HIGH']:
            recommendations.append(
                "Immediate investigation required - high risk indicators detected")
            recommendations.append(
                "Consider reporting to relevant authorities")

        if anomalies.get('layering_patterns'):
            recommendations.append(
                "Layering patterns detected - investigate transaction flow complexity")

        if anomalies.get('smurfing_patterns'):
            recommendations.append(
                "Smurfing patterns detected - examine small transaction patterns")

        if anomalies.get('volume_anomalies'):
            recommendations.append(
                "Volume anomalies detected - investigate unusual transaction amounts")

        # Add threat intelligence status
        if threat_intel_result and threat_intel_result.get('available', False):
            recommendations.append(
                "[SUCCESS] Address verified clean by threat intelligence sources")
        elif threat_intel_result and not threat_intel_result.get('available', False):
            recommendations.append(
                "[WARNING] Threat intelligence not available - manual verification recommended")

        if not recommendations:
            recommendations.append(
                "No immediate concerns detected - continue monitoring")

        return recommendations

    def _get_analysis_error_result(self, address: str, error_message: str) -> Dict[str, Any]:
        """Generate error result for failed analysis"""
        return {
            'address': address,
            'error': error_message,
            'backend_mode': self.backend_mode,
            'analysis_timestamp': self._get_current_timestamp(),
            'status': 'failed'
        }

    def _get_current_timestamp(self) -> str:
        """Get current timestamp in ISO format"""
        from datetime import datetime
        return datetime.now().isoformat()

    def check_illicit_addresses_in_graph(self, graph_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Check all addresses in a graph for illicit activity using threat intelligence.
        
        Args:
            graph_data: Graph data containing nodes and edges
            
        Returns:
            Dictionary with illicit address analysis
        """
        if not self.threat_intel_manager.is_available():
            return {
                "available": False,
                "error": "Threat intelligence not available",
                "illicit_addresses": [],
                "total_addresses": 0
            }
        
        try:
            logger.info("Checking addresses in graph for illicit activity...")
            result = self.threat_intel_manager.get_illicit_addresses_in_graph(graph_data)
            
            if result.get("available", False):
                illicit_count = len(result.get("illicit_addresses", []))
                total_count = result.get("total_addresses", 0)
                logger.info(f"Found {illicit_count} illicit addresses out of {total_count} total addresses")
            
            return result
            
        except Exception as e:
            logger.error(f"Error checking illicit addresses in graph: {e}")
            return {
                "available": False,
                "error": str(e),
                "illicit_addresses": [],
                "total_addresses": 0
            }

    def get_threat_intelligence_status(self) -> Dict[str, Any]:
        """
        Get threat intelligence system status.
        
        Returns:
            Dictionary with threat intelligence status information
        """
        return self.threat_intel_manager.get_source_status()

    def close(self):
        """Cleanup resources"""
        try:
            if hasattr(self, 'data_ingestor'):
                self.data_ingestor.close()
            logger.info("ChainBreak resources cleaned up successfully")
        except Exception as e:
            logger.error(f"Error during cleanup: {str(e)}")
