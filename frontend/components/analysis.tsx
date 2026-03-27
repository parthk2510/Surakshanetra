"use client";
import { config } from './config';

const logger = {
  info: (msg, meta = {}) => console.log(`[ANALYSIS] ${new Date().toISOString()} INFO: ${msg}`, meta),
  warn: (msg, meta = {}) => console.warn(`[ANALYSIS] ${new Date().toISOString()} WARN: ${msg}`, meta),
  error: (msg, meta = {}) => console.error(`[ANALYSIS] ${new Date().toISOString()} ERROR: ${msg}`, meta),
  debug: (msg, meta = {}) => console.log(`[ANALYSIS] ${new Date().toISOString()} DEBUG: ${msg}`, meta)
};

const riskBandFromScore = (score) => {
  if (score >= 80) return 'critical';
  if (score >= 60) return 'high';
  if (score >= 40) return 'medium';
  if (score >= 20) return 'low';
  return 'minimal';
};

const ensureNumber = (value, fallback = 0) => {
  const num = Number(value);
  return Number.isFinite(num) ? num : fallback;
};

const toTimestamp = (value) => {
  const num = Number(value);
  if (!Number.isFinite(num) || num <= 0) return null;
  return num < 10000000000 ? num * 1000 : num;
};

const hashId = (input) => {
  let hash = 0;
  for (let i = 0; i < input.length; i++) {
    const char = input.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash = hash & hash;
  }
  return Math.abs(hash).toString(36);
};

const createStats = () => ({
  inTxCount: 0,
  outTxCount: 0,
  totalInAmount: 0,
  totalOutAmount: 0,
  inCounterparties: new Set(),
  outCounterparties: new Set(),
  inAmounts: [],
  outAmounts: [],
  events: [],
  firstSeen: null,
  lastActive: null
});

const updateFirstLast = (stats, ts) => {
  if (!stats.firstSeen || ts < stats.firstSeen) stats.firstSeen = ts;
  if (!stats.lastActive || ts > stats.lastActive) stats.lastActive = ts;
};

const computeMeanStd = (values) => {
  if (!values.length) return { mean: 0, std: 0 };
  const mean = values.reduce((a, b) => a + b, 0) / values.length;
  const variance = values.reduce((a, b) => a + (b - mean) ** 2, 0) / values.length;
  return { mean, std: Math.sqrt(variance) };
};

const tarjanSCC = (nodes, outAdj) => {
  let index = 0;
  const stack = [];
  const indices = new Map();
  const lowlink = new Map();
  const onStack = new Set();
  const sccs = [];
  const nodeToScc = new Map();

  const strongconnect = (v) => {
    indices.set(v, index);
    lowlink.set(v, index);
    index += 1;
    stack.push(v);
    onStack.add(v);

    const neighbors = outAdj.get(v) || new Set();
    for (const w of neighbors) {
      if (!indices.has(w)) {
        strongconnect(w);
        lowlink.set(v, Math.min(lowlink.get(v), lowlink.get(w)));
      } else if (onStack.has(w)) {
        lowlink.set(v, Math.min(lowlink.get(v), indices.get(w)));
      }
    }

    if (lowlink.get(v) === indices.get(v)) {
      const scc = [];
      let w = null;
      do {
        w = stack.pop();
        onStack.delete(w);
        scc.push(w);
        nodeToScc.set(w, sccs.length);
      } while (w !== v && stack.length > 0);
      sccs.push(scc);
    }
  };

  for (const v of nodes) {
    if (!indices.has(v)) strongconnect(v);
  }

  return { sccs, nodeToScc };
};

const labelPropagation = (nodes, neighbors, maxIter = 20) => {
  const labels = new Map();
  for (const n of nodes) labels.set(n, n);

  const shuffled = (arr) => {
    const a = arr.slice();
    for (let i = a.length - 1; i > 0; i -= 1) {
      const j = Math.floor(Math.random() * (i + 1));
      const tmp = a[i];
      a[i] = a[j];
      a[j] = tmp;
    }
    return a;
  };

  for (let iter = 0; iter < maxIter; iter += 1) {
    let changes = 0;
    for (const node of shuffled(nodes)) {
      const nbrs = neighbors.get(node) || new Set();
      if (nbrs.size === 0) continue;
      const counts = new Map();
      for (const nbr of nbrs) {
        const label = labels.get(nbr) || nbr;
        counts.set(label, (counts.get(label) || 0) + 1);
      }
      let bestLabel = labels.get(node);
      let bestCount = -1;
      for (const [label, count] of counts.entries()) {
        if (count > bestCount || (count === bestCount && String(label) < String(bestLabel))) {
          bestLabel = label;
          bestCount = count;
        }
      }
      if (bestLabel !== labels.get(node)) {
        labels.set(node, bestLabel);
        changes += 1;
      }
    }
    if (changes === 0) break;
  }

  return labels;
};

