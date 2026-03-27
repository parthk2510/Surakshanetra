from pathlib import Path
import shutil
import json
import logging
from typing import Dict, List, Any, Optional, Set, Tuple
from datetime import datetime
from collections import defaultdict
import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

logger = logging.getLogger(__name__)


class AddressDataAggregator:
    def __init__(self):
        self.addresses = {}
        self.relationships = []
        self.clusters = defaultdict(set)
        self.metadata = {
            'created_at': datetime.now().isoformat(),
            'addresses_count': 0,
            'transactions_count': 0,
            'total_value': 0
        }
    
    def add_address(self, address: str, data: Dict[str, Any]):
        if address not in self.addresses:
            self.addresses[address] = {
                'address': address,
                'balance': 0,
                'total_received': 0,
                'total_sent': 0,
                'tx_count': 0,
                'transactions': [],
                'utxos': [],
                'first_seen': None,
                'last_seen': None,
                'tags': set(),
                'risk_score': 0,
                'cluster_id': None
            }
        
        addr_info = self.addresses[address]
        addr_info['balance'] = data.get('balance', addr_info['balance'])
        addr_info['total_received'] = data.get('total_received', addr_info['total_received'])
        addr_info['total_sent'] = data.get('total_sent', addr_info['total_sent'])
        addr_info['tx_count'] = data.get('tx_count', addr_info['tx_count'])
        
        if 'transactions' in data:
            addr_info['transactions'].extend(data['transactions'])
        if 'utxos' in data:
            addr_info['utxos'].extend(data['utxos'])
        if 'tags' in data:
            addr_info['tags'].update(data.get('tags', []))
        
        timestamps = [tx.get('time') for tx in addr_info['transactions'] if tx.get('time')]
        if timestamps:
            addr_info['first_seen'] = min(timestamps)
            addr_info['last_seen'] = max(timestamps)
        
        self.metadata['addresses_count'] = len(self.addresses)
        self.metadata['transactions_count'] += len(data.get('transactions', []))
        self.metadata['total_value'] += data.get('total_received', 0)
    
    def link_addresses(self, addr1: str, addr2: str, relationship_type: str, metadata: Dict = None):
        self.relationships.append({
            'source': addr1,
            'target': addr2,
            'type': relationship_type,
            'metadata': metadata or {},
            'timestamp': datetime.now().isoformat()
        })
    
    def create_cluster(self, cluster_id: str, addresses: List[str]):
        self.clusters[cluster_id].update(addresses)
        for addr in addresses:
            if addr in self.addresses:
                self.addresses[addr]['cluster_id'] = cluster_id
    
    def get_graph_data(self) -> Dict[str, Any]:
        nodes = []
        edges = []
        
        for addr, data in self.addresses.items():
            nodes.append({
                'id': addr,
                'type': 'address',
                'label': addr[:12] + '...',
                'balance': data['balance'],
                'tx_count': data['tx_count'],
                'cluster_id': data['cluster_id'],
                'tags': list(data['tags'])
            })
        
        for rel in self.relationships:
            edges.append({
                'id': f"{rel['source']}->{rel['target']}",
                'source': rel['source'],
                'target': rel['target'],
                'type': rel['type']
            })
        
        return {
            'nodes': nodes,
            'edges': edges,
            'metadata': self.metadata,
            'clusters': {k: list(v) for k, v in self.clusters.items()}
        }


