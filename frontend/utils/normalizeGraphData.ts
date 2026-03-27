/**
 * normalizeGraphData.js — Data Adapter Layer
 * ============================================
 * Intercepts and validates any data response (backend API, frontend analysis,
 * or loaded-from-storage) BEFORE it reaches UI components.
 *
 * Contract:
 *   Input  → Raw API response (any shape, possibly malformed)
 *   Output → Guaranteed { graph, risk, metadata } with safe defaults
 *
 * This prevents "is not iterable" and similar runtime crashes by
 * ensuring arrays are always arrays, numbers are always numbers,
 * and objects are always well-formed.
 */

// ──────────────────────────── Safe Coercion Helpers ────────────────────────────

/**
 * Coerce any value to a finite number. Returns `fallback` for NaN / Infinity.
 */
const toSafeNumber = (value, fallback = 0) => {
    const n = Number(value);
    return Number.isFinite(n) ? n : fallback;
};

/**
 * Coerce any value to a guaranteed array.
 * - Arrays → returned as-is
 * - Iterables (Set, Map.values, etc.) → Array.from
 * - Null / undefined / primitives → []
 */
const toSafeArray = (value) => {
    if (Array.isArray(value)) return value;
    if (value != null && typeof value[Symbol.iterator] === 'function') {
        try { return Array.from(value); } catch { return []; }
    }
    return [];
};

/**
 * Coerce any value to a plain object. Returns `{}` for non-objects.
 */
const toSafeObject = (value) => {
    if (value && typeof value === 'object' && !Array.isArray(value)) return value;
    return {};
};

// ────────────────────────────── Node Normalizer ────────────────────────────────

/**
 * Normalize a single node entry into the strict format expected by
 * GraphRenderer (D3) and UPIGraphRenderer (Sigma).
 *
 * Required output fields:
 *   id       : string
 *   label    : string
 *   type     : 'address' | 'transaction' | 'unknown'
 *
 * Optional enrichment:
 *   riskScore, riskBand, inTxCount, outTxCount, totalInAmount, totalOutAmount,
 *   balance, color, x, y, size, reasonCodes, etc.
 */
const normalizeNode = (raw) => {
    if (!raw || typeof raw !== 'object') return null;

    // Accept any of: id, upiId, accountId, address
    const id = String(
        raw.id ?? raw.upiId ?? raw.accountId ?? raw.address ?? ''
    ).trim();
    if (!id) return null;  // Nodes MUST have an ID

    return {
        id,
        label:   raw.label   ?? raw.upiId ?? raw.accountId ?? id,
        upiId:   raw.upiId   ?? raw.accountId ?? raw.label ?? id,
        type:    raw.type    ?? raw.nodeType ?? 'address',
        nodeType: raw.nodeType ?? raw.type ?? 'Account',
        riskScore:          toSafeNumber(raw.riskScore),
        riskBand:           raw.riskBand ?? raw.riskLevel ?? 'unknown',
        riskLevel:          raw.riskLevel ?? raw.riskBand ?? 'unknown',
        riskFactors:        toSafeArray(raw.riskFactors ?? raw.reasonCodes),
        inTxCount:          toSafeNumber(raw.inTxCount),
        outTxCount:         toSafeNumber(raw.outTxCount),
        totalInAmount:      toSafeNumber(raw.totalInAmount),
        totalOutAmount:     toSafeNumber(raw.totalOutAmount),
        balance:            toSafeNumber(raw.balance),
        transaction_count:  toSafeNumber(raw.transaction_count ?? raw.txCount),
        color:       raw.color ?? undefined,
        size:        toSafeNumber(raw.size, undefined),
        x:           raw.x ?? undefined,
        y:           raw.y ?? undefined,
        reasonCodes:  toSafeArray(raw.reasonCodes ?? raw.riskFactors),
        communityId:  raw.communityId ?? undefined,
        isAnomalous:  Boolean(raw.isAnomalous),
        isMalicious:  Boolean(raw.isMalicious),
        // UPI / Neo4j specific fields
        accountType:         raw.accountType ?? undefined,
        ipSubnet:            raw.ipSubnet ?? undefined,
        ipSubnets:           toSafeArray(raw.ipSubnets),
        deviceHash:          raw.deviceHash ?? undefined,
        deviceHashes:        toSafeArray(raw.deviceHashes),
        isDevice:            Boolean(raw.isDevice),
        deviceUsers:         toSafeNumber(raw.deviceUsers),
        multiDeviceFlag:     Boolean(raw.multiDeviceFlag),
        multiLocationFlag:   Boolean(raw.multiLocationFlag),
        velocityAnomalyFlag: Boolean(raw.velocityAnomalyFlag),
        // Preserve any extra fields the caller may need
        ...Object.fromEntries(
            Object.entries(raw).filter(([k]) =>
                !['id', 'label', 'upiId', 'accountId', 'type', 'nodeType',
                    'riskScore', 'riskBand', 'riskLevel', 'riskFactors',
                    'inTxCount', 'outTxCount', 'totalInAmount', 'totalOutAmount',
                    'balance', 'transaction_count', 'txCount', 'color', 'size', 'x', 'y',
                    'reasonCodes', 'communityId', 'isAnomalous', 'isMalicious',
                    'accountType', 'ipSubnet', 'ipSubnets', 'deviceHash', 'deviceHashes',
                    'isDevice', 'deviceUsers', 'multiDeviceFlag', 'multiLocationFlag',
                    'velocityAnomalyFlag'].includes(k)
            )
        )
    };
};

