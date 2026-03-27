#!/usr/bin/env python3
"""
Test script for Threat Intelligence Integration

This script demonstrates the integration of external OSINT/threat intelligence APIs
with the illicit detection module for enhanced malicious address detection.
"""

import sys
import os
import logging
from datetime import datetime

# Add the backend directory to the path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from illicit_detection.patterns import IllicitPatternDetector, RiskLevel
from illicit_detection.risk_scoring import RiskScorer
from illicit_detection.threat_intel_client import ThreatIntelClient, ThreatIntelSource
from illicit_detection.threat_intel_config import get_threat_intel_config, validate_threat_intel_config

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class MockNeo4jSession:
    """Mock Neo4j session for testing."""
    
    def run(self, query, parameters=None):
        """Mock run method that returns test data."""
        address = parameters.get('address', '') if parameters else ''
        
        # Mock malicious address data
        if 'malicious' in query and address in ['test_malicious_address', 'btc_blacklisted_address']:
            return MockResult([{
                'malicious': True,
                'risk_score': 0.9,
                'risk_level': 'critical',
                'last_seen': datetime.now(),
                'malicious_connections': 3,
                'total_volume': 150.5
            }])
        
        # Mock graph features data
        if 'illicit_ratio' in query:
            return MockResult([{
                'illicit_neighbors': 5,
                'total_neighbors': 10,
                'illicit_ratio': 0.5
            }])
        
        if 'velocity' in query:
            return MockResult([{
                'tx_count': 25,
                'days_span': 3,
                'velocity': 8.33
            }])
        
        # Default empty result
        return MockResult([])

class MockResult:
    """Mock Neo4j result."""
    
    def __init__(self, records):
        self.records = records
    
    def single(self):
        """Return single record."""
        return self.records[0] if self.records else None
    
    def __iter__(self):
        """Iterate over records."""
        return iter(self.records)

class MockBlockchainAPI:
    """Mock blockchain API for testing."""
    
    def check_threat_intel(self, address):
        """Mock threat intelligence check."""
        if address in ['test_malicious_address', 'btc_blacklisted_address']:
            return 0.8
        return 0.0

def test_threat_intel_client():
    """Test the ThreatIntelClient functionality."""
    logger.info("Testing Threat Intelligence Client")
    logger.info("=" * 50)
    
    # Get configuration
    config = get_threat_intel_config("testing")
    
    # Validate configuration
    is_valid, errors = validate_threat_intel_config(config)
    if not is_valid:
        logger.error(f"Configuration validation failed: {errors}")
        return
    
    # Initialize threat intelligence client
    threat_intel_client = ThreatIntelClient(config)
    
    # Test addresses
    test_addresses = [
        '1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa',  # Genesis block address
        '1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN2',  # Test address
        '3J98t1WpEZ73CNmQviecrnyiWrnqRhWNLy',  # Another test address
    ]
    
    for address in test_addresses:
        logger.info(f"\nTesting address: {address}")
        logger.info("-" * 30)
        
        # Test individual sources
        logger.info("Testing BTC Black DNSBL...")
        btcblack_result = threat_intel_client.check_btc_black(address)
        logger.info(f"  BTC Black: {'BLACKLISTED' if btcblack_result.blacklisted else 'CLEAN'}")
        logger.info(f"  Confidence: {btcblack_result.confidence}")
        logger.info(f"  Details: {btcblack_result.details}")
        
        logger.info("Testing ChainAbuse Database...")
        chainabuse_result = threat_intel_client.check_chainabuse(address)
        logger.info(f"  ChainAbuse: {'BLACKLISTED' if chainabuse_result.blacklisted else 'CLEAN'}")
        logger.info(f"  Confidence: {chainabuse_result.confidence}")
        logger.info(f"  Details: {chainabuse_result.details}")
        
        logger.info("Testing Cropty Blacklist...")
        cropty_result = threat_intel_client.check_cropty_blacklist(address)
        logger.info(f"  Cropty: {'BLACKLISTED' if cropty_result.blacklisted else 'CLEAN'}")
        logger.info(f"  Confidence: {cropty_result.confidence}")
        logger.info(f"  Details: {cropty_result.details}")
        
        # Test combined check
        logger.info("Testing combined threat intelligence check...")
        combined_result = threat_intel_client.check_all_sources(address)
        logger.info(f"  Final Blacklisted: {combined_result.get('final_blacklisted', False)}")
        logger.info(f"  Overall Confidence: {combined_result.get('overall_confidence', 0.0)}")
        logger.info(f"  Sources Checked: {combined_result.get('sources_checked', [])}")
        logger.info(f"  Blacklisted Sources: {combined_result.get('blacklisted_sources', [])}")
    
    # Test source status
    logger.info("\nThreat Intelligence Source Status:")
    status = threat_intel_client.get_source_status()
    for source, info in status.items():
        logger.info(f"  {source}: {info}")