class UnionFind {
  parent: Map<unknown, unknown>;
  size: Map<unknown, number>;
  constructor(nodes) {
    this.parent = new Map();
    this.size = new Map();
    for (const n of nodes) {
      this.parent.set(n, n);
      this.size.set(n, 1);
    }
  }
  find(x) {
    const p = this.parent.get(x);
    if (p === x) return x;
    const root = this.find(p);
    this.parent.set(x, root);
    return root;
  }
  union(a, b) {
    const ra = this.find(a);
    const rb = this.find(b);
    if (ra === rb) return;
    const sa = this.size.get(ra) || 1;
    const sb = this.size.get(rb) || 1;
    if (sa < sb) {
      this.parent.set(ra, rb);
      this.size.set(rb, sa + sb);
    } else {
      this.parent.set(rb, ra);
      this.size.set(ra, sa + sb);
    }
  }
}

const computePageRank = (nodes, outAdj, iterations = 20, damping = 0.85) => {
  const n = nodes.length;
  const ranks = new Map();
  if (n === 0) return ranks;
  const init = 1 / n;
  for (const node of nodes) ranks.set(node, init);

  for (let iter = 0; iter < iterations; iter += 1) {
    const newRanks = new Map();
    let sinkSum = 0;
    for (const node of nodes) {
      const out = outAdj.get(node) || new Set();
      if (out.size === 0) sinkSum += ranks.get(node) || 0;
    }
    const base = (1 - damping) / n;
    for (const node of nodes) newRanks.set(node, base + damping * sinkSum / n);
    for (const node of nodes) {
      const out = outAdj.get(node) || new Set();
      const rank = ranks.get(node) || 0;
      if (out.size === 0) continue;
      const share = (rank * damping) / out.size;
      for (const nbr of out) newRanks.set(nbr, (newRanks.get(nbr) || 0) + share);
    }
    for (const node of nodes) ranks.set(node, newRanks.get(node) || 0);
  }
  return ranks;
};

const computeCloseness = (nodes, neighbors) => {
  const closeness = new Map();
  for (const start of nodes) {
    const dist = new Map();
    dist.set(start, 0);
    const queue = [start];
    let head = 0;
    while (head < queue.length) {
      const v = queue[head++];
      const nbrs = neighbors.get(v) || new Set();
      for (const w of nbrs) {
        if (!dist.has(w)) {
          dist.set(w, dist.get(v) + 1);
          queue.push(w);
        }
      }
    }
    const reachable = dist.size;
    if (reachable <= 1) {
      closeness.set(start, 0);
    } else {
      let sumDist = 0;
      for (const d of dist.values()) sumDist += d;
      closeness.set(start, sumDist > 0 ? (reachable - 1) / sumDist : 0);
    }
  }
  return closeness;
};

const computeBetweenness = (nodes, neighbors) => {
  const betweenness = new Map();
  for (const n of nodes) betweenness.set(n, 0);

  for (const s of nodes) {
    const stack = [];
    const pred = new Map();
    const sigma = new Map();
    const dist = new Map();
    for (const v of nodes) {
      pred.set(v, []);
      sigma.set(v, 0);
      dist.set(v, -1);
    }
    sigma.set(s, 1);
    dist.set(s, 0);
    const queue = [s];
    let head = 0;
    while (head < queue.length) {
      const v = queue[head++];
      stack.push(v);
      const nbrs = neighbors.get(v) || new Set();
      for (const w of nbrs) {
        if (dist.get(w) < 0) {
          queue.push(w);
          dist.set(w, dist.get(v) + 1);
        }
        if (dist.get(w) === dist.get(v) + 1) {
          sigma.set(w, (sigma.get(w) || 0) + (sigma.get(v) || 0));
          pred.get(w).push(v);
        }
      }
    }
    const delta = new Map();
    for (const v of nodes) delta.set(v, 0);
    while (stack.length) {
      const w = stack.pop();
      for (const v of pred.get(w)) {
        const coeff = (sigma.get(v) || 0) / (sigma.get(w) || 1);
        delta.set(v, (delta.get(v) || 0) + coeff * (1 + (delta.get(w) || 0)));
      }
      if (w !== s) betweenness.set(w, (betweenness.get(w) || 0) + (delta.get(w) || 0));
    }
  }

  const n = nodes.length;
  const scale = n <= 2 ? 1 : 1 / ((n - 1) * (n - 2) / 2);
  for (const node of nodes) {
    betweenness.set(node, (betweenness.get(node) || 0) * scale);
  }
  return betweenness;
};

