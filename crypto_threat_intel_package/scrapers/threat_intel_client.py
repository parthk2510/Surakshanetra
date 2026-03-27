"""
Threat Intelligence Client for Cryptocurrency Address Analysis

This module provides integration with external OSINT/threat intelligence APIs
to enhance malicious address detection for BTC/ETH addresses.
"""

import logging
import requests
import dns.resolver
import dns.exception
import os
from typing import Dict, Optional, Any
from datetime import datetime
import time
import json
from dataclasses import dataclass
from enum import Enum

# Import configuration
try:
    from ..config.scraper_config import ScraperConfig
except ImportError:
    # Fallback for direct execution
    import sys
    from pathlib import Path
    sys.path.append(str(Path(__file__).parent.parent / "config"))
    from scraper_config import ScraperConfig

logger = logging.getLogger(__name__)

class ThreatIntelSource(Enum):
    BTC_BLACK = "btcblack"
    CHAINABUSE = "chainabuse"
    CROPTY = "cropty"
    BITCOINWHOSWHO = "bitcoinwhoswho"

@dataclass
class ThreatIntelResult:
    """Result from a single threat intelligence source."""
    source: ThreatIntelSource
    blacklisted: bool
    confidence: float
    details: Dict[str, Any]
    timestamp: datetime
    error: Optional[str] = None