def test_integrated_detection():
    """Test the integrated illicit detection with threat intelligence."""
    logger.info("\nTesting Integrated Illicit Detection with Threat Intelligence")
    logger.info("=" * 70)
    
    # Get configuration
    config = get_threat_intel_config("testing")
    
    # Initialize mock components
    mock_session = MockNeo4jSession()
    mock_api = MockBlockchainAPI()
    
    # Initialize detectors with threat intelligence
    pattern_detector = IllicitPatternDetector(mock_session, mock_api, config)
    risk_scorer = RiskScorer(mock_session, mock_api)
    
    # Test addresses
    test_addresses = [
        'test_malicious_address',      # Known malicious
        'btc_blacklisted_address',     # Potentially blacklisted
        'test_clean_address',          # Clean address
    ]
    
    for address in test_addresses:
        logger.info(f"\nTesting integrated detection for: {address}")
        logger.info("-" * 40)
        
        # Test pattern detection
        try:
            patterns = pattern_detector.detect_malicious_patterns(address)
            logger.info(f"Detected {len(patterns)} malicious patterns")
            
            for pattern in patterns:
                logger.info(f"  Pattern: {pattern.pattern_type}")
                logger.info(f"  Confidence: {pattern.confidence}")
                logger.info(f"  Risk Level: {pattern.risk_level.value}")
                logger.info(f"  Indicators: {pattern.indicators}")
        
        except Exception as e:
            logger.error(f"Error in pattern detection: {e}")
        
        # Test comprehensive risk score calculation
        try:
            risk_score_result = pattern_detector.calculate_risk_score(address)
            logger.info(f"Comprehensive Risk Score:")
            logger.info(f"  Risk Score: {risk_score_result.get('risk_score', 0)}")
            logger.info(f"  Risk Level: {risk_score_result.get('risk_level', 'unknown')}")
            logger.info(f"  Pattern Counts: {risk_score_result.get('pattern_counts', {})}")
            logger.info(f"  Malicious Floor Applied: {risk_score_result.get('malicious_floor_applied', False)}")
            logger.info(f"  Temporal Decay Factor: {risk_score_result.get('temporal_decay_factor', 1.0)}")
            logger.info(f"  Graph Features: {risk_score_result.get('graph_features', {})}")
            logger.info(f"  Graph Enhancement: {risk_score_result.get('graph_enhancement', 0.0)}")
        
        except Exception as e:
            logger.error(f"Error in comprehensive risk scoring: {e}")

def test_configuration_scenarios():
    """Test different configuration scenarios."""
    logger.info("\nTesting Configuration Scenarios")
    logger.info("=" * 40)
    
    # Test development configuration
    logger.info("Development Configuration:")
    dev_config = get_threat_intel_config("development")
    logger.info(f"  BTC Black: {dev_config['enable_btcblack']}")
    logger.info(f"  ChainAbuse: {dev_config['enable_chainabuse']}")
    logger.info(f"  Cropty: {dev_config['enable_cropty']}")
    
    # Test production configuration
    logger.info("Production Configuration:")
    prod_config = get_threat_intel_config("production")
    logger.info(f"  BTC Black: {prod_config['enable_btcblack']}")
    logger.info(f"  ChainAbuse: {prod_config['enable_chainabuse']}")
    logger.info(f"  Cropty: {prod_config['enable_cropty']}")
    logger.info(f"  Timeout: {prod_config['timeout']}")
    logger.info(f"  Retry Attempts: {prod_config['retry_attempts']}")
    
    # Test testing configuration
    logger.info("Testing Configuration:")
    test_config = get_threat_intel_config("testing")
    logger.info(f"  BTC Black: {test_config['enable_btcblack']}")
    logger.info(f"  ChainAbuse: {test_config['enable_chainabuse']}")
    logger.info(f"  Cropty: {test_config['enable_cropty']}")
    
    # Test configuration validation
    logger.info("Configuration Validation:")
    is_valid, errors = validate_threat_intel_config(dev_config)
    logger.info(f"  Development config valid: {is_valid}")
    if errors:
        logger.info(f"  Errors: {errors}")
    
    is_valid, errors = validate_threat_intel_config(test_config)
    logger.info(f"  Testing config valid: {is_valid}")
    if errors:
        logger.info(f"  Errors: {errors}")

