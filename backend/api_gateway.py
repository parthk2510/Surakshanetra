import time
import threading
import logging
from collections import deque
from datetime import datetime

logger = logging.getLogger(__name__)

class APIGateway:
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._request_lock = threading.Lock()
        self._last_request_time = 0
        self._min_interval = 0.3
        self._request_count = 0
        self._request_history = deque(maxlen=1000)
        self._rate_limit_hits = 0
        self._initialized = True
    
    def wait_for_slot(self):
        with self._request_lock:
            current_time = time.time()
            elapsed = current_time - self._last_request_time
            
            if elapsed < self._min_interval:
                sleep_time = self._min_interval - elapsed
                logger.debug(f"Rate limiting: sleeping {sleep_time:.3f}s")
                time.sleep(sleep_time)
            
            self._last_request_time = time.time()
            self._request_count += 1
            self._request_history.append({
                'timestamp': datetime.now().isoformat(),
                'count': self._request_count
            })
    
    def throttled_request(self, request_func, *args, **kwargs):
        max_retries = kwargs.pop('max_retries', 3)
        retry_delay = kwargs.pop('retry_delay', 10)
        
        for attempt in range(max_retries):
            self.wait_for_slot()
            
            try:
                response = request_func(*args, **kwargs)
                
                if hasattr(response, 'status_code') and response.status_code == 429:
                    self._rate_limit_hits += 1
                    logger.warning(f"Rate limit hit (429). Attempt {attempt + 1}/{max_retries}. Waiting {retry_delay}s")
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
                
                return response
                
            except Exception as e:
                if '429' in str(e) or 'rate limit' in str(e).lower():
                    self._rate_limit_hits += 1
                    logger.warning(f"Rate limit error. Attempt {attempt + 1}/{max_retries}. Waiting {retry_delay}s")
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
                raise
        
        raise Exception(f"Max retries ({max_retries}) exceeded due to rate limiting")
    
    def get_stats(self):
        return {
            'total_requests': self._request_count,
            'rate_limit_hits': self._rate_limit_hits,
            'min_interval': self._min_interval,
            'last_request': self._last_request_time
        }
    
    def set_interval(self, interval):
        self._min_interval = max(0.1, interval)


