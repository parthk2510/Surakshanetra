"""
UPI Neo4j Community Detection with Fingerprinting
===================================================
Loads UPI transaction CSV into Neo4j, runs community detection
(NetworkX greedy_modularity_communities), generates behavioral
fingerprints per account, stores results back in Neo4j.

CSV Column mapping:
    tx_id, timestamp, sender_id, sender_upi, sender_role, sender_device_id, sender_ip_subnet,
    sender_session_count_day, sender_unique_counterparties_24h, sender_amount_velocity_1h,
    sender_degree, receiver_id, receiver_upi, receiver_role, receiver_device_id, receiver_ip_subnet,
    receiver_session_count_day, receiver_unique_counterparties_24h, receiver_amount_velocity_1h,
    receiver_degree, amount_inr, status, pattern, label
"""

import logging
import re
import pandas as pd  # type: ignore
import numpy as np  # type: ignore
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from collections import defaultdict

logger = logging.getLogger('src.upi_neo4j_community')

# ─────────────────────────────────────────────────────────────────────────────
# Community detection imports (NetworkX only — no external louvain dependency)
# ─────────────────────────────────────────────────────────────────────────────
try:
    import networkx as nx
    from networkx.algorithms.community import greedy_modularity_communities
    HAS_NETWORKX = True
except ImportError:
    HAS_NETWORKX = False
    logger.warning(
        "networkx not available — install with: pip install networkx")


# ─────────────────────────────────────────────────────────────────────────────
# ID normalisation (applied once before any Neo4j MERGE)
# ─────────────────────────────────────────────────────────────────────────────

def _normalise_upi(raw: str) -> str:
    """Strip, lowercase, and remove characters outside [a-z0-9@._-].

    Applied to every sender/receiver UPI ID before it is written to Neo4j so
    that the same logical account is never stored under two different keys
    (e.g. ' User@Paytm ' vs 'user@paytm').
    """
    val = str(raw).strip().lower()
    val = re.sub(r"[^\w@.\-]", "", val)
    return val


# ─────────────────────────────────────────────────────────────────────────────
# Schema helpers
# ─────────────────────────────────────────────────────────────────────────────

def ensure_schema(driver) -> None:
    """
    Create all required constraints and indexes if they don't exist.
    """
    statements = [
        "CREATE CONSTRAINT IF NOT EXISTS FOR (a:UPI_Account) REQUIRE a.upi_id IS UNIQUE",
        "CREATE CONSTRAINT IF NOT EXISTS FOR (t:UPI_Transaction) REQUIRE t.tx_id IS UNIQUE",
        "CREATE INDEX IF NOT EXISTS FOR (a:UPI_Account) ON (a.risk_score)",
        "CREATE INDEX IF NOT EXISTS FOR (a:UPI_Account) ON (a.communityId)",
        "CREATE INDEX IF NOT EXISTS FOR (t:UPI_Transaction) ON (t.amount)",
    ]
    with driver.session(database="neo4j") as session:
        for stmt in statements:
            try:
                session.run(stmt)
            except Exception as exc:
                logger.debug("Schema statement skipped (%s): %s",
                             stmt[:60], exc)
    logger.info("Schema ensured (constraints + indexes)")


def seed_test_data(driver) -> bool:
    """
    Populate minimal test data when the database is empty.
    Uses UPI_Account + UPI_Transaction schema (matches get_neo4j_graph).
    Returns True if seed data was inserted, False if data already existed.
    """
    with driver.session(database="neo4j") as session:
        count = session.run(
            "MATCH (a:UPI_Account) RETURN count(a) AS n").single()["n"]
        if count > 0:
            logger.info(
                "Database already has %d UPI_Account nodes — skipping seed", count)
            return False

    logger.info("Database is empty — inserting seed test data")
    seed_transactions = [
        # (tx_id, src_upi, dst_upi, amount, src_type, dst_type, src_device, dst_device, src_ip, dst_ip)
        ("TX001", "acc_a@upi", "acc_b@upi", 5000.0,  "NORMAL",
         "NORMAL",         "DEV_1", "DEV_2", "192.168.1", "192.168.2"),
        ("TX002", "acc_b@upi", "acc_c@upi", 4800.0,  "MULE_COLLECTOR",
         "MULE_LAYER",     "DEV_2", "DEV_3", "192.168.2", "10.0.1"),
        ("TX003", "acc_c@upi", "acc_d@upi", 4600.0,  "MULE_LAYER",
         "MULE_SINK",      "DEV_3", "DEV_4", "10.0.1",    "10.0.2"),
        ("TX004", "acc_e@upi", "acc_f@upi", 2000.0,  "NORMAL",
         "NORMAL",         "DEV_5", "DEV_6", "172.16.1",  "172.16.2"),
        ("TX005", "acc_f@upi", "acc_g@upi", 1900.0,  "NORMAL",
         "NORMAL",         "DEV_6", "DEV_7", "172.16.2",  "172.16.3"),
        ("TX006", "acc_h@upi", "acc_b@upi", 3000.0,  "NORMAL",
         "MULE_COLLECTOR", "DEV_1", "DEV_2", "192.168.1", "192.168.2"),
        ("TX007", "acc_a@upi", "acc_c@upi", 1500.0,  "NORMAL",
         "MULE_LAYER",     "DEV_1", "DEV_3", "192.168.1", "10.0.1"),
        ("TX008", "acc_d@upi", "acc_i@upi", 4400.0,  "MULE_SINK",
         "NORMAL",         "DEV_4", "DEV_8", "10.0.2",    "10.0.3"),
    ]

    query = """
    UNWIND $rows AS r
    MERGE (src:UPI_Account {upi_id: r.src_upi})
      ON CREATE SET src.accountType  = r.src_type,
                    src.communityId  = null,
                    src.risk_score   = 0.0,
                    src.deviceHashes = CASE WHEN r.src_dev <> '' THEN [r.src_dev] ELSE [] END,
                    src.ipSubnets    = CASE WHEN r.src_ip  <> '' THEN [r.src_ip]  ELSE [] END,
                    src.created_at   = datetime()
    MERGE (dst:UPI_Account {upi_id: r.dst_upi})
      ON CREATE SET dst.accountType  = r.dst_type,
                    dst.communityId  = null,
                    dst.risk_score   = 0.0,
                    dst.deviceHashes = CASE WHEN r.dst_dev <> '' THEN [r.dst_dev] ELSE [] END,
                    dst.ipSubnets    = CASE WHEN r.dst_ip  <> '' THEN [r.dst_ip]  ELSE [] END,
                    dst.created_at   = datetime()
    MERGE (t:UPI_Transaction {tx_id: r.tx_id})
      ON CREATE SET t.amount    = r.amount,
                    t.timestamp = toString(datetime()),
                    t.status    = 'SUCCESS',
                    t.pattern   = 'NORMAL',
                    t.label     = 'seed',
                    t.source_ip = r.src_ip,
                    t.target_ip = r.dst_ip
    MERGE (src)-[:SENT]->(t)
    MERGE (dst)-[:RECEIVED]->(t)
    """
    rows = [
        {
            "tx_id": t[0], "src_upi": t[1], "dst_upi": t[2], "amount": t[3],
            "src_type": t[4], "dst_type": t[5],
            "src_dev": t[6], "dst_dev": t[7],
            "src_ip": t[8], "dst_ip": t[9],
        }
        for t in seed_transactions
    ]
    with driver.session(database="neo4j") as session:
        session.run(query, rows=rows)

    logger.info("Seed data inserted: %d transactions", len(seed_transactions))
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Step 1: Load CSV into Neo4j
# ─────────────────────────────────────────────────────────────────────────────

