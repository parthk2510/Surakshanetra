import os
import json
import logging
import time
import requests
import re
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, field
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
from functools import lru_cache
import hashlib
from datetime import datetime

logger = logging.getLogger(__name__)

BLOCKCHAIN_BASE = "https://blockchain.info"
BLOCKCHAIN_CHARTS_BASE = "https://api.blockchain.info"  # Charts API uses api subdomain
# Unified data directory - use data/graph (consistent with actual structure)
DATA_DIR = Path("data/graph")
DATA_DIR.mkdir(parents=True, exist_ok=True)

logger.info(f"BlockchainComFetcher using data directory: {DATA_DIR.resolve()}")


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class GraphNode:
    """Represents a node in the transaction graph"""
    id: str
    label: str
    type: str


@dataclass
class GraphEdge:
    """Represents an edge in the transaction graph"""
    id: str
    source: str
    target: str
    type: str
    value: int


@dataclass
class GraphMeta:
    """Metadata for the transaction graph"""
    address: str
    tx_count: int
    node_count: int
    edge_count: int


@dataclass
class GraphData:
    """Complete graph data structure"""
    nodes: List[GraphNode]
    edges: List[GraphEdge]
    meta: GraphMeta


@dataclass
class AddressInfo:
    """Comprehensive address information"""
    address: str
    hash160: str
    n_tx: int
    n_unredeemed: int
    total_received: int
    total_sent: int
    final_balance: int
    transactions: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class TransactionInfo:
    """Comprehensive transaction information"""
    hash: str
    ver: int
    vin_sz: int
    vout_sz: int
    size: int
    weight: int
    fee: int
    relayed_by: str
    lock_time: int
    tx_index: int
    double_spend: bool
    time: int
    block_index: Optional[int]
    block_height: Optional[int]
    inputs: List[Dict[str, Any]] = field(default_factory=list)
    outputs: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class BlockInfo:
    """Comprehensive block information"""
    hash: str
    ver: int
    prev_block: str
    mrkl_root: str
    time: int
    bits: int
    nonce: int
    n_tx: int
    size: int
    block_index: int
    main_chain: bool
    height: int
    received_time: int
    relayed_by: str
    transactions: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class UnspentOutput:
    """Unspent transaction output"""
    tx_hash: str
    tx_hash_big_endian: str
    tx_index: int
    tx_output_n: int
    script: str
    value: int
    value_hex: str
    confirmations: int
    tx_age: Optional[int] = None


@dataclass
class LatestBlock:
    """Latest block information"""
    hash: str
    time: int
    block_index: int
    height: int
    tx_indexes: List[int] = field(default_factory=list)


# ============================================================================
# EXCEPTIONS
# ============================================================================

class BlockchainAPIError(Exception):
    """Base exception for blockchain API errors"""
    pass


class RateLimitError(BlockchainAPIError):
    """Raised when API rate limit is exceeded"""
    pass


class InvalidAddressError(BlockchainAPIError):
    """Raised when an invalid address is provided"""
    pass


class TransactionNotFoundError(BlockchainAPIError):
    """Raised when a transaction is not found"""
    pass


class BlockNotFoundError(BlockchainAPIError):
    """Raised when a block is not found"""
    pass


class InvalidParameterError(BlockchainAPIError):
    """Raised when an invalid parameter is provided"""
    pass


# ============================================================================
# CONFIGURATION
# ============================================================================

@dataclass
class FetcherConfig:
    """Configuration for BlockchainComFetcher"""
    rate_limit_s: float = 0.2
    timeout: int = 20
    max_retries: int = 3
    backoff_factor: float = 0.3
    cache_enabled: bool = True
    cache_ttl: int = 300  # 5 minutes
    max_cache_size: int = 1000
    data_dir: Optional[Path] = None


# ============================================================================
# MAIN FETCHER CLASS
# ============================================================================