const computeClusteringCoefficient = (nodes, neighbors) => {
  const coefficients = new Map();
  for (const node of nodes) {
    const nbrs = neighbors.get(node) || new Set();
    const k = nbrs.size;
    if (k < 2) {
      coefficients.set(node, 0);
      continue;
    }
    const nbrArr = Array.from(nbrs);
    let links = 0;
    for (let i = 0; i < nbrArr.length; i += 1) {
      const ni = nbrArr[i];
      const setNi = neighbors.get(ni) || new Set();
      for (let j = i + 1; j < nbrArr.length; j += 1) {
        if (setNi.has(nbrArr[j])) links += 1;
      }
    }
    const possible = (k * (k - 1)) / 2;
    coefficients.set(node, possible > 0 ? links / possible : 0);
  }
  return coefficients;
};

const computeInOutPairs = (events) => {
  const inQueue = [];
  let matched = 0;
  let quick = 0;
  let totalHold = 0;
  for (const ev of events) {
    if (ev.type === 'in') {
      inQueue.push(ev);
    } else if (ev.type === 'out' && inQueue.length) {
      const inEvent = inQueue.shift();
      const delta = ev.timestamp - inEvent.timestamp;
      if (delta >= 0) {
        matched += 1;
        totalHold += delta;
        if (delta <= config.rules.rapidInOut.maxMinutes * 60000) quick += 1;
      }
    }
  }
  const avgHold = matched > 0 ? totalHold / matched : null;
  return { matched, quick, avgHold };
};

const computeDormantSpike = (times) => {
  if (times.length < 2) return false;
  const dormantMs = config.rules.dormantSpike.dormantDays * 86400000;
  const burstWindow = config.rules.dormantSpike.burstHours * 3600000;
  const burstCount = config.rules.dormantSpike.burstCount;
  for (let i = 1; i < times.length; i += 1) {
    if (times[i] - times[i - 1] >= dormantMs) {
      const start = times[i];
      let count = 0;
      for (let j = i; j < times.length; j += 1) {
        if (times[j] <= start + burstWindow) count += 1;
        else break;
      }
      if (count >= burstCount) return true;
    }
  }
  return false;
};

const computeStructuring = (amounts) => {
  const threshold = config.rules.structuring.threshold;
  const minCount = config.rules.structuring.minCount;
  const window = threshold * config.rules.structuring.windowPct;
  const near = amounts.filter(a => a >= threshold - window && a <= threshold);
  if (near.length >= minCount) return { triggered: true, count: near.length };
  if (amounts.length >= config.rules.structuring.repeatCount) {
    const rounded = amounts.map(a => Math.round(a * 100) / 100);
    const { std, mean } = computeMeanStd(rounded);
    if (mean > 0 && std / mean <= config.rules.structuring.varianceRatio) {
      return { triggered: true, count: amounts.length };
    }
  }
  return { triggered: false, count: 0 };
};

const computeFanRule = (uniqueCount, txCount, otherUnique, configRule) => {
  const ratio = otherUnique > 0 ? uniqueCount / otherUnique : uniqueCount;
  const triggered = uniqueCount >= configRule.unique && (txCount >= configRule.count || uniqueCount >= configRule.unique * 1.5) && ratio >= configRule.ratio;
  const severity = Math.min(1, uniqueCount / configRule.unique);
  return { triggered, severity };
};

const computeRapidRule = (outTxCount, pairs) => {
  const ratio = outTxCount > 0 ? pairs.quick / outTxCount : 0;
  const triggered = pairs.quick >= config.rules.rapidInOut.minMatches && ratio >= config.rules.rapidInOut.minRatio;
  const severity = Math.min(1, pairs.quick / config.rules.rapidInOut.minMatches);
  return { triggered, severity, ratio };
};