class TransactionProcessor:
    @staticmethod
    def process_transaction(tx: Dict[str, Any], source_address: str) -> Dict[str, Any]:
        processed = {
            'hash': tx.get('hash', ''),
            'time': tx.get('time', 0),
            'block_height': tx.get('block_height', 0),
            'confirmations': tx.get('confirmations', 0),
            'fee': tx.get('fee', 0),
            'size': tx.get('size', 0),
            'inputs': [],
            'outputs': [],
            'value_flow': {
                'total_input': 0,
                'total_output': 0,
                'net_change': 0
            }
        }
        
        for inp in tx.get('inputs', []):
            prev_out = inp.get('prev_out', {})
            processed['inputs'].append({
                'address': prev_out.get('addr', ''),
                'value': prev_out.get('value', 0),
                'script_type': prev_out.get('script', '')[:20]
            })
            processed['value_flow']['total_input'] += prev_out.get('value', 0)
        
        for out in tx.get('out', []):
            processed['outputs'].append({
                'address': out.get('addr', ''),
                'value': out.get('value', 0),
                'script_type': out.get('script', '')[:20],
                'spent': out.get('spent', False)
            })
            processed['value_flow']['total_output'] += out.get('value', 0)
        
        if source_address in [o['address'] for o in processed['outputs']]:
            processed['direction'] = 'incoming'
        elif source_address in [i['address'] for i in processed['inputs']]:
            processed['direction'] = 'outgoing'
        else:
            processed['direction'] = 'related'
        
        processed['value_flow']['net_change'] = processed['value_flow']['total_output'] - processed['value_flow']['total_input']
        
        return processed
    
    @staticmethod
    def extract_connected_addresses(tx: Dict[str, Any]) -> Set[str]:
        addresses = set()
        for inp in tx.get('inputs', []):
            if inp.get('address'):
                addresses.add(inp['address'])
        for out in tx.get('outputs', []):
            if out.get('address'):
                addresses.add(out['address'])
        return addresses
    
    @staticmethod
    def detect_patterns(transactions: List[Dict[str, Any]]) -> Dict[str, Any]:
        patterns = {
            'potential_mixers': [],
            'change_addresses': [],
            'peeling_chains': [],
            'round_numbers': [],
            'high_frequency': False
        }
        
        if len(transactions) > 100:
            patterns['high_frequency'] = True
        
        for tx in transactions:
            if len(tx.get('outputs', [])) > 10:
                patterns['potential_mixers'].append(tx['hash'])
            
            outputs = tx.get('outputs', [])
            if len(outputs) == 2:
                values = [o['value'] for o in outputs]
                if values[0] != values[1]:
                    smaller_idx = 0 if values[0] < values[1] else 1
                    patterns['change_addresses'].append(outputs[smaller_idx]['address'])
            
            for out in outputs:
                if out['value'] % 100000000 == 0:
                    patterns['round_numbers'].append(tx['hash'])
                    break
        
        return patterns


