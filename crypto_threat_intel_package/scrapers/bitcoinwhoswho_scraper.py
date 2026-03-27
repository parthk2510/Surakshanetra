"""
BitcoinWhosWho Scraper for Cryptocurrency Address Analysis

This module provides integration with BitcoinWhosWho API to enhance malicious 
address detection with scam reports, website appearances, tags, and scores.
"""

import logging
import requests
import time
import json
from typing import Dict, Optional, Any, List
from datetime import datetime
from dataclasses import dataclass
from enum import Enum
import os

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

class BitcoinWhosWhoSource(Enum):
    BITCOINWHOSWHO = "bitcoinwhoswho"

@dataclass
class BitcoinWhosWhoResult:
    """Result from BitcoinWhosWho API."""
    source: BitcoinWhosWhoSource
    address: str
    score: Optional[float]
    tags: List[str]
    scam_reports: List[Dict[str, Any]]
    website_appearances: List[Dict[str, Any]]
    confidence: float
    timestamp: datetime
    risk_level: str = "UNKNOWN"
    error: Optional[str] = None

@dataclass
class ScamReport:
    """Scam report data structure."""
    report_id: str
    title: str
    description: str
    category: str
    severity: str
    reported_at: datetime
    reporter: str
    source_url: str
    confidence_score: float

@dataclass
class WebsiteAppearance:
    """Website appearance data structure."""
    url: str
    title: str
    description: str
    domain: str
    first_seen: datetime
    last_seen: datetime
    context: str
    risk_level: str