def load_upi_csv_to_neo4j(csv_path: str, driver, batch_size: int = 50000) -> Dict[str, Any]:
    """
    Parse the UPI transaction CSV and load it into Neo4j.

    Creates:
        - (Account) nodes for senders and receivers
        - (Device)  nodes linked via [:USED_DEVICE]
        - [:TRANSACTED] relationships for each transaction

    Args:
        csv_path:   Path to upi_mule_dataset.csv
        driver:     Neo4j driver instance
        batch_size: Number of rows per batch

    Returns:
        Summary dict with counts
    """
    csv_file = Path(csv_path)
    if not csv_file.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    logger.info("Loading CSV: %s", csv_path)
    df = pd.read_csv(csv_path)
    logger.info("Read %d rows from CSV", len(df))

    ensure_schema(driver)

    total_rows = len(df)
    loaded_tx = 0
    errors = 0

    for start in range(0, total_rows, batch_size):
        batch_df = df.iloc[start:start + batch_size]
        transactions: List[Dict] = []

        for _, row in batch_df.iterrows():
            try:
                # Normalise UPI IDs once here so the same logical account
                # is never stored under two different Neo4j keys.
                src_upi = _normalise_upi(row.get('sender_upi', ''))
                dst_upi = _normalise_upi(row.get('receiver_upi', ''))
                if not src_upi or not dst_upi:
                    errors += 1
                    continue

                tx = {
                    'transactionId':            str(row.get('tx_id', '')),
                    'timestamp':                str(row.get('timestamp', '')),
                    'sourceAccount':            str(row.get('sender_id', '')),
                    'sourceUPI':                src_upi,
                    'sourceType':               str(row.get('sender_role', 'NORMAL')),
                    'sourceDeviceHash':         str(row.get('sender_device_id', '')),
                    'sourceIP':                 str(row.get('sender_ip_subnet', '')),
                    'sourceDegree':             int(row.get('sender_degree', 0)),
                    'sourceSessionCount':       int(row.get('sender_session_count_day', 0)),
                    'sourceUniqueCounterparties': int(row.get('sender_unique_counterparties_24h', 0)),
                    'sourceAmountVelocity':     float(row.get('sender_amount_velocity_1h', 0.0)),
                    'targetAccount':            str(row.get('receiver_id', '')),
                    'targetUPI':                dst_upi,
                    'targetType':               str(row.get('receiver_role', 'NORMAL')),
                    'targetDeviceHash':         str(row.get('receiver_device_id', '')),
                    'targetIP':                 str(row.get('receiver_ip_subnet', '')),
                    'targetDegree':             int(row.get('receiver_degree', 0)),
                    'targetSessionCount':       int(row.get('receiver_session_count_day', 0)),
                    'targetUniqueCounterparties': int(row.get('receiver_unique_counterparties_24h', 0)),
                    'targetAmountVelocity':     float(row.get('receiver_amount_velocity_1h', 0.0)),
                    'amount':                   float(row.get('amount_inr', 0.0)),
                    'status':                   str(row.get('status', 'UNKNOWN')),
                    'pattern':                  str(row.get('pattern', 'NORMAL')),
                    'label':                    str(row.get('label', 'unknown')),
                }
                transactions.append(tx)
            except Exception as exc:
                errors += 1
                logger.debug("Row parse error at index %d: %s", start, exc)
                continue

        if transactions:
            count = _batch_load_transactions(driver, transactions)
            loaded_tx += count
            logger.info("Loaded batch %d–%d: %d transactions",
                        start, start + batch_size, count)

    logger.info(
        "CSV load complete: %d transactions loaded, %d row errors", loaded_tx, errors)
    return {
        'totalRows':          total_rows,
        'transactionsLoaded': loaded_tx,
        'rowErrors':          errors,
        'timestamp':          datetime.utcnow().isoformat(),
    }


def _create_schema(driver):
    """Create indexes and constraints for performance."""
    queries = [
        "CREATE CONSTRAINT IF NOT EXISTS FOR (a:Account) REQUIRE a.accountId IS UNIQUE",
        "CREATE INDEX IF NOT EXISTS FOR (a:Account) ON (a.accountType)",
        "CREATE INDEX IF NOT EXISTS FOR (a:Account) ON (a.riskScore)",
        "CREATE INDEX IF NOT EXISTS FOR (a:Account) ON (a.communityId)",
        "CREATE INDEX IF NOT EXISTS FOR (t:Transaction) ON (t.transactionId)",
    ]
    with driver.session(database="neo4j") as session:
        for q in queries:
            try:
                session.run(q)
            except Exception as e:
                logger.debug(f"Schema query skipped: {e}")