const computePassthroughRule = (stats, pairs) => {
  if (stats.totalInAmount <= 0 || stats.totalOutAmount <= 0) return { triggered: false, severity: 0 };
  const ratio = stats.totalOutAmount / stats.totalInAmount;
  const holdOk = pairs.avgHold !== null && pairs.avgHold <= config.rules.passthrough.maxHoldMinutes * 60000;
  const ratioOk = ratio >= config.rules.passthrough.ratioLow && ratio <= config.rules.passthrough.ratioHigh;
  const countOk = pairs.matched >= config.rules.passthrough.minCount;
  const triggered = holdOk && ratioOk && countOk;
  const severity = triggered ? Math.min(1, pairs.matched / config.rules.passthrough.minCount) : 0;
  return { triggered, severity, ratio, avgHold: pairs.avgHold };
};

export const analyzeTransactions = (focusUpiIds, transactions, options = {}, nodeAttributes = new Map()) => {
  // ── Defensive: handle legacy 2-arg call pattern ──
  // If called as analyzeTransactions(transactions, settings) (old pattern),
  // detect it and rearrange arguments.
  if (Array.isArray(focusUpiIds) && focusUpiIds.length > 0 &&
    typeof focusUpiIds[0] === 'object' && focusUpiIds[0]?.from &&
    (transactions == null || typeof transactions !== 'object' || !Array.isArray(transactions))) {
    // Caller passed transactions as 1st arg — rearrange
    logger.warn('analyzeTransactions called with legacy 2-arg pattern, auto-correcting');
    const realTransactions = focusUpiIds;
    const realOptions = (transactions && typeof transactions === 'object') ? transactions : {};
    const upiIds = [...new Set(realTransactions.flatMap(tx => [tx.from, tx.to].filter(Boolean)))];
    focusUpiIds = upiIds;
    transactions = realTransactions;
    options = realOptions;
    nodeAttributes = new Map();
  }

  // ── Coerce inputs to safe types ──
  if (!Array.isArray(focusUpiIds)) {
    logger.warn('focusUpiIds is not an array, coercing', { type: typeof focusUpiIds });
    focusUpiIds = focusUpiIds ? [String(focusUpiIds)] : [];
  }
  if (!Array.isArray(transactions)) {
    logger.error('transactions is not an array', { type: typeof transactions, value: String(transactions).substring(0, 100) });
    transactions = [];
  }
  if (!(nodeAttributes instanceof Map)) {
    nodeAttributes = new Map();
  }

  logger.info('Starting transaction analysis', {
    focusCount: focusUpiIds.length,
    transactionCount: transactions.length,
    hasNodeAttributes: nodeAttributes.size > 0
  });

  if (transactions.length === 0) {
    logger.warn('No transactions to analyze, returning empty result');
    return {
      graph: { nodes: [], edges: [], metadata: { clusterRiskScore: 0, clusterRiskBand: 'low', totalNodes: 0, totalEdges: 0, communities: {}, suspiciousSubgraph: { nodes: [], edges: [] } } },
      risk: { clusterRiskScore: 0, clusterRiskBand: 'low' },
      metadata: { clusterRiskScore: 0, clusterRiskBand: 'low', totalNodes: 0, totalEdges: 0, communities: {}, suspiciousSubgraph: { nodes: [], edges: [] } }
    };
  }

  const focusSet = new Set(focusUpiIds);
  const nodesMap = new Map();
  const statsMap = new Map();
  const edgesMap = new Map();
  const neighbors = new Map();
  const outAdj = new Map();
  const inAdj = new Map();
  const counterpartyMap = new Map();

  const ensureNode = (id) => {
    if (!nodesMap.has(id)) {
      nodesMap.set(id, { id, upiId: id, label: id, type: 'address' });
      statsMap.set(id, createStats());
      neighbors.set(id, new Set());
      outAdj.set(id, new Set());
      inAdj.set(id, new Set());
      counterpartyMap.set(id, new Map());
    }
  };

  for (const tx of (Array.isArray(transactions) ? transactions : [])) {
    const from = tx.from;
    const to = tx.to;
    if (!from || !to) continue;
    const amount = ensureNumber(tx.amount, 0);
    const timestamp = toTimestamp(tx.timestamp) || Date.now();
    ensureNode(from);
    ensureNode(to);

    const fromStats = statsMap.get(from);
    const toStats = statsMap.get(to);

    fromStats.outTxCount += 1;
    fromStats.totalOutAmount += amount;
    fromStats.outCounterparties.add(to);
    fromStats.outAmounts.push(amount);
    fromStats.events.push({ timestamp, type: 'out', amount, counterparty: to });
    updateFirstLast(fromStats, timestamp);

    toStats.inTxCount += 1;
    toStats.totalInAmount += amount;
    toStats.inCounterparties.add(from);
    toStats.inAmounts.push(amount);
    toStats.events.push({ timestamp, type: 'in', amount, counterparty: from });
    updateFirstLast(toStats, timestamp);

    neighbors.get(from).add(to);
    neighbors.get(to).add(from);
    outAdj.get(from).add(to);
    inAdj.get(to).add(from);

    const edgeKey = `${from}|${to}`;
    const edge = edgesMap.get(edgeKey) || {
      id: tx.id || hashId(`${from}|${to}|${timestamp}|${amount}`),
      source: from,
      target: to,
      amount: 0,
      frequency: 0,
      firstTimestamp: timestamp,
      lastTimestamp: timestamp
    };
    edge.amount += amount;
    edge.frequency += Math.max(1, ensureNumber(tx.frequency, 1));
    edge.firstTimestamp = Math.min(edge.firstTimestamp, timestamp);
    edge.lastTimestamp = Math.max(edge.lastTimestamp, timestamp);
    edgesMap.set(edgeKey, edge);

    const cpFrom = counterpartyMap.get(from);
    const entryFrom = cpFrom.get(to) || { inAmount: 0, outAmount: 0, inCount: 0, outCount: 0 };
    entryFrom.outAmount += amount;
    entryFrom.outCount += 1;
    cpFrom.set(to, entryFrom);

    const cpTo = counterpartyMap.get(to);
    const entryTo = cpTo.get(from) || { inAmount: 0, outAmount: 0, inCount: 0, outCount: 0 };
    entryTo.inAmount += amount;
    entryTo.inCount += 1;
    cpTo.set(from, entryTo);
  }

  for (const id of focusSet) ensureNode(id);

  logger.info('Transaction processing completed', {
    totalNodes: nodesMap.size,
    totalEdges: edgesMap.size,
    transactionsProcessed: transactions.length
  });

  const nodeIds = Array.from(nodesMap.keys());

  logger.debug('Starting graph analysis algorithms');
  const scc = tarjanSCC(nodeIds, outAdj);
  const sccSizes = new Map();
  for (const component of scc.sccs) sccSizes.set(component.join('|'), component.length);
  const nodeToSccSize = new Map();
  for (const comp of scc.sccs) {
    for (const node of comp) nodeToSccSize.set(node, comp.length);
  }

  const uf = new UnionFind(nodeIds);
  for (const [node, nbrs] of neighbors.entries()) {
    for (const nbr of nbrs) uf.union(node, nbr);
  }
  const componentMap = new Map();
  for (const node of nodeIds) {
    const root = uf.find(node);
    componentMap.set(node, root);
  }
  const componentSizes = new Map();
  for (const root of componentMap.values()) componentSizes.set(root, (componentSizes.get(root) || 0) + 1);
  const componentIds = new Map();
  let componentIndex = 0;
  for (const root of componentSizes.keys()) {
    componentIds.set(root, componentIndex++);
  }

  const labels = labelPropagation(nodeIds, neighbors, 30);
  const labelToCommunity = new Map();
  let communityIndex = 0;
  for (const label of new Set(labels.values())) {
    labelToCommunity.set(label, communityIndex++);
  }

  const communities = {};
  for (const node of nodeIds) {
    const communityId = labelToCommunity.get(labels.get(node));
    if (!communities[communityId]) communities[communityId] = { members: [], size: 0, totalValue: 0, edgeCount: 0 };
    communities[communityId].members.push(node);
    communities[communityId].size += 1;
  }
  for (const edge of edgesMap.values()) {
    const cId = labelToCommunity.get(labels.get(edge.source));
    if (communities[cId]) communities[cId].totalValue += edge.amount;
  }

  const pageRank = computePageRank(nodeIds, outAdj, 30, 0.85);
  const closeness = nodeIds.length <= config.limits.maxClosenessNodes ? computeCloseness(nodeIds, neighbors) : new Map();
  const betweenness = nodeIds.length <= config.limits.maxCentralityNodes ? computeBetweenness(nodeIds, neighbors) : new Map();
  const clustering = computeClusteringCoefficient(nodeIds, neighbors);

  logger.info('Graph metrics computed', {
    communityCount: Object.keys(communities).length,
    sccCount: scc.sccs.length,
    hasCloseness: closeness.size > 0,
    hasBetweenness: betweenness.size > 0
  });

  const degreeValues = nodeIds.map(id => (statsMap.get(id)?.inTxCount || 0) + (statsMap.get(id)?.outTxCount || 0));
  const { mean: degreeMean, std: degreeStd } = computeMeanStd(degreeValues);
  const hubThreshold = degreeMean + degreeStd * 2;

  const nodeRiskScores = [];

  for (const nodeId of nodeIds) {
    const stats = statsMap.get(nodeId) || createStats();
    stats.events.sort((a, b) => a.timestamp - b.timestamp);
    const times = stats.events.map(e => e.timestamp);

    const inUnique = stats.inCounterparties.size;
    const outUnique = stats.outCounterparties.size;

    const fanIn = computeFanRule(inUnique, stats.inTxCount, outUnique, config.rules.fanIn);
    const fanOut = computeFanRule(outUnique, stats.outTxCount, inUnique, config.rules.fanOut);
    const inCycle = (nodeToSccSize.get(nodeId) || 1) >= config.rules.circular.minCycleSize;

    const pairs = computeInOutPairs(stats.events);
    const rapid = computeRapidRule(stats.outTxCount, pairs);
    const structuring = computeStructuring(stats.outAmounts);
    const dormantSpike = computeDormantSpike(times);
    const passthrough = computePassthroughRule(stats, pairs);

    const contributions: Record<string, number> = {};
    let score = 0;
    if (fanIn.triggered) { contributions.fanIn = config.weights.fanIn * fanIn.severity; score += contributions.fanIn; }
    if (fanOut.triggered) { contributions.fanOut = config.weights.fanOut * fanOut.severity; score += contributions.fanOut; }
    if (inCycle) { contributions.circular = config.weights.circular; score += contributions.circular; }
    if (rapid.triggered) { contributions.rapidInOut = config.weights.rapidInOut * rapid.severity; score += contributions.rapidInOut; }
    if (structuring.triggered) { contributions.structuring = config.weights.structuring; score += contributions.structuring; }
    if (dormantSpike) { contributions.dormantSpike = config.weights.dormantSpike; score += contributions.dormantSpike; }
    if (passthrough.triggered) { contributions.passthrough = config.weights.passthrough * passthrough.severity; score += contributions.passthrough; }

    score = Math.min(100, Math.round(score));
    const riskBand = riskBandFromScore(score);

    const reasonCodes = [];
    if (fanIn.triggered) reasonCodes.push('FAN_IN');
    if (fanOut.triggered) reasonCodes.push('FAN_OUT');
    if (inCycle) reasonCodes.push('CIRCULAR_FLOW');
    if (rapid.triggered) reasonCodes.push('RAPID_IN_OUT');
    if (structuring.triggered) reasonCodes.push('AMOUNT_STRUCTURING');
    if (dormantSpike) reasonCodes.push('DORMANT_SPIKE');
    if (passthrough.triggered) reasonCodes.push('PASSTHROUGH');

    const degree = (stats.inTxCount || 0) + (stats.outTxCount || 0);
    const isHub = degree >= hubThreshold && degree > 0;

    const cpSummary = Array.from((counterpartyMap.get(nodeId) || new Map()).entries())
      .map(([counterparty, v]) => ({
        counterparty,
        inAmount: v.inAmount,
        outAmount: v.outAmount,
        inCount: v.inCount,
        outCount: v.outCount,
        totalAmount: v.inAmount + v.outAmount
      }))
      .sort((a, b) => b.totalAmount - a.totalAmount)
      .slice(0, 10);

    const timeline = stats.events.slice(0, config.limits.maxTimelineEvents);

    const existing = nodeAttributes.get(nodeId) || {};

    const nodeData = {
      id: nodeId,
      label: nodeId,
      type: 'address',
      upiId: nodeId,
      bank: existing.bank || null,
      flags: Array.from(new Set([...(existing.flags || []), ...reasonCodes])),
      riskScore: score,
      riskScoreNormalized: score / 100,
      riskBand,
      inTxCount: stats.inTxCount,
      outTxCount: stats.outTxCount,
      totalInAmount: Math.round(stats.totalInAmount),
      totalOutAmount: Math.round(stats.totalOutAmount),
      balance: Math.round(stats.totalInAmount - stats.totalOutAmount),
      inUniqueCounterparties: inUnique,
      outUniqueCounterparties: outUnique,
      firstSeen: stats.firstSeen,
      lastActive: stats.lastActive,
      degree,
      isHub,
      hubScore: isHub ? degree : 0,
      pageRank: pageRank.get(nodeId) || 0,
      closenessCentrality: closeness.get(nodeId) || 0,
      betweennessCentrality: betweenness.get(nodeId) || 0,
      clusteringCoefficient: clustering.get(nodeId) || 0,
      communityId: labelToCommunity.get(labels.get(nodeId)),
      componentId: componentIds.get(componentMap.get(nodeId)),
      componentSize: componentSizes.get(componentMap.get(nodeId)) || 1,
      reasonCodes,
      ruleContributions: contributions,
      timeline,
      counterpartySummary: cpSummary
    };

    nodesMap.set(nodeId, { ...nodesMap.get(nodeId), ...nodeData });
    nodeRiskScores.push(score);
  }

  const sortedScores = nodeRiskScores.slice().sort((a, b) => b - a);
  const topCount = Math.max(1, Math.ceil(sortedScores.length * 0.1));
  const topScores = sortedScores.slice(0, topCount);
  const avgTop = topScores.length ? topScores.reduce((a, b) => a + b, 0) / topScores.length : 0;
  const maxScore = sortedScores.length ? sortedScores[0] : 0;
  const clusterRiskScore = Math.round(maxScore * 0.6 + avgTop * 0.4);
  const clusterRiskBand = riskBandFromScore(clusterRiskScore);

  for (const node of nodesMap.values()) {
    node.clusterRiskScore = clusterRiskScore;
    node.clusterRiskBand = clusterRiskBand;
    node.clusterHighlight = clusterRiskScore >= 60;
  }

  const suspiciousNodes = new Set(nodeIds.filter(id => (nodesMap.get(id)?.riskScore || 0) >= 60));
  const suspiciousEdges = [];
  for (const edge of edgesMap.values()) {
    if (suspiciousNodes.has(edge.source) || suspiciousNodes.has(edge.target)) suspiciousEdges.push(edge);
  }

  const edges = Array.from(edgesMap.values()).map(edge => {
    const direction = focusSet.has(edge.target) && !focusSet.has(edge.source)
      ? 'incoming'
      : focusSet.has(edge.source) && !focusSet.has(edge.target)
        ? 'outgoing'
        : 'internal';
    const amount = edge.amount;
    const size = Math.max(1, Math.min(6, Math.log10(amount + 1)));
    return {
      id: edge.id,
      source: edge.source,
      target: edge.target,
      amount,
      timestamp: edge.lastTimestamp,
      frequency: edge.frequency,
      direction,
      value: amount,
      weight: edge.frequency,
      size
    };
  });

  const graph = {
    nodes: Array.from(nodesMap.values()),
    edges,
    metadata: {
      clusterRiskScore,
      clusterRiskBand,
      totalNodes: nodeIds.length,
      totalEdges: edges.length,
      communities,
      suspiciousSubgraph: {
        nodes: Array.from(suspiciousNodes).map(id => nodesMap.get(id)),
        edges: suspiciousEdges
      }
    }
  };

  const risk = {
    clusterRiskScore,
    clusterRiskBand
  };

  const highRiskCount = Array.from(nodesMap.values()).filter(n => n.riskScore >= 60).length;
  const criticalRiskCount = Array.from(nodesMap.values()).filter(n => n.riskScore >= 80).length;

  logger.info('Analysis completed successfully', {
    totalNodes: nodeIds.length,
    totalEdges: edges.length,
    clusterRiskScore,
    clusterRiskBand,
    highRiskAccounts: highRiskCount,
    criticalRiskAccounts: criticalRiskCount,
    communityCount: Object.keys(communities).length
  });

  return { graph, risk, metadata: graph.metadata };
};