class RecursiveFetcher:
    def __init__(self, fetcher_instance):
        self.fetcher = fetcher_instance
        self.gateway = APIGateway()
        self.visited = set()
        self.results = {}
        self.max_depth = 2
        self.max_addresses = 100
    
    def fetch_address_recursive(self, address, depth=1, parent_address=None):
        if address in self.visited:
            return None
        
        if len(self.visited) >= self.max_addresses:
            logger.warning(f"Max addresses ({self.max_addresses}) reached")
            return None
        
        if depth > self.max_depth:
            return None
        
        self.visited.add(address)
        
        try:
            logger.info(f"Fetching address {address[:16]}... (depth={depth}, visited={len(self.visited)})")
            
            self.gateway.wait_for_slot()
            address_data = self.fetcher.fetch_address(address, limit=50)
            
            self.gateway.wait_for_slot()
            utxo_data = self.fetcher.fetch_unspent(address)
            
            result = {
                'address': address,
                'depth': depth,
                'parent': parent_address,
                'basic_info': {
                    'n_tx': address_data.get('n_tx', 0),
                    'total_received': address_data.get('total_received', 0),
                    'total_sent': address_data.get('total_sent', 0),
                    'final_balance': address_data.get('final_balance', 0)
                },
                'transactions': address_data.get('txs', []),
                'unspent_outputs': utxo_data.get('unspent_outputs', []),
                'neighbors': []
            }
            
            self.results[address] = result
            
            if depth < self.max_depth:
                neighbors = self._extract_neighbors(address_data.get('txs', []), address)
                result['neighbors'] = neighbors[:20]
                
                for neighbor in neighbors[:10]:
                    if neighbor not in self.visited and len(self.visited) < self.max_addresses:
                        self.fetch_address_recursive(neighbor, depth + 1, address)
            
            return result
            
        except Exception as e:
            logger.error(f"Error fetching {address}: {e}")
            return None
    
    def _extract_neighbors(self, transactions, source_address):
        neighbors = set()
        
        for tx in transactions:
            for inp in tx.get('inputs', []):
                prev_out = inp.get('prev_out', {})
                addr = prev_out.get('addr')
                if addr and addr != source_address:
                    neighbors.add(addr)
            
            for out in tx.get('out', []):
                addr = out.get('addr')
                if addr and addr != source_address:
                    neighbors.add(addr)
        
        return list(neighbors)
    
    def build_graph(self):
        """
        Build a graph structure from recursive fetch results.
        Returns nodes and edges compatible with the frontend graph renderer.
        """
        nodes = []
        edges = []
        node_set = set()
        edge_set = set()
        
        # Build nodes from all addresses
        for addr, data in self.results.items():
            # Add address node
            if addr not in node_set:
                nodes.append({
                    'id': addr,
                    'label': addr[:12] + '...',
                    'type': 'address',
                    'depth': data.get('depth', 0),
                    'n_tx': data.get('basic_info', {}).get('n_tx', 0),
                    'total_received': data.get('basic_info', {}).get('total_received', 0),
                    'total_sent': data.get('basic_info', {}).get('total_sent', 0),
                    'final_balance': data.get('basic_info', {}).get('final_balance', 0)
                })
                node_set.add(addr)
            
            # Process transactions and create edges
            transactions = data.get('transactions', [])
            for tx in transactions:
                tx_hash = tx.get('hash', '')
                if not tx_hash:
                    continue
                
                # Add transaction node
                if tx_hash not in node_set:
                    nodes.append({
                        'id': tx_hash,
                        'label': tx_hash[:12] + '...',
                        'type': 'transaction',
                        'time': tx.get('time', 0),
                        'size': tx.get('size', 0),
                        'fee': tx.get('fee', 0)
                    })
                    node_set.add(tx_hash)
                
                # Create edges from transaction inputs (address -> transaction)
                for inp in tx.get('inputs', []):
                    prev_out = inp.get('prev_out', {})
                    src_addr = prev_out.get('addr')
                    if src_addr and src_addr in self.results:
                        edge_id = f"{src_addr}->{tx_hash}"
                        if edge_id not in edge_set:
                            edges.append({
                                'id': edge_id,
                                'source': src_addr,
                                'target': tx_hash,
                                'type': 'SENT_FROM',
                                'value': prev_out.get('value', 0)
                            })
                            edge_set.add(edge_id)
                
                # Create edges to transaction outputs (transaction -> address)
                for out in tx.get('out', []):
                    dst_addr = out.get('addr')
                    if dst_addr:
                        # Add destination address node if not already present
                        if dst_addr not in node_set:
                            nodes.append({
                                'id': dst_addr,
                                'label': dst_addr[:12] + '...',
                                'type': 'address',
                                'depth': data.get('depth', 0) + 1
                            })
                            node_set.add(dst_addr)
                        
                        edge_id = f"{tx_hash}->{dst_addr}"
                        if edge_id not in edge_set:
                            edges.append({
                                'id': edge_id,
                                'source': tx_hash,
                                'target': dst_addr,
                                'type': 'SENT_TO',
                                'value': out.get('value', 0)
                            })
                            edge_set.add(edge_id)
                
                # Create parent-child edges between addresses (if parent exists)
                parent = data.get('parent')
                if parent and parent in self.results:
                    edge_id = f"{parent}->{addr}"
                    if edge_id not in edge_set:
                        edges.append({
                            'id': edge_id,
                            'source': parent,
                            'target': addr,
                            'type': 'CONNECTED',
                            'value': 0
                        })
                        edge_set.add(edge_id)
        
        return {
            'nodes': nodes,
            'edges': edges,
            'meta': {
                'node_count': len(nodes),
                'edge_count': len(edges),
                'address_count': len(self.results),
                'visited_count': len(self.visited),
                'max_depth': self.max_depth
            }
        }
    
    def get_results(self):
        return {
            'addresses': self.results,
            'visited_count': len(self.visited),
            'max_depth': self.max_depth
        }
    
    def get_graph_results(self):
        """
        Get results in graph format for frontend consumption.
        """
        graph_data = self.build_graph()
        return {
            'graph': graph_data,
            'addresses': self.results,
            'visited_count': len(self.visited),
            'max_depth': self.max_depth
        }
    
    def reset(self):
        self.visited.clear()
        self.results.clear()


api_gateway = APIGateway()