def test_threat_intel_summary():
    """Summarize the threat intelligence integration."""
    logger.info("\n" + "=" * 70)
    logger.info("THREAT INTELLIGENCE INTEGRATION SUMMARY")
    logger.info("=" * 70)
    
    features = [
        "✅ BTC Black DNSBL Integration",
        "   - DNS query: ${address}.bl.btcblack.it",
        "   - Returns blacklist status via DNS records",
        "   - High confidence for blacklisted addresses",
        "",
        "✅ ChainAbuse Database Integration",
        "   - Scraper: chainabuse.com",
        "   - Returns detailed abuse reports",
        "   - Confidence based on report quality",
        "   - No API key required",
        "",
        "✅ Cropty Blacklist Integration",
        "   - API: cropty.io/api/blacklist/{address}",
        "   - Returns risk level and blacklist status",
        "   - 200 = blacklisted, 404 = clean",
        "",
        "✅ Unified Threat Intelligence Client",
        "   - Aggregates results from all sources",
        "   - Normalizes confidence scores",
        "   - Provides comprehensive blacklist status",
        "   - Handles errors and timeouts gracefully",
        "",
        "✅ Enhanced Illicit Detection Integration",
        "   - Threat intel results force CRITICAL risk level",
        "   - Confidence ≥0.95 for blacklisted addresses",
        "   - Enhanced logging and audit trails",
        "   - Fallback to local detection if APIs fail",
        "",
        "✅ Configuration Management",
        "   - Environment-based configuration",
        "   - API key management",
        "   - Source enable/disable options",
        "   - Timeout and retry settings",
        "   - Configuration validation"
    ]
    
    for feature in features:
        logger.info(feature)
    
    logger.info("\n" + "=" * 70)
    logger.info("KEY BENEFITS:")
    logger.info("=" * 70)
    
    benefits = [
        "🎯 Real-time threat intelligence from multiple sources",
        "📊 Dynamic confidence scoring based on source reliability",
        "🛡️ Guaranteed CRITICAL risk for blacklisted addresses",
        "🔄 Automatic retry and error handling",
        "⚙️ Flexible configuration for different environments",
        "📈 Enhanced detection accuracy with external validation",
        "🔍 Comprehensive audit trails for compliance",
        "🚀 Production-ready with proper error handling"
    ]
    
    for benefit in benefits:
        logger.info(benefit)
    
    logger.info("\n" + "=" * 70)
    logger.info("SETUP INSTRUCTIONS:")
    logger.info("=" * 70)
    
    setup_steps = [
        "1. Install required dependencies:",
        "   pip install dnspython requests",
        "",
        "2. ChainAbuse Database Integration:",
        "   - No API key required",
        "   - Uses web scraping for data collection",
        "   - Provides detailed abuse reports",
        "   - Enhanced categorization and confidence scoring",
        "",
        "3. Configure threat intelligence:",
        "   - Set enable_btcblack=True for DNSBL queries",
        "   - Set enable_chainabuse=True for ChainAbuse scraping",
        "   - Set enable_cropty=True for blacklist checks",
        "",
        "4. Initialize with configuration:",
        "   threat_intel_config = get_threat_intel_config('production')",
        "   detector = IllicitPatternDetector(session, api, threat_intel_config)",
        "",
        "5. Monitor logs for threat intelligence results:",
        "   - BLACKLISTED addresses get CRITICAL risk",
        "   - All sources checked and aggregated",
        "   - Errors handled gracefully with fallbacks"
    ]
    
    for step in setup_steps:
        logger.info(step)

if __name__ == "__main__":
    test_threat_intel_client()
    test_integrated_detection()
    test_configuration_scenarios()
    test_threat_intel_summary()