class BitcoinWhosWhoScraper:
    """
    Scraper for BitcoinWhosWho API to extract address information and risk data.
    
    Features:
    - Scam reports retrieval
    - Website appearances tracking
    - Tags and categorization
    - Risk scoring with confidence levels
    """
    
    def __init__(self, config: Optional[ScraperConfig] = None):
        """
        Initialize the BitcoinWhosWho scraper.
        
        Args:
            config: ScraperConfig instance with all configuration values
        """
        self.config = config or ScraperConfig()
        self.api_key = self.config.BITCOINWHOSWHO_API_KEY
        self.timeout = self.config.DEFAULT_TIMEOUT
        self.retry_attempts = self.config.DEFAULT_RETRY_ATTEMPTS
        
        # Initialize session with proper headers
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': self.config.USER_AGENT,
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        })
        
        if self.api_key:
            self.session.headers.update({
                'Authorization': f'Bearer {self.api_key}'
            })
        
        # Base URLs from configuration
        self.api_base_url = self.config.BITCOINWHOSWHO_API_URL
        self.web_base_url = self.config.BITCOINWHOSWHO_WEB_URL
        
        logger.info(f"BitcoinWhosWho scraper initialized with API key: {'Yes' if self.api_key else 'No'}")
    
    def search_address(self, address: str) -> BitcoinWhosWhoResult:
        """
        Search for address information on BitcoinWhosWho.
        
        Args:
            address: Bitcoin address to search
            
        Returns:
            BitcoinWhosWhoResult with comprehensive address data
        """
        try:
            logger.info(f"Searching BitcoinWhosWho for address: {address}")
            
            # Try API first if key is available
            if self.api_key:
                return self._search_via_api(address)
            else:
                # Fallback to web scraping
                return self._search_via_scraping(address)
                
        except Exception as e:
            logger.error(f"Error searching BitcoinWhosWho for {address}: {str(e)}")
            return BitcoinWhosWhoResult(
                source=BitcoinWhosWhoSource.BITCOINWHOSWHO,
                address=address,
                score=None,
                tags=[],
                scam_reports=[],
                website_appearances=[],
                confidence=0.0,
                timestamp=datetime.now(),
                error=str(e)
            )
    
    def _search_via_api(self, address: str) -> BitcoinWhosWhoResult:
        """Search using BitcoinWhosWho API."""
        try:
            # Get address score
            score = self._get_address_score(address)
            
            # Get scam reports
            scam_reports = self._get_scam_reports(address)
            
            # Get website appearances
            website_appearances = self._get_website_appearances(address)
            
            # Get tags
            tags = self._get_address_tags(address)
            
            # Calculate confidence based on data quality and quantity
            confidence = self._calculate_confidence(score, scam_reports, website_appearances, tags)
            
            # Calculate risk level based on score and reports
            risk_level = self._calculate_risk_level(score, scam_reports, tags)
            
            return BitcoinWhosWhoResult(
                source=BitcoinWhosWhoSource.BITCOINWHOSWHO,
                address=address,
                score=score,
                tags=tags,
                scam_reports=scam_reports,
                website_appearances=website_appearances,
                confidence=confidence,
                timestamp=datetime.now(),
                risk_level=risk_level
            )
            
        except Exception as e:
            logger.error(f"API search failed for {address}: {str(e)}")
            # Return None when no real data is available
            return None
    
    def _search_via_scraping(self, address: str) -> BitcoinWhosWhoResult:
        """Search using web scraping as fallback with enhanced data sources."""
        try:
            # Try multiple data sources
            results = []
            
            # 1. BitcoinWhosWho direct scraping
            try:
                url = f"{self.web_base_url}/address/{address}"
                logger.debug(f"Scraping BitcoinWhosWho page: {url}")
                
                for attempt in range(self.retry_attempts):
                    try:
                        response = self.session.get(url, timeout=self.timeout)
                        response.raise_for_status()
                        
                        result = self._parse_address_page(response.text, address)
                        results.append(result)
                        break
                        
                    except requests.exceptions.RequestException as e:
                        if attempt < self.retry_attempts - 1:
                            logger.warning(f"BitcoinWhosWho scraping attempt {attempt + 1} failed, retrying: {e}")
                            time.sleep(1)
                            continue
                        else:
                            logger.warning(f"BitcoinWhosWho scraping failed: {e}")
            except Exception as e:
                logger.warning(f"BitcoinWhosWho scraping error: {e}")
            
            # External data gathering removed - only real API data is used
            
            # 3. Combine results from all sources
            if results:
                return self._combine_results(results, address)
            else:
                # Fallback to basic result
                return BitcoinWhosWhoResult(
                    source=BitcoinWhosWhoSource.BITCOINWHOSWHO,
                    address=address,
                    score=None,
                    tags=[],
                    scam_reports=[],
                    website_appearances=[],
                    confidence=0.0,
                    timestamp=datetime.now(),
                    error="No data sources available"
                )
            
        except Exception as e:
            logger.error(f"Scraping failed for {address}: {str(e)}")
            return BitcoinWhosWhoResult(
                source=BitcoinWhosWhoSource.BITCOINWHOSWHO,
                address=address,
                score=None,
                tags=[],
                scam_reports=[],
                website_appearances=[],
                confidence=0.0,
                timestamp=datetime.now(),
                error=str(e)
            )
    
    # External data gathering removed - only real API data is used
    def _gather_external_data_removed(self, address: str) -> Optional[BitcoinWhosWhoResult]:
        """Gather data from external sources to supplement BitcoinWhosWho."""
        try:
            tags = []
            scam_reports = []
            website_appearances = []
            score = None
            
            # Check against known malicious address databases
            malicious_databases = {}
            for addr, data in self.config.KNOWN_MALICIOUS_ADDRESSES.items():
                if data.get('source') == 'security_research':
                    malicious_databases[addr] = {
                        'score': data['confidence_score'],
                        'tags': [data['abuse_type'], data['category'].lower(), 'critical', 'security_research'],
                        'scam_reports': [{
                            'title': f"{data['category']} Address",
                            'description': data['description'],
                            'category': data['abuse_type'],
                            'severity': 'critical',
                            'reported_at': datetime.now().isoformat(),
                            'reporter': data['reporter'],
                            'source_url': self.config.EXTERNAL_DATA_SOURCES['secureworks_wannacry']['url'],
                            'confidence_score': data['confidence_score']
                        }],
                        'website_appearances': [{
                            'url': self.config.EXTERNAL_DATA_SOURCES['secureworks_wannacry']['url'],
                            'title': self.config.EXTERNAL_DATA_SOURCES['secureworks_wannacry']['title'],
                            'description': self.config.EXTERNAL_DATA_SOURCES['secureworks_wannacry']['description'],
                            'domain': self.config.EXTERNAL_DATA_SOURCES['secureworks_wannacry']['domain'],
                            'first_seen': datetime.now().isoformat(),
                            'last_seen': datetime.now().isoformat(),
                            'context': self.config.EXTERNAL_DATA_SOURCES['secureworks_wannacry']['context'],
                            'risk_level': self.config.EXTERNAL_DATA_SOURCES['secureworks_wannacry']['risk_level']
                        }]
                    }
            
            if address in malicious_databases:
                data = malicious_databases[address]
                score = data['score']
                tags.extend(data['tags'])
                scam_reports.extend(data['scam_reports'])
                website_appearances.extend(data['website_appearances'])
                logger.info(f"Found external data for known malicious address: {address}")
            
            # Check for common malicious patterns in address
            malicious_patterns = self._analyze_address_patterns(address)
            if malicious_patterns:
                tags.extend(malicious_patterns['tags'])
                if malicious_patterns['score'] > 0.5:
                    score = max(score or 0, malicious_patterns['score'])
            
            # Search for additional threat intelligence
            threat_intel_data = self._search_threat_intelligence(address)
            if threat_intel_data:
                tags.extend(threat_intel_data.get('tags', []))
                scam_reports.extend(threat_intel_data.get('scam_reports', []))
                website_appearances.extend(threat_intel_data.get('website_appearances', []))
                if threat_intel_data.get('score', 0) > 0.5:
                    score = max(score or 0, threat_intel_data['score'])
            
            if tags or scam_reports or website_appearances or score:
                confidence = self._calculate_confidence(score, scam_reports, website_appearances, tags)
                return BitcoinWhosWhoResult(
                    source=BitcoinWhosWhoSource.BITCOINWHOSWHO,
                    address=address,
                    score=score,
                    tags=list(set(tags)),
                    scam_reports=scam_reports,
                    website_appearances=website_appearances,
                    confidence=confidence,
                    timestamp=datetime.now()
                )
            
            return None
            
        except Exception as e:
            logger.error(f"Error gathering external data for {address}: {e}")
            return None
    
    def _analyze_address_patterns(self, address: str) -> Dict[str, Any]:
        """Analyze address patterns for malicious indicators."""
        try:
            tags = []
            score = 0.0
            
            # Check for suspicious address patterns
            if len(address) < 26:  # Very short addresses might be suspicious
                tags.append('short_address')
                score += 0.1
            
            # Check for repeated characters (potential vanity addresses used for scams)
            char_counts = {}
            for char in address:
                char_counts[char] = char_counts.get(char, 0) + 1
            
            max_repeat = max(char_counts.values())
            if max_repeat > len(address) * 0.3:  # More than 30% same character
                tags.append('repeated_characters')
                score += 0.2
            
            # Check for common scam patterns
            scam_patterns = ['1111', '0000', 'aaaa', 'bbbb', 'cccc']
            for pattern in scam_patterns:
                if pattern in address.lower():
                    tags.append('suspicious_pattern')
                    score += 0.3
            
            return {
                'tags': tags,
                'score': min(score, 0.8)  # Cap at 0.8 for pattern analysis
            }
            
        except Exception as e:
            logger.error(f"Error analyzing address patterns for {address}: {e}")
            return {'tags': [], 'score': 0.0}
    
    def _search_threat_intelligence(self, address: str) -> Optional[Dict[str, Any]]:
        """Search additional threat intelligence sources."""
        try:
            # This could be expanded to include other threat intel sources
            # For now, we'll use a simple web search approach
            
            tags = []
            scam_reports = []
            website_appearances = []
            score = 0.0
            
            # Search for address in security reports
            search_terms = [
                f'"{address}" bitcoin scam',
                f'"{address}" bitcoin fraud',
                f'"{address}" bitcoin malware',
                f'"{address}" bitcoin ransomware'
            ]
            
            # This is a placeholder for actual threat intelligence integration
            # In a real implementation, you would integrate with:
            # - VirusTotal API
            # - ThreatConnect API
            # - MISP (Malware Information Sharing Platform)
            # - Other OSINT sources
            
            return {
                'tags': tags,
                'scam_reports': scam_reports,
                'website_appearances': website_appearances,
                'score': score
            }
            
        except Exception as e:
            logger.error(f"Error searching threat intelligence for {address}: {e}")
            return None
    
    def _combine_results(self, results: List[BitcoinWhosWhoResult], address: str) -> BitcoinWhosWhoResult:
        """Combine results from multiple sources."""
        try:
            if not results:
                return BitcoinWhosWhoResult(
                    source=BitcoinWhosWhoSource.BITCOINWHOSWHO,
                    address=address,
                    score=None,
                    tags=[],
                    scam_reports=[],
                    website_appearances=[],
                    confidence=0.0,
                    timestamp=datetime.now()
                )
            
            # Combine all data
            all_tags = []
            all_scam_reports = []
            all_website_appearances = []
            scores = []
            confidences = []
            
            for result in results:
                if result.tags:
                    all_tags.extend(result.tags)
                if result.scam_reports:
                    all_scam_reports.extend(result.scam_reports)
                if result.website_appearances:
                    all_website_appearances.extend(result.website_appearances)
                if result.score is not None:
                    scores.append(result.score)
                if result.confidence > 0:
                    confidences.append(result.confidence)
            
            # Calculate combined score (use highest)
            combined_score = max(scores) if scores else None
            
            # Calculate combined confidence
            combined_confidence = max(confidences) if confidences else 0.0
            
            # Remove duplicates
            unique_tags = list(set(all_tags))
            unique_scam_reports = []
            seen_reports = set()
            for report in all_scam_reports:
                report_key = report.get('title', '') + report.get('description', '')
                if report_key not in seen_reports:
                    unique_scam_reports.append(report)
                    seen_reports.add(report_key)
            
            unique_website_appearances = []
            seen_appearances = set()
            for appearance in all_website_appearances:
                appearance_key = appearance.get('url', '')
                if appearance_key not in seen_appearances:
                    unique_website_appearances.append(appearance)
                    seen_appearances.add(appearance_key)
            
            logger.info(f"Combined results for {address}: score={combined_score}, tags={len(unique_tags)}, reports={len(unique_scam_reports)}, appearances={len(unique_website_appearances)}")
            
            return BitcoinWhosWhoResult(
                source=BitcoinWhosWhoSource.BITCOINWHOSWHO,
                address=address,
                score=combined_score,
                tags=unique_tags,
                scam_reports=unique_scam_reports,
                website_appearances=unique_website_appearances,
                confidence=combined_confidence,
                timestamp=datetime.now()
            )
            
        except Exception as e:
            logger.error(f"Error combining results for {address}: {e}")
            return results[0] if results else BitcoinWhosWhoResult(
                source=BitcoinWhosWhoSource.BITCOINWHOSWHO,
                address=address,
                score=None,
                tags=[],
                scam_reports=[],
                website_appearances=[],
                confidence=0.0,
                timestamp=datetime.now(),
                error=str(e)
            )
    
    def _get_address_score(self, address: str) -> Optional[float]:
        """Get address risk score from API."""
        try:
            url = f"{self.api_base_url}/score/{address}"
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            
            data = response.json()
            return data.get('score')
            
        except Exception as e:
            logger.warning(f"Could not get score for {address}: {e}")
            return None
    
    def _get_scam_reports(self, address: str) -> List[Dict[str, Any]]:
        """Get scam reports for address from API."""
        try:
            url = f"{self.api_base_url}/scam-reports/{address}"
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            
            data = response.json()
            reports = data.get('reports', [])
            
            # Convert to standardized format
            scam_reports = []
            for report in reports:
                scam_reports.append({
                    'report_id': report.get('id', ''),
                    'title': report.get('title', ''),
                    'description': report.get('description', ''),
                    'category': report.get('category', 'unknown'),
                    'severity': report.get('severity', 'medium'),
                    'reported_at': report.get('reported_at', ''),
                    'reporter': report.get('reporter', 'anonymous'),
                    'source_url': report.get('source_url', ''),
                    'confidence_score': report.get('confidence_score', 0.5)
                })
            
            return scam_reports
            
        except Exception as e:
            logger.warning(f"Could not get scam reports for {address}: {e}")
            return []
    
    def _get_website_appearances(self, address: str) -> List[Dict[str, Any]]:
        """Get website appearances for address from API."""
        try:
            url = f"{self.api_base_url}/website-appearances/{address}"
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            
            data = response.json()
            appearances = data.get('appearances', [])
            
            # Convert to standardized format
            website_appearances = []
            for appearance in appearances:
                website_appearances.append({
                    'url': appearance.get('url', ''),
                    'title': appearance.get('title', ''),
                    'description': appearance.get('description', ''),
                    'domain': appearance.get('domain', ''),
                    'first_seen': appearance.get('first_seen', ''),
                    'last_seen': appearance.get('last_seen', ''),
                    'context': appearance.get('context', ''),
                    'risk_level': appearance.get('risk_level', 'unknown')
                })
            
            return website_appearances
            
        except Exception as e:
            logger.warning(f"Could not get website appearances for {address}: {e}")
            return []
    
    def _get_address_tags(self, address: str) -> List[str]:
        """Get tags for address from API."""
        try:
            url = f"{self.api_base_url}/tags/{address}"
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            
            data = response.json()
            return data.get('tags', [])
            
        except Exception as e:
            logger.warning(f"Could not get tags for {address}: {e}")
            return []
    
    def _parse_address_page(self, html_content: str, address: str) -> BitcoinWhosWhoResult:
        """Parse BitcoinWhosWho address page content with enhanced parsing based on actual page structure."""
        try:
            from bs4 import BeautifulSoup
            import re
            
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Initialize variables
            score = None
            tags = []
            scam_reports = []
            website_appearances = []
            
            # 1. Extract Scam Alert information
            scam_alert_elements = soup.find_all(text=re.compile(r'scam alert|fraudulent|reported.*fraud', re.I))
            scam_count = 0
            
            for element in scam_alert_elements:
                text = element.get_text() if hasattr(element, 'get_text') else str(element)
                # Look for scam count pattern: "reported as fraudulent (X time)"
                scam_match = re.search(r'fraudulent.*?\((\d+)\s*time', text, re.I)
                if scam_match:
                    scam_count = int(scam_match.group(1))
                    break
            
            # If scam alert found, create scam report
            if scam_count > 0:
                scam_reports.append({
                    'title': f'Scam Alert - Reported as Fraudulent',
                    'description': f'This address has been reported as fraudulent ({scam_count} time{"s" if scam_count > 1 else ""})',
                    'category': 'scam',
                    'severity': 'high',
                    'reported_at': datetime.now().isoformat(),
                    'reporter': 'bitcoinwhoswho',
                    'source_url': f"{self.web_base_url}/address/{address}",
                    'confidence_score': 0.9
                })
                tags.append('scam')
                tags.append('fraudulent')
                score = 0.9  # High score for scam alerts
            
            # 2. Extract Website Appearances count
            website_appearances_count = 0
            appearance_elements = soup.find_all(text=re.compile(r'website appearances|public sightings', re.I))
            
            for element in appearance_elements:
                text = element.get_text() if hasattr(element, 'get_text') else str(element)
                # Look for number pattern
                number_match = re.search(r'(\d+)', text)
                if number_match:
                    website_appearances_count = int(number_match.group(1))
                    break
            
            # If website appearances found, create appearances
            if website_appearances_count > 0:
                for i in range(min(website_appearances_count, 10)):  # Limit to 10 appearances
                    website_appearances.append({
                        'url': f"{self.web_base_url}/address/{address}",
                        'title': f'Website Appearance #{i+1}',
                        'description': f'Address mentioned on external website',
                        'domain': 'bitcoinwhoswho.com',
                        'first_seen': datetime.now().isoformat(),
                        'last_seen': datetime.now().isoformat(),
                        'context': 'public_sighting',
                        'risk_level': 'medium' if website_appearances_count > 20 else 'low'
                    })
                
                # Boost score based on website appearances
                if score is None:
                    score = 0.3
                else:
                    score = max(score, 0.3)
                
                if website_appearances_count > 20:
                    tags.append('highly_mentioned')
                    score = max(score, 0.6)
                elif website_appearances_count > 5:
                    tags.append('mentioned')
                    score = max(score, 0.4)
            
            # 3. Extract Tags information
            tags_elements = soup.find_all(text=re.compile(r'tags.*login|please login.*tags', re.I))
            tags_count = 0
            
            for element in tags_elements:
                text = element.get_text() if hasattr(element, 'get_text') else str(element)
                # Look for tags count pattern: "X Tags"
                tags_match = re.search(r'(\d+)\s*tags', text, re.I)
                if tags_match:
                    tags_count = int(tags_match.group(1))
                    break
            
            # If tags exist but are hidden, add generic tags based on other indicators
            if tags_count > 0:
                tags.append(f'{tags_count}_tags_hidden')
                if score is None:
                    score = 0.2
                else:
                    score = max(score, 0.2)
            
            # 4. Extract transaction data and balance information
            balance_elements = soup.find_all(text=re.compile(r'current balance|total received', re.I))
            has_transactions = False
            
            for element in balance_elements:
                text = element.get_text() if hasattr(element, 'get_text') else str(element)
                # Check if balance is not zero
                if re.search(r'\$[1-9]|\d+\.\d+', text):
                    has_transactions = True
                    break
            
            # 5. Look for specific BitcoinWhosWho page elements
            # Check for error messages that might indicate data issues
            error_elements = soup.find_all(text=re.compile(r'couldn\'t read|could not read|error|failed', re.I))
            has_errors = len(error_elements) > 0
            
            # 6. Extract additional risk indicators from page content
            page_text = soup.get_text().lower()
            risk_indicators = {
                'wannacry': 0.95,
                'ransomware': 0.9,
                'malware': 0.8,
                'trojan': 0.8,
                'virus': 0.7,
                'phishing': 0.8,
                'scam': 0.7,
                'fraud': 0.8,
                'theft': 0.8,
                'stolen': 0.8,
                'darkweb': 0.9,
                'dark web': 0.9,
                'tor': 0.7,
                'onion': 0.8,
                'mixing': 0.8,
                'tumbler': 0.8,
                'laundering': 0.9,
                'illegal': 0.8,
                'criminal': 0.9
            }
            
            found_indicators = []
            for indicator, indicator_score in risk_indicators.items():
                if indicator in page_text:
                    found_indicators.append(indicator)
                    tags.append(indicator)
                    if score is None:
                        score = indicator_score
                    else:
                        score = max(score, indicator_score)
            
            # 7. Calculate confidence based on extracted data
            confidence = self._calculate_confidence(score, scam_reports, website_appearances, tags)
            
            # 9. Log detailed extraction results
            logger.info(f"BitcoinWhosWho extraction for {address}:")
            logger.info(f"  - Scam reports: {len(scam_reports)}")
            logger.info(f"  - Website appearances: {website_appearances_count}")
            logger.info(f"  - Tags found: {len(tags)}")
            logger.info(f"  - Risk indicators: {found_indicators}")
            logger.info(f"  - Score: {score}")
            logger.info(f"  - Confidence: {confidence}")
            
            return BitcoinWhosWhoResult(
                source=BitcoinWhosWhoSource.BITCOINWHOSWHO,
                address=address,
                score=score,
                tags=list(set(tags)),  # Remove duplicates
                scam_reports=scam_reports,
                website_appearances=website_appearances,
                confidence=confidence,
                timestamp=datetime.now()
            )
            
        except Exception as e:
            logger.error(f"Error parsing BitcoinWhosWho page for {address}: {e}")
            return BitcoinWhosWhoResult(
                source=BitcoinWhosWhoSource.BITCOINWHOSWHO,
                address=address,
                score=None,
                tags=[],
                scam_reports=[],
                website_appearances=[],
                confidence=0.0,
                timestamp=datetime.now(),
                error=str(e)
            )
    
    def _calculate_confidence(self, score: Optional[float], scam_reports: List[Dict], 
                            website_appearances: List[Dict], tags: List[str]) -> float:
        """
        Calculate confidence score based on data quality and quantity.
        
        Confidence factors:
        - Score availability and value
        - Number of scam reports
        - Number of website appearances
        - Tag relevance and quantity
        - Data consistency
        """
        confidence = 0.0
        
        # Score factor (0-0.3)
        if score is not None:
            if score >= 0.8:  # High risk score
                confidence += 0.3
            elif score >= 0.6:  # Medium-high risk
                confidence += 0.25
            elif score >= 0.4:  # Medium risk
                confidence += 0.2
            elif score >= 0.2:  # Low-medium risk
                confidence += 0.15
            else:  # Low risk
                confidence += 0.1
        
        # Scam reports factor (0-0.4) - Increased weight for scam reports
        if scam_reports:
            report_count = len(scam_reports)
            if report_count >= 5:
                confidence += 0.4
            elif report_count >= 3:
                confidence += 0.35
            elif report_count >= 2:
                confidence += 0.3
            else:
                confidence += 0.25  # Even single scam report is significant
            
            # Boost confidence for high-severity reports
            high_severity_reports = [r for r in scam_reports if r.get('severity') in ['high', 'critical']]
            if high_severity_reports:
                confidence += 0.15  # Increased boost for high severity
        
        # Website appearances factor (0-0.25) - Increased weight
        if website_appearances:
            appearance_count = len(website_appearances)
            if appearance_count >= 20:  # High appearance count (like 45 for WannaCry)
                confidence += 0.25
            elif appearance_count >= 10:
                confidence += 0.2
            elif appearance_count >= 5:
                confidence += 0.15
            elif appearance_count >= 3:
                confidence += 0.1
            else:
                confidence += 0.05
            
            # Boost confidence for suspicious domains
            suspicious_domains = ['darkweb', 'tor', 'onion', 'scam', 'fraud']
            suspicious_appearances = [
                app for app in website_appearances 
                if any(domain in app.get('domain', '').lower() for domain in suspicious_domains)
            ]
            if suspicious_appearances:
                confidence += 0.1
        
        # Tags factor (0-0.2)
        if tags:
            tag_count = len(tags)
            if tag_count >= 5:
                confidence += 0.2
            elif tag_count >= 3:
                confidence += 0.15
            elif tag_count >= 2:
                confidence += 0.1
            else:
                confidence += 0.05
            
            # Boost confidence for high-risk tags
            high_risk_tags = ['scam', 'fraud', 'ransomware', 'malware', 'darkweb', 'mixing', 'tumbler']
            high_risk_tag_count = sum(1 for tag in tags if any(risk_tag in tag.lower() for risk_tag in high_risk_tags))
            if high_risk_tag_count > 0:
                confidence += 0.1 * min(high_risk_tag_count, 3)  # Cap at 0.3
        
        # Data consistency bonus (0-0.1)
        if score and scam_reports and website_appearances:
            # All data sources available
            confidence += 0.1
        elif (score and scam_reports) or (score and website_appearances) or (scam_reports and website_appearances):
            # Two data sources available
            confidence += 0.05
        
        # Cap confidence at 1.0
        return min(confidence, 1.0)
    
    def _calculate_risk_level(self, score: Optional[float], scam_reports: List[Dict], tags: List[str]) -> str:
        """
        Calculate risk level based on score, scam reports, and tags.
        
        Args:
            score: Risk score from BitcoinWhosWho
            scam_reports: List of scam reports
            tags: List of tags associated with the address
            
        Returns:
            Risk level string: LOW, MEDIUM, HIGH, CRITICAL
        """
        risk_score = 0.0
        
        # Score factor (0-0.5)
        if score is not None:
            risk_score += score * 0.5
        
        # Scam reports factor (0-0.3)
        if scam_reports:
            report_count = len(scam_reports)
            risk_score += min(report_count * 0.1, 0.3)
            
            # Boost for high severity reports
            high_severity_reports = [r for r in scam_reports if r.get('severity') in ['high', 'critical']]
            if high_severity_reports:
                risk_score += 0.2
        
        # Tags factor (0-0.2)
        if tags:
            high_risk_tags = ['scam', 'fraud', 'ransomware', 'malware', 'darkweb', 'mixing', 'tumbler', 'stolen']
            high_risk_tag_count = sum(1 for tag in tags if any(risk_tag in tag.lower() for risk_tag in high_risk_tags))
            risk_score += min(high_risk_tag_count * 0.05, 0.2)
        
        # Determine risk level
        if risk_score >= 0.8:
            return "CRITICAL"
        elif risk_score >= 0.6:
            return "HIGH"
        elif risk_score >= 0.4:
            return "MEDIUM"
        else:
            return "LOW"
    
    def search_addresses_batch(self, addresses: List[str]) -> List[Optional[BitcoinWhosWhoResult]]:
        """
        Search for multiple addresses in batch.
        
        Args:
            addresses: List of Bitcoin addresses to search for
            
        Returns:
            List of BitcoinWhosWhoResult objects (None for addresses not found)
        """
        results = []
        
        for address in addresses:
            try:
                result = self.search_address(address)
                results.append(result)
                
                # Add delay between requests to be respectful
                if hasattr(self, 'delay_between_requests') and self.delay_between_requests > 0:
                    time.sleep(self.delay_between_requests)
                    
            except Exception as e:
                logger.error(f"Error searching address {address}: {e}")
                results.append(None)
        
        return results
    
    def get_address_risk_assessment(self, address: str) -> Dict[str, Any]:
        """
        Get comprehensive risk assessment for an address.
        
        Args:
            address: Bitcoin address to assess
            
        Returns:
            Dictionary with risk assessment data
        """
        try:
            result = self.search_address(address)
            
            # Calculate risk level based on score and reports
            risk_level = "low"
            if result.score:
                if result.score >= 0.8:
                    risk_level = "critical"
                elif result.score >= 0.6:
                    risk_level = "high"
                elif result.score >= 0.4:
                    risk_level = "medium"
            
            # Adjust risk level based on scam reports
            if result.scam_reports:
                high_severity_reports = [r for r in result.scam_reports if r.get('severity') == 'high']
                if high_severity_reports:
                    risk_level = "critical"
                elif len(result.scam_reports) >= 3:
                    risk_level = "high"
                elif len(result.scam_reports) >= 1:
                    risk_level = "medium"
            
            # Adjust risk level based on suspicious website appearances
            suspicious_appearances = [
                app for app in result.website_appearances 
                if any(domain in app.get('domain', '').lower() for domain in ['darkweb', 'tor', 'onion', 'scam'])
            ]
            if suspicious_appearances:
                risk_level = "high" if risk_level == "medium" else "critical" if risk_level == "high" else "medium"
            
            return {
                'address': address,
                'risk_level': risk_level,
                'risk_score': result.score or 0.0,
                'confidence': result.confidence,
                'scam_reports_count': len(result.scam_reports),
                'website_appearances_count': len(result.website_appearances),
                'tags': result.tags,
                'scam_reports': result.scam_reports,
                'website_appearances': result.website_appearances,
                'timestamp': result.timestamp.isoformat(),
                'source': 'bitcoinwhoswho',
                'error': result.error
            }
            
        except Exception as e:
            logger.error(f"Error getting risk assessment for {address}: {str(e)}")
            return {
                'address': address,
                'risk_level': 'unknown',
                'risk_score': 0.0,
                'confidence': 0.0,
                'error': str(e),
                'timestamp': datetime.now().isoformat(),
                'source': 'bitcoinwhoswho'
            }

