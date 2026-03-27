"""
Configuration file for threat intelligence scrapers
Contains all configurable values to avoid hardcoding
"""

import os
from typing import Dict, Any, List, Tuple

class ScraperConfig:
    """Configuration class for all scrapers"""
    
    # API Endpoints
    CHAINABUSE_BASE_URL = os.getenv('CHAINABUSE_BASE_URL', 'https://chainabuse.com')
    BITCOINWHOSWHO_API_URL = os.getenv('BITCOINWHOSWHO_API_URL', 'https://www.bitcoinwhoswho.com/api')
    BITCOINWHOSWHO_WEB_URL = os.getenv('BITCOINWHOSWHO_WEB_URL', 'https://www.bitcoinwhoswho.com')
    CROPTY_API_URL = os.getenv('CROPTY_API_URL', 'https://www.cropty.io/api/blacklist')
    BTC_BLACK_DNSBL = os.getenv('BTC_BLACK_DNSBL', 'bl.btcblack.it')
    
    # API Keys
    BITCOINWHOSWHO_API_KEY = os.getenv('BITCOINWHOSWHO_API_KEY')
    CHAINABUSE_API_KEY = os.getenv('CHAINABUSE_API_KEY')
    CROPTY_API_KEY = os.getenv('CROPTY_API_KEY')
    
    # Request Settings
    DEFAULT_TIMEOUT = int(os.getenv('SCRAPER_TIMEOUT', '15'))
    DEFAULT_RETRY_ATTEMPTS = int(os.getenv('SCRAPER_RETRY_ATTEMPTS', '3'))
    DEFAULT_DELAY_BETWEEN_REQUESTS = float(os.getenv('SCRAPER_DELAY', '2.0'))
    
    # User Agent
    USER_AGENT = os.getenv('SCRAPER_USER_AGENT', 'ChainBreak-ThreatIntel/1.0')
    
    # Known Malicious Addresses Database
    KNOWN_MALICIOUS_ADDRESSES = {
        # WannaCry ransomware addresses
        os.getenv('WANNACRY_ADDRESS_1', '13AM4VW2dhxYgXeQepoHkHSQuy6NgaEb94'): {
            'category': 'Ransomware',
            'description': 'WannaCry ransomware address - used to collect ransom payments',
            'reporter': 'Security Research',
            'abuse_type': 'ransomware',
            'confidence_score': 0.95,
            'source': 'security_research'
        },
        os.getenv('WANNACRY_ADDRESS_2', '1Q2TWHE3GMdB6BZKafqwxXtWAWgFt5Jvm3'): {
            'category': 'Ransomware',
            'description': 'WannaCry ransomware address - used to collect ransom payments',
            'reporter': 'Security Research',
            'abuse_type': 'ransomware',
            'confidence_score': 0.95,
            'source': 'security_research'
        },
        # Other known malicious addresses
        os.getenv('SCAM_ADDRESS_1', '1HZwkjkeaoZfTSaJxDw6aKkxp45agDiEzN'): {
            'category': 'Scam',
            'description': 'Known scam address - reported for fraudulent activity',
            'reporter': 'Community Reports',
            'abuse_type': 'scam',
            'confidence_score': 0.8,
            'source': 'community_reports'
        }
    }
    
    # External Data Sources
    EXTERNAL_DATA_SOURCES = {
        'secureworks_wannacry': {
            'url': os.getenv('SECUREWORKS_WANNACRY_URL', 'https://www.secureworks.jp/research/wcry-ransomware-analysis'),
            'title': 'WannaCry Ransomware Analysis',
            'description': 'Security research report on WannaCry ransomware',
            'domain': 'secureworks.jp',
            'context': 'security_research',
            'risk_level': 'critical'
        }
    }
    
    # Suspicious Pattern Detection
    SUSPICIOUS_PATTERNS = {
        'scam_patterns': os.getenv('SCAM_PATTERNS', '1111,0000,aaaa,bbbb,cccc,dddd').split(','),
        'sequential_patterns': os.getenv('SEQUENTIAL_PATTERNS', '1234,abcd,4321,dcba').split(','),
        'short_address_threshold': int(os.getenv('SHORT_ADDRESS_THRESHOLD', '26')),
        'repeated_char_threshold': float(os.getenv('REPEATED_CHAR_THRESHOLD', '0.4')),
        'suspicious_confidence_threshold': float(os.getenv('SUSPICIOUS_CONFIDENCE_THRESHOLD', '0.3'))
    }
    
    # Risk Scoring Weights
    RISK_SCORING_WEIGHTS = {
        'ransomware': int(os.getenv('RANSOMWARE_WEIGHT', '5')),
        'scam_fraud': int(os.getenv('SCAM_FRAUD_WEIGHT', '3')),
        'terrorism_financing': int(os.getenv('TERRORISM_WEIGHT', '10')),
        'money_laundering': int(os.getenv('MONEY_LAUNDERING_WEIGHT', '4')),
        'drug_trafficking': int(os.getenv('DRUG_TRAFFICKING_WEIGHT', '6')),
        'weapons_trafficking': int(os.getenv('WEAPONS_WEIGHT', '8')),
        'child_exploitation': int(os.getenv('CHILD_EXPLOITATION_WEIGHT', '10')),
        'hacking_theft': int(os.getenv('HACKING_THEFT_WEIGHT', '4')),
        'darknet_market': int(os.getenv('DARKNET_MARKET_WEIGHT', '5')),
        'gambling': int(os.getenv('GAMBLING_WEIGHT', '2')),
        'mixing_service': int(os.getenv('MIXING_SERVICE_WEIGHT', '3')),
        'counterfeit': int(os.getenv('COUNTERFEIT_WEIGHT', '3'))
    }
    
    # Confidence Factors
    CONFIDENCE_FACTORS = {
        'chainabuse': float(os.getenv('CHAINABUSE_CONFIDENCE', '0.8')),
        'bitcoinwhoswho': float(os.getenv('BITCOINWHOSWHO_CONFIDENCE', '0.7')),
        'cropty': float(os.getenv('CROPTY_CONFIDENCE', '0.6')),
        'btcblack': float(os.getenv('BTC_BLACK_CONFIDENCE', '0.9'))
    }
    
    # Risk Level Thresholds
    RISK_LEVEL_THRESHOLDS = {
        'critical': int(os.getenv('CRITICAL_RISK_THRESHOLD', '8')),
        'high': int(os.getenv('HIGH_RISK_THRESHOLD', '5')),
        'medium': int(os.getenv('MEDIUM_RISK_THRESHOLD', '3')),
        'low': int(os.getenv('LOW_RISK_THRESHOLD', '1'))
    }
    
    # Test Addresses (for development/testing only)
    TEST_ADDRESSES = {
        'wannacry': os.getenv('TEST_WANNACRY_ADDRESS', '13AM4VW2dhxYgXeQepoHkHSQuy6NgaEb94'),
        'genesis': os.getenv('TEST_GENESIS_ADDRESS', '1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa'),
        'common': os.getenv('TEST_COMMON_ADDRESS', '3J98t1WpEZ73CNmQviecrnyiWrnqRhWNLy'),
        'bech32': os.getenv('TEST_BECH32_ADDRESS', 'bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh')
    }
    
    @classmethod
    def get_config(cls) -> Dict[str, Any]:
        """Get complete configuration dictionary"""
        return {
            'endpoints': {
                'chainabuse_base_url': cls.CHAINABUSE_BASE_URL,
                'bitcoinwhoswho_api_url': cls.BITCOINWHOSWHO_API_URL,
                'bitcoinwhoswho_web_url': cls.BITCOINWHOSWHO_WEB_URL,
                'cropty_api_url': cls.CROPTY_API_URL,
                'btc_black_dnsbl': cls.BTC_BLACK_DNSBL
            },
            'api_keys': {
                'bitcoinwhoswho_api_key': cls.BITCOINWHOSWHO_API_KEY,
                'chainabuse_api_key': cls.CHAINABUSE_API_KEY,
                'cropty_api_key': cls.CROPTY_API_KEY
            },
            'request_settings': {
                'timeout': cls.DEFAULT_TIMEOUT,
                'retry_attempts': cls.DEFAULT_RETRY_ATTEMPTS,
                'delay_between_requests': cls.DEFAULT_DELAY_BETWEEN_REQUESTS,
                'user_agent': cls.USER_AGENT
            },
            'known_malicious_addresses': cls.KNOWN_MALICIOUS_ADDRESSES,
            'external_data_sources': cls.EXTERNAL_DATA_SOURCES,
            'suspicious_patterns': cls.SUSPICIOUS_PATTERNS,
            'risk_scoring_weights': cls.RISK_SCORING_WEIGHTS,
            'confidence_factors': cls.CONFIDENCE_FACTORS,
            'risk_level_thresholds': cls.RISK_LEVEL_THRESHOLDS,
            'test_addresses': cls.TEST_ADDRESSES
        }
    
    @classmethod
    def validate_config(cls) -> Tuple[bool, List[str]]:
        """Validate configuration and return (is_valid, errors)"""
        errors = []
        
        # Check required URLs
        required_urls = [
            ('CHAINABUSE_BASE_URL', cls.CHAINABUSE_BASE_URL),
            ('BITCOINWHOSWHO_API_URL', cls.BITCOINWHOSWHO_API_URL),
            ('BITCOINWHOSWHO_WEB_URL', cls.BITCOINWHOSWHO_WEB_URL),
            ('CROPTY_API_URL', cls.CROPTY_API_URL)
        ]
        
        for name, url in required_urls:
            if not url or not url.startswith(('http://', 'https://')):
                errors.append(f"Invalid {name}: {url}")
        
        # Check numeric values
        numeric_configs = [
            ('DEFAULT_TIMEOUT', cls.DEFAULT_TIMEOUT),
            ('DEFAULT_RETRY_ATTEMPTS', cls.DEFAULT_RETRY_ATTEMPTS),
            ('DEFAULT_DELAY_BETWEEN_REQUESTS', cls.DEFAULT_DELAY_BETWEEN_REQUESTS)
        ]
        
        for name, value in numeric_configs:
            if not isinstance(value, (int, float)) or value <= 0:
                errors.append(f"Invalid {name}: {value}")
        
        return len(errors) == 0, errors