// ────────────────────────────── Edge Normalizer ────────────────────────────────

/**
 * Normalize a single edge entry.
 *
 * Required output fields:
 *   source  : string (node ID)
 *   target  : string (node ID)
 */
const normalizeEdge = (raw) => {
    if (!raw || typeof raw !== 'object') return null;

    // Handle D3-style object references (after simulation, source/target become objects)
    const source = typeof raw.source === 'object' ? raw.source?.id : raw.source;
    const target = typeof raw.target === 'object' ? raw.target?.id : raw.target;

    if (!source || !target) return null;

    return {
        id:        raw.id ?? `${source}-${target}`,
        source:    String(source),
        target:    String(target),
        edgeType:  raw.edgeType ?? raw.type ?? 'TRANSACTED',
        amount:    toSafeNumber(raw.amount),
        weight:    toSafeNumber(raw.weight ?? raw.frequency, 1),
        frequency: toSafeNumber(raw.frequency, 1),
        size:      toSafeNumber(raw.size, 1),
        color:     raw.color ?? undefined,
        direction: raw.direction ?? undefined,
        value:     toSafeNumber(raw.value ?? raw.amount),
        timestamp:      raw.timestamp ?? undefined,
        firstTimestamp: raw.firstTimestamp ?? undefined,
        lastTimestamp:  raw.lastTimestamp ?? undefined,
        status:    raw.status ?? undefined,
        pattern:   raw.pattern ?? undefined,
        label:     raw.label ?? undefined,
    };
};

// ────────────────────────── Metadata / Risk Normalizer ─────────────────────────

const normalizeMetadata = (raw, nodeCount, edgeCount) => {
    const meta = toSafeObject(raw);
    return {
        totalNodes: toSafeNumber(meta.totalNodes, nodeCount),
        totalEdges: toSafeNumber(meta.totalEdges, edgeCount),
        clusterRiskScore: toSafeNumber(meta.clusterRiskScore),
        clusterRiskBand: meta.clusterRiskBand ?? 'unknown',
        communities: toSafeObject(meta.communities),
        suspiciousSubgraph: {
            nodes: toSafeArray(meta.suspiciousSubgraph?.nodes),
            edges: toSafeArray(meta.suspiciousSubgraph?.edges),
        },
        // Pass through any extra metadata
        ...Object.fromEntries(
            Object.entries(meta).filter(([k]) =>
                !['totalNodes', 'totalEdges', 'clusterRiskScore', 'clusterRiskBand',
                    'communities', 'suspiciousSubgraph'].includes(k)
            )
        )
    };
};

const normalizeRisk = (raw) => {
    const risk = toSafeObject(raw);
    return {
        clusterRiskScore: toSafeNumber(risk.clusterRiskScore),
        clusterRiskBand: risk.clusterRiskBand ?? 'unknown',
        averageRiskScore: toSafeNumber(risk.averageRiskScore),
        distribution: {
            critical: toSafeNumber(risk.distribution?.critical),
            high: toSafeNumber(risk.distribution?.high),
            medium: toSafeNumber(risk.distribution?.medium),
            low: toSafeNumber(risk.distribution?.low),
        },
        // Pass through extras
        ...Object.fromEntries(
            Object.entries(risk).filter(([k]) =>
                !['clusterRiskScore', 'clusterRiskBand', 'averageRiskScore', 'distribution'].includes(k)
            )
        )
    };
};

// ─────────────────────── EMPTY STATE (safe fallback) ──────────────────────────