class ThreatIntelClient:
    """
    Client for querying multiple threat intelligence sources.
    
    Integrates with:
    - BTC Black (DNSBL)
    - Bitcoin Abuse Database
    - Cropty Blacklist
    - BitcoinWhosWho (Scam reports, website appearances, tags, scores)
    """
    
    def __init__(self, config: Optional[ScraperConfig] = None):
        """
        Initialize the threat intelligence client.
        
        Args:
            config: ScraperConfig instance with all configuration values
        """
        self.config = config or ScraperConfig()
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': self.config.USER_AGENT,
            'Accept': 'application/json'
        })
        
        # Set timeouts from configuration
        self.timeout = self.config.DEFAULT_TIMEOUT
        self.retry_attempts = self.config.DEFAULT_RETRY_ATTEMPTS
        
        # Enable/disable sources (can be overridden by environment variables)
        self.enable_btcblack = os.getenv('ENABLE_BTC_BLACK', 'true').lower() == 'true'
        self.enable_chainabuse = os.getenv('ENABLE_CHAINABUSE', 'true').lower() == 'true'
        self.enable_cropty = os.getenv('ENABLE_CROPTY', 'true').lower() == 'true'
        self.enable_bitcoinwhoswho = os.getenv('ENABLE_BITCOINWHOSWHO', 'true').lower() == 'true'
        
        # ChainAbuse scraper instance
        self.chainabuse_scraper = None
        if self.enable_chainabuse:
            try:
                import sys
                # Add parent directory to path to import chainabuse_scraper
                parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                if parent_dir not in sys.path:
                    sys.path.append(parent_dir)
                from chainabuse_scraper import ChainAbuseScraper
                self.chainabuse_scraper = ChainAbuseScraper(self.config)
                logger.info("ChainAbuse scraper initialized")
            except ImportError as e:
                logger.warning(f"Could not import ChainAbuse scraper: {e}")
                self.enable_chainabuse = False
        
        # BitcoinWhosWho scraper instance
        self.bitcoinwhoswho_scraper = None
        if self.enable_bitcoinwhoswho:
            try:
                import sys
                # Add parent directory to path to import bitcoinwhoswho_scraper
                parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                if parent_dir not in sys.path:
                    sys.path.append(parent_dir)
                from bitcoinwhoswho_scraper import BitcoinWhosWhoScraper
                self.bitcoinwhoswho_scraper = BitcoinWhosWhoScraper(self.config)
                logger.info("BitcoinWhosWho scraper initialized")
            except ImportError as e:
                logger.warning(f"Could not import BitcoinWhosWho scraper: {e}")
                self.enable_bitcoinwhoswho = False
        
        logger.info(f"ThreatIntelClient initialized with sources: "
                   f"BTCBlack={self.enable_btcblack}, "
                   f"ChainAbuse={self.enable_chainabuse}, "
                   f"Cropty={self.enable_cropty}, "
                   f"BitcoinWhosWho={self.enable_bitcoinwhoswho}")
    
    def check_btc_black(self, address: str) -> ThreatIntelResult:
        """
        Check address against BTC Black DNSBL.
        
        Args:
            address: Bitcoin address to check
            
        Returns:
            ThreatIntelResult with blacklist status
        """
        try:
            if not self.enable_btcblack:
                return ThreatIntelResult(
                    source=ThreatIntelSource.BTC_BLACK,
                    blacklisted=False,
                    confidence=0.0,
                    details={'disabled': True},
                    timestamp=datetime.now()
                )
            
            # Construct DNSBL query
            query_address = f"{address}.{self.config.BTC_BLACK_DNSBL}"
            
            logger.debug(f"Querying BTC Black DNSBL: {query_address}")
            
            # Perform DNS query
            resolver = dns.resolver.Resolver()
            resolver.timeout = self.timeout
            resolver.lifetime = self.timeout
            
            try:
                answers = resolver.resolve(query_address, 'A')
                # If we get any A record, the address is blacklisted
                blacklisted = len(answers) > 0
                confidence = 0.9 if blacklisted else 0.1
                
                details = {
                    'dnsbl_query': query_address,
                    'dns_records': [str(answer) for answer in answers],
                    'record_count': len(answers)
                }
                
                logger.info(f"BTC Black DNSBL query for {address}: {'BLACKLISTED' if blacklisted else 'CLEAN'}")
                
                return ThreatIntelResult(
                    source=ThreatIntelSource.BTC_BLACK,
                    blacklisted=blacklisted,
                    confidence=confidence,
                    details=details,
                    timestamp=datetime.now()
                )
                
            except dns.resolver.NXDOMAIN:
                # No DNS record found - address is clean
                return ThreatIntelResult(
                    source=ThreatIntelSource.BTC_BLACK,
                    blacklisted=False,
                    confidence=0.1,
                    details={
                        'dnsbl_query': query_address,
                        'status': 'not_found',
                        'record_count': 0
                    },
                    timestamp=datetime.now()
                )
                
        except dns.exception.DNSException as e:
            logger.error(f"DNS error checking BTC Black for {address}: {e}")
            return ThreatIntelResult(
                source=ThreatIntelSource.BTC_BLACK,
                blacklisted=False,
                confidence=0.0,
                details={'error': 'dns_error'},
                timestamp=datetime.now(),
                error=str(e)
            )
        except Exception as e:
            logger.error(f"Error checking BTC Black for {address}: {e}")
            return ThreatIntelResult(
                source=ThreatIntelSource.BTC_BLACK,
                blacklisted=False,
                confidence=0.0,
                details={'error': 'unknown_error'},
                timestamp=datetime.now(),
                error=str(e)
            )
    
    def check_chainabuse(self, address: str) -> ThreatIntelResult:
        """
        Check address against ChainAbuse database.
        
        Args:
            address: Bitcoin address to check
            
        Returns:
            ThreatIntelResult with abuse report information
        """
        try:
            if not self.enable_chainabuse:
                return ThreatIntelResult(
                    source=ThreatIntelSource.CHAINABUSE,
                    blacklisted=False,
                    confidence=0.0,
                    details={'disabled': True},
                    timestamp=datetime.now()
                )
            
            if not self.chainabuse_scraper:
                logger.warning("ChainAbuse scraper not available")
                return ThreatIntelResult(
                    source=ThreatIntelSource.CHAINABUSE,
                    blacklisted=False,
                    confidence=0.0,
                    details={'error': 'scraper_not_available'},
                    timestamp=datetime.now(),
                    error="ChainAbuse scraper not initialized"
                )
            
            logger.debug(f"Querying ChainAbuse for {address}")
            
            # Use the ChainAbuse scraper to search for the address
            report = self.chainabuse_scraper.search_address(address)
            
            if report:
                # Address found in ChainAbuse - it's malicious
                blacklisted = True
                confidence = report.confidence_score or 0.9
                
                details = {
                    'report_found': True,
                    'category': report.category,
                    'description': report.description,
                    'reporter': report.reporter,
                    'reported_at': report.reported_at.isoformat() if report.reported_at else None,
                    'abuse_type': report.abuse_type,
                    'confidence_score': report.confidence_score,
                    'source_url': report.source_url
                }
                
                logger.info(f"ChainAbuse query for {address}: BLACKLISTED - {report.category}")
                
                return ThreatIntelResult(
                    source=ThreatIntelSource.CHAINABUSE,
                    blacklisted=blacklisted,
                    confidence=confidence,
                    details=details,
                    timestamp=datetime.now()
                )
            else:
                # Address not found in ChainAbuse - clean
                blacklisted = False
                confidence = 0.1
                
                details = {
                    'report_found': False,
                    'status': 'not_found'
                }
                
                logger.info(f"ChainAbuse query for {address}: CLEAN")
                
                return ThreatIntelResult(
                    source=ThreatIntelSource.CHAINABUSE,
                    blacklisted=blacklisted,
                    confidence=confidence,
                    details=details,
                    timestamp=datetime.now()
                )
            
        except Exception as e:
            logger.error(f"Error checking ChainAbuse for {address}: {str(e)}")
            return ThreatIntelResult(
                source=ThreatIntelSource.CHAINABUSE,
                blacklisted=False,
                confidence=0.0,
                details={'error': 'unknown_error'},
                timestamp=datetime.now(),
                error=str(e)
            )
    
    def check_cropty_blacklist(self, address: str) -> ThreatIntelResult:
        """
        Check address against Cropty blacklist.
        
        Args:
            address: Bitcoin address to check
            
        Returns:
            ThreatIntelResult with blacklist status
        """
        try:
            if not self.enable_cropty:
                return ThreatIntelResult(
                    source=ThreatIntelSource.CROPTY,
                    blacklisted=False,
                    confidence=0.0,
                    details={'disabled': True},
                    timestamp=datetime.now()
                )
            
            # Construct API URL
            url = f"{self.config.CROPTY_API_URL}/{address}"
            
            logger.debug(f"Querying Cropty API for {address}")
            
            # Make API request with retries
            for attempt in range(self.retry_attempts):
                try:
                    response = self.session.get(url, timeout=self.timeout)
                    
                    # Cropty returns 200 for blacklisted, 404 for clean
                    if response.status_code == 200:
                        blacklisted = True
                        confidence = 0.8
                        
                        try:
                            data = response.json()
                            reason = data.get('reason', 'Unknown')
                            risk_level = data.get('risk_level', 'high')
                        except json.JSONDecodeError:
                            reason = 'Blacklisted'
                            risk_level = 'high'
                            data = {}
                        
                        details = {
                            'api_url': url,
                            'reason': reason,
                            'risk_level': risk_level,
                            'response_data': data,
                            'attempt': attempt + 1
                        }
                        
                        logger.info(f"Cropty API query for {address}: BLACKLISTED - {reason}")
                        
                        return ThreatIntelResult(
                            source=ThreatIntelSource.CROPTY,
                            blacklisted=blacklisted,
                            confidence=confidence,
                            details=details,
                            timestamp=datetime.now()
                        )
                        
                    elif response.status_code == 404:
                        # Address not found in blacklist - clean
                        blacklisted = False
                        confidence = 0.1
                        
                        details = {
                            'api_url': url,
                            'status': 'not_found',
                            'attempt': attempt + 1
                        }
                        
                        logger.info(f"Cropty API query for {address}: CLEAN")
                        
                        return ThreatIntelResult(
                            source=ThreatIntelSource.CROPTY,
                            blacklisted=blacklisted,
                            confidence=confidence,
                            details=details,
                            timestamp=datetime.now()
                        )
                    
                    else:
                        # Unexpected status code
                        response.raise_for_status()
                        
                except requests.exceptions.RequestException as e:
                    if attempt < self.retry_attempts - 1:
                        logger.warning(f"Cropty API request failed (attempt {attempt + 1}), retrying: {e}")
                        time.sleep(1)  # Brief delay before retry
                        continue
                    else:
                        raise e
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error checking Cropty for {address}: {e}")
            return ThreatIntelResult(
                source=ThreatIntelSource.CROPTY,
                blacklisted=False,
                confidence=0.0,
                details={'error': 'request_error'},
                timestamp=datetime.now(),
                error=str(e)
            )
        except Exception as e:
            logger.error(f"Error checking Cropty for {address}: {e}")
            return ThreatIntelResult(
                source=ThreatIntelSource.CROPTY,
                blacklisted=False,
                confidence=0.0,
                details={'error': 'unknown_error'},
                timestamp=datetime.now(),
                error=str(e)
            )
    
    def check_bitcoinwhoswho(self, address: str) -> ThreatIntelResult:
        """
        Check address against BitcoinWhosWho database.
        
        Args:
            address: Bitcoin address to check
            
        Returns:
            ThreatIntelResult with BitcoinWhosWho data
        """
        try:
            if not self.enable_bitcoinwhoswho:
                return ThreatIntelResult(
                    source=ThreatIntelSource.BITCOINWHOSWHO,
                    blacklisted=False,
                    confidence=0.0,
                    details={'disabled': True},
                    timestamp=datetime.now()
                )
            
            if not self.bitcoinwhoswho_scraper:
                logger.warning("BitcoinWhosWho scraper not available")
                return ThreatIntelResult(
                    source=ThreatIntelSource.BITCOINWHOSWHO,
                    blacklisted=False,
                    confidence=0.0,
                    details={'error': 'scraper_not_available'},
                    timestamp=datetime.now(),
                    error="BitcoinWhosWho scraper not initialized"
                )
            
            logger.debug(f"Querying BitcoinWhosWho for {address}")
            
            # Get risk assessment from BitcoinWhosWho
            risk_assessment = self.bitcoinwhoswho_scraper.get_address_risk_assessment(address)
            
            # Determine if address is blacklisted based on risk level and score
            blacklisted = False
            confidence = risk_assessment.get('confidence', 0.0)
            
            # Consider address blacklisted if:
            # 1. Risk level is critical or high
            # 2. Risk score is above 0.6
            # 3. Has scam reports
            # 4. Has suspicious website appearances
            risk_level = risk_assessment.get('risk_level', 'low')
            risk_score = risk_assessment.get('risk_score', 0.0)
            scam_reports_count = risk_assessment.get('scam_reports_count', 0)
            website_appearances_count = risk_assessment.get('website_appearances_count', 0)
            
            if (risk_level in ['critical', 'high'] or 
                risk_score >= 0.6 or 
                scam_reports_count > 0 or
                website_appearances_count > 0):
                blacklisted = True
                
                # Boost confidence for blacklisted addresses
                if risk_level == 'critical':
                    confidence = max(confidence, 0.95)
                elif risk_level == 'high':
                    confidence = max(confidence, 0.85)
                elif scam_reports_count > 0:
                    confidence = max(confidence, 0.8)
                elif website_appearances_count > 0:
                    confidence = max(confidence, 0.7)
            
            details = {
                'risk_level': risk_level,
                'risk_score': risk_score,
                'scam_reports_count': scam_reports_count,
                'website_appearances_count': website_appearances_count,
                'tags': risk_assessment.get('tags', []),
                'scam_reports': risk_assessment.get('scam_reports', []),
                'website_appearances': risk_assessment.get('website_appearances', []),
                'source': 'bitcoinwhoswho'
            }
            
            if blacklisted:
                logger.info(f"BitcoinWhosWho query for {address}: BLACKLISTED - {risk_level} (score: {risk_score})")
            else:
                logger.info(f"BitcoinWhosWho query for {address}: CLEAN")
            
            return ThreatIntelResult(
                source=ThreatIntelSource.BITCOINWHOSWHO,
                blacklisted=blacklisted,
                confidence=confidence,
                details=details,
                timestamp=datetime.now()
            )
            
        except Exception as e:
            logger.error(f"Error checking BitcoinWhosWho for {address}: {str(e)}")
            return ThreatIntelResult(
                source=ThreatIntelSource.BITCOINWHOSWHO,
                blacklisted=False,
                confidence=0.0,
                details={'error': 'unknown_error'},
                timestamp=datetime.now(),
                error=str(e)
            )
    
    def check_all_sources(self, address: str) -> Dict[str, Any]:
        """
        Check address against all configured threat intelligence sources.
        
        Args:
            address: Bitcoin address to check
            
        Returns:
            Dictionary with aggregated results from all sources
        """
        logger.info(f"Checking address {address} against all threat intelligence sources")
        
        results = {}
        sources_checked = []
        blacklisted_sources = []
        max_confidence = 0.0
        
        # Check BTC Black
        btcblack_result = self.check_btc_black(address)
        results['btcblack'] = {
            'blacklisted': btcblack_result.blacklisted,
            'confidence': btcblack_result.confidence,
            'details': btcblack_result.details,
            'error': btcblack_result.error
        }
        sources_checked.append('btcblack')
        if btcblack_result.blacklisted:
            blacklisted_sources.append('btcblack')
        max_confidence = max(max_confidence, btcblack_result.confidence)
        
        # Check ChainAbuse
        chainabuse_result = self.check_chainabuse(address)
        results['chainabuse'] = {
            'blacklisted': chainabuse_result.blacklisted,
            'confidence': chainabuse_result.confidence,
            'details': chainabuse_result.details,
            'error': chainabuse_result.error
        }
        sources_checked.append('chainabuse')
        if chainabuse_result.blacklisted:
            blacklisted_sources.append('chainabuse')
        max_confidence = max(max_confidence, chainabuse_result.confidence)
        
        # Check Cropty
        cropty_result = self.check_cropty_blacklist(address)
        results['cropty'] = {
            'blacklisted': cropty_result.blacklisted,
            'confidence': cropty_result.confidence,
            'details': cropty_result.details,
            'error': cropty_result.error
        }
        sources_checked.append('cropty')
        if cropty_result.blacklisted:
            blacklisted_sources.append('cropty')
        max_confidence = max(max_confidence, cropty_result.confidence)
        
        # Check BitcoinWhosWho
        bitcoinwhoswho_result = self.check_bitcoinwhoswho(address)
        results['bitcoinwhoswho'] = {
            'blacklisted': bitcoinwhoswho_result.blacklisted,
            'confidence': bitcoinwhoswho_result.confidence,
            'details': bitcoinwhoswho_result.details,
            'error': bitcoinwhoswho_result.error
        }
        sources_checked.append('bitcoinwhoswho')
        if bitcoinwhoswho_result.blacklisted:
            blacklisted_sources.append('bitcoinwhoswho')
        max_confidence = max(max_confidence, bitcoinwhoswho_result.confidence)
        
        # Determine final blacklist status
        final_blacklisted = len(blacklisted_sources) > 0
        
        # Calculate overall confidence
        if final_blacklisted:
            # Use highest confidence from blacklisted sources
            overall_confidence = max_confidence
        else:
            # Use average confidence from clean sources
            clean_confidences = [r['confidence'] for r in results.values() if not r['blacklisted']]
            overall_confidence = sum(clean_confidences) / len(clean_confidences) if clean_confidences else 0.1
        
        # Categorize illicit activity if blacklisted
        illicit_activity_analysis = None
        if final_blacklisted:
            illicit_activity_analysis = self._categorize_illicit_activity(results)
        
        # Build final result
        final_result = {
            **results,
            'final_blacklisted': final_blacklisted,
            'overall_confidence': overall_confidence,
            'sources_checked': sources_checked,
            'blacklisted_sources': blacklisted_sources,
            'illicit_activity_analysis': illicit_activity_analysis,
            'timestamp': datetime.now().isoformat()
        }
        
        logger.info(f"Threat intelligence check complete for {address}: "
                   f"{'BLACKLISTED' if final_blacklisted else 'CLEAN'} "
                   f"(sources: {blacklisted_sources if blacklisted_sources else 'none'}, "
                   f"confidence: {overall_confidence:.2f})")
        
        return final_result
    
    def _categorize_illicit_activity(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enhanced categorization of illicit activity based on threat intelligence results with improved accuracy.
        
        Args:
            results: Results from all threat intelligence sources
            
        Returns:
            Dictionary with illicit activity analysis
        """
        activity_types = {
            'ransomware': 0,
            'scam_fraud': 0,
            'terrorism_financing': 0,
            'money_laundering': 0,
            'drug_trafficking': 0,
            'weapons_trafficking': 0,
            'child_exploitation': 0,
            'hacking_theft': 0,
            'darknet_market': 0,
            'gambling': 0,
            'mixing_service': 0,
            'counterfeit': 0,
            'other': 0
        }
        
        evidence_sources = []
        risk_indicators = []
        confidence_factors = []
        
        # Enhanced keyword patterns with weights and context
        activity_patterns = {
            'ransomware': {
                'keywords': ['ransomware', 'ransom', 'encrypt', 'lock', 'wannacry', 'locky', 'cerber', 'cryptolocker', 'petya', 'notpetya'],
                'weight': self.config.RISK_SCORING_WEIGHTS['ransomware'],
                'context_boost': ['malware', 'virus', 'trojan', 'attack', 'infected']
            },
            'scam_fraud': {
                'keywords': ['scam', 'fraud', 'fake', 'phishing', 'impersonation', 'social engineering', 'ponzi', 'pyramid'],
                'weight': self.config.RISK_SCORING_WEIGHTS['scam_fraud'],
                'context_boost': ['fake', 'bogus', 'deceptive', 'misleading']
            },
            'terrorism_financing': {
                'keywords': ['terrorism', 'terrorist', 'extremist', 'isis', 'al-qaeda', 'boko haram', 'taliban'],
                'weight': self.config.RISK_SCORING_WEIGHTS['terrorism_financing'],
                'context_boost': ['funding', 'financing', 'support', 'donation']
            },
            'money_laundering': {
                'keywords': ['laundering', 'mixing', 'tumbler', 'obfuscation', 'clean', 'wash'],
                'weight': self.config.RISK_SCORING_WEIGHTS['money_laundering'],
                'context_boost': ['illegal', 'criminal', 'proceeds', 'dirty money']
            },
            'drug_trafficking': {
                'keywords': ['drug', 'narcotic', 'cocaine', 'heroin', 'marijuana', 'cannabis', 'opioid', 'fentanyl'],
                'weight': self.config.RISK_SCORING_WEIGHTS['drug_trafficking'],
                'context_boost': ['trafficking', 'smuggling', 'distribution', 'dealer']
            },
            'weapons_trafficking': {
                'keywords': ['weapon', 'gun', 'firearm', 'explosive', 'ammunition', 'bomb', 'grenade'],
                'weight': self.config.RISK_SCORING_WEIGHTS['weapons_trafficking'],
                'context_boost': ['trafficking', 'smuggling', 'illegal', 'unlicensed']
            },
            'child_exploitation': {
                'keywords': ['child', 'minor', 'exploitation', 'abuse', 'pornography', 'pedophile'],
                'weight': self.config.RISK_SCORING_WEIGHTS['child_exploitation'],
                'context_boost': ['illegal', 'criminal', 'underage', 'minor']
            },
            'hacking_theft': {
                'keywords': ['hack', 'theft', 'stolen', 'breach', 'compromise', 'unauthorized', 'cybercrime'],
                'weight': self.config.RISK_SCORING_WEIGHTS['hacking_theft'],
                'context_boost': ['data', 'personal', 'financial', 'identity']
            },
            'darknet_market': {
                'keywords': ['darknet', 'dark web', 'market', 'silk road', 'alphabay', 'hansa', 'tor'],
                'weight': self.config.RISK_SCORING_WEIGHTS['darknet_market'],
                'context_boost': ['onion', 'hidden', 'anonymous', 'illegal']
            },
            'gambling': {
                'keywords': ['gambling', 'casino', 'betting', 'poker', 'lottery', 'sportsbook'],
                'weight': self.config.RISK_SCORING_WEIGHTS['gambling'],
                'context_boost': ['illegal', 'unlicensed', 'offshore']
            },
            'mixing_service': {
                'keywords': ['mixer', 'tumbler', 'obfuscation', 'privacy', 'anonymity'],
                'weight': self.config.RISK_SCORING_WEIGHTS['mixing_service'],
                'context_boost': ['service', 'coin', 'bitcoin', 'cryptocurrency']
            },
            'counterfeit': {
                'keywords': ['counterfeit', 'fake', 'replica', 'knockoff', 'forgery'],
                'weight': self.config.RISK_SCORING_WEIGHTS['counterfeit'],
                'context_boost': ['goods', 'products', 'documents', 'currency']
            }
        }
        
        # Analyze ChainAbuse results with enhanced pattern matching
        if results.get('chainabuse', {}).get('blacklisted', False):
            details = results['chainabuse'].get('details', {})
            category = details.get('category', '').lower()
            description = details.get('description', '').lower()
            abuse_type = details.get('abuse_type', '').lower()
            
            evidence_sources.append('ChainAbuse')
            confidence_factors.append(self.config.CONFIDENCE_FACTORS['chainabuse'])
            
            # Enhanced pattern matching with context
            text_to_analyze = f"{category} {description} {abuse_type}"
            
            for activity, pattern_data in activity_patterns.items():
                score = 0
                keyword_matches = 0
                context_matches = 0
                
                # Check for keyword matches
                for keyword in pattern_data['keywords']:
                    if keyword in text_to_analyze:
                        keyword_matches += 1
                        score += pattern_data['weight']
                
                # Check for context boosters
                for context_word in pattern_data['context_boost']:
                    if context_word in text_to_analyze:
                        context_matches += 1
                        score += pattern_data['weight'] * 0.5
                
                if score > 0:
                    activity_types[activity] += score
                    if keyword_matches > 0:
                        risk_indicators.append(f'ChainAbuse {activity} indicators: {keyword_matches} keywords, {context_matches} context matches')
        
        # Analyze BitcoinWhosWho results with enhanced scoring
        if results.get('bitcoinwhoswho', {}).get('blacklisted', False):
            details = results['bitcoinwhoswho'].get('details', {})
            tags = details.get('tags', [])
            scam_reports = details.get('scam_reports', [])
            website_appearances = details.get('website_appearances', [])
            
            evidence_sources.append('BitcoinWhosWho')
            confidence_factors.append(self.config.CONFIDENCE_FACTORS['bitcoinwhoswho'])
            
            # Analyze tags with enhanced scoring
            for tag in tags:
                tag_lower = tag.lower()
                
                for activity, pattern_data in activity_patterns.items():
                    score = 0
                    
                    # Check for exact tag matches (higher weight)
                    if any(keyword in tag_lower for keyword in pattern_data['keywords']):
                        score += pattern_data['weight'] * 1.5  # Boost for exact tag matches
                    
                    # Check for partial matches
                    elif any(keyword in tag_lower for keyword in pattern_data['keywords'][:3]):  # Check first 3 keywords
                        score += pattern_data['weight'] * 0.8
                    
                    if score > 0:
                        activity_types[activity] += score
                        risk_indicators.append(f'BitcoinWhosWho {activity} tag: {tag}')
            
            # Analyze scam reports with enhanced pattern matching
            for report in scam_reports:
                report_text = f"{report.get('title', '')} {report.get('description', '')}".lower()
                
                for activity, pattern_data in activity_patterns.items():
                    score = 0
                    
                    for keyword in pattern_data['keywords']:
                        if keyword in report_text:
                            score += pattern_data['weight'] * 0.5  # Lower weight for report text
                    
                    if score > 0:
                        activity_types[activity] += score
                        risk_indicators.append(f'BitcoinWhosWho {activity} report: {report.get("title", "Unknown")}')
            
            # Analyze website appearances for suspicious domains
            suspicious_domains = ['darkweb', 'tor', 'onion', 'scam', 'fraud', 'malware', 'virus']
            for appearance in website_appearances:
                domain = appearance.get('domain', '').lower()
                if any(suspicious in domain for suspicious in suspicious_domains):
                    activity_types['darknet_market'] += 2
                    risk_indicators.append(f'Suspicious domain appearance: {domain}')
        
        # Analyze Cropty results with enhanced pattern matching
        if results.get('cropty', {}).get('blacklisted', False):
            details = results['cropty'].get('details', {})
            reason = details.get('reason', '').lower()
            
            evidence_sources.append('Cropty')
            confidence_factors.append(self.config.CONFIDENCE_FACTORS['cropty'])
            
            for activity, pattern_data in activity_patterns.items():
                score = 0
                
                for keyword in pattern_data['keywords']:
                    if keyword in reason:
                        score += pattern_data['weight'] * 0.8  # Slightly lower weight for Cropty
                
                if score > 0:
                    activity_types[activity] += score
                    risk_indicators.append(f'Cropty {activity} report: {reason}')
        
        # BTC Black analysis
        if results.get('btcblack', {}).get('blacklisted', False):
            evidence_sources.append('BTC Black')
            confidence_factors.append(self.config.CONFIDENCE_FACTORS['btcblack'])
            activity_types['other'] += 2  # Generic malicious activity
            risk_indicators.append('BTC Black DNSBL listing - confirmed malicious')
        
        # Calculate overall confidence based on evidence quality
        overall_confidence = 0.0
        if confidence_factors:
            overall_confidence = sum(confidence_factors) / len(confidence_factors)
        
        # Apply confidence multiplier to scores
        for activity in activity_types:
            activity_types[activity] = int(activity_types[activity] * overall_confidence)
        
        # Determine primary illicit activity type
        primary_activity = max(activity_types, key=activity_types.get)
        primary_score = activity_types[primary_activity]
        
        # Get secondary activities (if any)
        secondary_activities = []
        for activity, score in activity_types.items():
            if score > 0 and activity != primary_activity:
                secondary_activities.append({
                    'type': activity,
                    'score': score,
                    'confidence': min(score / 5.0, 1.0)  # Normalize to 0-1
                })
        
        # Sort secondary activities by score
        secondary_activities.sort(key=lambda x: x['score'], reverse=True)
        
        # Enhanced risk level determination
        if primary_score >= self.config.RISK_LEVEL_THRESHOLDS['critical']:
            overall_risk_level = 'critical'
        elif primary_score >= self.config.RISK_LEVEL_THRESHOLDS['high']:
            overall_risk_level = 'high'
        elif primary_score >= self.config.RISK_LEVEL_THRESHOLDS['medium']:
            overall_risk_level = 'medium'
        elif primary_score >= self.config.RISK_LEVEL_THRESHOLDS['low']:
            overall_risk_level = 'low'
        else:
            overall_risk_level = 'minimal'
        
        # Additional risk factors
        risk_factors = []
        if len(evidence_sources) >= 3:
            risk_factors.append('Multiple source confirmation')
        if overall_confidence >= 0.8:
            risk_factors.append('High confidence evidence')
        if any(activity in ['terrorism_financing', 'child_exploitation'] for activity, score in activity_types.items() if score > 0):
            risk_factors.append('High-priority criminal activity')
        
        return {
            'primary_activity_type': primary_activity,
            'primary_activity_score': primary_score,
            'secondary_activities': secondary_activities[:3],  # Top 3 secondary activities
            'overall_risk_level': overall_risk_level,
            'evidence_sources': evidence_sources,
            'risk_indicators': risk_indicators,
            'risk_factors': risk_factors,
            'activity_breakdown': {k: v for k, v in activity_types.items() if v > 0},
            'confidence': overall_confidence,
            'evidence_quality': 'high' if overall_confidence >= 0.8 else 'medium' if overall_confidence >= 0.6 else 'low'
        }
    
    def get_source_status(self) -> Dict[str, Any]:
        """
        Get the status of all threat intelligence sources.
        
        Returns:
            Dictionary with source configuration and status
        """
        return {
            'btcblack': {
                'enabled': self.enable_btcblack,
                'type': 'DNSBL',
                'endpoint': 'bl.btcblack.it'
            },
            'chainabuse': {
                'enabled': self.enable_chainabuse,
                'type': 'Scraper',
                'endpoint': 'chainabuse.com',
                'scraper_available': bool(self.chainabuse_scraper)
            },
            'cropty': {
                'enabled': self.enable_cropty,
                'type': 'API',
                'endpoint': 'cropty.io/api/blacklist'
            },
            'bitcoinwhoswho': {
                'enabled': self.enable_bitcoinwhoswho,
                'type': 'API/Scraper',
                'endpoint': 'bitcoinwhoswho.com',
                'scraper_available': bool(self.bitcoinwhoswho_scraper),
                'api_key_configured': bool(self.bitcoinwhoswho_scraper and self.bitcoinwhoswho_scraper.api_key)
            }
        }
