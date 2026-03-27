"""
Threat Intelligence Integration Module for ChainBreak

This module integrates the crypto threat intelligence package with ChainBreak
to provide illicit address detection capabilities.
"""

import logging
import sys
import os
from typing import Dict, Any, Optional, List
from pathlib import Path

# Path to crypto threat intel package
threat_intel_path = Path(__file__).resolve().parent.parent / "crypto_threat_intel_package"

# Add package paths
sys.path.append(str(threat_intel_path))


try:
    from threat_intel_client import ThreatIntelClient
    from scraper_config import ScraperConfig
    THREAT_INTEL_AVAILABLE = True
except ImportError as e:
    logging.warning(f"Threat intelligence package not available: {e}")
    THREAT_INTEL_AVAILABLE = False

logger = logging.getLogger(__name__)


class ThreatIntelligenceManager:
    """
    Manager class for threat intelligence integration with ChainBreak.
    
    This class provides a unified interface for checking addresses against
    multiple threat intelligence sources and integrating results with
    ChainBreak's analysis pipeline.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the threat intelligence manager.
        
        Args:
            config: Optional configuration dictionary. If not provided,
                   uses default development configuration.
        """
        self.config = config or self._get_default_config()
        self.threat_intel_client = None
        self.enabled = False
        
        if THREAT_INTEL_AVAILABLE:
            try:
                # Initialize threat intelligence client with ScraperConfig
                scraper_config = ScraperConfig()
                self.threat_intel_client = ThreatIntelClient(scraper_config)
                self.enabled = True
                logger.info("Threat intelligence manager initialized successfully")
                
            except Exception as e:
                logger.error(f"Failed to initialize threat intelligence: {e}")
                self.enabled = False
        else:
            logger.warning("Threat intelligence package not available")
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Get default threat intelligence configuration."""
        return {
            "enable_btcblack": True,
            "enable_chainabuse": True,
            "enable_cropty": True,
            "enable_bitcoinwhoswho": True,
            "timeout": 15,
            "retry_attempts": 3
        }
    
    def is_available(self) -> bool:
        """Check if threat intelligence is available and enabled."""
        return self.enabled and self.threat_intel_client is not None
    
    def check_address(self, address: str) -> Dict[str, Any]:
        """
        Check an address against all configured threat intelligence sources.
        
        Args:
            address: Bitcoin address to check
            
        Returns:
            Dictionary with threat intelligence results
        """
        if not self.is_available():
            return {
                "available": False,
                "error": "Threat intelligence not available",
                "address": address,
                "blacklisted": False,
                "confidence": 0.0
            }
        
        try:
            logger.info(f"Checking address {address} against threat intelligence sources")
            
            # Check all sources
            results = self.threat_intel_client.check_all_sources(address)
            
            # Extract key information
            blacklisted = results.get("final_blacklisted", False)
            confidence = results.get("overall_confidence", 0.0)
            blacklisted_sources = results.get("blacklisted_sources", [])
            
            # Determine risk level based on results
            risk_level = self._determine_risk_level(blacklisted, confidence, blacklisted_sources)
            
            threat_intel_result = {
                "available": True,
                "address": address,
                "blacklisted": blacklisted,
                "confidence": confidence,
                "risk_level": risk_level,
                "blacklisted_sources": blacklisted_sources,
                "sources_checked": results.get("sources_checked", []),
                "illicit_activity_analysis": results.get("illicit_activity_analysis"),
                "detailed_results": results,
                "timestamp": results.get("timestamp")
            }
            
            logger.info(f"Threat intelligence check completed for {address}: "
                       f"{'BLACKLISTED' if blacklisted else 'CLEAN'} "
                       f"(confidence: {confidence:.2f}, sources: {blacklisted_sources})")
            
            return threat_intel_result
            
        except Exception as e:
            logger.error(f"Error checking address {address} against threat intelligence: {e}")
            return {
                "available": True,
                "address": address,
                "blacklisted": False,
                "confidence": 0.0,
                "error": str(e),
                "risk_level": "unknown"
            }
    
    def check_addresses_batch(self, addresses: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Check multiple addresses against threat intelligence sources.
        
        Args:
            addresses: List of Bitcoin addresses to check
            
        Returns:
            Dictionary mapping addresses to their threat intelligence results
        """
        if not self.is_available():
            return {
                addr: {
                    "available": False,
                    "error": "Threat intelligence not available",
                    "blacklisted": False,
                    "confidence": 0.0
                }
                for addr in addresses
            }
        
        results = {}
        for address in addresses:
            results[address] = self.check_address(address)
        
        return results
    
    def _determine_risk_level(self, blacklisted: bool, confidence: float, 
                            blacklisted_sources: List[str]) -> str:
        """
        Determine risk level based on threat intelligence results.
        
        Args:
            blacklisted: Whether address is blacklisted
            confidence: Confidence score
            blacklisted_sources: List of sources that blacklisted the address
            
        Returns:
            Risk level string
        """
        if not blacklisted:
            return "low"
        
        # If blacklisted by multiple sources, it's critical
        if len(blacklisted_sources) >= 2:
            return "critical"
        
        # If high confidence, it's high risk
        if confidence >= 0.8:
            return "high"
        
        # If medium confidence, it's medium risk
        if confidence >= 0.5:
            return "medium"
        
        # Otherwise low risk
        return "low"
    
    def get_source_status(self) -> Dict[str, Any]:
        """
        Get status of all threat intelligence sources.
        
        Returns:
            Dictionary with source status information
        """
        if not self.is_available():
            return {
                "available": False,
                "error": "Threat intelligence not available"
            }
        
        try:
            status = self.threat_intel_client.get_source_status()
            return {
                "available": True,
                "sources": status,
                "config": self.config
            }
        except Exception as e:
            logger.error(f"Error getting source status: {e}")
            return {
                "available": True,
                "error": str(e)
            }
    
    def enhance_risk_score(self, address: str, base_risk_score: float, 
                          base_risk_level: str) -> Dict[str, Any]:
        """
        Enhance risk score with threat intelligence data.
        
        Args:
            address: Bitcoin address
            base_risk_score: Base risk score from ChainBreak analysis
            base_risk_level: Base risk level from ChainBreak analysis
            
        Returns:
            Enhanced risk assessment
        """
        threat_intel_result = self.check_address(address)
        
        if not threat_intel_result.get("available", False):
            return {
                "enhanced": False,
                "base_risk_score": base_risk_score,
                "base_risk_level": base_risk_level,
                "final_risk_score": base_risk_score,
                "final_risk_level": base_risk_level,
                "threat_intel_available": False
            }
        
        # If address is blacklisted by threat intelligence, force critical risk
        if threat_intel_result.get("blacklisted", False):
            threat_confidence = threat_intel_result.get("confidence", 0.0)
            
            # Use threat intelligence confidence as the risk score
            enhanced_risk_score = max(base_risk_score, threat_confidence)
            
            # Force critical risk level for blacklisted addresses
            enhanced_risk_level = "critical"
            
            logger.info(f"Address {address} blacklisted by threat intelligence - "
                       f"forcing CRITICAL risk level (confidence: {threat_confidence:.2f})")
            
            return {
                "enhanced": True,
                "base_risk_score": base_risk_score,
                "base_risk_level": base_risk_level,
                "final_risk_score": enhanced_risk_score,
                "final_risk_level": enhanced_risk_level,
                "threat_intel_available": True,
                "threat_intel_blacklisted": True,
                "threat_intel_confidence": threat_confidence,
                "threat_intel_sources": threat_intel_result.get("blacklisted_sources", []),
                "enhancement_reason": "Address blacklisted by threat intelligence"
            }
        
        # If not blacklisted, use base risk score but note threat intel availability
        return {
            "enhanced": True,
            "base_risk_score": base_risk_score,
            "base_risk_level": base_risk_level,
            "final_risk_score": base_risk_score,
            "final_risk_level": base_risk_level,
            "threat_intel_available": True,
            "threat_intel_blacklisted": False,
            "threat_intel_confidence": threat_intel_result.get("confidence", 0.0),
            "enhancement_reason": "Address clean according to threat intelligence"
        }
    
    def get_illicit_addresses_in_graph(self, graph_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Check all addresses in a graph for illicit activity.
        
        Args:
            graph_data: Graph data containing nodes and edges
            
        Returns:
            Dictionary with illicit address analysis
        """
        if not self.is_available():
            return {
                "available": False,
                "error": "Threat intelligence not available",
                "illicit_addresses": [],
                "total_addresses": 0
            }
        
        try:
            # Extract addresses from graph nodes
            addresses = []
            if "nodes" in graph_data:
                for node in graph_data["nodes"]:
                    if "id" in node and isinstance(node["id"], str):
                        # Check if it looks like a Bitcoin address
                        if len(node["id"]) >= 26 and len(node["id"]) <= 35:
                            addresses.append(node["id"])
            
            if not addresses:
                return {
                    "available": True,
                    "illicit_addresses": [],
                    "total_addresses": 0,
                    "message": "No addresses found in graph"
                }
            
            logger.info(f"Checking {len(addresses)} addresses for illicit activity")
            
            # Check all addresses
            threat_results = self.check_addresses_batch(addresses)
            
            # Find illicit addresses
            illicit_addresses = []
            for addr, result in threat_results.items():
                if result.get("blacklisted", False):
                    illicit_addresses.append({
                        "address": addr,
                        "confidence": result.get("confidence", 0.0),
                        "risk_level": result.get("risk_level", "unknown"),
                        "sources": result.get("blacklisted_sources", []),
                        "illicit_activity_analysis": result.get("illicit_activity_analysis"),
                        "details": result.get("detailed_results", {})
                    })
            
            logger.info(f"Found {len(illicit_addresses)} illicit addresses out of {len(addresses)} total")
            
            return {
                "available": True,
                "illicit_addresses": illicit_addresses,
                "total_addresses": len(addresses),
                "illicit_percentage": (len(illicit_addresses) / len(addresses)) * 100 if addresses else 0,
                "threat_results": threat_results
            }
            
        except Exception as e:
            logger.error(f"Error checking addresses in graph: {e}")
            return {
                "available": True,
                "error": str(e),
                "illicit_addresses": [],
                "total_addresses": 0
            }


# Global threat intelligence manager instance
_threat_intel_manager = None


def get_threat_intel_manager(config: Optional[Dict[str, Any]] = None) -> ThreatIntelligenceManager:
    """
    Get the global threat intelligence manager instance.
    
    Args:
        config: Optional configuration dictionary
        
    Returns:
        ThreatIntelligenceManager instance
    """
    global _threat_intel_manager
    
    if _threat_intel_manager is None:
        _threat_intel_manager = ThreatIntelligenceManager(config)
    
    return _threat_intel_manager


def check_address_threat_intel(address: str) -> Dict[str, Any]:
    """
    Convenience function to check an address against threat intelligence.
    
    Args:
        address: Bitcoin address to check
        
    Returns:
        Threat intelligence results
    """
    manager = get_threat_intel_manager()
    return manager.check_address(address)


def enhance_risk_with_threat_intel(address: str, base_risk_score: float, 
                                  base_risk_level: str) -> Dict[str, Any]:
    """
    Convenience function to enhance risk score with threat intelligence.
    
    Args:
        address: Bitcoin address
        base_risk_score: Base risk score
        base_risk_level: Base risk level
        
    Returns:
        Enhanced risk assessment
    """
    manager = get_threat_intel_manager()
    return manager.enhance_risk_score(address, base_risk_score, base_risk_level)
