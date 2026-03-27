"""
Threat Intelligence Configuration

This module provides configuration settings for external threat intelligence APIs
used in cryptocurrency address analysis.
"""

# Default threat intelligence configuration
DEFAULT_THREAT_INTEL_CONFIG = {
    # BTC Black DNSBL settings
    "enable_btcblack": True,
    "btcblack_timeout": 10,
    
    # ChainAbuse Database settings
    "enable_chainabuse": True,
    "chainabuse_timeout": 10,
    
    # Cropty Blacklist settings
    "enable_cropty": True,
    "cropty_timeout": 10,
    
    # BitcoinWhosWho settings
    "enable_bitcoinwhoswho": True,
    "bitcoinwhoswho_timeout": 10,
    "bitcoinwhoswho_api_key": None,
    
    # General settings
    "timeout": 10,
    "retry_attempts": 2,
    "enable_logging": True,
    "log_level": "INFO"
}

# Example configuration with API keys
EXAMPLE_THREAT_INTEL_CONFIG = {
    # BTC Black DNSBL settings
    "enable_btcblack": True,
    "btcblack_timeout": 10,
    
    # ChainAbuse Database settings
    "enable_chainabuse": True,
    "chainabuse_timeout": 10,
    
    # Cropty Blacklist settings
    "enable_cropty": True,
    "cropty_timeout": 10,
    
    # BitcoinWhosWho settings
    "enable_bitcoinwhoswho": True,
    "bitcoinwhoswho_timeout": 10,
    "bitcoinwhoswho_api_key": "your_api_key_here",
    
    # General settings
    "timeout": 10,
    "retry_attempts": 2,
    "enable_logging": True,
    "log_level": "INFO"
}

# Production configuration template
PRODUCTION_THREAT_INTEL_CONFIG = {
    # BTC Black DNSBL settings
    "enable_btcblack": True,
    "btcblack_timeout": 5,
    
    # ChainAbuse Database settings
    "enable_chainabuse": True,
    "chainabuse_timeout": 5,
    
    # Cropty Blacklist settings
    "enable_cropty": True,
    "cropty_timeout": 5,
    
    # BitcoinWhosWho settings
    "enable_bitcoinwhoswho": True,
    "bitcoinwhoswho_timeout": 5,
    "bitcoinwhoswho_api_key": None,  # Load from environment
    
    # General settings
    "timeout": 5,
    "retry_attempts": 3,
    "enable_logging": True,
    "log_level": "WARNING"
}

def get_threat_intel_config(environment="development"):
    """
    Get threat intelligence configuration based on environment.
    
    Args:
        environment: Environment name ("development", "production", "testing")
        
    Returns:
        Dictionary with threat intelligence configuration
    """
    import os
    
    if environment == "production":
        config = PRODUCTION_THREAT_INTEL_CONFIG.copy()
        # Load API keys from environment variables
        config["bitcoinwhoswho_api_key"] = os.getenv("BITCOINWHOSWHO_API_KEY")
    elif environment == "testing":
        config = DEFAULT_THREAT_INTEL_CONFIG.copy()
        # Disable external APIs for testing
        config["enable_btcblack"] = False
        config["enable_chainabuse"] = False
        config["enable_cropty"] = False
        config["enable_bitcoinwhoswho"] = False
    else:  # development
        config = DEFAULT_THREAT_INTEL_CONFIG.copy()
    
    return config

def validate_threat_intel_config(config):
    """
    Validate threat intelligence configuration.
    
    Args:
        config: Configuration dictionary to validate
        
    Returns:
        Tuple of (is_valid, error_messages)
    """
    errors = []
    
    # Check required fields
    required_fields = ["timeout", "retry_attempts"]
    for field in required_fields:
        if field not in config:
            errors.append(f"Missing required field: {field}")
    
    # Check timeout values
    if config.get("timeout", 0) <= 0:
        errors.append("Timeout must be positive")
    
    if config.get("retry_attempts", 0) < 0:
        errors.append("Retry attempts must be non-negative")
    
    # Check ChainAbuse scraper availability if enabled
    if config.get("enable_chainabuse", False):
        # ChainAbuse doesn't require API key, just scraper availability
        pass
    
    # Check boolean fields
    boolean_fields = ["enable_btcblack", "enable_chainabuse", "enable_cropty", "enable_bitcoinwhoswho", "enable_logging"]
    for field in boolean_fields:
        if field in config and not isinstance(config[field], bool):
            errors.append(f"Field {field} must be boolean")
    
    return len(errors) == 0, errors