class CaseFileManager:
    def __init__(self, data_dir: str = "data/cases"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.active_cases = {}
    
    def create_case(self, case_id: str, metadata: Dict[str, Any] = None) -> str:
        case_path = self.data_dir / f"{case_id}.json"
        
        case_data = {
            'case_id': case_id,
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat(),
            'metadata': metadata or {},
            'addresses': {},
            'relationships': [],
            'clusters': {},
            'timeline': [],
            'notes': []
        }
        
        with open(case_path, 'w') as f:
            json.dump(case_data, f, indent=2)
        
        self.active_cases[case_id] = case_data
        return case_id
    
    def load_case(self, case_id: str) -> Optional[Dict[str, Any]]:
        case_path = self.data_dir / f"{case_id}.json"
        
        if case_path.exists():
            with open(case_path, 'r') as f:
                case_data = json.load(f)
                self.active_cases[case_id] = case_data
                return case_data
        
        return None
    
    def update_case(self, case_id: str, updates: Dict[str, Any]):
        if case_id in self.active_cases:
            case_data = self.active_cases[case_id]
        else:
            case_data = self.load_case(case_id)
            if not case_data:
                return False
        
        case_data['updated_at'] = datetime.now().isoformat()
        
        for key, value in updates.items():
            if key == 'addresses' and isinstance(value, dict):
                case_data['addresses'].update(value)
            elif key == 'relationships' and isinstance(value, list):
                case_data['relationships'].extend(value)
            elif key == 'clusters' and isinstance(value, dict):
                case_data['clusters'].update(value)
            elif key == 'timeline' and isinstance(value, list):
                case_data['timeline'].extend(value)
            else:
                case_data[key] = value
        
        case_path = self.data_dir / f"{case_id}.json"
        with open(case_path, 'w') as f:
            json.dump(case_data, f, indent=2)
        
        return True
    
    def get_case_addresses(self, case_id: str) -> List[str]:
        case_data = self.active_cases.get(case_id) or self.load_case(case_id)
        return list(case_data.get('addresses', {}).keys()) if case_data else []
    
    def list_cases(self) -> List[Dict[str, Any]]:
        cases = []
        for case_file in self.data_dir.glob("*.json"):
            try:
                with open(case_file, 'r') as f:
                    data = json.load(f)
                    cases.append({
                        'case_id': data['case_id'],
                        'created_at': data['created_at'],
                        'updated_at': data['updated_at'],
                        'address_count': len(data.get('addresses', {}))
                    })
            except:
                continue
        return cases


class JSONDataIngestor:
    def __init__(self, data_dir: str = "data", case_manager: CaseFileManager = None):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.graph_dir = self.data_dir / "graph"
        self.graph_dir.mkdir(exist_ok=True)
        self.cache_dir = self.data_dir / "cache"
        self.cache_dir.mkdir(exist_ok=True)
        
        self.case_manager = case_manager or CaseFileManager()
        self.aggregator = AddressDataAggregator()
        self.tx_processor = TransactionProcessor()
        
        self.address_cache = {}
        self.tx_cache = {}
        self.pending_addresses = set()
        
        logger.info(f"JSONDataIngestor initialized with data_dir: {self.data_dir}")
    
    def ingest_address_batch(self, addresses: List[str], case_id: Optional[str] = None, 
                            fetch_callback=None, max_workers: int = 3) -> Dict[str, Any]:
        results = {
            'success': [],
            'failed': [],
            'total': len(addresses),
            'case_id': case_id
        }
        
        if case_id and case_id not in self.case_manager.active_cases:
            self.case_manager.create_case(case_id, {'addresses': addresses})
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {}
            for addr in addresses:
                if fetch_callback:
                    future = executor.submit(self._ingest_single_address, addr, fetch_callback)
                    futures[future] = addr
            
            for future in as_completed(futures):
                addr = futures[future]
                try:
                    success = future.result()
                    if success:
                        results['success'].append(addr)
                    else:
                        results['failed'].append(addr)
                except Exception as e:
                    logger.error(f"Error ingesting {addr}: {e}")
                    results['failed'].append(addr)
        
        if case_id:
            self._update_case_with_aggregated_data(case_id)
        
        return results
    
    def _ingest_single_address(self, address: str, fetch_callback) -> bool:
        try:
            if address in self.address_cache:
                data = self.address_cache[address]
            else:
                data = fetch_callback(address)
                if not data:
                    return False
                self.address_cache[address] = data
            
            self._process_address_data(address, data)
            self._extract_relationships(address, data)
            self._save_address_snapshot(address, data)
            
            return True
        except Exception as e:
            logger.error(f"Failed to ingest {address}: {e}")
            return False
    
    def _process_address_data(self, address: str, data: Dict[str, Any]):
        txs = data.get('txs', []) or []

        processed_data = {
            'address': address,
            'balance': data.get('balance', 0) or data.get('final_balance', 0),
            'total_received': data.get('total_received', 0),
            'total_sent': data.get('total_sent', 0),
            'tx_count': int(data.get('n_tx') or len(txs)),
            'transactions': [],
            'utxos': data.get('unspent_outputs', []) or data.get('utxos', []),
            'tags': set()
        }
        
        for tx in txs[:100]:
            processed_tx = self.tx_processor.process_transaction(tx, address)
            processed_data['transactions'].append(processed_tx)
            self.tx_cache[processed_tx['hash']] = processed_tx
        
        patterns = self.tx_processor.detect_patterns(processed_data['transactions'])
        if patterns['potential_mixers']:
            processed_data['tags'].add('potential_mixer')
        if patterns['high_frequency']:
            processed_data['tags'].add('high_frequency')
        
        self.aggregator.add_address(address, processed_data)
    
    def _extract_relationships(self, address: str, data: Dict[str, Any]):
        connected_addresses = set()
        
        for tx in data.get('txs', [])[:50]:
            addresses = self.tx_processor.extract_connected_addresses(
                self.tx_processor.process_transaction(tx, address)
            )
            connected_addresses.update(addresses)
        
        for connected_addr in connected_addresses:
            if connected_addr != address:
                self.aggregator.link_addresses(
                    address, connected_addr, 'transacted_with',
                    {'tx_count': 1}
                )
                self.pending_addresses.add(connected_addr)
    
    def _save_address_snapshot(self, address: str, data: Dict[str, Any]):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        addr_hash = hashlib.sha256(address.encode()).hexdigest()[:12]
        filename = f"address_{addr_hash}_{timestamp}.json"
        
        filepath = self.cache_dir / filename
        with open(filepath, 'w') as f:
            json.dump({
                'address': address,
                'timestamp': timestamp,
                'data': data
            }, f, indent=2)
    
    def _update_case_with_aggregated_data(self, case_id: str):
        graph_data = self.aggregator.get_graph_data()
        
        self.case_manager.update_case(case_id, {
            'addresses': {
                addr: self.aggregator.addresses[addr] 
                for addr in self.aggregator.addresses
            },
            'relationships': self.aggregator.relationships,
            'clusters': graph_data['clusters'],
            'timeline': [{
                'timestamp': datetime.now().isoformat(),
                'event': 'data_ingestion',
                'addresses_added': len(self.aggregator.addresses)
            }]
        })
    
    def get_address_transactions(self, address: str, limit: int = 50) -> List[Dict[str, Any]]:
        if address in self.address_cache:
            data = self.aggregator.addresses.get(address, {})
            return data.get('transactions', [])[:limit]
        
        for json_file in self.cache_dir.glob(f"address_*_{address[:12]}*.json"):
            try:
                with open(json_file, 'r') as f:
                    data = json.load(f)
                    if data.get('address') == address:
                        return data.get('data', {}).get('txs', [])[:limit]
            except:
                continue
        
        return []
    
    def get_transaction_details(self, tx_hash: str) -> Optional[Dict[str, Any]]:
        return self.tx_cache.get(tx_hash)
    
    def get_pending_addresses(self) -> List[str]:
        return list(self.pending_addresses - set(self.address_cache.keys()))
    
    def get_graph_for_case(self, case_id: str) -> Dict[str, Any]:
        case_data = self.case_manager.load_case(case_id)
        if not case_data:
            return {}
        
        return self.aggregator.get_graph_data()
    
    def export_case_graph(self, case_id: str, format: str = 'json') -> str:
        graph_data = self.get_graph_for_case(case_id)
        
        if format == 'json':
            export_path = self.graph_dir / f"{case_id}_graph.json"
            with open(export_path, 'w') as f:
                json.dump(graph_data, f, indent=2)
        elif format == 'gexf':
            export_path = self.graph_dir / f"{case_id}_graph.gexf"
            self._export_to_gexf(graph_data, export_path)
        
        return str(export_path)
    
    def _export_to_gexf(self, graph_data: Dict[str, Any], filepath: Path):
        gexf_content = '<?xml version="1.0" encoding="UTF-8"?>\n'
        gexf_content += '<gexf xmlns="http://www.gexf.net/1.2draft" version="1.2">\n'
        gexf_content += '  <graph mode="static" defaultedgetype="directed">\n'
        gexf_content += '    <nodes>\n'
        
        for node in graph_data['nodes']:
            gexf_content += f'      <node id="{node["id"]}" label="{node["label"]}">\n'
            gexf_content += '        <attvalues>\n'
            gexf_content += f'          <attvalue for="balance" value="{node.get("balance", 0)}"/>\n'
            gexf_content += f'          <attvalue for="tx_count" value="{node.get("tx_count", 0)}"/>\n'
            gexf_content += '        </attvalues>\n'
            gexf_content += '      </node>\n'
        
        gexf_content += '    </nodes>\n'
        gexf_content += '    <edges>\n'
        
        for idx, edge in enumerate(graph_data['edges']):
            gexf_content += f'      <edge id="{idx}" source="{edge["source"]}" target="{edge["target"]}" />\n'
        
        gexf_content += '    </edges>\n'
        gexf_content += '  </graph>\n'
        gexf_content += '</gexf>\n'
        
        with open(filepath, 'w') as f:
            f.write(gexf_content)
    
    def get_address_statistics(self, address: str) -> Dict[str, Any]:
        data = self.aggregator.addresses.get(address)
        if not data:
            return {}
        
        transactions = data.get('transactions', [])
        
        return {
            'address': address,
            'balance': data.get('balance', 0),
            'total_received': data.get('total_received', 0),
            'total_sent': data.get('total_sent', 0),
            'tx_count': len(transactions),
            'first_seen': data.get('first_seen'),
            'last_seen': data.get('last_seen'),
            'tags': list(data.get('tags', [])),
            'cluster_id': data.get('cluster_id'),
            'avg_tx_value': sum(tx.get('value_flow', {}).get('total_output', 0) for tx in transactions) / len(transactions) if transactions else 0,
            'incoming_tx': len([tx for tx in transactions if tx.get('direction') == 'incoming']),
            'outgoing_tx': len([tx for tx in transactions if tx.get('direction') == 'outgoing'])
        }
    
    def merge_cases(self, target_case_id: str, source_case_ids: List[str]) -> bool:
        target_case = self.case_manager.load_case(target_case_id)
        if not target_case:
            return False
        
        for source_id in source_case_ids:
            source_case = self.case_manager.load_case(source_id)
            if source_case:
                self.case_manager.update_case(target_case_id, {
                    'addresses': source_case.get('addresses', {}),
                    'relationships': source_case.get('relationships', []),
                    'clusters': source_case.get('clusters', {})
                })
        
        return True
    
    def is_operational(self) -> bool:
        return self.data_dir.exists() and self.data_dir.is_dir()
    
    def clear_cache(self):
        self.address_cache.clear()
        self.tx_cache.clear()
        self.pending_addresses.clear()
    
    def close(self):
        self.clear_cache()
