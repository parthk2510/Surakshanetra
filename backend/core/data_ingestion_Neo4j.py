"""
Data Ingestion Layer for ChainBreak
Handles BlockCypher API integration and Neo4j data storage
"""

from abc import ABC, abstractmethod
from neo4j import GraphDatabase, Driver as Neo4jDriver
from blockcypher import get_address_details, get_transaction_details
import logging
import time
import json
import uuid
import traceback
from datetime import datetime
from typing import Dict, Any, List, Optional
from pathlib import Path

logger = logging.getLogger('data_ingestion')


class BaseDataIngestor(ABC):
    """Abstract base class for data ingestion"""
    
    @abstractmethod
    def ingest_address_data(self, address: str, blockchain: str = 'btc') -> bool:
        """Ingest data for a specific address"""
        pass
    
    @abstractmethod
    def get_address_transactions(self, address: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get transactions for an address"""
        pass
    
    @abstractmethod
    def get_transaction_details(self, tx_hash: str) -> Optional[Dict[str, Any]]:
        """Get details for a specific transaction"""
        pass
    
    @abstractmethod
    def is_operational(self) -> bool:
        """Check if the ingestor is operational"""
        pass


def _log_structured(level: str, event_name: str, mode: str = None, batch_id: str = None, row_number: int = None, **kwargs):
    """
    Log structured JSON-formatted messages.
    
    Args:
        level: Log level (INFO, WARNING, ERROR)
        event_name: Name of the event being logged
        mode: Current mode (neo4j, json, etc.)
        batch_id: Unique identifier for the batch (if applicable)
        row_number: Row number being processed (if applicable)
        **kwargs: Additional fields to include in the log
    """
    log_entry = {
        "event_name": event_name,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "level": level
    }
    
    if mode:
        log_entry["mode"] = mode
    if batch_id:
        log_entry["batch_id"] = batch_id
    if row_number is not None:
        log_entry["row_number"] = row_number
    
    log_entry.update(kwargs)
    
    # Log as JSON string
    log_message = json.dumps(log_entry)
    
    if level == "INFO":
        logger.info(log_message)
    elif level == "WARNING":
        logger.warning(log_message)
    elif level == "ERROR":
        logger.error(log_message)


class Neo4jDataIngestor(BaseDataIngestor):
    """Neo4j-based data ingestor for blockchain and UPI transaction data"""
    
    def __init__(self, uri: str, username: str, password: str):
        """
        Initialize Neo4j ingestor with connection details.
        
        Args:
            uri: Neo4j database URI
            username: Database username
            password: Database password (stored in memory only, never logged)
        """
        self.uri = uri
        self.username = username
        self.password = password
        self.driver = None
        self._connect()
    
    def _connect(self):
        """Establish Neo4j connection and setup database"""
        try:
            _log_structured(
                "INFO",
                "neo4j_connection_attempt",
                mode="neo4j"
            )
            
            self.driver = GraphDatabase.driver(
                self.uri,
                auth=(self.username, self.password),
                fetch_size=5000
            )
            
            # Test connection
            self._test_connection()
            
            # Setup database constraints and indexes
            self._setup_database()
            
            _log_structured(
                "INFO",
                "neo4j_connection_success",
                mode="neo4j"
            )
            
        except Exception as e:
            _log_structured(
                "ERROR",
                "neo4j_connection_failed",
                mode="neo4j",
                error_type=type(e).__name__,
                error_message=str(e)
            )
            raise
    
    def _test_connection(self):
        """Test Neo4j connection"""
        with self.driver.session() as session:
            session.run("RETURN 1")
    
    def _setup_database(self):
        """Setup database constraints and indexes"""
        with self.driver.session() as session:
            try:
                session.run("""
                    CREATE CONSTRAINT address_unique IF NOT EXISTS 
                    FOR (a:Address) REQUIRE a.address IS UNIQUE
                """)
                session.run("""
                    CREATE CONSTRAINT transaction_unique IF NOT EXISTS 
                    FOR (t:Transaction) REQUIRE t.tx_hash IS UNIQUE
                """)
                session.run("""
                    CREATE CONSTRAINT block_unique IF NOT EXISTS 
                    FOR (b:Block) REQUIRE b.block_hash IS UNIQUE
                """)
                
                # UPI constraints
                session.run("""
                    CREATE CONSTRAINT upi_account_unique IF NOT EXISTS 
                    FOR (u:UPI_Account) REQUIRE u.upi_id IS UNIQUE
                """)
                session.run("""
                    CREATE CONSTRAINT upi_transaction_unique IF NOT EXISTS 
                    FOR (ut:UPI_Transaction) REQUIRE ut.tx_id IS UNIQUE
                """)
                
                session.run("""
                    CREATE INDEX address_balance IF NOT EXISTS 
                    FOR (a:Address) ON (a.balance)
                """)
                session.run("""
                    CREATE INDEX transaction_value IF NOT EXISTS 
                    FOR (t:Transaction) ON (t.value)
                """)
                
                # UPI indexes
                session.run("""
                    CREATE INDEX upi_account_risk_score IF NOT EXISTS 
                    FOR (u:UPI_Account) ON (u.risk_score)
                """)
                session.run("""
                    CREATE INDEX upi_transaction_amount IF NOT EXISTS 
                    FOR (ut:UPI_Transaction) ON (ut.amount)
                """)
                session.run("""
                    CREATE INDEX upi_transaction_timestamp IF NOT EXISTS 
                    FOR (ut:UPI_Transaction) ON (ut.timestamp)
                """)
                
                logger.info("Database constraints and indexes set up successfully")
            except Exception as e:
                logger.warning(f"Some database setup operations failed: {e}")
    
    def ingest_address_data(self, address: str, blockchain: str = 'btc') -> bool:
        """Ingest blockchain data for an address"""
        try:
            logger.info(f"Ingesting data for address: {address}")
            
            # Get address details from BlockCypher
            address_data = get_address_details(address, coin_symbol=blockchain)
            if not address_data:
                logger.warning(f"No data found for address: {address}")
                return False
            
            # Create address node
            self._create_address_node(address, address_data)
            
            # Ingest transactions
            self._ingest_transactions(address, address_data.get('txrefs', []))
            
            logger.info(f"Successfully ingested data for address: {address}")
            return True
            
        except Exception as e:
            logger.error(f"Error ingesting data for address {address}: {str(e)}")
            return False
    
    def get_address_transactions(self, address: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get transactions for an address from Neo4j"""
        try:
            with self.driver.session() as session:
                result = session.run("""
                    MATCH (a:Address {address: $address})-[:PARTICIPATED_IN]->(t:Transaction)
                    RETURN t ORDER BY t.timestamp DESC LIMIT $limit
                """, address=address, limit=limit)
                return [dict(record['t']) for record in result]
        except Exception as e:
            logger.error(f"Error getting transactions for {address}: {e}")
            return []
    
    def get_transaction_details(self, tx_hash: str) -> Optional[Dict[str, Any]]:
        """Get transaction details from Neo4j"""
        try:
            with self.driver.session() as session:
                result = session.run("""
                    MATCH (t:Transaction {tx_hash: $tx_hash})
                    RETURN t
                """, tx_hash=tx_hash)
                record = result.single()
                return dict(record['t']) if record else None
        except Exception as e:
            logger.error(f"Error getting transaction {tx_hash}: {e}")
            return None
    
    def is_operational(self) -> bool:
        """Check if Neo4j connection is operational"""
        try:
            with self.driver.session() as session:
                session.run("RETURN 1")
            return True
        except:
            return False
    
    def _create_address_node(self, address: str, address_data: Dict[str, Any]):
        """Create or update address node in Neo4j"""
        with self.driver.session() as session:
            session.run("""
                MERGE (a:Address {address: $address})
                SET a.balance = $balance,
                    a.total_received = $total_received,
                    a.total_sent = $total_sent,
                    a.n_tx = $n_tx,
                    a.last_updated = datetime()
            """, address=address, 
                 balance=address_data.get('balance', 0),
                 total_received=address_data.get('total_received', 0),
                 total_sent=address_data.get('total_sent', 0),
                 n_tx=address_data.get('n_tx', 0))
    
    def _ingest_transactions(self, address: str, transactions: List[Dict[str, Any]]):
        """Ingest transaction data into Neo4j"""
        for tx in transactions:
            try:
                self._create_transaction_nodes(tx, address)
            except Exception as e:
                logger.warning(f"Failed to ingest transaction {tx.get('tx_hash', 'unknown')}: {e}")
                continue
    
    def _create_transaction_nodes(self, tx_data: Dict[str, Any], source_address: str):
        """Create transaction and related nodes"""
        tx_hash = tx_data.get('tx_hash')
        if not tx_hash:
            return
        
        with self.driver.session() as session:
            # Create transaction node
            session.run("""
                MERGE (t:Transaction {tx_hash: $tx_hash})
                SET t.value = $value,
                    t.timestamp = $timestamp,
                    t.block_height = $block_height,
                    t.confirmations = $confirmations
            """, tx_hash=tx_hash,
                 value=tx_data.get('value', 0),
                 timestamp=tx_data.get('confirmed', ''),
                 block_height=tx_data.get('block_height', 0),
                 confirmations=tx_data.get('confirmations', 0))
            
            # Create relationships
            session.run("""
                MATCH (a:Address {address: $address})
                MATCH (t:Transaction {tx_hash: $tx_hash})
                MERGE (a)-[:PARTICIPATED_IN]->(t)
            """, address=source_address, tx_hash=tx_hash)
    
    def ingest_upi_transactions(self, transactions: List[Dict[str, Any]], db_mode: str = None) -> Dict[str, Any]:
        """
        Ingest UPI transactions into Neo4j with comprehensive logging and validation.
        
        Args:
            transactions: List of transaction dictionaries
            db_mode: Database mode (e.g., 'neo4j', 'json')
        
        Returns:
            Dictionary containing ingestion summary and statistics
        """
        start_time = time.time()
        ingestion_id = str(uuid.uuid4())[:8]
        
        # Initialize result structure
        result = {
            "success": False,
            "ingestion_id": ingestion_id,
            "total_rows_read": len(transactions),
            "valid_rows_processed": 0,
            "rows_skipped": 0,
            "nodes_created": 0,
            "nodes_matched": 0,
            "relationships_created": 0,
            "batches_processed": 0,
            "batches_failed": 0,
            "execution_time_ms": 0,
            "error": None
        }
        
        _log_structured(
            "INFO",
            "ingestion_started",
            mode=db_mode or "unknown",
            ingestion_id=ingestion_id,
            total_rows=len(transactions)
        )
        
        # Step 1: Strict Neo4j mode validation
        if db_mode != "neo4j":
            error_msg = f"Ingestion aborted: DB_MODE is '{db_mode}', expected 'neo4j'"
            _log_structured(
                "ERROR",
                "ingestion_aborted_mode_mismatch",
                mode=db_mode,
                ingestion_id=ingestion_id,
                reason="DB_MODE is not 'neo4j'"
            )
            result["error"] = error_msg
            result["execution_time_ms"] = round((time.time() - start_time) * 1000, 2)
            return result
        
        # Step 2: Verify Neo4j driver is initialized
        if not self.driver:
            error_msg = "Ingestion aborted: Neo4j driver is not initialized"
            _log_structured(
                "ERROR",
                "ingestion_aborted_driver_not_initialized",
                mode="neo4j",
                ingestion_id=ingestion_id,
                reason="Neo4j driver is not initialized"
            )
            result["error"] = error_msg
            result["execution_time_ms"] = round((time.time() - start_time) * 1000, 2)
            return result
        
        # Step 3: Verify session can be opened
        try:
            with self.driver.session() as test_session:
                test_session.run("RETURN 1")
            _log_structured(
                "INFO",
                "neo4j_connection_verified",
                mode="neo4j",
                ingestion_id=ingestion_id
            )
        except Exception as e:
            error_msg = f"Ingestion aborted: Cannot open Neo4j session - {str(e)}"
            _log_structured(
                "ERROR",
                "ingestion_aborted_connection_failed",
                mode="neo4j",
                ingestion_id=ingestion_id,
                reason="Cannot open Neo4j session",
                error_type=type(e).__name__
            )
            result["error"] = error_msg
            result["execution_time_ms"] = round((time.time() - start_time) * 1000, 2)
            return result
        
        # Step 4: Validate and filter transactions
        valid_transactions = []
        for idx, tx in enumerate(transactions, start=1):
            tx_id = tx.get('id')
            sender_upi = tx.get('from')
            receiver_upi = tx.get('to')
            
            # Skip rows with missing required fields
            if not tx_id or not sender_upi or not receiver_upi:
                _log_structured(
                    "WARNING",
                    "row_skipped_missing_fields",
                    mode="neo4j",
                    ingestion_id=ingestion_id,
                    row_number=idx,
                    reason="Missing required fields (id, from, or to)"
                )
                result["rows_skipped"] += 1
                continue
            
            valid_transactions.append(tx)
        
        result["valid_rows_processed"] = len(valid_transactions)
        
        if not valid_transactions:
            _log_structured(
                "WARNING",
                "ingestion_aborted_no_valid_rows",
                mode="neo4j",
                ingestion_id=ingestion_id,
                reason="No valid transactions to ingest"
            )
            result["error"] = "No valid transactions to ingest"
            result["execution_time_ms"] = round((time.time() - start_time) * 1000, 2)
            return result
        
        _log_structured(
            "INFO",
            "transactions_validated",
            mode="neo4j",
            ingestion_id=ingestion_id,
            valid_count=len(valid_transactions),
            skipped_count=result["rows_skipped"]
        )
        
        # Step 5: Process in batches
        batch_size = 5000
        total_batches = (len(valid_transactions) + batch_size - 1) // batch_size
        
        for batch_num in range(total_batches):
            batch_start = batch_num * batch_size
            batch_end = min(batch_start + batch_size, len(valid_transactions))
            batch = valid_transactions[batch_start:batch_end]
            batch_id = f"{ingestion_id}_batch{batch_num + 1}"
            
            _log_structured(
                "INFO",
                "batch_processing_started",
                mode="neo4j",
                ingestion_id=ingestion_id,
                batch_id=batch_id,
                batch_number=batch_num + 1,
                total_batches=total_batches,
                batch_size=len(batch)
            )
            
            try:
                batch_result = self._ingest_upi_transaction_batch_hardened(batch, batch_id)
                
                result["nodes_created"] += batch_result["nodes_created"]
                result["nodes_matched"] += batch_result["nodes_matched"]
                result["relationships_created"] += batch_result["relationships_created"]
                result["batches_processed"] += 1
                
                _log_structured(
                    "INFO",
                    "batch_commit_success",
                    mode="neo4j",
                    ingestion_id=ingestion_id,
                    batch_id=batch_id,
                    nodes_created=batch_result["nodes_created"],
                    nodes_matched=batch_result["nodes_matched"],
                    relationships_created=batch_result["relationships_created"]
                )
                
            except Exception as e:
                result["batches_failed"] += 1
                _log_structured(
                    "ERROR",
                    "batch_commit_failed",
                    mode="neo4j",
                    ingestion_id=ingestion_id,
                    batch_id=batch_id,
                    error_type=type(e).__name__,
                    error_message=str(e)
                )
                logger.error(f"Batch {batch_id} failed: {traceback.format_exc()}")
        
        # Step 6: Final summary
        result["success"] = result["batches_processed"] > 0
        result["execution_time_ms"] = round((time.time() - start_time) * 1000, 2)
        
        if result["success"]:
            _log_structured(
                "INFO",
                "ingestion_completed_success",
                mode="neo4j",
                ingestion_id=ingestion_id,
                total_rows_read=result["total_rows_read"],
                valid_rows_processed=result["valid_rows_processed"],
                rows_skipped=result["rows_skipped"],
                nodes_created=result["nodes_created"],
                nodes_matched=result["nodes_matched"],
                relationships_created=result["relationships_created"],
                batches_processed=result["batches_processed"],
                batches_failed=result["batches_failed"],
                execution_time_ms=result["execution_time_ms"]
            )
        else:
            _log_structured(
                "ERROR",
                "ingestion_completed_failure",
                mode="neo4j",
                ingestion_id=ingestion_id,
                error=result["error"] or "All batches failed",
                execution_time_ms=result["execution_time_ms"]
            )
        
        return result
    
    def _ingest_upi_transaction_batch_hardened(self, transactions: List[Dict[str, Any]], batch_id: str) -> Dict[str, Any]:
        """
        Ingest a batch of UPI transactions using UNWIND for maximum throughput.
        3 queries total (accounts, transactions, relationships) instead of 5 per row.
        """
        result = {"nodes_created": 0, "nodes_matched": 0, "relationships_created": 0}

        # Build flat list of account records (senders + receivers de-duped in Python to optimize Neo4j)
        account_dict = {}
        tx_rows = []
        rel_rows = []

        for tx_data in transactions:
            tx_id       = tx_data.get('id')
            sender_upi  = tx_data.get('from')
            receiver_upi = tx_data.get('to')
            if not tx_id or not sender_upi or not receiver_upi:
                continue
            ts = tx_data.get('timestamp', 0)
            
            # Keep the highest timestamp for last_active
            if sender_upi not in account_dict or ts > account_dict[sender_upi]:
                account_dict[sender_upi] = ts
            if receiver_upi not in account_dict or ts > account_dict[receiver_upi]:
                account_dict[receiver_upi] = ts

            tx_rows.append({
                'tx_id':     tx_id,
                'amount':    float(tx_data.get('amount', 0)),
                'timestamp': ts,
                'status':    tx_data.get('status', 'unknown'),
                'pattern':   tx_data.get('pattern', ''),
                'label':     tx_data.get('label', ''),
            })
            rel_rows.append({'sender': sender_upi, 'receiver': receiver_upi, 'tx_id': tx_id})

        account_rows = [{'upi_id': k, 'timestamp': v} for k, v in account_dict.items()]

        if not tx_rows:
            return result

        with self.driver.session() as session:
            with session.begin_transaction() as tx:
                try:
                    # 1) Upsert all accounts in one UNWIND
                    tx.run("""
                        UNWIND $rows AS row
                        MERGE (u:UPI_Account {upi_id: row.upi_id})
                        ON CREATE SET u.created_at   = datetime(),
                                      u.first_seen   = row.timestamp,
                                      u.last_active  = row.timestamp
                        ON MATCH  SET u.last_active  = CASE
                            WHEN u.last_active IS NULL OR row.timestamp > u.last_active
                            THEN row.timestamp ELSE u.last_active END
                    """, rows=account_rows)

                    # 2) Insert all transactions in one UNWIND (using CREATE for speed since txs are unique)
                    tx.run("""
                        UNWIND $rows AS row
                        MERGE (t:UPI_Transaction {tx_id: row.tx_id})
                        ON CREATE SET
                            t.amount     = row.amount,
                            t.timestamp  = row.timestamp,
                            t.status     = row.status,
                            t.pattern    = row.pattern,
                            t.label      = row.label,
                            t.created_at = datetime()
                        """, rows=tx_rows)

                    # 3) Create all transaction relationships in one UNWIND
                    tx.run("""
                        UNWIND $rows AS row
                        MATCH (s:UPI_Account    {upi_id: row.sender})
                        MATCH (r:UPI_Account    {upi_id: row.receiver})
                        MATCH (t:UPI_Transaction {tx_id:  row.tx_id})
                        MERGE (s)-[:SENT]->(t)
                        MERGE (r)-[:RECEIVED]->(t)
                    """, rows=rel_rows)

                    # 4) Create TRANSACTED_WITH relationships using deduplicated pairs to prevent supernode locking
                    unique_pairs = list({ (r['sender'], r['receiver']) for r in rel_rows })
                    pair_rows = [{'sender': s, 'receiver': r} for s, r in unique_pairs]
                    
                    tx.run("""
                        UNWIND $rows AS row
                        MATCH (s:UPI_Account {upi_id: row.sender})
                        MATCH (r:UPI_Account {upi_id: row.receiver})
                        MERGE (s)-[:TRANSACTED_WITH]->(r)
                    """, rows=pair_rows)

                    tx.commit()

                    result["nodes_created"]       = len(tx_rows) * 2  # approximate
                    result["relationships_created"] = len(rel_rows) * 3

                except Exception as e:
                    tx.rollback()
                    raise e

        return result

    
    def update_upi_account_risk_scores(self, account_risks: Dict[str, Dict[str, Any]]) -> bool:
        """Update UPI account risk scores in Neo4j using bulk UNWIND operations for efficiency."""
        try:
            logger.info(f"Updating risk scores for {len(account_risks)} UPI accounts")
            
            updates = []
            for upi_id, risk_data in account_risks.items():
                in_c = risk_data.get('inCounterparties', 0)
                out_c = risk_data.get('outCounterparties', 0)
                in_c_val = in_c if isinstance(in_c, int) else len(in_c or set())
                out_c_val = out_c if isinstance(out_c, int) else len(out_c or set())
                
                updates.append({
                    'upi_id': upi_id,
                    'risk_score': risk_data.get('riskScore', 0.0),
                    'risk_band': risk_data.get('riskBand', 'minimal'),
                    'reason_codes': risk_data.get('reasonCodes', []),
                    'total_in_amount': risk_data.get('totalInAmount', 0.0),
                    'total_out_amount': risk_data.get('totalOutAmount', 0.0),
                    'in_tx_count': risk_data.get('inTxCount', 0),
                    'out_tx_count': risk_data.get('outTxCount', 0),
                    'in_counterparties': in_c_val,
                    'out_counterparties': out_c_val
                })
                
            query = """
                UNWIND $updates AS risk
                MERGE (account:UPI_Account {upi_id: risk.upi_id})
                SET account.risk_score = risk.risk_score,
                    account.risk_band = risk.risk_band,
                    account.reason_codes = risk.reason_codes,
                    account.total_in_amount = risk.total_in_amount,
                    account.total_out_amount = risk.total_out_amount,
                    account.in_tx_count = risk.in_tx_count,
                    account.out_tx_count = risk.out_tx_count,
                    account.in_counterparties = risk.in_counterparties,
                    account.out_counterparties = risk.out_counterparties,
                    account.last_updated = datetime()
                    
                WITH account, risk
                // Lookup by accountId (indexed via unique constraint)
                OPTIONAL MATCH (a1:Account {accountId: risk.upi_id})
                SET a1.riskScore = risk.risk_score,
                    a1.riskLevel = risk.risk_band,
                    a1.riskFactors = risk.reason_codes
                    
                WITH account, risk
                // Lookup by upiId (now indexed)
                OPTIONAL MATCH (a2:Account {upiId: risk.upi_id})
                SET a2.riskScore = risk.risk_score,
                    a2.riskLevel = risk.risk_band,
                    a2.riskFactors = risk.reason_codes
            """
            
            # Write in batches of 5000
            batch_size = 5000
            with self.driver.session() as session:
                for upi_id, risk_data in account_risks.items():
                    try:
                        session.run("""
                            MERGE (account:UPI_Account {upi_id: $upi_id})
                            SET account.risk_score = $risk_score,
                                account.risk_band = $risk_band,
                                account.reason_codes = $reason_codes,
                                account.total_in_amount = $total_in_amount,
                                account.total_out_amount = $total_out_amount,
                                account.in_tx_count = $in_tx_count,
                                account.out_tx_count = $out_tx_count,
                                account.in_counterparties = $in_counterparties,
                                account.out_counterparties = $out_counterparties,
                                account.last_updated = datetime()
                        """, upi_id=upi_id,
                             risk_score=risk_data.get('riskScore', 0),
                             risk_band=risk_data.get('riskBand', 'minimal'),
                             reason_codes=risk_data.get('reasonCodes', []),
                             total_in_amount=risk_data.get('totalInAmount', 0),
                             total_out_amount=risk_data.get('totalOutAmount', 0),
                             in_tx_count=risk_data.get('inTxCount', 0),
                             out_tx_count=risk_data.get('outTxCount', 0),
                             in_counterparties=len(risk_data.get('inCounterparties', set())),
                             out_counterparties=len(risk_data.get('outCounterparties', set())))
                    except Exception as e:
                        logger.warning(f"Failed to update risk score batch starting at idx {i}: {e}")
            
            logger.info(f"Successfully updated risk scores for {len(account_risks)} UPI accounts")
            return True
            
        except Exception as e:
            logger.error(f"Error updating UPI account risk scores: {str(e)}")
            return False
            
    
    def get_upi_account_info(self, upi_id: str) -> Optional[Dict[str, Any]]:
        """Get UPI account information from Neo4j"""
        try:
            with self.driver.session() as session:
                result = session.run("""
                    MATCH (account:UPI_Account {upi_id: $upi_id})
                    RETURN account
                """, upi_id=upi_id)
                record = result.single()
                return dict(record['account']) if record else None
        except Exception as e:
            logger.error(f"Error getting UPI account info for {upi_id}: {e}")
            return None
    
    def get_upi_transaction_count(self) -> int:
        """Get total count of UPI transactions in Neo4j"""
        try:
            with self.driver.session() as session:
                result = session.run("""
                    MATCH (tx:UPI_Transaction)
                    RETURN count(tx) as count
                """)
                return result.single()['count']
        except Exception as e:
            logger.error(f"Error getting UPI transaction count: {e}")
            return 0

    def close(self):
        """Close Neo4j driver connection"""
        if hasattr(self, 'driver'):
            self.driver.close()