def _batch_load_transactions(driver, transactions: List[Dict]) -> int:
    """Load a batch of transactions into Neo4j using MERGE."""
    query = """
    UNWIND $transactions AS tx

    // ── 1. Merge UPI_Account nodes ─────────────────────────────────────────
    MERGE (src:UPI_Account {upi_id: tx.sourceUPI})
    ON CREATE SET
        src.accountType              = tx.sourceType,
        src.communityId              = null,
        src.risk_score               = 0.0,
        src.deviceHashes             = CASE WHEN tx.sourceDeviceHash <> '' THEN [tx.sourceDeviceHash] ELSE [] END,
        src.ipSubnets                = CASE WHEN tx.sourceIP <> ''          THEN [tx.sourceIP]          ELSE [] END,
        src.degree                   = tx.sourceDegree,
        src.session_count            = tx.sourceSessionCount,
        src.unique_counterparties_24h = tx.sourceUniqueCounterparties,
        src.amount_velocity_1h       = tx.sourceAmountVelocity,
        src.created_at               = datetime()
    ON MATCH SET
        src.accountType  = CASE WHEN src.accountType = 'NORMAL' THEN tx.sourceType ELSE src.accountType END,
        src.deviceHashes = CASE
            WHEN tx.sourceDeviceHash <> '' AND NOT tx.sourceDeviceHash IN coalesce(src.deviceHashes, [])
            THEN coalesce(src.deviceHashes, []) + [tx.sourceDeviceHash]
            ELSE src.deviceHashes END,
        src.ipSubnets = CASE
            WHEN tx.sourceIP <> '' AND NOT tx.sourceIP IN coalesce(src.ipSubnets, [])
            THEN coalesce(src.ipSubnets, []) + [tx.sourceIP]
            ELSE src.ipSubnets END

    MERGE (dst:UPI_Account {upi_id: tx.targetUPI})
    ON CREATE SET
        dst.accountType              = tx.targetType,
        dst.communityId              = null,
        dst.risk_score               = 0.0,
        dst.deviceHashes             = CASE WHEN tx.targetDeviceHash <> '' THEN [tx.targetDeviceHash] ELSE [] END,
        dst.ipSubnets                = CASE WHEN tx.targetIP <> ''          THEN [tx.targetIP]          ELSE [] END,
        dst.degree                   = tx.targetDegree,
        dst.session_count            = tx.targetSessionCount,
        dst.unique_counterparties_24h = tx.targetUniqueCounterparties,
        dst.amount_velocity_1h       = tx.targetAmountVelocity,
        dst.created_at               = datetime()
    ON MATCH SET
        dst.accountType  = CASE WHEN dst.accountType = 'NORMAL' THEN tx.targetType ELSE dst.accountType END,
        dst.deviceHashes = CASE
            WHEN tx.targetDeviceHash <> '' AND NOT tx.targetDeviceHash IN coalesce(dst.deviceHashes, [])
            THEN coalesce(dst.deviceHashes, []) + [tx.targetDeviceHash]
            ELSE dst.deviceHashes END,
        dst.ipSubnets = CASE
            WHEN tx.targetIP <> '' AND NOT tx.targetIP IN coalesce(dst.ipSubnets, [])
            THEN coalesce(dst.ipSubnets, []) + [tx.targetIP]
            ELSE dst.ipSubnets END

    // ── 2. Merge UPI_Transaction node ───────────────────────────────────────
    MERGE (t:UPI_Transaction {tx_id: tx.transactionId})
    ON CREATE SET
        t.timestamp = tx.timestamp,
        t.amount    = tx.amount,
        t.status    = tx.status,
        t.pattern   = tx.pattern,
        t.label     = tx.label,
        t.source_ip = tx.sourceIP,
        t.target_ip = tx.targetIP

    // ── 3. SENT / RECEIVED relationships (always created) ──────────────────
    MERGE (src)-[:SENT]->(t)
    MERGE (dst)-[:RECEIVED]->(t)
    RETURN count(t) AS loaded
    """
    with driver.session(database="neo4j") as session:
        result = session.run(query, transactions=transactions)
        record = result.single()
        return int(record["loaded"]) if record else 0


# ─────────────────────────────────────────────────────────────────────────────
# Step 2: Extract graph from Neo4j for analysis
# ─────────────────────────────────────────────────────────────────────────────

def get_neo4j_graph(driver, limit: Optional[int] = None) -> Dict[str, Any]:
    """
    Query Neo4j and return nodes + edges as Python dicts.

    Args:
        limit: Maximum number of transaction rows to read. None = no limit (full graph).

    Returns:
        {'nodes': [...], 'edges': [...]}
    """
    limit_clause = f"LIMIT {int(limit)}" if limit else ""
    query = f"""
    MATCH (src:UPI_Account)-[:SENT]->(t:UPI_Transaction)<-[:RECEIVED]-(dst:UPI_Account)
    RETURN
        src.upi_id      AS src_id,
        src.upi_id      AS src_upi,
        coalesce(src.accountType, 'NORMAL') AS src_type,
        src.risk_score  AS src_risk,
        src.communityId AS src_comm,
        dst.upi_id      AS dst_id,
        dst.upi_id      AS dst_upi,
        coalesce(dst.accountType, 'NORMAL') AS dst_type,
        dst.risk_score  AS dst_risk,
        dst.communityId AS dst_comm,
        t.amount        AS amount,
        t.timestamp     AS ts,
        t.status        AS status,
        t.pattern       AS pattern,
        t.label         AS label
    {limit_clause}
    """
    nodes_map: Dict[str, Dict] = {}
    edges: List[Dict] = []

    with driver.session(database="neo4j") as session:
        result = session.run(query)
        for record in result:
            src_id = record["src_id"]
            dst_id = record["dst_id"]

            if src_id and src_id not in nodes_map:
                nodes_map[src_id] = {
                    "id":          src_id,
                    "upiId":       record["src_upi"],
                    "accountType": record["src_type"],
                    "riskScore":   _safe_float(record["src_risk"]),
                    "communityId": record["src_comm"],
                    "nodeType":    "Account",
                }
            if dst_id and dst_id not in nodes_map:
                nodes_map[dst_id] = {
                    "id":          dst_id,
                    "upiId":       record["dst_upi"],
                    "accountType": record["dst_type"],
                    "riskScore":   _safe_float(record["dst_risk"]),
                    "communityId": record["dst_comm"],
                    "nodeType":    "Account",
                }

            edges.append({
                "source":    src_id,
                "target":    dst_id,
                "amount":    _safe_float(record["amount"]),
                "timestamp": str(record["ts"]) if record["ts"] else None,
                "status":    record["status"],
                "pattern":   record["pattern"],
                "label":     record["label"],
                "edgeType":  "TRANSACTED",
            })

    return {"nodes": list(nodes_map.values()), "edges": edges}


def _safe_float(value: Any, default: float = 0.0) -> float:
    """
    Convert any Neo4j numeric value to float.
    Handles None, int, float, and rejects non-numeric types that would
    cause TypeError if len() were called on them.
    """
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        logger.warning(
            "Could not convert risk score value %r to float — using %.1f", value, default)
        return default


# ─────────────────────────────────────────────────────────────────────────────
# Step 3: Community detection on the graph from Neo4j
# ─────────────────────────────────────────────────────────────────────────────