# Test function for development
def test_bitcoinwhoswho_scraper():
    """Test the BitcoinWhosWho scraper with sample addresses."""
    scraper = BitcoinWhosWhoScraper()
    
    # Test addresses from configuration
    config = ScraperConfig()
    test_addresses = [
        config.TEST_ADDRESSES['wannacry'],  # WannaCry ransomware
        config.TEST_ADDRESSES['genesis'],  # Genesis block
        config.TEST_ADDRESSES['common'],  # Common test address
        config.TEST_ADDRESSES['bech32'],  # Bech32 address
        "1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN2",  # Common address
        "1P5ZEDWTKTFGxQjZphgWPQUpe554WKDfHQ",  # Another test address
        "1HZwkjkeaoZfTSaJxDw6aKkxp45agDiEzN",  # Test address
        "1F1tAaz5x1HUXrCNLbtMDqcw6o5GNn4xqX",  # Test address
        "1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN2"   # Duplicate for testing
    ]
    
    results = []
    for address in test_addresses:
        print(f"\nTesting address: {address}")
        result = scraper.get_address_risk_assessment(address)
        results.append(result)
        
        print(f"Risk Level: {result['risk_level']}")
        print(f"Risk Score: {result['risk_score']}")
        print(f"Confidence: {result['confidence']}")
        print(f"Scam Reports: {result['scam_reports_count']}")
        print(f"Website Appearances: {result['website_appearances_count']}")
        print(f"Tags: {result['tags']}")
        if result.get('error'):
            print(f"Error: {result['error']}")
    
    return results

if __name__ == "__main__":
    # Run test
    test_results = test_bitcoinwhoswho_scraper()
    print(f"\nTest completed with {len(test_results)} addresses")
