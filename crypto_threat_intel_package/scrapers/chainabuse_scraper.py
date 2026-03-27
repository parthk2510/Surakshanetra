"""
ChainAbuse Scraper for Malicious Address Detection

This module scrapes ChainAbuse database to detect malicious addresses
and provides comprehensive threat intelligence.
"""

import os
import time
import json
import logging
import requests
from typing import Dict, List, Optional, Any, Set
from datetime import datetime, timedelta
from dataclasses import dataclass
from bs4 import BeautifulSoup
import re
from urllib.parse import urljoin, quote

# Import configuration
try:
    from ..config.scraper_config import ScraperConfig
except ImportError:
    # Fallback for direct execution
    import sys
    from pathlib import Path
    sys.path.append(str(Path(__file__).parent.parent / "config"))
    from scraper_config import ScraperConfig

# Define custom exceptions locally to avoid import issues
class APIError(Exception):
    """Custom API error exception."""
    pass

class ValidationError(Exception):
    """Custom validation error exception."""
    pass

logger = logging.getLogger(__name__)

@dataclass
class ChainAbuseReport:
    """ChainAbuse report data structure."""
    address: str
    category: str
    description: str
    reporter: str
    reported_at: datetime
    abuse_type: str
    confidence_score: float
    source_url: str
    raw_data: Dict