def run_community_detection_neo4j(
    driver,
    algorithm: str = 'greedy_modularity',
    resolution: float = 1.0,
) -> Dict[str, Any]:
    """
    Run community detection on the Neo4j graph and write communityId back to nodes.

    Preference order:
        1. Neo4j GDS Louvain (if GDS plugin is installed) — uses the full
           in-memory graph, no Python memory overhead, writes communityId
           atomically back to every UPI_Account node.
        2. NetworkX algorithms (fallback when GDS is not available):
           'greedy_modularity' - Clauset-Newman-Moore (default fallback)
           'label_prop'        - Label propagation
           'wcc'               - Weakly Connected Components (fastest)

    Args:
        driver:     Neo4j driver
        algorithm:  Preferred NetworkX algorithm used only when GDS is absent.
        resolution: Resolution hint (informational; passed through for logging).

    Returns:
        Summary dict with community statistics

    Raises:
        ImportError:  if neither GDS nor networkx is available
        ValueError:   if the graph is empty (no Account nodes or no edges)
    """
    # ── Prefer GDS: it runs on the full graph with no Python memory copy ──────
    gds_version = _check_gds_available(driver)
    if gds_version:
        logger.info(
            "GDS %s available — delegating to run_gds_community_detection "
            "(ignoring algorithm='%s')",
            gds_version, algorithm,
        )
        return run_gds_community_detection(driver)

    # ── GDS not available: fall through to NetworkX ───────────────────────────
    if not HAS_NETWORKX:
        raise ImportError(
            "Neither Neo4j GDS nor networkx is available. "
            "Install GDS plugin or: pip install networkx"
        )

    logger.info(
        "GDS not available — running NetworkX '%s' on graph fetched from Neo4j",
        algorithm,
    )

    graph_data = get_neo4j_graph(driver)
    account_nodes = [n for n in graph_data["nodes"]
                     if n.get("nodeType") == "Account"]
    tx_edges = [e for e in graph_data["edges"]
                if e.get("edgeType") == "TRANSACTED"]

    # ── Guard: empty graph ───────────────────────────────────────────────────
    if not account_nodes:
        raise ValueError(
            "Community detection requires at least one Account node in Neo4j. "
            "Load data first (load_upi_csv_to_neo4j or seed_test_data)."
        )
    if not tx_edges:
        raise ValueError(
            "Community detection requires at least one TRANSACTED edge in Neo4j. "
            "The graph has accounts but no transactions — load transaction data first."
        )

    logger.info("Graph has %d account nodes and %d transaction edges",
                len(account_nodes), len(tx_edges))

    # ── Build NetworkX graph (Account-only, undirected for community algos) ──
    G_directed = nx.DiGraph()
    for node in account_nodes:
        nid = node["id"]
        if nid:
            G_directed.add_node(
                nid, **{k: v for k, v in node.items() if k != "id"})

    for edge in tx_edges:
        src, dst = edge["source"], edge["target"]
        if not src or not dst:
            continue
        # Only add edges between Account nodes (skip if a node was filtered out)
        if src not in G_directed or dst not in G_directed:
            continue
        weight = _safe_float(edge.get("amount"), default=1.0) or 1.0
        if G_directed.has_edge(src, dst):
            G_directed[src][dst]["weight"] = G_directed[src][dst].get(
                "weight", 0.0) + weight
            G_directed[src][dst]["count"] = G_directed[src][dst].get(
                "count", 0) + 1
        else:
            G_directed.add_edge(src, dst, weight=weight, count=1)

    # Undirected view for community algorithms
    G = G_directed.to_undirected()

    if G.number_of_nodes() == 0:
        raise ValueError(
            "No Account nodes were added to the NetworkX graph. Check data integrity.")
    if G.number_of_edges() == 0:
        raise ValueError(
            "No edges between Account nodes in the NetworkX graph. "
            "A graph without links has an undefined modularity — aborting."
        )

    logger.info("NetworkX graph: %d nodes, %d edges (undirected)",
                G.number_of_nodes(), G.number_of_edges())

    # ── Run community detection ───────────────────────────────────────────────
    partition: Dict[str, int] = {}

    if algorithm == "label_prop":
        communities_gen = nx.community.label_propagation_communities(G)
        for comm_id, comm_set in enumerate(communities_gen):
            for node_id in comm_set:
                partition[node_id] = comm_id

    elif algorithm == "wcc":
        for comm_id, component in enumerate(nx.weakly_connected_components(G_directed)):
            for node_id in component:
                partition[node_id] = comm_id

    else:
        # Default: greedy_modularity_communities (Clauset-Newman-Moore)
        if algorithm not in ("greedy_modularity",):
            logger.warning(
                "Unknown algorithm '%s' — falling back to greedy_modularity", algorithm)
        communities_list = list(
            greedy_modularity_communities(G, weight="weight"))
        for comm_id, comm_set in enumerate(communities_list):
            for node_id in comm_set:
                partition[node_id] = comm_id

    communities: Dict[int, List[str]] = defaultdict(list)
    for node_id, comm_id in partition.items():
        communities[comm_id].append(node_id)

    num_communities = len(communities)
    logger.info("Found %d communities using '%s'", num_communities, algorithm)

    # ── Modularity ────────────────────────────────────────────────────────────
    modularity = 0.0
    if partition and G.number_of_edges() > 0:
        try:
            community_sets = [set(members) for members in communities.values()]
            modularity = nx.community.modularity(G, community_sets)
        except Exception as exc:
            logger.warning("Modularity computation failed: %s", exc)

    # ── Write results back to Neo4j ──────────────────────────────────────────
    _write_communities_to_neo4j(driver, partition)

    community_summary = _build_community_summary(communities, account_nodes)

    return {
        "algorithm":      algorithm,
        "resolution":     resolution,
        "numCommunities": num_communities,
        "modularity":     round(float(modularity), 4),
        "totalNodes":     len(account_nodes),
        "totalEdges":     len(tx_edges),
        "communities":    community_summary,
        "timestamp":      datetime.utcnow().isoformat(),
    }


def _write_communities_to_neo4j(driver, partition: Dict[str, int]) -> None:
    """Write communityId assignments back to Account nodes in Neo4j."""
    if not partition:
        return
    updates = [{"accountId": node_id, "communityId": comm_id}
               for node_id, comm_id in partition.items()]
    query = """
    UNWIND $updates AS u
    MATCH (a:UPI_Account {upi_id: u.accountId})
    SET a.communityId = u.communityId
    """
    batch_size = 1000
    for i in range(0, len(updates), batch_size):
        batch = updates[i:i + batch_size]
        with driver.session(database="neo4j") as session:
            session.run(query, updates=batch)

    logger.info(f"Wrote {len(updates)} communityId assignments to Neo4j")


def _build_community_summary(
    communities: Dict[int, List[str]],
    nodes: List[Dict],
) -> List[Dict]:
    """Build per-community statistics with type-safe risk score handling."""
    node_info = {n["id"]: n for n in nodes}
    summary = []

    for comm_id, members in communities.items():
        # _safe_float ensures we always have scalar floats — no len() on integers
        risk_scores = [_safe_float(node_info.get(
            m, {}).get("riskScore")) for m in members]

        mule_types = {"MULE_COLLECTOR", "MULE_SINK", "MULE_LAYER"}
        mule_count = sum(
            1 for m in members
            if node_info.get(m, {}).get("accountType") in mule_types
        )

        avg_risk = float(np.mean(risk_scores)) if risk_scores else 0.0
        max_risk = float(np.max(risk_scores)) if risk_scores else 0.0

        if avg_risk >= 70 or mule_count > 0:
            risk_level = "critical"
        elif avg_risk >= 50:
            risk_level = "high"
        elif avg_risk >= 30:
            risk_level = "medium"
        else:
            risk_level = "low"

        summary.append({
            "communityId":  comm_id,
            "memberCount":  len(members),
            "muleCount":    mule_count,
            "avgRiskScore": round(avg_risk, 2),
            "maxRiskScore": round(max_risk, 2),
            "riskLevel":    risk_level,
        })

    summary.sort(key=lambda x: (x["muleCount"],
                 x["avgRiskScore"]), reverse=True)
    return summary


# ─────────────────────────────────────────────────────────────────────────────
# Step 4: Fingerprinting on Neo4j data
# ─────────────────────────────────────────────────────────────────────────────