export const EMPTY_ANALYSIS = Object.freeze({
    graph: Object.freeze({
        nodes: [],
        edges: [],
        metadata: Object.freeze({
            totalNodes: 0,
            totalEdges: 0,
            clusterRiskScore: 0,
            clusterRiskBand: 'unknown',
            communities: {},
            suspiciousSubgraph: { nodes: [], edges: [] },
        }),
    }),
    risk: Object.freeze({
        clusterRiskScore: 0,
        clusterRiskBand: 'unknown',
        averageRiskScore: 0,
        distribution: { critical: 0, high: 0, medium: 0, low: 0 },
    }),
    metadata: Object.freeze({
        totalNodes: 0,
        totalEdges: 0,
        clusterRiskScore: 0,
        clusterRiskBand: 'unknown',
        communities: {},
        suspiciousSubgraph: { nodes: [], edges: [] },
    }),
});

// ──────────────────────── MAIN ADAPTER FUNCTION ───────────────────────────────

/**
 * normalizeGraphData(response)
 *
 * The single entry-point for ALL data flowing into the UI.
 *
 * Accepts any of:
 *   - Backend API response:   { graph: { nodes, edges, metadata }, risk, metadata }
 *   - Frontend analysis:      { graph: { nodes, edges, metadata }, risk, metadata }
 *   - Stored analysis:        (same shape, from localStorage)
 *   - Malformed/null:          returns EMPTY_ANALYSIS
 *
 * @param {any} response - Raw data from any source
 * @returns {{ graph: Object, risk: Object, metadata: Object }}
 */
export const normalizeGraphData = (response) => {
    // Gate: completely invalid input
    if (!response || typeof response !== 'object') {
        console.warn('[normalizeGraphData] Received null/invalid response, returning empty state');
        return { ...EMPTY_ANALYSIS };
    }

    try {
        // ── Extract the graph sub-object ──
        const rawGraph = toSafeObject(response.graph ?? response);

        // ── Normalize nodes ──
        const rawNodes = toSafeArray(rawGraph.nodes ?? response.nodes);
        const nodes = rawNodes
            .map(normalizeNode)
            .filter(Boolean); // Drop any null entries

        // ── Build a valid-node-ID set (for edge validation) ──
        const validNodeIds = new Set(nodes.map(n => n.id));

        // ── Normalize edges ──────────────────────────────────────────────────
        // USED_DEVICE and other edge types may reference device nodes that are
        // included in the same payload but were not seen first.  Build a
        // looser filter: keep edges where BOTH endpoints have a non-empty ID
        // AND at least the source OR target is a known node.  Full-match is
        // the preferred path; partial-match prevents silently dropping Device
        // edges when the device node list is ordered after account nodes.
        const rawEdges = toSafeArray(rawGraph.edges ?? response.edges);
        const edges = rawEdges
            .map(normalizeEdge)
            .filter(e => {
                if (!e) return false;
                const srcOk = validNodeIds.has(e.source);
                const dstOk = validNodeIds.has(e.target);
                // Accept USED_DEVICE edges even if device node wasn't normalized
                // (device nodes may be absent when Neo4j is not connected)
                if (e.edgeType === 'USED_DEVICE') return srcOk;
                return srcOk && dstOk;
            });

        // ── Normalize metadata and risk ──
        const metadata = normalizeMetadata(
            rawGraph.metadata ?? response.metadata,
            nodes.length,
            edges.length
        );

        const risk = normalizeRisk(response.risk ?? rawGraph.metadata ?? {});

        // Ensure risk distribution counts are populated from nodes if missing
        if (risk.distribution.critical === 0 && risk.distribution.high === 0 &&
            risk.distribution.medium === 0 && risk.distribution.low === 0 && nodes.length > 0) {
            nodes.forEach(n => {
                const score = n.riskScore ?? 0;
                if (score >= 80) risk.distribution.critical++;
                else if (score >= 60) risk.distribution.high++;
                else if (score >= 40) risk.distribution.medium++;
                else risk.distribution.low++;
            });
        }

        // Ensure averageRiskScore is computed if missing
        if (risk.averageRiskScore === 0 && nodes.length > 0) {
            const totalRisk = nodes.reduce((sum, n) => sum + (n.riskScore ?? 0), 0);
            risk.averageRiskScore = Math.round(totalRisk / nodes.length);
        }

        const result = {
            graph: {
                nodes,
                edges,
                metadata,
            },
            risk,
            metadata, // Duplicate at top level for backward compatibility
        };

        console.log(`[normalizeGraphData] Normalized: ${nodes.length} nodes, ${edges.length} edges, risk=${risk.clusterRiskScore}`);
        return result;

    } catch (err) {
        console.error('[normalizeGraphData] Normalization failed, returning empty state:', err);
        return { ...EMPTY_ANALYSIS };
    }
};

export default normalizeGraphData;