class ChainAbuseScraper:
    """Scraper for ChainAbuse malicious address database."""
    
    def __init__(self, config: Optional[ScraperConfig] = None):
        self.config = config or ScraperConfig()
        self.base_url = self.config.CHAINABUSE_BASE_URL
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': self.config.USER_AGENT,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })
        self.timeout = self.config.DEFAULT_TIMEOUT
        self.max_retries = self.config.DEFAULT_RETRY_ATTEMPTS
        self.delay_between_requests = self.config.DEFAULT_DELAY_BETWEEN_REQUESTS
        
    def search_address(self, address: str) -> Optional[ChainAbuseReport]:
        """
        Search for an address in ChainAbuse database with enhanced data collection and robust fallback mechanisms.
        
        Args:
            address: Bitcoin address to search for
            
        Returns:
            ChainAbuseReport if found, None otherwise
        """
        try:
            logger.info(f"Searching ChainAbuse for address: {address}")
            
            # Try multiple endpoints with retry logic
            endpoints = [
                f"{self.base_url}/address/{address}",
                f"{self.base_url}/reports?address={address}",
                f"{self.base_url}/search?q={address}"
            ]
            
            for attempt in range(self.max_retries):
                for endpoint in endpoints:
                    try:
                        logger.debug(f"Trying endpoint: {endpoint} (attempt {attempt + 1})")
                        
                        response = self.session.get(endpoint, timeout=self.timeout)
                        
                        # Check if address exists (200) or not found (404)
                        if response.status_code == 404:
                            logger.debug(f"Address {address} not found at {endpoint}")
                            continue
                        elif response.status_code == 200:
                            # Parse the response
                            soup = BeautifulSoup(response.content, 'html.parser')
                            
                            # Extract report information
                            report = self._parse_address_page_enhanced(soup, address)
                            
                            if report:
                                logger.info(f"Found ChainAbuse report for address: {address}")
                                logger.debug(f"Report details: Category={report.category}, Type={report.abuse_type}, Confidence={report.confidence_score}")
                                return report
                        
                        # Add delay between requests
                        time.sleep(self.delay_between_requests)
                        
                    except requests.exceptions.RequestException as e:
                        logger.warning(f"Request failed for {endpoint}: {str(e)}")
                        continue
                    except Exception as e:
                        logger.warning(f"Unexpected error for {endpoint}: {str(e)}")
                        continue
                
                # If all endpoints failed, wait before retry
                if attempt < self.max_retries - 1:
                    logger.info(f"All endpoints failed, retrying in {self.delay_between_requests * 2} seconds...")
                    time.sleep(self.delay_between_requests * 2)
            
            # If all attempts failed, return None (no real data found)
            logger.info(f"No ChainAbuse data found for address: {address}")
            return None
            
        except Exception as e:
            logger.error(f"Unexpected error searching ChainAbuse: {str(e)}")
            return None
    
    def get_recent_reports(self, limit: int = 50) -> List[ChainAbuseReport]:
        """
        Get recent malicious address reports from ChainAbuse.
        
        Args:
            limit: Maximum number of reports to fetch
            
        Returns:
            List of recent ChainAbuseReport objects
        """
        try:
            logger.info(f"Fetching recent ChainAbuse reports (limit: {limit})")
            
            # Recent reports URL
            reports_url = f"{self.base_url}/reports"
            
            response = self.session.get(reports_url, timeout=self.timeout)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Parse recent reports
            reports = self._parse_recent_reports(soup, limit)
            
            logger.info(f"Found {len(reports)} recent reports")
            return reports
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching recent ChainAbuse reports: {str(e)}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error fetching recent reports: {str(e)}")
            return []
    
    def get_address_details(self, address: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about a specific address.
        
        Args:
            address: Bitcoin address to get details for
            
        Returns:
            Dictionary with detailed address information
        """
        try:
            logger.info(f"Getting detailed information for address: {address}")
            
            # Address detail URL
            detail_url = f"{self.base_url}/address/{address}"
            
            response = self.session.get(detail_url, timeout=self.timeout)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Parse address details
            details = self._parse_address_details(soup, address)
            
            return details
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting details for {address}: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error getting address details: {str(e)}")
            return None
    
    def _parse_search_results(self, soup: BeautifulSoup, address: str) -> List[ChainAbuseReport]:
        """Parse search results page."""
        reports = []
        
        try:
            # Look for report cards/containers
            report_containers = soup.find_all('div', class_=re.compile(r'report|card|item'))
            
            for container in report_containers:
                try:
                    # Extract address
                    addr_elem = container.find('a', href=re.compile(r'/address/'))
                    if not addr_elem:
                        continue
                    
                    reported_address = addr_elem.get_text(strip=True)
                    if reported_address.lower() != address.lower():
                        continue
                    
                    # Extract category with multiple fallback methods
                    category = 'Unknown'
                    
                    # Method 1: Look for category/type/tag spans
                    category_elem = container.find('span', class_=re.compile(r'category|type|tag|abuse-type'))
                    if category_elem:
                        category = category_elem.get_text(strip=True)
                    
                    # Method 2: Look for category divs
                    if category == 'Unknown':
                        category_elem = container.find('div', class_=re.compile(r'category|type|tag'))
                        if category_elem:
                            category = category_elem.get_text(strip=True)
                    
                    # Method 3: Look for any element with category-like text
                    if category == 'Unknown':
                        for elem in container.find_all(['span', 'div', 'p']):
                            text = elem.get_text(strip=True).lower()
                            if any(word in text for word in ['ransomware', 'scam', 'fraud', 'phishing', 'malware', 'virus']):
                                category = elem.get_text(strip=True)
                                break
                    
                    # Method 4: Extract from description if category not found
                    if category == 'Unknown':
                        desc_elem = container.find('p', class_=re.compile(r'description|summary'))
                        if desc_elem:
                            desc_text = desc_elem.get_text(strip=True).lower()
                            if 'ransomware' in desc_text or 'wannacry' in desc_text:
                                category = 'Ransomware'
                            elif 'scam' in desc_text or 'fraud' in desc_text:
                                category = 'Scam/Fraud'
                            elif 'phishing' in desc_text:
                                category = 'Phishing'
                            elif 'malware' in desc_text or 'virus' in desc_text:
                                category = 'Malware'
                    
                    # Extract description
                    desc_elem = container.find('p', class_=re.compile(r'description|summary'))
                    description = desc_elem.get_text(strip=True) if desc_elem else ''
                    
                    # Extract reporter
                    reporter_elem = container.find('span', class_=re.compile(r'reporter|user'))
                    reporter = reporter_elem.get_text(strip=True) if reporter_elem else 'Anonymous'
                    
                    # Extract date
                    date_elem = container.find('time') or container.find('span', class_=re.compile(r'date|time'))
                    reported_at = datetime.now()  # Default to now
                    if date_elem:
                        date_text = date_elem.get_text(strip=True)
                        try:
                            reported_at = datetime.strptime(date_text, '%Y-%m-%d %H:%M:%S')
                        except ValueError:
                            try:
                                reported_at = datetime.strptime(date_text, '%Y-%m-%d')
                            except ValueError:
                                pass
                    
                    # Extract abuse type
                    abuse_type = self._categorize_abuse(category, description)
                    
                    # Calculate confidence score
                    confidence_score = self._calculate_confidence(category, description, reporter)
                    
                    # Create report
                    report = ChainAbuseReport(
                        address=reported_address,
                        category=category,
                        description=description,
                        reporter=reporter,
                        reported_at=reported_at,
                        abuse_type=abuse_type,
                        confidence_score=confidence_score,
                        source_url=f"{self.base_url}/address/{reported_address}",
                        raw_data={'container_html': str(container)}
                    )
                    
                    reports.append(report)
                    
                except Exception as e:
                    logger.warning(f"Error parsing report container: {str(e)}")
                    continue
            
        except Exception as e:
            logger.error(f"Error parsing search results: {str(e)}")
        
        return reports
    
    def _parse_address_page_enhanced(self, soup: BeautifulSoup, address: str) -> Optional[ChainAbuseReport]:
        """Parse address details page to extract report information with enhanced data collection."""
        try:
            # Look for main content area
            content = soup.find('main') or soup.find('div', class_=re.compile(r'content|main'))
            if not content:
                content = soup
            
            # Extract address information
            address_elem = content.find('h1') or content.find('h2') or content.find('span', class_=re.compile(r'address'))
            if address_elem:
                found_address = address_elem.get_text(strip=True)
                if found_address != address:
                    logger.warning(f"Address mismatch: expected {address}, found {found_address}")
            
            # Enhanced category extraction
            category = 'Unknown'
            category_elem = content.find('span', class_=re.compile(r'category|type|abuse-type|tag'))
            if category_elem:
                category = category_elem.get_text(strip=True)
            else:
                # Try alternative selectors
                category_elem = content.find('div', class_=re.compile(r'category|type'))
                if category_elem:
                    category = category_elem.get_text(strip=True)
            
            # Enhanced description extraction
            description = ''
            desc_elem = content.find('p', class_=re.compile(r'description|details|summary')) or content.find('div', class_=re.compile(r'description|details'))
            if desc_elem:
                description = desc_elem.get_text(strip=True)
            else:
                # Try alternative selectors
                desc_elem = content.find('div', class_=re.compile(r'content|text'))
                if desc_elem:
                    description = desc_elem.get_text(strip=True)
            
            # Enhanced reporter extraction
            reporter = 'Anonymous'
            reporter_elem = content.find('span', class_=re.compile(r'reporter|reported-by|user'))
            if reporter_elem:
                reporter = reporter_elem.get_text(strip=True)
            else:
                # Try alternative selectors
                reporter_elem = content.find('div', class_=re.compile(r'reporter|user'))
                if reporter_elem:
                    reporter = reporter_elem.get_text(strip=True)
            
            # Enhanced date extraction
            reported_at = datetime.now()
            date_elem = content.find('time') or content.find('span', class_=re.compile(r'date|reported-at|timestamp'))
            if date_elem:
                date_text = date_elem.get_text(strip=True)
                # Try multiple date formats
                date_formats = [
                    '%Y-%m-%d %H:%M:%S',
                    '%Y-%m-%d',
                    '%m/%d/%Y',
                    '%d/%m/%Y',
                    '%B %d, %Y',
                    '%Y-%m-%dT%H:%M:%S'
                ]
                
                for fmt in date_formats:
                    try:
                        reported_at = datetime.strptime(date_text, fmt)
                        break
                    except ValueError:
                        continue
            
            # Enhanced abuse type categorization
            abuse_type = self._categorize_abuse_enhanced(category, description)
            
            # Enhanced confidence calculation
            confidence_score = self._calculate_confidence_enhanced(category, description, reporter, content)
            
            # If we found a report in ChainAbuse, it's 100% malicious
            if confidence_score > 0:  # Any report found means it's malicious
                confidence_score = 1.0
            
            # Collect additional metadata
            metadata = self._extract_metadata(content)
            
            # Create report with enhanced data
            report = ChainAbuseReport(
                address=address,
                category=category,
                description=description,
                reporter=reporter,
                reported_at=reported_at,
                abuse_type=abuse_type,
                confidence_score=confidence_score,
                source_url=f"{self.base_url}/address/{address}",
                raw_data={
                    'page_html': str(content),
                    'metadata': metadata,
                    'extraction_timestamp': datetime.now().isoformat()
                }
            )
            
            return report
            
        except Exception as e:
            logger.error(f"Error parsing address page: {str(e)}")
            return None
    
    def _parse_recent_reports(self, soup: BeautifulSoup, limit: int) -> List[ChainAbuseReport]:
        """Parse recent reports page."""
        reports = []
        
        try:
            # Look for report items
            report_items = soup.find_all('div', class_=re.compile(r'report-item|report-card'))
            
            for i, item in enumerate(report_items[:limit]):
                try:
                    # Extract address
                    addr_elem = item.find('a', href=re.compile(r'/address/'))
                    if not addr_elem:
                        continue
                    
                    address = addr_elem.get_text(strip=True)
                    
                    # Extract other details (similar to search results)
                    category_elem = item.find('span', class_=re.compile(r'category|type'))
                    category = category_elem.get_text(strip=True) if category_elem else 'Unknown'
                    
                    desc_elem = item.find('p', class_=re.compile(r'description'))
                    description = desc_elem.get_text(strip=True) if desc_elem else ''
                    
                    reporter_elem = item.find('span', class_=re.compile(r'reporter'))
                    reporter = reporter_elem.get_text(strip=True) if reporter_elem else 'Anonymous'
                    
                    date_elem = item.find('time') or item.find('span', class_=re.compile(r'date'))
                    reported_at = datetime.now()
                    if date_elem:
                        date_text = date_elem.get_text(strip=True)
                        try:
                            reported_at = datetime.strptime(date_text, '%Y-%m-%d %H:%M:%S')
                        except ValueError:
                            try:
                                reported_at = datetime.strptime(date_text, '%Y-%m-%d')
                            except ValueError:
                                pass
                    
                    abuse_type = self._categorize_abuse(category, description)
                    confidence_score = self._calculate_confidence(category, description, reporter)
                    
                    report = ChainAbuseReport(
                        address=address,
                        category=category,
                        description=description,
                        reporter=reporter,
                        reported_at=reported_at,
                        abuse_type=abuse_type,
                        confidence_score=confidence_score,
                        source_url=f"{self.base_url}/address/{address}",
                        raw_data={'item_html': str(item)}
                    )
                    
                    reports.append(report)
                    
                except Exception as e:
                    logger.warning(f"Error parsing recent report item: {str(e)}")
                    continue
                
                # Add delay between processing items
                time.sleep(0.1)
            
        except Exception as e:
            logger.error(f"Error parsing recent reports: {str(e)}")
        
        return reports
    
    def _parse_address_details(self, soup: BeautifulSoup, address: str) -> Dict[str, Any]:
        """Parse address detail page."""
        details = {
            'address': address,
            'reports': [],
            'total_reports': 0,
            'first_reported': None,
            'last_reported': None,
            'categories': set(),
            'abuse_types': set()
        }
        
        try:
            # Look for report sections
            report_sections = soup.find_all('div', class_=re.compile(r'report|case'))
            
            for section in report_sections:
                try:
                    # Extract report details
                    category_elem = section.find('span', class_=re.compile(r'category|type'))
                    category = category_elem.get_text(strip=True) if category_elem else 'Unknown'
                    
                    desc_elem = section.find('p', class_=re.compile(r'description|summary'))
                    description = desc_elem.get_text(strip=True) if desc_elem else ''
                    
                    reporter_elem = section.find('span', class_=re.compile(r'reporter|user'))
                    reporter = reporter_elem.get_text(strip=True) if reporter_elem else 'Anonymous'
                    
                    date_elem = section.find('time') or section.find('span', class_=re.compile(r'date|time'))
                    reported_at = datetime.now()
                    if date_elem:
                        date_text = date_elem.get_text(strip=True)
                        try:
                            reported_at = datetime.strptime(date_text, '%Y-%m-%d %H:%M:%S')
                        except ValueError:
                            try:
                                reported_at = datetime.strptime(date_text, '%Y-%m-%d')
                            except ValueError:
                                pass
                    
                    abuse_type = self._categorize_abuse(category, description)
                    confidence_score = self._calculate_confidence(category, description, reporter)
                    
                    report = ChainAbuseReport(
                        address=address,
                        category=category,
                        description=description,
                        reporter=reporter,
                        reported_at=reported_at,
                        abuse_type=abuse_type,
                        confidence_score=confidence_score,
                        source_url=f"{self.base_url}/address/{address}",
                        raw_data={'section_html': str(section)}
                    )
                    
                    details['reports'].append(report)
                    details['categories'].add(category)
                    details['abuse_types'].add(abuse_type)
                    
                except Exception as e:
                    logger.warning(f"Error parsing report section: {str(e)}")
                    continue
            
            # Calculate summary statistics
            details['total_reports'] = len(details['reports'])
            if details['reports']:
                details['first_reported'] = min(r.reported_at for r in details['reports'])
                details['last_reported'] = max(r.reported_at for r in details['reports'])
            
            # Convert sets to lists for JSON serialization
            details['categories'] = list(details['categories'])
            details['abuse_types'] = list(details['abuse_types'])
            
        except Exception as e:
            logger.error(f"Error parsing address details: {str(e)}")
        
        return details
    
    def _categorize_abuse(self, category: str, description: str) -> str:
        """Categorize the type of abuse based on category and description."""
        text = f"{category} {description}".lower()
        
        if any(word in text for word in ['scam', 'fraud', 'fake']):
            return 'scam'
        elif any(word in text for word in ['ransomware', 'ransom']):
            return 'ransomware'
        elif any(word in text for word in ['darknet', 'dark web', 'market']):
            return 'darknet_market'
        elif any(word in text for word in ['mixing', 'mixer', 'tumbler']):
            return 'mixing_service'
        elif any(word in text for word in ['gambling', 'casino']):
            return 'gambling'
        elif any(word in text for word in ['exchange', 'trading']):
            return 'exchange'
        elif any(word in text for word in ['mining', 'pool']):
            return 'mining_pool'
        else:
            return 'other'
    
    def _calculate_confidence(self, category: str, description: str, reporter: str) -> float:
        """Calculate confidence score for a report."""
        confidence = 0.5  # Base confidence
        
        # Boost confidence for verified reporters
        if reporter.lower() in ['verified', 'admin', 'moderator']:
            confidence += 0.3
        
        # Boost confidence for detailed descriptions
        if len(description) > 50:
            confidence += 0.1
        
        # Boost confidence for specific categories
        if category.lower() in ['scam', 'ransomware', 'darknet']:
            confidence += 0.1
        
        return min(confidence, 1.0)
    
    def get_malicious_addresses_batch(self, addresses: List[str]) -> Dict[str, Optional[ChainAbuseReport]]:
        """
        Check multiple addresses for malicious activity.
        
        Args:
            addresses: List of Bitcoin addresses to check
            
        Returns:
            Dictionary mapping addresses to their ChainAbuseReport (if found)
        """
        results = {}
        
        for address in addresses:
            try:
                report = self.search_address(address)
                results[address] = report
                
                # Add delay between requests
                time.sleep(self.delay_between_requests)
                
            except Exception as e:
                logger.error(f"Error checking address {address}: {str(e)}")
                results[address] = None
        
        return results

    def _categorize_abuse_enhanced(self, category: str, description: str) -> str:
        """Enhanced categorization of abuse type based on category and description."""
        text = f"{category} {description}".lower()
        
        # Enhanced keyword matching with weights
        abuse_patterns = {
            'scam': ['scam', 'fraud', 'fake', 'phishing', 'impersonation', 'social engineering'],
            'ransomware': ['ransomware', 'ransom', 'encrypt', 'lock', 'malware'],
            'darknet_market': ['darknet', 'dark web', 'market', 'silk road', 'alphabay', 'hansa'],
            'mixing_service': ['mixing', 'mixer', 'tumbler', 'laundering', 'obfuscation'],
            'theft': ['theft', 'stolen', 'hack', 'breach', 'compromise', 'unauthorized'],
            'terrorism': ['terrorism', 'terrorist', 'extremist', 'funding'],
            'drugs': ['drug', 'narcotic', 'cocaine', 'heroin', 'marijuana'],
            'weapons': ['weapon', 'gun', 'firearm', 'explosive', 'ammunition'],
            'child_exploitation': ['child', 'minor', 'exploitation', 'abuse', 'pornography'],
            'counterfeit': ['counterfeit', 'fake', 'replica', 'knockoff']
        }
        
        scores = {}
        for abuse_type, keywords in abuse_patterns.items():
            score = sum(1 for keyword in keywords if keyword in text)
            if score > 0:
                scores[abuse_type] = score
        
        if scores:
            # Return the abuse type with highest score
            return max(scores, key=scores.get)
        
        return 'other'

    def _calculate_confidence_enhanced(self, category: str, description: str, reporter: str, content: BeautifulSoup) -> float:
        """Enhanced confidence calculation with more factors."""
        confidence = 0.5  # Base confidence
        
        # Reporter credibility
        reporter_lower = reporter.lower()
        if reporter_lower in ['verified', 'admin', 'moderator', 'trusted']:
            confidence += 0.3
        elif reporter_lower in ['anonymous', 'unknown']:
            confidence -= 0.1
        
        # Description quality
        if len(description) > 100:
            confidence += 0.2
        elif len(description) > 50:
            confidence += 0.1
        elif len(description) < 10:
            confidence -= 0.1
        
        # Category specificity
        specific_categories = ['scam', 'ransomware', 'darknet', 'theft', 'terrorism']
        if category.lower() in specific_categories:
            confidence += 0.15
        
        # Content structure analysis
        if content.find('div', class_=re.compile(r'evidence|proof|screenshot')):
            confidence += 0.1
        
        if content.find('div', class_=re.compile(r'verified|confirmed')):
            confidence += 0.1
        
        # Date recency (newer reports might be more relevant)
        # This would require date parsing, simplified for now
        
        return min(max(confidence, 0.0), 1.0)

    def _extract_metadata(self, content: BeautifulSoup) -> Dict[str, Any]:
        """Extract additional metadata from the page content."""
        metadata = {
            'has_evidence': False,
            'has_screenshots': False,
            'has_links': False,
            'verification_status': 'unknown',
            'page_elements': []
        }
        
        # Check for evidence elements
        if content.find('div', class_=re.compile(r'evidence|proof|screenshot|image')):
            metadata['has_evidence'] = True
            metadata['has_screenshots'] = True
        
        # Check for external links
        links = content.find_all('a', href=True)
        if links:
            metadata['has_links'] = True
            metadata['external_links'] = [link['href'] for link in links if link['href'].startswith('http')]
        
        # Check verification status
        if content.find('div', class_=re.compile(r'verified|confirmed|trusted')):
            metadata['verification_status'] = 'verified'
        elif content.find('div', class_=re.compile(r'unverified|pending')):
            metadata['verification_status'] = 'unverified'
        
        # Extract page elements for analysis
        elements = content.find_all(['div', 'span', 'p'], class_=True)
        metadata['page_elements'] = [elem.get('class', []) for elem in elements[:10]]  # Limit to first 10
        
        return metadata

    def _search_alternative_sources(self, address: str) -> Optional[ChainAbuseReport]:
        """
        Search alternative sources when primary ChainAbuse search fails.
        
        Args:
            address: Bitcoin address to search for
            
        Returns:
            ChainAbuseReport if found in alternative sources, None otherwise
        """
        try:
            logger.info(f"Searching alternative sources for address: {address}")
            
            # Check against known malicious address databases
            known_malicious_addresses = self.config.KNOWN_MALICIOUS_ADDRESSES
            
            if address in known_malicious_addresses:
                data = known_malicious_addresses[address]
                logger.info(f"Found address {address} in alternative malicious database")
                
                return ChainAbuseReport(
                    address=address,
                    category=data['category'],
                    description=data['description'],
                    reporter=data['reporter'],
                    reported_at=datetime.now(),
                    abuse_type=data['abuse_type'],
                    confidence_score=data['confidence_score'],
                    source_url=f"{self.base_url}/address/{address}",
                    raw_data={'source': 'alternative_database', 'timestamp': datetime.now().isoformat()}
                )
            
            # Check for suspicious patterns in the address
            suspicious_patterns = self._analyze_address_patterns(address)
            if suspicious_patterns['is_suspicious']:
                logger.info(f"Address {address} shows suspicious patterns")
                
                return ChainAbuseReport(
                    address=address,
                    category='Suspicious Activity',
                    description=f"Suspicious address patterns detected: {', '.join(suspicious_patterns['patterns'])}",
                    reporter='Pattern Analysis',
                    reported_at=datetime.now(),
                    abuse_type='suspicious',
                    confidence_score=suspicious_patterns['confidence'],
                    source_url=f"{self.base_url}/address/{address}",
                    raw_data={'source': 'pattern_analysis', 'patterns': suspicious_patterns['patterns']}
                )
            
            logger.info(f"No alternative sources found for address: {address}")
            return None
            
        except Exception as e:
            logger.error(f"Error searching alternative sources for {address}: {str(e)}")
            return None
    
    def _analyze_address_patterns(self, address: str) -> Dict[str, Any]:
        """
        Analyze address patterns for suspicious indicators.
        
        Args:
            address: Bitcoin address to analyze
            
        Returns:
            Dictionary with pattern analysis results
        """
        try:
            patterns = []
            confidence = 0.0
            
            # Check for very short addresses (potential vanity addresses used for scams)
            if len(address) < self.config.SUSPICIOUS_PATTERNS['short_address_threshold']:
                patterns.append('unusually_short')
                confidence += 0.3
            
            # Check for repeated characters (potential vanity addresses)
            char_counts = {}
            for char in address:
                char_counts[char] = char_counts.get(char, 0) + 1
            
            max_repeat = max(char_counts.values())
            threshold = len(address) * self.config.SUSPICIOUS_PATTERNS['repeated_char_threshold']
            if max_repeat > threshold:
                patterns.append('repeated_characters')
                confidence += 0.4
            
            # Check for common scam patterns
            scam_patterns = self.config.SUSPICIOUS_PATTERNS['scam_patterns']
            for pattern in scam_patterns:
                if pattern in address.lower():
                    patterns.append('suspicious_pattern')
                    confidence += 0.5
            
            # Check for sequential patterns
            sequential_patterns = self.config.SUSPICIOUS_PATTERNS['sequential_patterns']
            if any(seq in address for seq in sequential_patterns):
                patterns.append('sequential_pattern')
                confidence += 0.3
            
            # Check for palindrome-like patterns
            if len(address) > 10:
                first_half = address[:len(address)//2]
                second_half = address[len(address)//2:]
                if first_half == second_half[::-1]:
                    patterns.append('palindrome_pattern')
                    confidence += 0.4
            
            is_suspicious = confidence > self.config.SUSPICIOUS_PATTERNS['suspicious_confidence_threshold']
            
            return {
                'is_suspicious': is_suspicious,
                'patterns': patterns,
                'confidence': min(confidence, 0.8)  # Cap at 0.8 for pattern analysis
            }
            
        except Exception as e:
            logger.error(f"Error analyzing address patterns for {address}: {str(e)}")
            return {'is_suspicious': False, 'patterns': [], 'confidence': 0.0}
    
    def search_addresses_batch(self, addresses: List[str]) -> List[Optional[ChainAbuseReport]]:
        """
        Search for multiple addresses in batch.
        
        Args:
            addresses: List of Bitcoin addresses to search for
            
        Returns:
            List of ChainAbuseReport objects (None for addresses not found)
        """
        results = []
        
        for address in addresses:
            try:
                result = self.search_address(address)
                results.append(result)
                
                # Add delay between requests to be respectful
                if self.delay_between_requests > 0:
                    time.sleep(self.delay_between_requests)
                    
            except Exception as e:
                logger.error(f"Error searching address {address}: {e}")
                results.append(None)
        
        return results

# Global scraper instance
chainabuse_scraper = ChainAbuseScraper()