def run_fingerprinting_neo4j(driver, csv_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Compute behavioral fingerprints for all accounts using:
      - CSV fields (degree, session_count, ip_subnet, device_hash, amount_velocity)
      - Transaction history from Neo4j

    Writes riskScore, riskLevel, riskFactors, fingerprintHash to Account nodes.

    Returns:
        Summary of fingerprinting results
    """
    try:
        from .upi_fingerprinting import UPIFingerprinter  # type: ignore
    except ImportError:
        from backend.upi_fingerprinting import UPIFingerprinter  # type: ignore

    fingerprinter = UPIFingerprinter()

    account_query = """
    MATCH (a:UPI_Account)
    OPTIONAL MATCH (a)-[:SENT]->(r_out:UPI_Transaction)<-[:RECEIVED]-(dst:UPI_Account)
    OPTIONAL MATCH (src2:UPI_Account)-[:SENT]->(r_in:UPI_Transaction)<-[:RECEIVED]-(a)
    WITH a,
         collect(DISTINCT {
             transactionId:    r_out.tx_id,
             timestamp:        r_out.timestamp,
             amount:           r_out.amount,
             status:           r_out.status,
             sourceAccount:    a.upi_id,
             targetAccount:    dst.upi_id,
             sourceIP:         '',
             sourceDeviceHash: ''
         }) AS outTxs,
         collect(DISTINCT {
             transactionId:    r_in.tx_id,
             timestamp:        r_in.timestamp,
             amount:           r_in.amount,
             status:           r_in.status,
             sourceAccount:    src2.upi_id,
             targetAccount:    a.upi_id,
             sourceIP:         '',
             sourceDeviceHash: ''
         }) AS inTxs
    RETURN a.upi_id      AS accountId,
           a.upi_id      AS upiId,
           coalesce(a.accountType, 'NORMAL') AS accountType,
           ''            AS ipSubnet,
           ''            AS deviceHash,
           0             AS degree,
           outTxs, inTxs
    """

    processed = 0
    high_risk = 0
    fingerprint_results: List[Dict] = []

    with driver.session(database="neo4j") as session:
        account_records = list(session.run(account_query))

    logger.info("Computing fingerprints for %d accounts", len(account_records))

    for record in account_records:
        account_id = record["accountId"]
        if not account_id:
            continue

        account_data = {
            "accountId":   account_id,
            "upiId":       record["upiId"],
            "accountType": record["accountType"],
            "ipSubnet":    record["ipSubnet"],
            "deviceHash":  record["deviceHash"],
        }

        txs = []
        for tx in (record.get("outTxs") or []):
            if tx and tx.get("transactionId"):
                txs.append(dict(tx))
        for tx in (record.get("inTxs") or []):
            if tx and tx.get("transactionId"):
                txs.append(dict(tx))

        fingerprint = fingerprinter.generate_fingerprint(account_data, txs)
        risk_score = _safe_float(fingerprint.get("riskScore", 0))
        risk_level = fingerprint.get("riskLevel", "minimal")
        risk_factors = fingerprint.get("riskFactors", [])
        fp_hash = fingerprint.get("fingerprintHash", "")

        _write_fingerprint_to_neo4j(driver, account_id, risk_score, risk_level, risk_factors, fp_hash)

        processed += 1
        if risk_score >= 60:
            high_risk += 1

        fingerprint_results.append({
            'accountId': account_id,
            'riskScore': round(risk_score, 2),
            'riskLevel': risk_level,
            'riskFactors': risk_factors,
        })

    logger.info(
        "Fingerprinting complete: %d accounts processed, %d high-risk", processed, high_risk)

    return {
        "accountsProcessed": processed,
        "highRiskAccounts":  high_risk,
        "timestamp":         datetime.utcnow().isoformat(),
        "topHighRisk": sorted(
            [r for r in fingerprint_results if r["riskScore"] >= 50],
            key=lambda x: x["riskScore"],
            reverse=True,
        )[:20],
    }


def _write_fingerprint_to_neo4j(driver, account_id: str, risk_score: float,
                                 risk_level: str, risk_factors: List[str], fp_hash: str):
    query = """
    MATCH (a:UPI_Account {upi_id: $accountId})
    SET a.risk_score        = $riskScore,
        a.risk_band         = $riskLevel,
        a.risk_factors      = $riskFactors,
        a.fingerprintHash   = $fpHash,
        a.lastFingerprintAt = datetime()
    """
    with driver.session(database="neo4j") as session:
        session.run(
            query,
            accountId=account_id,
            riskScore=float(risk_score),
            riskLevel=risk_level,
            riskFactors=risk_factors or [],
            fpHash=fp_hash
        )


# ─────────────────────────────────────────────────────────────────────────────
# Step 5: Mule detection results from Neo4j
# ─────────────────────────────────────────────────────────────────────────────

def get_mule_detection_results(
    driver,
    min_risk: float = 50.0,
    limit: int = 200,
) -> Dict[str, Any]:
    """
    Query Neo4j for high-risk accounts with community + fingerprint information.
    Detects footprint anomalies like multiple IP subnets or device hashes.
    """
    account_query = """
    MATCH (a:UPI_Account)
    WHERE coalesce(a.risk_score, 0) >= $minRisk
       OR coalesce(a.accountType, 'NORMAL') IN ['MULE_COLLECTOR', 'MULE_SINK', 'MULE_LAYER']
       OR size(coalesce(a.deviceHashes, [])) > 1
       OR size(coalesce(a.ipSubnets, []))    > 1
    OPTIONAL MATCH (a)-[:SENT]->(r_out:UPI_Transaction)<-[:RECEIVED]-(dst)
    OPTIONAL MATCH (src2:UPI_Account)-[:SENT]->(r_in:UPI_Transaction)<-[:RECEIVED]-(a)
    WITH a,
         count(DISTINCT dst)   AS uniqueDest,
         count(DISTINCT src2)  AS uniqueSrc,
         count(DISTINCT r_out) AS outTx,
         count(DISTINCT r_in)  AS inTx,
         sum(coalesce(r_out.amount, 0)) AS outAmt,
         sum(coalesce(r_in.amount,  0)) AS inAmt
    RETURN a.upi_id       AS accountId,
           a.upi_id       AS upiId,
           coalesce(a.accountType, 'NORMAL') AS accountType,
           a.risk_score   AS riskScore,
           a.risk_band    AS riskLevel,
           a.risk_factors AS riskFactors,
           a.communityId  AS communityId,
           coalesce(a.ipSubnets,    []) AS ipSubnets,
           coalesce(a.deviceHashes, []) AS deviceHashes,
           size(coalesce(a.deviceHashes, [])) > 1 AS multiDeviceFlag,
           size(coalesce(a.ipSubnets,    [])) > 1 AS multiLocationFlag,
           uniqueDest, uniqueSrc, outTx, inTx, outAmt, inAmt
    ORDER BY coalesce(a.risk_score, 0) DESC
    LIMIT $limit
    """

    community_query = """
    MATCH (a:UPI_Account)
    WHERE a.communityId IS NOT NULL
    WITH a.communityId AS commId,
         count(a) AS total,
         sum(CASE WHEN coalesce(a.risk_score, 0) >= 60
                    OR size(coalesce(a.deviceHashes, [])) > 1
                    OR size(coalesce(a.ipSubnets, [])) > 1
                  THEN 1 ELSE 0 END) AS highRiskCount,
         sum(CASE WHEN coalesce(a.accountType, 'NORMAL') IN ['MULE_COLLECTOR','MULE_SINK','MULE_LAYER']
                  THEN 1 ELSE 0 END) AS muleCount,
         avg(coalesce(a.risk_score, 0)) AS avgRisk
    WHERE highRiskCount > 0 OR muleCount > 0
    RETURN commId, total, highRiskCount, muleCount, round(avgRisk, 2) AS avgRisk
    ORDER BY muleCount DESC, avgRisk DESC
    LIMIT 50
    """

    tx_velocity_query = """
    MATCH (a:UPI_Account {upi_id: $accId})-[:SENT]->(r:UPI_Transaction)
    WHERE r.timestamp IS NOT NULL
    RETURN r.timestamp AS ts, '' AS ip
    ORDER BY r.timestamp ASC
    """

    mule_accounts: List[Dict] = []
    community_summary: List[Dict] = []

    with driver.session(database="neo4j") as session:
        account_records = list(session.run(account_query, minRisk=float(min_risk), limit=limit))
        community_records = list(session.run(community_query))

    for record in account_records:
        base_risk = _safe_float(record["riskScore"])
        factors = list(record["riskFactors"] or [])

        if record["multiLocationFlag"] and "MULTIPLE_LOCATIONS" not in factors:
            factors.append("MULTIPLE_LOCATIONS")
            base_risk = max(base_risk, 85.0)
        if record["multiDeviceFlag"] and "MULTIPLE_DEVICES" not in factors:
            factors.append("MULTIPLE_DEVICES")
            base_risk = max(base_risk, 80.0)

        velocity_anomaly = False

        if velocity_anomaly and "FAST_LOCATION_CHANGE" not in factors:
            factors.append("FAST_LOCATION_CHANGE")
            base_risk = max(base_risk, 90.0)

        subnets = list(record["ipSubnets"] or [])
        devices = list(record["deviceHashes"] or [])

        # FIX: record["riskLevel"] via dict access, not getattr
        stored_risk_level = record["riskLevel"] or "unknown"
        effective_risk_level = "critical" if base_risk >= 70 else stored_risk_level

        mule_accounts.append({
            "accountId":          record["accountId"],
            "upiId":              record["upiId"],
            "accountType":        record["accountType"],
            "riskScore":          round(base_risk, 2),
            "riskLevel":          effective_risk_level,
            "riskFactors":        factors,
            "communityId":        record["communityId"],
            "ipSubnets":          subnets,
            "deviceHashes":       devices,
            # Backward-compat scalar fields for UI
            "ipSubnet":           subnets[0] if subnets else "",
            "deviceHash":         devices[0] if devices else "",
            "multiDeviceFlag":    bool(record["multiDeviceFlag"]),
            "multiLocationFlag":  bool(record["multiLocationFlag"]),
            "velocityAnomalyFlag": velocity_anomaly,
            "outTransactions":    int(record["outTx"]),
            "inTransactions":     int(record["inTx"]),
            "uniqueDestinations": int(record["uniqueDest"]),
            "uniqueSources":      int(record["uniqueSrc"]),
            "outAmount":          round(_safe_float(record["outAmt"]), 2),
            "inAmount":           round(_safe_float(record["inAmt"]),  2),
        })

    # ── Community summary ─────────────────────────────────────────────────
    for record in community_records:
        community_summary.append({
            "communityId":      record["commId"],
            "totalMembers":     int(record["total"]),
            "highRiskCount":    int(record["highRiskCount"]),
            "muleCount":        int(record["muleCount"]),
            "avgRiskScore":     _safe_float(record["avgRisk"]),
            "riskLevel":        "critical" if record["muleCount"] > 0 else "high",
        })

    mule_networks = _detect_mule_networks_from_neo4j(mule_accounts)

    risk_scores_list = [a["riskScore"] for a in mule_accounts]
    return {
        "muleAccounts":            mule_accounts,
        "suspiciousCommunities":   community_summary,
        "muleNetworks":            mule_networks,
        "summary": {
            "totalMuleAccounts":          len(mule_accounts),
            "totalSuspiciousCommunities": len(community_summary),
            "totalNetworks":              len(mule_networks),
            "avgRiskScore":               round(
                float(np.mean(risk_scores_list)) if risk_scores_list else 0.0, 2
            ),
        },
        "timestamp": datetime.utcnow().isoformat(),
    }


def _detect_mule_networks_from_neo4j(mule_accounts: List[Dict]) -> List[Dict]:
    """Group mule accounts into networks by shared IP subnet or device hash."""
    networks_by_ip:     Dict[str, List[str]] = defaultdict(list)
    networks_by_device: Dict[str, List[str]] = defaultdict(list)

    for acc in mule_accounts:
        for ip in acc.get("ipSubnets", []):
            if ip:
                networks_by_ip[ip].append(acc["accountId"])
        for dev in acc.get("deviceHashes", []):
            if dev:
                networks_by_device[dev].append(acc["accountId"])

    networks: List[Dict] = []
    seen_keys: set = set()
    net_idx = 0

    for ip, members in networks_by_ip.items():
        if len(members) >= 2:
            key = frozenset(members)
            if key not in seen_keys:
                seen_keys.add(key)
                networks.append({
                    "networkId":    f"network_ip_{net_idx}",
                    "clusterType":  "SHARED_IP_SUBNET",
                    "clusterKey":   ip,
                    "members":      members,
                    "totalMembers": len(members),
                })
                net_idx += 1

    for device, members in networks_by_device.items():
        if len(members) >= 2:
            key = frozenset(members)
            if key not in seen_keys:
                seen_keys.add(key)
                networks.append({
                    "networkId":    f"network_dev_{net_idx}",
                    "clusterType":  "SHARED_DEVICE",
                    "clusterKey":   str(device)[:16] + "...",
                    "members":      members,
                    "totalMembers": len(members),
                })
                net_idx += 1

    networks.sort(key=lambda x: x["totalMembers"], reverse=True)
    return networks[:50]


# ─────────────────────────────────────────────────────────────────────────────
# Step 6: Graph statistics
# ─────────────────────────────────────────────────────────────────────────────

def get_neo4j_graph_stats(driver) -> Dict[str, Any]:
    """Return basic graph statistics from Neo4j."""
    query = """
    MATCH (a:UPI_Account)
    OPTIONAL MATCH (a)-[:SENT]->(r:UPI_Transaction)
    WITH count(DISTINCT a)           AS totalAccounts,
         count(r)                    AS totalTransactions,
         count(DISTINCT a.communityId) AS numCommunities,
         sum(CASE WHEN coalesce(a.risk_score, 0) >= 80
                  THEN 1 ELSE 0 END) AS criticalRisk,
         sum(CASE WHEN coalesce(a.risk_score, 0) >= 60
                   AND coalesce(a.risk_score, 0) <  80
                  THEN 1 ELSE 0 END) AS highRisk,
         sum(CASE WHEN coalesce(a.accountType, 'NORMAL') IN ['MULE_COLLECTOR','MULE_SINK','MULE_LAYER']
                  THEN 1 ELSE 0 END) AS knownMules
    RETURN totalAccounts, totalTransactions, numCommunities,
           criticalRisk, highRisk, knownMules
    """
    with driver.session(database="neo4j") as session:
        record = session.run(query).single()
        if record:
            return {
                "totalAccounts":       record["totalAccounts"],
                "totalTransactions":   record["totalTransactions"],
                "numCommunities":      record["numCommunities"],
                "criticalRiskAccounts": record["criticalRisk"],
                "highRiskAccounts":    record["highRisk"],
                "knownMuleAccounts":   record["knownMules"],
            }
    return {}


# ─────────────────────────────────────────────────────────────────────────────
# Database size verification (Cypher)
# ─────────────────────────────────────────────────────────────────────────────

def verify_database_size(driver) -> Dict[str, Any]:
    """
    Run lightweight Cypher COUNT queries to report the current database size.

    Useful before kicking off heavy operations (community detection, fingerprinting)
    to confirm data was loaded correctly and to estimate runtime.

    Returns:
        Dict with keys: accountCount, txCount, sentRels, receivedRels,
                        withCommunity, numCommunities
    """
    queries = {
        "accountCount":  "MATCH (a:UPI_Account)      RETURN count(a)  AS n",
        "txCount":       "MATCH (t:UPI_Transaction)   RETURN count(t)  AS n",
        "sentRels":      "MATCH ()-[:SENT]->()         RETURN count(*)  AS n",
        "receivedRels":  "MATCH ()-[:RECEIVED]->()     RETURN count(*)  AS n",
        "withCommunity": "MATCH (a:UPI_Account) WHERE a.communityId IS NOT NULL RETURN count(a) AS n",
        "numCommunities":"MATCH (a:UPI_Account) WHERE a.communityId IS NOT NULL RETURN count(DISTINCT a.communityId) AS n",
    }
    stats: Dict[str, Any] = {}
    with driver.session(database="neo4j") as session:
        for key, q in queries.items():
            try:
                record = session.run(q).single()
                stats[key] = int(record["n"]) if record else 0
            except Exception as exc:
                stats[key] = f"error: {exc}"
    logger.info("DB size verification: %s", stats)
    return stats


# ─────────────────────────────────────────────────────────────────────────────
# GDS community detection (Louvain via Neo4j Graph Data Science)
# ─────────────────────────────────────────────────────────────────────────────

def _check_gds_available(driver) -> Optional[str]:
    """Return the GDS version string if the plugin is installed, else None."""
    try:
        with driver.session(database="neo4j") as session:
            record = session.run("RETURN gds.version() AS v").single()
            return str(record["v"]) if record else None
    except Exception:
        return None


def _read_community_stats_from_neo4j(driver) -> List[Dict]:
    """
    Read per-community statistics after GDS has written communityId back to nodes.
    Matches the shape produced by _build_community_summary so downstream code
    works identically whether GDS or NetworkX ran the detection.
    """
    query = """
    MATCH (a:UPI_Account)
    WHERE a.communityId IS NOT NULL
    WITH a.communityId AS commId,
         count(a)                               AS memberCount,
         avg(coalesce(a.risk_score, 0))         AS avgRisk,
         max(coalesce(a.risk_score, 0))         AS maxRisk,
         sum(CASE WHEN coalesce(a.accountType, 'NORMAL')
                       IN ['MULE_COLLECTOR','MULE_SINK','MULE_LAYER']
                  THEN 1 ELSE 0 END)            AS muleCount
    RETURN commId, memberCount, avgRisk, maxRisk, muleCount
    ORDER BY muleCount DESC, avgRisk DESC
    """
    summary: List[Dict] = []
    with driver.session(database="neo4j") as session:
        for record in session.run(query):
            avg_risk = _safe_float(record["avgRisk"])
            mule_count = int(record["muleCount"])
            if avg_risk >= 70 or mule_count > 0:
                risk_level = "critical"
            elif avg_risk >= 50:
                risk_level = "high"
            elif avg_risk >= 30:
                risk_level = "medium"
            else:
                risk_level = "low"
            summary.append({
                "communityId":  record["commId"],
                "memberCount":  int(record["memberCount"]),
                "muleCount":    mule_count,
                "avgRiskScore": round(avg_risk, 2),
                "maxRiskScore": round(_safe_float(record["maxRisk"]), 2),
                "riskLevel":    risk_level,
            })
    return summary


def run_gds_community_detection(
    driver,
    write_property: str = "communityId",
) -> Dict[str, Any]:
    """
    Run Louvain community detection via Neo4j GDS and write communityId back to
    every UPI_Account node in one atomic GDS call.

    GDS operates on the full in-memory projection of the graph — there is no
    row-level LIMIT, so every account and transaction in the database is used.

    The Cypher projection bridges the indirect
        (UPI_Account)-[:SENT]->(UPI_Transaction)<-[:RECEIVED]-(UPI_Account)
    path into a direct weighted relationship that GDS can process.

    After the write, the per-community stats are read back from Neo4j and
    returned in the same shape as _build_community_summary so all downstream
    analytics (mule detection, fingerprinting lookups) work unchanged.

    Falls back to NetworkX greedy_modularity if GDS is not installed.

    Args:
        driver:         Active Neo4j driver.
        write_property: Node property name to write the community integer into.
                        Defaults to 'communityId' (matches the existing schema).

    Returns:
        Summary dict with algorithm, numCommunities, modularity, communities list.
    """
    GRAPH_NAME = "upi_comm_proj"

    gds_version = _check_gds_available(driver)
    if not gds_version:
        logger.info(
            "GDS plugin not found — falling back to NetworkX greedy_modularity"
        )
        return run_community_detection_neo4j(driver, algorithm="greedy_modularity")

    logger.info("GDS %s detected — running gds.louvain on full graph", gds_version)

    with driver.session(database="neo4j") as session:
        # ── Drop stale projection if it exists from a previous aborted run ───
        try:
            session.run("CALL gds.graph.drop($name, false)", name=GRAPH_NAME)
            logger.debug("Dropped pre-existing GDS projection '%s'", GRAPH_NAME)
        except Exception:
            pass

        # ── Cypher projection: Account nodes + weighted direct edges ─────────
        # gds.graph.project.cypher works with GDS 1.x and 2.x.
        _proj_cypher_standard = """
            CALL gds.graph.project.cypher(
              $name,
              'MATCH (a:UPI_Account) RETURN id(a) AS id',
              'MATCH (src:UPI_Account)-[:SENT]->(t:UPI_Transaction)
                      <-[:RECEIVED]-(dst:UPI_Account)
               RETURN id(src) AS source, id(dst) AS target,
                      coalesce(t.amount, 1.0) AS weight'
            )
            YIELD nodeCount, relationshipCount
            """
        _proj_cypher_alpha = _proj_cypher_standard.replace(
            "gds.graph.project.cypher", "gds.alpha.graph.project.cypher"
        )
        try:
            proj_record = session.run(_proj_cypher_standard, name=GRAPH_NAME).single()
        except Exception:
            proj_record = session.run(_proj_cypher_alpha, name=GRAPH_NAME).single()

        node_count = int(proj_record["nodeCount"])
        rel_count  = int(proj_record["relationshipCount"])
        logger.info(
            "GDS projection '%s': %d nodes, %d relationships",
            GRAPH_NAME, node_count, rel_count,
        )

        if node_count == 0 or rel_count == 0:
            session.run("CALL gds.graph.drop($name, false)", name=GRAPH_NAME)
            raise ValueError(
                "GDS projection is empty — load UPI transaction data first."
            )

        # ── Louvain: write communityId back to Neo4j ─────────────────────────
        try:
            louvain_record = session.run(
                """
                CALL gds.louvain.write($name, {writeProperty: $prop})
                YIELD communityCount, modularity, ranLevels
                """,
                name=GRAPH_NAME,
                prop=write_property,
            ).single()
        except Exception:
            louvain_record = session.run(
                """
                CALL gds.louvain.write($name, {writeProperty: $prop})
                YIELD communityCount, modularity, levels AS ranLevels
                """,
                name=GRAPH_NAME,
                prop=write_property,
            ).single()

        num_communities = int(louvain_record["communityCount"])
        modularity      = float(louvain_record["modularity"])
        ran_levels      = int(louvain_record["ranLevels"])
        logger.info(
            "GDS Louvain finished: %d communities, modularity=%.4f, levels=%d",
            num_communities, modularity, ran_levels,
        )

        # ── Drop in-memory projection to free RAM ─────────────────────────────
        session.run("CALL gds.graph.drop($name, false)", name=GRAPH_NAME)

    # ── Read community stats back from Neo4j (communityId now persisted) ──────
    community_stats = _read_community_stats_from_neo4j(driver)

    return {
        "algorithm":      "gds_louvain",
        "gdsVersion":     gds_version,
        "numCommunities": num_communities,
        "modularity":     round(modularity, 4),
        "ranLevels":      ran_levels,
        "communities":    community_stats,
        "timestamp":      datetime.utcnow().isoformat(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# End-to-end pipeline test
# ─────────────────────────────────────────────────────────────────────────────

def run_pipeline_test(driver, csv_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Small end-to-end pipeline test.

    Steps:
        1. Ensure schema (constraints + indexes)
        2. Seed test data if DB is empty
        3. (Optional) Load CSV if csv_path provided
        4. Build graph, validate non-empty
        5. Run community detection (greedy_modularity)
        6. Update a sample of risk scores
        7. Query mule detection results
        8. Print summary

    Returns:
        Dict with results from each step

    Raises:
        ValueError  if the graph is empty after seeding
        RuntimeError if any pipeline step fails unexpectedly
    """
    results: Dict[str, Any] = {}
    logger.info("=== Starting end-to-end pipeline test ===")

    # Step 1: Schema
    ensure_schema(driver)
    results["schema"] = "ok"

    # Step 2: Seed / CSV
    seeded = seed_test_data(driver)
    results["seeded"] = seeded

    if csv_path:
        load_result = load_upi_csv_to_neo4j(csv_path, driver)
        results["csv_load"] = load_result
        logger.info("CSV load: %s", load_result)

    # Step 3: Graph stats pre-detection
    stats = get_neo4j_graph_stats(driver)
    results["pre_stats"] = stats
    logger.info("Pre-detection stats: %s", stats)

    if not stats.get("totalAccounts", 0):
        raise ValueError(
            "Pipeline test failed: no Account nodes found after seeding. "
            "Check Neo4j connectivity and credentials."
        )

    # Step 4: Community detection
    community_result = run_community_detection_neo4j(
        driver, algorithm="greedy_modularity")
    results["community_detection"] = {
        "algorithm":      community_result["algorithm"],
        "numCommunities": community_result["numCommunities"],
        "modularity":     community_result["modularity"],
        "totalNodes":     community_result["totalNodes"],
        "totalEdges":     community_result["totalEdges"],
    }
    logger.info(
        "Community detection: %d communities, modularity=%.4f",
        community_result["numCommunities"],
        community_result["modularity"],
    )

    # Step 5: Synthetic risk score update (mark known mule types)
    risk_update_query = """
    MATCH (a:UPI_Account)
    WHERE a.accountType IN ['MULE_COLLECTOR', 'MULE_SINK', 'MULE_LAYER']
    SET a.risk_score   = 85.0,
        a.risk_band    = 'critical',
        a.risk_factors = ['KNOWN_MULE_TYPE']
    RETURN count(a) AS updated
    """
    with driver.session(database="neo4j") as session:
        updated_count = session.run(risk_update_query).single()["updated"]
    results["risk_score_updates"] = int(updated_count)
    logger.info("Risk scores updated for %d mule accounts", updated_count)

    # Step 6: Mule detection
    mule_result = get_mule_detection_results(driver, min_risk=50.0, limit=50)
    results["mule_detection"] = mule_result["summary"]
    logger.info("Mule detection summary: %s", mule_result["summary"])

    # Step 7: Post stats
    post_stats = get_neo4j_graph_stats(driver)
    results["post_stats"] = post_stats

    logger.info("=== Pipeline test complete ===")
    _print_pipeline_summary(results)
    return results


def _print_pipeline_summary(results: Dict[str, Any]) -> None:
    """Print a human-readable summary of pipeline test results."""
    sep = "─" * 60
    print(sep)
    print("PIPELINE TEST SUMMARY")
    print(sep)

    pre = results.get("pre_stats",  {})
    post = results.get("post_stats", {})
    cd = results.get("community_detection", {})
    md = results.get("mule_detection", {})

    print(f"  Accounts total   : {pre.get('totalAccounts', 0)}")
    print(f"  Transactions     : {pre.get('totalTransactions', 0)}")
    print(f"  Communities found: {cd.get('numCommunities', 0)}")
    print(f"  Modularity       : {cd.get('modularity', 0.0):.4f}")
    print(f"  Risk score updates: {results.get('risk_score_updates', 0)}")
    print(f"  Mule accounts    : {md.get('totalMuleAccounts', 0)}")
    print(
        f"  Suspicious communities: {md.get('totalSuspiciousCommunities', 0)}")
    print(f"  Mule networks    : {md.get('totalNetworks', 0)}")
    print(f"  Avg risk score   : {md.get('avgRiskScore', 0.0):.2f}")
    print(f"  Critical risk    : {post.get('criticalRiskAccounts', 0)}")
    print(f"  High risk        : {post.get('highRiskAccounts', 0)}")
    print(sep)
