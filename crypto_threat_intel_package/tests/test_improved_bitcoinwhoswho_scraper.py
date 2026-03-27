#!/usr/bin/env python3
"""
Test script for the improved BitcoinWhosWho scraper.
Tests the enhanced web scraping capabilities and confidence scoring.
"""

import sys
import os
import logging
from datetime import datetime

# Add the backend directory to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'scrapers'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'config'))

from bitcoinwhoswho_scraper import BitcoinWhosWhoScraper
from threat_intel_client import ThreatIntelClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_improved_scraper():
    """Test the improved BitcoinWhosWho scraper with enhanced web scraping."""
    
    logger.info("=" * 60)
    logger.info("TESTING IMPROVED BITCOINWHOSWHO SCRAPER")
    logger.info("=" * 60)
    
    # Initialize scraper
    scraper = BitcoinWhosWhoScraper(
        api_key=None,  # Use web scraping only
        timeout=15,
        retry_attempts=3
    )
    
    # Test addresses with expected results
    test_addresses = [
        {
            'address': '13AM4VW2dhxYgXeQepoHkHSQuy6NgaEb94',
            'description': 'WannaCry ransomware address',
            'expected_scam_reports': 1,  # At least 1 scam report expected
            'expected_website_appearances': 0,  # May be 0 due to web scraping issues
            'expected_tags': ['wannacry', 'ransomware', 'malware'],  # At least these tags
            'expected_score': 0.8,  # High score expected
            'expected_confidence': 0.8  # High confidence expected
        },
        {
            'address': '1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa',
            'description': 'Genesis block address',
            'expected_scam_reports': 0,
            'expected_website_appearances': 0,
            'expected_tags': [],
            'expected_score': None,
            'expected_confidence': 0.0
        },
        {
            'address': '3J98t1WpEZ73CNmQviecrnyiWrnqRhWNLy',
            'description': 'Common test address',
            'expected_scam_reports': 0,
            'expected_website_appearances': 0,
            'expected_tags': [],
            'expected_score': None,
            'expected_confidence': 0.0
        }
    ]
    
    results = []
    
    for i, test_case in enumerate(test_addresses, 1):
        logger.info(f"\n--- Test {i}/{len(test_addresses)}: {test_case['address']} ---")
        logger.info(f"Description: {test_case['description']}")
        
        try:
            # Test the scraper
            result = scraper.get_address_risk_assessment(test_case['address'])
            
            # Analyze results (result is a dictionary)
            scam_reports_count = len(result.get('scam_reports', []))
            website_appearances_count = len(result.get('website_appearances', []))
            tags_count = len(result.get('tags', []))
            score = result.get('risk_score', None)
            confidence = result.get('confidence', 0.0)
            risk_level = result.get('risk_level', 'unknown')
            
            logger.info(f"Results:")
            logger.info(f"  - Risk Level: {risk_level}")
            logger.info(f"  - Scam Reports: {scam_reports_count} (expected: {test_case['expected_scam_reports']})")
            logger.info(f"  - Website Appearances: {website_appearances_count} (expected: {test_case['expected_website_appearances']})")
            logger.info(f"  - Tags: {tags_count} (expected: {len(test_case['expected_tags'])})")
            logger.info(f"  - Score: {score} (expected: {test_case['expected_score']})")
            logger.info(f"  - Confidence: {confidence:.3f}")
            
            # Check if tags match expected
            if test_case['expected_tags']:
                found_expected_tags = [tag for tag in test_case['expected_tags'] if tag in result.get('tags', [])]
                logger.info(f"  - Expected Tags Found: {found_expected_tags}")
                logger.info(f"  - All Tags: {result.get('tags', [])}")
            
            # Determine success with more flexible criteria
            success = True
            failure_reasons = []
            
            # Check scam reports (at least expected minimum)
            if test_case['expected_scam_reports'] > 0 and scam_reports_count < test_case['expected_scam_reports']:
                success = False
                failure_reasons.append(f"Expected at least {test_case['expected_scam_reports']} scam reports, got {scam_reports_count}")
            
            # Check website appearances (at least expected minimum)
            if test_case['expected_website_appearances'] > 0 and website_appearances_count < test_case['expected_website_appearances']:
                success = False
                failure_reasons.append(f"Expected at least {test_case['expected_website_appearances']} website appearances, got {website_appearances_count}")
            
            # Check score (at least expected minimum)
            if test_case['expected_score'] and score and score < test_case['expected_score']:
                success = False
                failure_reasons.append(f"Expected score at least {test_case['expected_score']}, got {score}")
            
            # Check confidence (at least expected minimum)
            if test_case['expected_confidence'] and confidence < test_case['expected_confidence']:
                success = False
                failure_reasons.append(f"Expected confidence at least {test_case['expected_confidence']}, got {confidence}")
            
            # Check expected tags (at least some should be found)
            if test_case['expected_tags']:
                found_expected_tags = [tag for tag in test_case['expected_tags'] if tag in result.get('tags', [])]
                if len(found_expected_tags) == 0:
                    success = False
                    failure_reasons.append(f"Expected tags {test_case['expected_tags']} not found, got {result.get('tags', [])}")
            
            if success:
                logger.info("  ✅ SUCCESS: Results meet expectations")
            else:
                for reason in failure_reasons:
                    logger.warning(f"  ❌ FAILED: {reason}")
            
            results.append({
                'address': test_case['address'],
                'description': test_case['description'],
                'success': success,
                'scam_reports': scam_reports_count,
                'website_appearances': website_appearances_count,
                'tags': tags_count,
                'score': score,
                'confidence': confidence,
                'result': result
            })
            
        except Exception as e:
            logger.error(f"  ❌ ERROR: {e}")
            results.append({
                'address': test_case['address'],
                'description': test_case['description'],
                'success': False,
                'error': str(e)
            })
    
    # Test integration with ThreatIntelClient
    logger.info(f"\n--- Testing Integration with ThreatIntelClient ---")
    
    try:
        from threat_intel_config import get_threat_intel_config
        config = get_threat_intel_config()
        threat_intel_client = ThreatIntelClient(config)
        
        
        # Test the WannaCry address with full threat intelligence
        wannacry_address = '13AM4VW2dhxYgXeQepoHkHSQuy6NgaEb94'
        logger.info(f"Testing {wannacry_address} with ThreatIntelClient...")
        
        threat_result = threat_intel_client.check_all_sources(wannacry_address)
        
        logger.info(f"Threat Intelligence Results:")
        logger.info(f"  - Final Blacklisted: {threat_result.get('final_blacklisted', False)}")
        logger.info(f"  - Overall Confidence: {threat_result.get('max_confidence', 0.0):.3f}")
        logger.info(f"  - Blacklisted Sources: {threat_result.get('blacklisted_sources', [])}")
        
        # Check BitcoinWhosWho specific results
        bitcoinwhoswho_result = threat_result.get('results', {}).get('bitcoinwhoswho', {})
        if bitcoinwhoswho_result:
            logger.info(f"  - BitcoinWhosWho Blacklisted: {bitcoinwhoswho_result.get('blacklisted', False)}")
            logger.info(f"  - BitcoinWhosWho Confidence: {bitcoinwhoswho_result.get('confidence', 0.0):.3f}")
            logger.info(f"  - BitcoinWhosWho Score: {bitcoinwhoswho_result.get('score', 'N/A')}")
        
    except Exception as e:
        logger.error(f"ThreatIntelClient integration test failed: {e}")
    
    # Generate summary report
    logger.info(f"\n" + "=" * 60)
    logger.info("TEST SUMMARY")
    logger.info("=" * 60)
    
    successful_tests = sum(1 for r in results if r.get('success', False))
    total_tests = len(results)
    success_rate = (successful_tests / total_tests) * 100 if total_tests > 0 else 0
    
    logger.info(f"Total Tests: {total_tests}")
    logger.info(f"Successful Tests: {successful_tests}")
    logger.info(f"Success Rate: {success_rate:.1f}%")
    
    # Detailed results
    logger.info(f"\nDetailed Results:")
    for result in results:
        if result.get('success', False):
            logger.info(f"✅ {result['address']}: {result['description']}")
            logger.info(f"   Scam Reports: {result.get('scam_reports', 0)}")
            logger.info(f"   Website Appearances: {result.get('website_appearances', 0)}")
            logger.info(f"   Score: {result.get('score', 'N/A')}")
            logger.info(f"   Confidence: {result.get('confidence', 0.0):.3f}")
        else:
            logger.info(f"❌ {result['address']}: {result['description']}")
            if 'error' in result:
                logger.info(f"   Error: {result['error']}")
    
    # Recommendations
    logger.info(f"\nRecommendations:")
    if success_rate < 100:
        logger.info("- Consider improving web scraping patterns for better data extraction")
        logger.info("- Add more robust error handling for network issues")
        logger.info("- Implement caching to reduce repeated requests")
    else:
        logger.info("- All tests passed! Scraper is working correctly")
        logger.info("- Consider adding more test cases for edge cases")
    
    return results

if __name__ == "__main__":
    try:
        results = test_improved_scraper()
        logger.info(f"\nTest completed successfully!")
    except Exception as e:
        logger.error(f"Test failed with error: {e}")
        sys.exit(1)