class BlockchainComFetcher:
    """
    Comprehensive Blockchain.info API Client
    
    Implements all endpoints from the Blockchain Data API:
    - Single Address (/rawaddr)
    - Multi Address (/multiaddr)
    - Balance (/balance)
    - Unspent Outputs (/unspent)
    - Latest Block (/latestblock)
    - Block by Hash (/rawblock)
    - Block by Height (/block-height)
    - Transaction (/rawtx)
    - Unconfirmed Transactions (/unconfirmed-transactions)
    - Blocks by Day/Pool (/blocks)
    - Charts (/charts)
    """
    
    def __init__(
        self,
        config: Optional[FetcherConfig] = None,
        session: Optional[requests.Session] = None
    ):
        self.config = config or FetcherConfig()
        self.session = session or self._create_session(
            self.config.max_retries,
            self.config.backoff_factor
        )

        # Initialize cache
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._cache_timestamps: Dict[str, float] = {}

        # Update data directory if specified in config
        if self.config.data_dir:
            global DATA_DIR
            DATA_DIR = self.config.data_dir
            DATA_DIR.mkdir(parents=True, exist_ok=True)

        self._last_request_time = 0.0

    @classmethod
    def from_config_file(cls, config_path: Union[str, Path]) -> "BlockchainComFetcher":
        """Create instance from configuration file"""
        config_path = Path(config_path)
        if not config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_path}")

        with open(config_path, 'r', encoding='utf-8') as f:
            config_data = json.load(f)

        config = FetcherConfig(**config_data)
        return cls(config=config)

    # ========================================================================
    # CACHE MANAGEMENT
    # ========================================================================

    def _get_cache_key(self, url: str, params: Optional[Dict[str, Any]] = None) -> str:
        """Generate cache key for URL and parameters"""
        key_data = f"{url}|{json.dumps(params or {}, sort_keys=True)}"
        return hashlib.sha1(key_data.encode()).hexdigest()

    def _is_cache_valid(self, cache_key: str) -> bool:
        """Check if cache entry is still valid"""
        if not self.config.cache_enabled:
            return False

        if cache_key not in self._cache_timestamps:
            return False

        age = time.time() - self._cache_timestamps[cache_key]
        return age < self.config.cache_ttl

    def _get_cached_response(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Get cached response if valid"""
        if self._is_cache_valid(cache_key):
            logger.debug(f"Cache hit for key: {cache_key}")
            return self._cache.get(cache_key)
        return None

    def _cache_response(self, cache_key: str, data: Dict[str, Any]) -> None:
        """Cache response data"""
        if not self.config.cache_enabled:
            return

        # Implement LRU-style cache eviction
        if len(self._cache) >= self.config.max_cache_size:
            # Remove oldest entry
            oldest_key = min(self._cache_timestamps, key=self._cache_timestamps.get)
            del self._cache[oldest_key]
            del self._cache_timestamps[oldest_key]

        self._cache[cache_key] = data
        self._cache_timestamps[cache_key] = time.time()
        logger.debug(f"Cached response for key: {cache_key}")

    def clear_cache(self) -> None:
        """Clear all cached data"""
        self._cache.clear()
        self._cache_timestamps.clear()
        logger.info("Cache cleared")

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        return {
            "cache_enabled": self.config.cache_enabled,
            "cache_size": len(self._cache),
            "max_cache_size": self.config.max_cache_size,
            "cache_ttl": self.config.cache_ttl,
            "oldest_entry_age": min(self._cache_timestamps.values()) if self._cache_timestamps else 0,
            "newest_entry_age": max(self._cache_timestamps.values()) if self._cache_timestamps else 0
        }

    # ========================================================================
    # SESSION MANAGEMENT
    # ========================================================================

    def _create_session(self, max_retries: int, backoff_factor: float) -> requests.Session:
        """Create a session with retry strategy and connection pooling"""
        session = requests.Session()

        # Use allowed_methods instead of deprecated method_whitelist for newer requests versions
        retry_kwargs = {
            "total": max_retries,
            "status_forcelist": [429, 500, 502, 503, 504],
            "backoff_factor": backoff_factor
        }

        # Check if allowed_methods is supported (newer requests versions)
        try:
            retry_strategy = Retry(
                allowed_methods=["HEAD", "GET", "OPTIONS"],
                **retry_kwargs
            )
        except TypeError:
            # Fallback to method_whitelist for older requests versions
            retry_strategy = Retry(
                method_whitelist=["HEAD", "GET", "OPTIONS"],
                **retry_kwargs
            )

        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        return session

    # ========================================================================
    # VALIDATION
    # ========================================================================

    def _validate_address(self, address: str) -> None:
        """Validate Bitcoin address format"""
        if not address or not isinstance(address, str):
            raise InvalidAddressError(f"Invalid address: {address}")

        # Basic validation for Bitcoin addresses (P2PKH, P2SH, Bech32)
        if not re.match(r'^[13][a-km-zA-HJ-NP-Z1-9]{25,34}$|^bc1[a-z0-9]{39,59}$', address):
            raise InvalidAddressError(f"Invalid Bitcoin address format: {address}")

    def _validate_addresses(self, addresses: List[str]) -> None:
        """Validate multiple Bitcoin addresses"""
        if not addresses or not isinstance(addresses, list):
            raise InvalidAddressError("Addresses must be a non-empty list")
        
        for addr in addresses:
            self._validate_address(addr)

    def _validate_tx_hash(self, tx_hash: str) -> None:
        """Validate transaction hash format"""
        if not tx_hash or not isinstance(tx_hash, str):
            raise TransactionNotFoundError(f"Invalid transaction hash: {tx_hash}")

        if not re.match(r'^[a-fA-F0-9]{64}$', tx_hash):
            raise TransactionNotFoundError(f"Invalid transaction hash format: {tx_hash}")

    def _validate_block_hash(self, block_hash: str) -> None:
        """Validate block hash format"""
        if not block_hash or not isinstance(block_hash, str):
            raise BlockNotFoundError(f"Invalid block hash: {block_hash}")

        if not re.match(r'^[a-fA-F0-9]{64}$', block_hash):
            raise BlockNotFoundError(f"Invalid block hash format: {block_hash}")

    def _validate_block_height(self, height: int) -> None:
        """Validate block height"""
        if not isinstance(height, int) or height < 0:
            raise InvalidParameterError(f"Block height must be a non-negative integer, got: {height}")

    # ========================================================================
    # RATE LIMITING
    # ========================================================================

    def _rate_limit_wait(self) -> None:
        """Enforce rate limiting"""
        current_time = time.time()
        time_since_last = current_time - self._last_request_time

        if time_since_last < self.config.rate_limit_s:
            sleep_time = self.config.rate_limit_s - time_since_last
            time.sleep(sleep_time)

        self._last_request_time = time.time()

    # ========================================================================
    # HTTP REQUEST
    # ========================================================================

    def _get(self, url: str, params: Optional[Dict[str, Any]] = None, allow_fallback: bool = False) -> Dict[str, Any]:
        """Make HTTP GET request with caching, error handling and rate limiting
        
        Args:
            url: URL to fetch
            params: Query parameters
            allow_fallback: If True, return empty dict instead of raising error on JSON parse failure
        
        Returns:
            Parsed JSON response or fallback dict
        """
        cache_key = self._get_cache_key(url, params)

        # Try to get from cache first
        cached_data = self._get_cached_response(cache_key)
        if cached_data is not None:
            return cached_data

        response = None
        try:
            self._rate_limit_wait()
            logger.debug(f"Making request to {url} with params {params}")

            response = self.session.get(url, params=params, timeout=self.config.timeout)
            
            # Log HTTP status for better debugging
            if response.status_code >= 400:
                logger.error(f"HTTP {response.status_code} error for {url}")
            elif response.status_code >= 300:
                logger.warning(f"HTTP {response.status_code} redirect for {url}")
            else:
                logger.debug(f"HTTP {response.status_code} success for {url}")
            
            response.raise_for_status()

            # Defensive: Validate Content-Type before parsing JSON
            content_type = response.headers.get('Content-Type', '')
            if 'application/json' not in content_type and 'text/json' not in content_type:
                logger.warning(f"Unexpected Content-Type: {content_type} for {url}")
                logger.debug(f"Response preview: {response.text[:500]}")
                
                if allow_fallback:
                    logger.warning(f"Using fallback for non-JSON response from {url}")
                    return {"values": [], "status": "fallback", "error": "Invalid Content-Type"}
                else:
                    raise BlockchainAPIError(
                        f"Invalid Content-Type '{content_type}' (expected JSON) for {url}. "
                        f"Response preview: {response.text[:200]}"
                    )

            # Try to parse JSON with defensive error handling
            try:
                data = response.json()
                logger.debug(f"Successfully parsed JSON from {url}")
            except json.JSONDecodeError as json_err:
                logger.error(f"JSON decode error for {url}: {json_err}")
                logger.debug(f"Raw response: {response.text[:1000]}")
                
                if allow_fallback:
                    logger.warning(f"Using fallback for invalid JSON from {url}")
                    return {"values": [], "status": "fallback", "error": str(json_err)}
                else:
                    raise BlockchainAPIError(
                        f"Invalid JSON response from {url}: {json_err}. "
                        f"Response: {response.text[:500]}"
                    ) from json_err

            # Cache the response
            self._cache_response(cache_key, data)

            return data

        except requests.exceptions.HTTPError as e:
            status_code = getattr(response, 'status_code', 'unknown') if response else 'unknown'

            if status_code == 500:
                logger.error(f"[5xx Server Error] External API 500 for {url}")
                raise BlockchainAPIError(f"Remote server error 500 for {url}: {e}") from e
            elif status_code == 429:
                logger.warning(f"[4xx Client Error] Rate limit exceeded for {url}")
                raise RateLimitError(f"Rate limit exceeded for {url}") from e
            elif status_code == 404:
                logger.warning(f"[4xx Client Error] Resource not found: {url}")
                if "rawtx" in url:
                    raise TransactionNotFoundError(f"Transaction not found: {url.split('/')[-1]}") from e
                elif "rawblock" in url:
                    raise BlockNotFoundError(f"Block not found: {url.split('/')[-1]}") from e
                else:
                    raise BlockchainAPIError(f"Resource not found: {url}") from e
            else:
                logger.error(f"[HTTP Error] Status {status_code} for {url}")
                raise BlockchainAPIError(f"HTTP error {status_code} for {url}: {e}") from e

        except requests.exceptions.Timeout as e:
            logger.error(f"[Network Error] Request timeout for {url}")
            raise BlockchainAPIError(f"Request timeout for {url}") from e

        except requests.exceptions.ConnectionError as e:
            logger.error(f"[Network Error] Connection error for {url}")
            raise BlockchainAPIError(f"Connection error for {url}") from e

        except BlockchainAPIError:
            # Re-raise our custom exceptions
            raise

        except Exception as e:
            logger.error(f"[Unexpected Error] {type(e).__name__} for {url}: {e}")
            raise BlockchainAPIError(f"Unexpected error: {e}") from e

    # ========================================================================
    # SINGLE ADDRESS API
    # ========================================================================

    def fetch_address(self, address: str, limit: int = 50, offset: int = 0) -> Dict[str, Any]:
        """
        Fetch address data with transaction history.
        
        Endpoint: https://blockchain.info/rawaddr/$bitcoin_address
        
        Args:
            address: Bitcoin address (base58 or hash160)
            limit: Number of transactions to show (Default: 50, Max: 50 per API call)
            offset: Skip the first n transactions (for pagination)
            
        Returns:
            Dict containing address data with transactions
        """
        self._validate_address(address)
        # API hard limit is 50 per request
        actual_limit = min(limit, 50)
        if offset < 0:
            raise InvalidParameterError(f"Offset must be non-negative, got {offset}")

        url = f"{BLOCKCHAIN_BASE}/rawaddr/{address}"
        params = {"limit": actual_limit, "offset": offset}
        return self._get(url, params=params)

    def fetch_all_transactions(
        self, 
        address: str, 
        max_limit: int = 1000,
        rate_limit_delay: float = 0.25
    ) -> Dict[str, Any]:
        """
        PRODUCTION-RESILIENT: Fetch all transactions for an address using deep pagination.
        
        The Blockchain.info API has a hard limit of 50 transactions per request.
        This function automatically paginates to fetch up to max_limit transactions.
        Supports up to 10000 transactions for comprehensive analysis.
        
        Args:
            address: Bitcoin address
            max_limit: Maximum number of transactions to fetch (default: 1000, max: 10000)
            rate_limit_delay: Seconds to wait between API calls (default: 0.25)
            
        Returns:
            Dict containing:
            - address: The Bitcoin address
            - hash160: Hash160 of the address
            - n_tx: Total number of transactions
            - total_received: Total received in satoshis
            - total_sent: Total sent in satoshis
            - final_balance: Current balance in satoshis
            - txs: Array of ALL fetched transactions (up to max_limit)
            - pagination_info: Metadata about the pagination process
        """
        self._validate_address(address)
        
        logger.info(f"Starting deep pagination for {address[:12]}... (max_limit={max_limit})")
        
        # Fetch initial batch to get address metadata
        try:
            initial_data = self.fetch_address(address, limit=50, offset=0)
        except Exception as e:
            logger.error(f"Failed to fetch initial data for {address}: {e}")
            raise
        
        all_txs = initial_data.get("txs", [])
        total_txs_on_chain = initial_data.get("n_tx", 0)
        
        # Calculate how many we need to fetch
        target_count = min(max_limit, total_txs_on_chain)
        
        logger.info(f"Address has {total_txs_on_chain} total txs, fetching up to {target_count}")
        
        # Pagination loop - fetch in batches of 50
        offset = 50
        batch_count = 1
        errors_encountered = 0
        max_errors = 5
        
        while len(all_txs) < target_count and offset < total_txs_on_chain:
            # Rate limiting - CRITICAL to avoid 429 errors
            time.sleep(rate_limit_delay)
            
            try:
                batch_data = self.fetch_address(address, limit=50, offset=offset)
                new_txs = batch_data.get("txs", [])
                
                if not new_txs:
                    logger.info(f"No more transactions at offset {offset}, stopping pagination")
                    break
                
                all_txs.extend(new_txs)
                batch_count += 1
                offset += 50
                
                # Progress logging every 5 batches
                if batch_count % 5 == 0:
                    logger.info(f"Pagination progress: {len(all_txs)}/{target_count} txs fetched (batch {batch_count})")
                
                # Safety check - if we got fewer than 50, we've reached the end
                if len(new_txs) < 50:
                    logger.info(f"Received partial batch ({len(new_txs)} txs), pagination complete")
                    break
                    
            except RateLimitError as e:
                errors_encountered += 1
                logger.warning(f"Rate limit hit at offset {offset}, waiting 2 seconds... (error {errors_encountered}/{max_errors})")
                time.sleep(2.0)
                
                if errors_encountered >= max_errors:
                    logger.error(f"Too many rate limit errors, stopping at {len(all_txs)} transactions")
                    break
                continue
                
            except Exception as e:
                errors_encountered += 1
                logger.warning(f"Error at offset {offset}: {e} (error {errors_encountered}/{max_errors})")
                
                if errors_encountered >= max_errors:
                    logger.error(f"Too many errors, stopping at {len(all_txs)} transactions")
                    break
                    
                time.sleep(1.0)
                continue
        
        # Build complete response
        result = {
            "address": initial_data.get("address", address),
            "hash160": initial_data.get("hash160", ""),
            "n_tx": initial_data.get("n_tx", 0),
            "n_unredeemed": initial_data.get("n_unredeemed", 0),
            "total_received": initial_data.get("total_received", 0),
            "total_sent": initial_data.get("total_sent", 0),
            "final_balance": initial_data.get("final_balance", 0),
            "txs": all_txs[:max_limit],  # Enforce max_limit
            "pagination_info": {
                "total_on_chain": total_txs_on_chain,
                "fetched_count": len(all_txs),
                "batches_fetched": batch_count,
                "errors_encountered": errors_encountered,
                "max_limit_requested": max_limit
            }
        }
        
        logger.info(f"Deep pagination complete: {len(all_txs)} txs fetched in {batch_count} batches")
        
        return result

    def fetch_address_full(self, address: str, max_limit: int = 1000) -> AddressInfo:
        """
        Fetch complete address information with all transactions.
        Uses deep pagination for production resilience.
        
        Args:
            address: Bitcoin address
            max_limit: Maximum transactions to fetch
            
        Returns:
            AddressInfo dataclass with comprehensive data
        """
        data = self.fetch_all_transactions(address, max_limit=max_limit)
        
        return AddressInfo(
            address=data.get("address", address),
            hash160=data.get("hash160", ""),
            n_tx=data.get("n_tx", 0),
            n_unredeemed=data.get("n_unredeemed", 0),
            total_received=data.get("total_received", 0),
            total_sent=data.get("total_sent", 0),
            final_balance=data.get("final_balance", 0),
            transactions=data.get("txs", [])
        )

    # ========================================================================
    # MULTI ADDRESS API
    # ========================================================================

    def fetch_multi_address(
        self, 
        addresses: List[str], 
        limit: int = 50, 
        offset: int = 0
    ) -> Dict[str, Any]:
        """
        Fetch data for multiple addresses at once.
        
        Endpoint: https://blockchain.info/multiaddr?active=$address|$address
        
        Args:
            addresses: List of Bitcoin addresses (base58 or xpub)
            limit: Number of transactions to show (Default: 50, Max: 100)
            offset: Skip the first n transactions
            
        Returns:
            Dict containing:
            - addresses: Array of address data with balances
            - txs: Latest transactions across all addresses
        """
        self._validate_addresses(addresses)
        
        # API handles max 100 per request. If limit > 100, we need to paginate.
        chunk_size = 100
        
        # Initial request
        current_limit = min(limit, chunk_size)
        url = f"{BLOCKCHAIN_BASE}/multiaddr"
        params = {
            "active": "|".join(addresses),
            "n": current_limit,
            "offset": offset
        }
        data = self._get(url, params=params)
        
        # If user requested more than 100, fetch recursively
        if limit > chunk_size and len(data.get("txs", [])) == current_limit:
            remaining = limit - current_limit
            current_offset = offset + current_limit
            
            while remaining > 0:
                next_batch_size = min(remaining, chunk_size)
                # Sleep briefly to avoid aggressive rate limiting
                time.sleep(0.1)
                
                params["n"] = next_batch_size
                params["offset"] = current_offset
                
                next_data = self._get(url, params=params)
                new_txs = next_data.get("txs", [])
                
                if not new_txs:
                    break
                    
                data["txs"].extend(new_txs)
                
                # Update counters
                remaining -= len(new_txs)
                current_offset += len(new_txs)
                
                if len(new_txs) < next_batch_size:
                    break

        return data

    def fetch_multi_address_balances(self, addresses: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Fetch balance summaries for multiple addresses.
        
        Args:
            addresses: List of Bitcoin addresses
            
        Returns:
            Dict mapping address to balance info
        """
        data = self.fetch_multi_address(addresses, limit=1)
        result = {}
        
        for addr_data in data.get("addresses", []):
            addr = addr_data.get("address", "")
            result[addr] = {
                "n_tx": addr_data.get("n_tx", 0),
                "total_received": addr_data.get("total_received", 0),
                "total_sent": addr_data.get("total_sent", 0),
                "final_balance": addr_data.get("final_balance", 0)
            }
        
        return result

    # ========================================================================
    # BALANCE API
    # ========================================================================

    def fetch_balance(self, addresses: Union[str, List[str]]) -> Dict[str, Dict[str, Any]]:
        """
        Fetch balance for one or more addresses.
        
        Endpoint: https://blockchain.info/balance?active=$address
        
        Args:
            addresses: Single address or list of addresses
            
        Returns:
            Dict mapping address to balance data:
            - final_balance: Current balance
            - n_tx: Number of transactions
            - total_received: Total received
        """
        if isinstance(addresses, str):
            addresses = [addresses]
        
        self._validate_addresses(addresses)
        
        url = f"{BLOCKCHAIN_BASE}/balance"
        params = {"active": "|".join(addresses)}
        return self._get(url, params=params)

    def get_address_balance(self, address: str) -> int:
        """
        Get the current balance for a single address in satoshis.
        
        Args:
            address: Bitcoin address
            
        Returns:
            Balance in satoshis
        """
        data = self.fetch_balance(address)
        return data.get(address, {}).get("final_balance", 0)

    # ========================================================================
    # UNSPENT OUTPUTS API
    # ========================================================================

    def fetch_unspent(
        self, 
        addresses: Union[str, List[str]], 
        limit: int = 250, 
        confirmations: int = 0
    ) -> Dict[str, Any]:
        """
        Fetch unspent outputs for one or more addresses.
        
        Endpoint: https://blockchain.info/unspent?active=$address
        
        Args:
            addresses: Single address or list of addresses
            limit: Maximum UTXOs to return (Default: 250, Max: 1000)
            confirmations: Minimum confirmations required (Default: 0)
            
        Returns:
            Dict containing:
            - unspent_outputs: Array of unspent transaction outputs
        """
        if isinstance(addresses, str):
            addresses = [addresses]
        
        self._validate_addresses(addresses)
        
        if limit < 1 or limit > 1000:
            raise InvalidParameterError(f"Limit must be between 1 and 1000, got {limit}")
        
        url = f"{BLOCKCHAIN_BASE}/unspent"
        params = {
            "active": "|".join(addresses),
            "limit": limit,
            "confirmations": confirmations
        }
        
        try:
            return self._get(url, params=params)
        except BlockchainAPIError as e:
            # Handle "No free outputs to spend" error
            if "No free outputs" in str(e):
                return {"unspent_outputs": []}
            raise

    def get_unspent_outputs(self, address: str) -> List[UnspentOutput]:
        """
        Get unspent outputs as typed objects.
        
        Args:
            address: Bitcoin address
            
        Returns:
            List of UnspentOutput objects
        """
        data = self.fetch_unspent(address)
        outputs = []
        
        for utxo in data.get("unspent_outputs", []):
            outputs.append(UnspentOutput(
                tx_hash=utxo.get("tx_hash", ""),
                tx_hash_big_endian=utxo.get("tx_hash_big_endian", ""),
                tx_index=utxo.get("tx_index", 0),
                tx_output_n=utxo.get("tx_output_n", 0),
                script=utxo.get("script", ""),
                value=utxo.get("value", 0),
                value_hex=utxo.get("value_hex", ""),
                confirmations=utxo.get("confirmations", 0),
                tx_age=utxo.get("tx_age")
            ))
        
        return outputs

    # ========================================================================
    # TRANSACTION API
    # ========================================================================

    def fetch_tx(self, tx_hash: str, format: str = "json") -> Dict[str, Any]:
        """
        Fetch transaction data by hash.
        
        Endpoint: https://blockchain.info/rawtx/$tx_hash
        
        Args:
            tx_hash: Transaction hash (64 hex characters)
            format: Response format ('json' or 'hex')
            
        Returns:
            Transaction data including inputs, outputs, fees, etc.
        """
        self._validate_tx_hash(tx_hash)
        url = f"{BLOCKCHAIN_BASE}/rawtx/{tx_hash}"
        params = {}
        if format == "hex":
            params["format"] = "hex"
        return self._get(url, params=params if params else None)

    def get_transaction(self, tx_hash: str) -> TransactionInfo:
        """
        Get transaction as typed object.
        
        Args:
            tx_hash: Transaction hash
            
        Returns:
            TransactionInfo object with comprehensive data
        """
        data = self.fetch_tx(tx_hash)
        
        return TransactionInfo(
            hash=data.get("hash", tx_hash),
            ver=data.get("ver", 0),
            vin_sz=data.get("vin_sz", 0),
            vout_sz=data.get("vout_sz", 0),
            size=data.get("size", 0),
            weight=data.get("weight", 0),
            fee=data.get("fee", 0),
            relayed_by=data.get("relayed_by", ""),
            lock_time=data.get("lock_time", 0),
            tx_index=data.get("tx_index", 0),
            double_spend=data.get("double_spend", False),
            time=data.get("time", 0),
            block_index=data.get("block_index"),
            block_height=data.get("block_height"),
            inputs=data.get("inputs", []),
            outputs=data.get("out", [])
        )

    # ========================================================================
    # BLOCK API
    # ========================================================================

    def fetch_block(self, block_hash: str, format: str = "json") -> Dict[str, Any]:
        """
        Fetch block data by hash.
        
        Endpoint: https://blockchain.info/rawblock/$block_hash
        
        Args:
            block_hash: Block hash (64 hex characters)
            format: Response format ('json' or 'hex')
            
        Returns:
            Block data including transactions, merkle root, etc.
        """
        self._validate_block_hash(block_hash)
        url = f"{BLOCKCHAIN_BASE}/rawblock/{block_hash}"
        params = {}
        if format == "hex":
            params["format"] = "hex"
        return self._get(url, params=params if params else None)

    def fetch_block_by_height(self, height: int) -> Dict[str, Any]:
        """
        Fetch block data by height.
        
        Endpoint: https://blockchain.info/block-height/$block_height?format=json
        
        Args:
            height: Block height (0-indexed)
            
        Returns:
            Dict containing 'blocks' array with block(s) at that height
        """
        self._validate_block_height(height)
        url = f"{BLOCKCHAIN_BASE}/block-height/{height}"
        params = {"format": "json"}
        return self._get(url, params=params)

    def get_block(self, block_hash: str) -> BlockInfo:
        """
        Get block as typed object.
        
        Args:
            block_hash: Block hash
            
        Returns:
            BlockInfo object with comprehensive data
        """
        data = self.fetch_block(block_hash)
        
        return BlockInfo(
            hash=data.get("hash", block_hash),
            ver=data.get("ver", 0),
            prev_block=data.get("prev_block", ""),
            mrkl_root=data.get("mrkl_root", ""),
            time=data.get("time", 0),
            bits=data.get("bits", 0),
            nonce=data.get("nonce", 0),
            n_tx=data.get("n_tx", 0),
            size=data.get("size", 0),
            block_index=data.get("block_index", 0),
            main_chain=data.get("main_chain", True),
            height=data.get("height", 0),
            received_time=data.get("received_time", 0),
            relayed_by=data.get("relayed_by", ""),
            transactions=data.get("tx", [])
        )

    # ========================================================================
    # LATEST BLOCK API
    # ========================================================================

    def fetch_latest_block(self) -> Dict[str, Any]:
        """
        Fetch the latest block.
        
        Endpoint: https://blockchain.info/latestblock
        
        Returns:
            Dict containing:
            - hash: Block hash
            - time: Block timestamp
            - block_index: Block index
            - height: Block height
            - txIndexes: Array of transaction indexes
        """
        url = f"{BLOCKCHAIN_BASE}/latestblock"
        return self._get(url)

    def get_latest_block(self) -> LatestBlock:
        """
        Get latest block as typed object.
        
        Returns:
            LatestBlock object
        """
        data = self.fetch_latest_block()
        
        return LatestBlock(
            hash=data.get("hash", ""),
            time=data.get("time", 0),
            block_index=data.get("block_index", 0),
            height=data.get("height", 0),
            tx_indexes=data.get("txIndexes", [])
        )

    def get_current_block_height(self) -> int:
        """
        Get the current blockchain height.
        
        Returns:
            Current block height
        """
        return self.get_latest_block().height

    # ========================================================================
    # UNCONFIRMED TRANSACTIONS API
    # ========================================================================

    def fetch_unconfirmed_transactions(self) -> Dict[str, Any]:
        """
        Fetch unconfirmed (mempool) transactions.
        
        Endpoint: https://blockchain.info/unconfirmed-transactions?format=json
        
        Returns:
            Dict containing 'txs' array of unconfirmed transactions
        """
        url = f"{BLOCKCHAIN_BASE}/unconfirmed-transactions"
        params = {"format": "json"}
        return self._get(url, params=params)

    def get_mempool_transactions(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get unconfirmed transactions from the mempool.
        
        Args:
            limit: Maximum transactions to return
            
        Returns:
            List of unconfirmed transactions
        """
        data = self.fetch_unconfirmed_transactions()
        txs = data.get("txs", [])
        return txs[:limit] if limit else txs

    # ========================================================================
    # BLOCKS BY DAY/POOL API
    # ========================================================================

    def fetch_blocks_for_day(self, timestamp_ms: Optional[int] = None) -> Dict[str, Any]:
        """
        Fetch blocks mined on a specific day.
        
        Endpoint: https://blockchain.info/blocks/$time_in_milliseconds?format=json
        
        Args:
            timestamp_ms: Unix timestamp in milliseconds (default: today)
            
        Returns:
            Dict containing 'blocks' array of blocks mined that day
        """
        if timestamp_ms is None:
            timestamp_ms = int(time.time() * 1000)
        
        url = f"{BLOCKCHAIN_BASE}/blocks/{timestamp_ms}"
        params = {"format": "json"}
        return self._get(url, params=params)

    def fetch_blocks_for_pool(self, pool_name: str) -> Dict[str, Any]:
        """
        Fetch blocks mined by a specific pool.
        
        Endpoint: https://blockchain.info/blocks/$pool_name?format=json
        
        Args:
            pool_name: Mining pool name (e.g., "AntPool", "F2Pool")
            
        Returns:
            Dict containing 'blocks' array of blocks mined by the pool
        """
        if not pool_name or not isinstance(pool_name, str):
            raise InvalidParameterError("Pool name must be a non-empty string")
        
        url = f"{BLOCKCHAIN_BASE}/blocks/{pool_name}"
        params = {"format": "json"}
        return self._get(url, params=params)

    def get_blocks_today(self) -> List[Dict[str, Any]]:
        """
        Get blocks mined today.
        
        Returns:
            List of blocks mined today
        """
        data = self.fetch_blocks_for_day()
        return data.get("blocks", [])

    # ========================================================================
    # CHARTS API
    # ========================================================================

    def fetch_chart(self, chart_type: str, timespan: str = "1year") -> Dict[str, Any]:
        """
        Fetch chart data from Blockchain Charts API.
        
        **CORRECT** Endpoint: https://api.blockchain.info/charts/$chart-type?format=json&timespan=1year
        
        Available chart types:
        - market-price: Bitcoin market price (USD)
        - total-bitcoins: Total bitcoins in circulation
        - market-cap: Bitcoin market capitalization (USD)
        - trade-volume: Exchange trade volume (USD)
        - blocks-size: Average block size (bytes)
        - avg-block-size: Average block size (bytes)
        - n-transactions: Number of transactions per day
        - n-transactions-per-block: Average transactions per block
        - median-confirmation-time: Median confirmation time (minutes)
        - hash-rate: Network hash rate (TH/s)
        - difficulty: Mining difficulty
        - miners-revenue: Miners revenue (USD)
        - transaction-fees: Total transaction fees (BTC)
        - cost-per-transaction: Average cost per transaction (USD)
        - unique-addresses: Number of unique addresses used
        - n-transactions-excluding-popular: Transactions excluding popular addresses
        - n-transactions-excluding-chains-longer-than-100: Transactions excluding long chains
        - output-volume: Total output volume (BTC)
        - estimated-transaction-volume: Estimated transaction volume (BTC)
        - estimated-transaction-volume-usd: Estimated transaction volume (USD)
        
        Args:
            chart_type: Type of chart to fetch (see list above)
            timespan: Time range - options: "1year", "2years", "3months", "30days", "7days", "1days", "all"
            
        Returns:
            Dict containing:
            - status: "ok" or "error"
            - name: Chart name
            - unit: Unit of measurement
            - period: Time period
            - description: Chart description
            - values: Array of {x: unix_timestamp (seconds), y: value}
            
        Example:
            >>> fetcher.fetch_chart("market-price", "7days")
            {"status": "ok", "name": "Market Price", "values": [{"x": 1234567890, "y": 45000.50}, ...]}
        """
        if not chart_type or not isinstance(chart_type, str):
            raise InvalidParameterError("Chart type must be a non-empty string")
        
        # Use api.blockchain.info for charts (NOT blockchain.info)
        url = f"{BLOCKCHAIN_CHARTS_BASE}/charts/{chart_type}"
        params = {
            "format": "json",  # Required: Ensures JSON response
            "timespan": timespan  # Optional: Default is "1year"
        }
        
        logger.info(f"Fetching chart data: {chart_type} (timespan={timespan}) from {url}")
        
        # Use allow_fallback=True for charts to handle HTML/error responses gracefully
        try:
            result = self._get(url, params=params, allow_fallback=True)
            
            # Check if we got a fallback response
            if result.get("status") == "fallback":
                logger.warning(f"Chart API returned invalid response for {chart_type}, using empty dataset")
            
            return result
            
        except BlockchainAPIError as e:
            logger.error(f"Failed to fetch chart {chart_type}: {e}")
            # Return empty dataset instead of crashing
            logger.warning(f"Returning empty dataset for chart {chart_type} due to API error")
            return {
                "status": "error",
                "name": chart_type,
                "values": [],
                "error": str(e)
            }

    def get_market_price_history(self, timespan: str = "1year") -> List[Dict[str, Any]]:
        """
        Get Bitcoin market price history.
        
        Args:
            timespan: Time range for data
            
        Returns:
            List of {x: timestamp, y: price_usd}
        """
        data = self.fetch_chart("market-price", timespan)
        return data.get("values", [])

    def get_hash_rate_history(self, timespan: str = "1year") -> List[Dict[str, Any]]:
        """
        Get network hash rate history.
        
        Args:
            timespan: Time range for data
            
        Returns:
            List of {x: timestamp, y: hash_rate}
        """
        data = self.fetch_chart("hash-rate", timespan)
        return data.get("values", [])

    def get_difficulty_history(self, timespan: str = "1year") -> List[Dict[str, Any]]:
        """
        Get mining difficulty history.
        
        Args:
            timespan: Time range for data
            
        Returns:
            List of {x: timestamp, y: difficulty}
        """
        data = self.fetch_chart("difficulty", timespan)
        return data.get("values", [])

    def get_transaction_count_history(self, timespan: str = "1year") -> List[Dict[str, Any]]:
        """
        Get daily transaction count history.
        
        Args:
            timespan: Time range for data
            
        Returns:
            List of {x: timestamp, y: tx_count}
        """
        data = self.fetch_chart("n-transactions", timespan)
        return data.get("values", [])

    # ========================================================================
    # COMPREHENSIVE DATA FETCH
    # ========================================================================

    def fetch_address_comprehensive(self, address: str) -> Dict[str, Any]:
        self._validate_address(address)

        addr_data = self.fetch_all_transactions(address, max_limit=2000, rate_limit_delay=0.3)

        total_on_chain = addr_data.get("n_tx", 0)
        first_page_txs = addr_data.get("txs", [])

        unspent_outputs = []
        try:
            unspent_data = self.fetch_unspent(address)
            unspent_outputs = unspent_data.get("unspent_outputs", [])
        except BlockchainAPIError as e:
            logger.warning(f"Failed to fetch unspent outputs for {address}: {e}")

        balance_details = {}
        try:
            balance_data = self.fetch_balance(address)
            balance_details = balance_data.get(address, {})
        except BlockchainAPIError as e:
            logger.warning(f"Failed to fetch balance for {address}: {e}")

        total_received = addr_data.get("total_received", 0)
        total_sent = addr_data.get("total_sent", 0)
        final_balance = addr_data.get("final_balance", 0)

        nodes = {}
        edges = []
        transactions_map = {}

        addr_node = {
            "id": address,
            "type": "address",
            "balance": final_balance,
            "totalReceived": total_received,
            "totalSent": total_sent,
            "txCount": total_on_chain,
            "riskScore": 0,
            "isSuspicious": False,
            "tags": [],
            "communityId": None,
            "betweennessCentrality": 0,
            "firstSeen": None,
            "lastActive": None,
            "utxos": unspent_outputs,
            "rawData": {
                "hash160": addr_data.get("hash160", ""),
                "n_tx": total_on_chain,
                "n_unredeemed": addr_data.get("n_unredeemed", 0),
                "total_received": total_received,
                "total_sent": total_sent,
                "final_balance": final_balance,
            },
        }
        nodes[address] = addr_node

        for tx in first_page_txs:
            tx_hash = tx.get("hash", "")
            if not tx_hash:
                continue

            tx_time = tx.get("time")
            tx_fee = tx.get("fee", 0)
            tx_block_height = tx.get("block_height")
            tx_block_hash = tx.get("block_hash")

            nodes[tx_hash] = {
                "id": tx_hash,
                "type": "transaction",
                "hash": tx_hash,
                "time": tx_time,
                "blockHash": tx_block_hash,
                "blockHeight": tx_block_height,
                "fee": tx_fee,
                "riskScore": 0,
                "communityId": None,
                "betweennessCentrality": 0,
                "rawData": tx,
            }

            tx_inputs = []
            for vin in tx.get("inputs", []):
                prev_out = vin.get("prev_out") or {}
                src_addr = prev_out.get("addr")
                src_value = prev_out.get("value", 0)
                if src_addr:
                    tx_inputs.append({"addr": src_addr, "value": src_value, "n": prev_out.get("n")})
                    if src_addr not in nodes:
                        nodes[src_addr] = {
                            "id": src_addr,
                            "type": "address",
                            "balance": 0,
                            "totalReceived": 0,
                            "totalSent": 0,
                            "txCount": 0,
                            "riskScore": 0,
                            "isSuspicious": False,
                            "tags": [],
                            "communityId": None,
                            "betweennessCentrality": 0,
                        }
                    edges.append({
                        "id": f"{src_addr}->{tx_hash}",
                        "source": src_addr,
                        "target": tx_hash,
                        "value": src_value,
                        "timestamp": tx_time,
                        "txHash": tx_hash,
                        "type": "input",
                    })

            tx_outputs = []
            for vout in tx.get("out", []):
                dst_addr = vout.get("addr")
                dst_value = vout.get("value", 0)
                out_n = vout.get("n")
                if dst_addr:
                    tx_outputs.append({"addr": dst_addr, "value": dst_value, "n": out_n})
                    if dst_addr not in nodes:
                        nodes[dst_addr] = {
                            "id": dst_addr,
                            "type": "address",
                            "balance": 0,
                            "totalReceived": 0,
                            "totalSent": 0,
                            "txCount": 0,
                            "riskScore": 0,
                            "isSuspicious": False,
                            "tags": [],
                            "communityId": None,
                            "betweennessCentrality": 0,
                        }
                    edges.append({
                        "id": f"{tx_hash}->{dst_addr}-{out_n}",
                        "source": tx_hash,
                        "target": dst_addr,
                        "value": dst_value,
                        "timestamp": tx_time,
                        "txHash": tx_hash,
                        "type": "output",
                    })

            transactions_map[tx_hash] = {
                "hash": tx_hash,
                "time": tx_time,
                "blockHash": tx_block_hash,
                "blockHeight": tx_block_height,
                "confirmations": tx.get("block_height"),
                "fee": tx_fee,
                "inputs": tx_inputs,
                "outputs": tx_outputs,
                "minerPool": None,
                "rawData": tx,
            }

        has_more = total_on_chain > len(first_page_txs)
        next_offset = len(first_page_txs) if has_more else None

        case_id = f"CASE-Investigation-{datetime.now().strftime('%b-%d-%Y')}"

        return {
            "metadata": {
                "caseId": case_id,
                "createdAt": datetime.now().isoformat() + "Z",
                "lastUpdated": datetime.now().isoformat(),
                "primaryAddress": address,
                "investigatedAddresses": [address],
            },
            "nodes": nodes,
            "edges": edges,
            "transactions": transactions_map,
            "blocks": {},
            "globalContext": {
                "marketPrice": 0,
                "networkHashRate": 0,
                "networkDifficulty": 0,
                "transactionRate": [],
                "lastBlockHeight": 0,
                "mempoolSize": 0,
            },
            "detectedCommunities": {},
            "investigativeLeads": [],
            "suspiciousPatterns": {
                "mixerCandidates": [],
                "bridgeNodes": [],
                "timingAnomalies": [],
                "dustingTargets": [],
                "whales": [],
            },
            "pagination": {
                "totalTransactions": total_on_chain,
                "fetchedCount": len(first_page_txs),
                "pageSize": 50,
                "hasMore": has_more,
                "nextOffset": next_offset,
            },
            "address": address,
            "basic_info": {
                "address": addr_data.get("address", address),
                "hash160": addr_data.get("hash160", ""),
                "n_tx": total_on_chain,
                "n_unredeemed": addr_data.get("n_unredeemed", 0),
                "total_received": total_received,
                "total_sent": total_sent,
                "final_balance": final_balance,
            },
            "unspent_outputs": unspent_outputs,
            "balance_details": balance_details,
            "fetched_at": datetime.now().isoformat(),
            "fetch_status": "complete",
        }

    def fetch_block_comprehensive(self, block_identifier: Union[str, int]) -> Dict[str, Any]:
        """
        Fetch all available data for a block.
        
        Args:
            block_identifier: Block hash (string) or height (int)
            
        Returns:
            Dict with comprehensive block data
        """
        result = {
            "fetched_at": datetime.now().isoformat(),
            "block_data": {},
            "transaction_count": 0,
            "transaction_summaries": []
        }
        
        try:
            if isinstance(block_identifier, int):
                # Fetch by height
                height_data = self.fetch_block_by_height(block_identifier)
                blocks = height_data.get("blocks", [])
                if blocks:
                    result["block_data"] = blocks[0]
            else:
                # Fetch by hash
                result["block_data"] = self.fetch_block(block_identifier)
            
            # Extract transaction summaries
            txs = result["block_data"].get("tx", [])
            result["transaction_count"] = len(txs)
            
            # Create summaries for first 100 transactions
            for tx in txs[:100]:
                summary = {
                    "hash": tx.get("hash", ""),
                    "size": tx.get("size", 0),
                    "fee": tx.get("fee", 0),
                    "input_count": len(tx.get("inputs", [])),
                    "output_count": len(tx.get("out", []))
                }
                result["transaction_summaries"].append(summary)
                
        except BlockchainAPIError as e:
            logger.warning(f"Failed to fetch block {block_identifier}: {e}")
        
        return result

    def fetch_network_stats(self) -> Dict[str, Any]:
        """
        Fetch current network statistics.
        
        Returns:
            Dict with network stats:
            - latest_block: Latest block info
            - mempool_size: Unconfirmed transaction count
            - blocks_today: Blocks mined today
            - difficulty: Current difficulty
            - hash_rate: Current hash rate
        """
        result = {
            "fetched_at": datetime.now().isoformat(),
            "latest_block": {},
            "mempool_size": 0,
            "blocks_today": 0,
            "charts": {}
        }
        
        try:
            result["latest_block"] = self.fetch_latest_block()
        except BlockchainAPIError as e:
            logger.warning(f"Failed to fetch latest block: {e}")
        
        try:
            mempool = self.fetch_unconfirmed_transactions()
            result["mempool_size"] = len(mempool.get("txs", []))
        except BlockchainAPIError as e:
            logger.warning(f"Failed to fetch mempool: {e}")
        
        try:
            today_blocks = self.fetch_blocks_for_day()
            result["blocks_today"] = len(today_blocks.get("blocks", []))
        except BlockchainAPIError as e:
            logger.warning(f"Failed to fetch today's blocks: {e}")
        
        # Fetch recent chart data
        for chart_type in ["hash-rate", "difficulty", "n-transactions"]:
            try:
                chart_data = self.fetch_chart(chart_type, timespan="7days")
                values = chart_data.get("values", [])
                if values:
                    result["charts"][chart_type] = {
                        "latest_value": values[-1].get("y", 0) if values else 0,
                        "data_points": len(values)
                    }
            except BlockchainAPIError as e:
                logger.warning(f"Failed to fetch chart {chart_type}: {e}")
        
        return result

    def build_graph_for_address(self, address: str, tx_limit: int = 50) -> Dict[str, Any]:
        """Build optimized graph data for an address with better performance"""
        logger.info(f"Building graph for address {address} with limit {tx_limit}")

        data = self.fetch_address(address, limit=tx_limit)
        transactions = data.get("txs", [])

        if not transactions:
            logger.warning(f"No transactions found for address {address}")
            return self._create_empty_graph(address)

        # Use sets for O(1) lookups and deduplication
        nodes_set = set()
        edges_list = []

        # Pre-allocate collections for better performance
        nodes_dict = {}
        edges_dict = {}  # For deduplication

        # Add the main address node
        main_node = GraphNode(id=address, label=address[:12], type="address")
        nodes_dict[address] = main_node
        nodes_set.add(address)

        processed_txs = 0
        total_inputs = 0
        total_outputs = 0

        for tx in transactions:
            txid = tx.get("hash")
            if not txid:
                continue

            processed_txs += 1

            # Add transaction node
            if txid not in nodes_set:
                tx_node = GraphNode(id=txid, label=txid[:12], type="transaction")
                nodes_dict[txid] = tx_node
                nodes_set.add(txid)

            # Process inputs
            for vin in tx.get("inputs", []):
                prev_out = vin.get("prev_out") or {}
                src_addr = prev_out.get("addr")
                if not src_addr:
                    continue

                total_inputs += 1

                # Add source address node
                if src_addr not in nodes_set:
                    src_node = GraphNode(id=src_addr, label=src_addr[:12], type="address")
                    nodes_dict[src_addr] = src_node
                    nodes_set.add(src_addr)

                # Create edge with deduplication
                edge_id = f"{src_addr}->{txid}"
                if edge_id not in edges_dict:
                    edge = GraphEdge(
                        id=edge_id,
                        source=src_addr,
                        target=txid,
                        type="SENT_FROM",
                        value=prev_out.get("value", 0)
                    )
                    edges_list.append(edge)
                    edges_dict[edge_id] = edge

            # Process outputs
            for vout in tx.get("out", []):
                dst_addr = vout.get("addr")
                if not dst_addr:
                    continue

                total_outputs += 1

                # Add destination address node
                if dst_addr not in nodes_set:
                    dst_node = GraphNode(id=dst_addr, label=dst_addr[:12], type="address")
                    nodes_dict[dst_addr] = dst_node
                    nodes_set.add(dst_addr)

                # Create edge with deduplication
                edge_id = f"{txid}->{dst_addr}"
                if edge_id not in edges_dict:
                    edge = GraphEdge(
                        id=edge_id,
                        source=txid,
                        target=dst_addr,
                        type="SENT_TO",
                        value=vout.get("value", 0)
                    )
                    edges_list.append(edge)
                    edges_dict[edge_id] = edge

        # Convert to final format
        graph_data = GraphData(
            nodes=list(nodes_dict.values()),
            edges=edges_list,
            meta=GraphMeta(
                address=address,
                tx_count=len(transactions),
                node_count=len(nodes_dict),
                edge_count=len(edges_list)
            )
        )

        logger.info(
            f"Graph built: {len(nodes_dict)} nodes, {len(edges_list)} edges, "
            f"{processed_txs} transactions processed"
        )

        # Return dict format for backward compatibility
        return {
            "nodes": [{"id": n.id, "label": n.label, "type": n.type} for n in graph_data.nodes],
            "edges": [{"id": e.id, "source": e.source, "target": e.target, "type": e.type, "value": e.value} for e in graph_data.edges],
            "meta": {
                "address": graph_data.meta.address,
                "tx_count": graph_data.meta.tx_count,
                "node_count": graph_data.meta.node_count,
                "edge_count": graph_data.meta.edge_count
            }
        }

    def _create_empty_graph(self, address: str) -> Dict[str, Any]:
        """Create an empty graph structure"""
        return {
            "nodes": [{"id": address, "label": address[:12], "type": "address"}],
            "edges": [],
            "meta": {
                "address": address,
                "tx_count": 0,
                "node_count": 1,
                "edge_count": 0
            }
        }

    def save_graph(self, graph: Dict[str, Any], filename: Optional[str] = None) -> str:
        """Save graph to file with sanitized filename"""
        data_dir = self.config.data_dir or DATA_DIR
        data_dir.mkdir(parents=True, exist_ok=True)

        if not filename:
            address = graph.get("meta", {}).get("address", "graph")

            safe_address = re.sub(r'[^A-Za-z0-9_\-]', '_', address)

            if address.startswith(("1", "3", "bc1")):
                prefix = "btc_graph_"
            elif address.startswith("0x") and len(address) == 42:
                prefix = "eth_graph_"
            else:
                prefix = "graph_"

            filename = f"{prefix}{safe_address[:12]}.json"

        path = data_dir / filename

        # Use temporary file for atomic write
        tmp = str(path) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(graph, f, ensure_ascii=False, indent=2)

        os.replace(tmp, path)

        logger.info(
            f"Graph saved: path={path} nodes={len(graph.get('nodes', []))} edges={len(graph.get('edges', []))}"
        )
        return str(path)