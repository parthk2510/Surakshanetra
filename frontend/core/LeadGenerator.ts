// @ts-nocheck
export class LeadGenerator {
    constructor(config = {}) {
      this.config = {
        bridgeThreshold: config.bridgeThreshold || 0.3,
        mixerInputRatio: config.mixerInputRatio || 20,
        mixerFreshRatio: config.mixerFreshRatio || 0.75,
        dustThreshold: config.dustThreshold || 1000,
        whaleThreshold: config.whaleThreshold || 100e8,
        megaWhaleThreshold: config.megaWhaleThreshold || 1000e8,
        consolidationWindow: config.consolidationWindow || 3600,
        minConsolidationTx: config.minConsolidationTx || 10,
        cycleMaxDepth: config.cycleMaxDepth || 10,
        peelChainDepth: config.peelChainDepth || 5,
        structuringThreshold: config.structuringThreshold || 10e8,
        structuringWindow: config.structuringWindow || 86400,
        sleepingWhaleAge: config.sleepingWhaleAge || 31536000 * 3,
        coinjoinOutputs: config.coinjoinOutputs || 5,
        coinjoinEquality: config.coinjoinEquality || 0.95,
        batchOutputThreshold: config.batchOutputThreshold || 50,
        riskScoreThresholds: config.riskScoreThresholds || { critical: 80, high: 60, medium: 40, low: 20 },
        ...config
      };
    }
  
    generateLeads(caseFile) {
      const { nodes, edges, detectedCommunities: communities, globalContext } = caseFile;
      this.nodes = new Map(Object.entries(nodes));
      this.edges = edges;
      this.communities = communities;
      this.globalContext = globalContext;
      this.adjacencyList = this._buildAdjacencyList();
      this.incomingMap = this._buildIncomingMap();
      this.timestampSorted = this._sortEdgesByTimestamp();
      this.riskScores = new Map();
      
      const leads = [];
      const detectors = [
        () => this._detectBridgeMules(),
        () => this._detectMixerPatterns(),
        () => this._detectTimingAnomalies(),
        () => this._detectDustingAttacks(),
        () => this._detectWhales(),
        () => this._detectRapidConsolidation(),
        () => this._detectCircularFlows(),
        () => this._detectFreshOutputs(),
        () => this._detectPeelChains(),
        () => this._detectStructuring(),
        () => this._detectSleepingWhales(),
        () => this._detectCoinjoin(),
        () => this._detectBatching(),
        () => this._detectLayering(),
        () => this._detectExchangePatterns(),
        () => this._calculateRiskScores()
      ];
  
      for (const detector of detectors) {
        try {
          leads.push(...detector());
        } catch (e) {
          continue;
        }
      }
  
      return leads
        .filter((lead, idx, arr) => idx === arr.findIndex(l => l.id === lead.id))
        .sort((a, b) => {
          const scoreDiff = (b.riskScore || 0) - (a.riskScore || 0);
          if (scoreDiff !== 0) return scoreDiff;
          const priorityOrder = { critical: 0, high: 1, medium: 2, low: 3 };
          return priorityOrder[a.priority] - priorityOrder[b.priority];
        });
    }
  
    _buildAdjacencyList() {
      const adjacency = new Map();
      for (const node of this.nodes.values()) {
        if (node.type === 'address') adjacency.set(node.id, []);
      }
      for (const edge of this.edges) {
        if (this.nodes.has(edge.source) && this.nodes.has(edge.target)) {
          adjacency.get(edge.source)?.push(edge);
        }
      }
      return adjacency;
    }
  
    _buildIncomingMap() {
      const incoming = new Map();
      for (const node of this.nodes.values()) {
        if (node.type === 'address') incoming.set(node.id, []);
      }
      for (const edge of this.edges) {
        if (this.nodes.has(edge.target)) {
          incoming.get(edge.target)?.push(edge);
        }
      }
      return incoming;
    }
  
    _sortEdgesByTimestamp() {
      return this.edges.filter(e => e.timestamp).sort((a, b) => a.timestamp - b.timestamp);
    }
  
    _detectBridgeMules() {
      const leads = [];
      const communityMap = new Map();
      for (const node of this.nodes.values()) {
        if (node.communityId !== null) {
          if (!communityMap.has(node.communityId)) communityMap.set(node.communityId, new Set());
          communityMap.get(node.communityId).add(node.id);
        }
      }
  
      for (const node of this.nodes.values()) {
        if (node.type !== 'address' || !node.betweennessCentrality || node.betweennessCentrality < this.config.bridgeThreshold) continue;
        
        const connected = new Set();
        const edges = this.adjacencyList.get(node.id) || [];
        const incoming = this.incomingMap.get(node.id) || [];
        
        for (const edge of [...edges, ...incoming]) {
          const otherId = edge.source === node.id ? edge.target : edge.source;
          const other = this.nodes.get(otherId);
          if (other?.communityId !== null) connected.add(other.communityId);
        }
  
        if (connected.size >= 2) {
          leads.push({
            id: `bridge_${node.id}_${Date.now()}`,
            type: 'bridge_mule',
            priority: 'high',
            nodeId: node.id,
            riskScore: Math.min(95, 60 + node.betweennessCentrality * 40),
            description: `🌉 Bridge Mule: High betweenness (${(node.betweennessCentrality * 100).toFixed(1)}%) connects ${connected.size} communities`,
            evidence: {
              betweenness: node.betweennessCentrality,
              communitiesConnected: connected.size,
              balance: node.balance,
              txCount: node.txCount,
              degree: edges.length + incoming.length
            },
            timestamp: new Date().toISOString(),
            status: 'new'
          });
        }
      }
      return leads;
    }
  
    _detectMixerPatterns() {
      const leads = [];
      for (const node of this.nodes.values()) {
        if (node.type !== 'address') continue;
        
        const inputs = this.incomingMap.get(node.id) || [];
        const outputs = this.adjacencyList.get(node.id) || [];
        
        if (inputs.length === 1 && outputs.length >= this.config.mixerInputRatio) {
          const fresh = outputs.filter(e => {
            const target = this.nodes.get(e.target);
            return target?.type === 'address' && (target.txCount || 0) <= 1;
          });
          
          if (fresh.length >= outputs.length * this.config.mixerFreshRatio) {
            leads.push({
              id: `mixer_${node.id}_${Date.now()}`,
              type: 'mixer_pattern',
              priority: 'critical',
              nodeId: node.id,
              riskScore: 90,
              description: `🔄 Mixer: ${outputs.length} outputs, ${fresh.length} fresh addresses`,
              evidence: {
                inputCount: 1,
                outputCount: outputs.length,
                freshOutputCount: fresh.length,
                totalValue: outputs.reduce((s, e) => s + (e.value || 0), 0),
                fanOutRatio: outputs.length
              },
              timestamp: new Date().toISOString(),
              status: 'new'
            });
          }
        }
  
        if (inputs.length >= this.config.mixerInputRatio && outputs.length === 1) {
          leads.push({
            id: `consolidation_mixer_${node.id}_${Date.now()}`,
            type: 'mixer_pattern',
            priority: 'high',
            nodeId: node.id,
            riskScore: 75,
            description: `🔀 Reverse Mixer: ${inputs.length} inputs to 1 output`,
            evidence: {
              inputCount: inputs.length,
              outputCount: 1,
              totalValue: inputs.reduce((s, e) => s + (e.value || 0), 0),
              fanInRatio: inputs.length
            },
            timestamp: new Date().toISOString(),
            status: 'new'
          });
        }
      }
      return leads;
    }
  
    _detectTimingAnomalies() {
      const leads = [];
      if (!this.globalContext?.transactionRate?.length) return leads;
      
      const rates = this.globalContext.transactionRate;
      const avgRate = rates.reduce((s, p) => s + p.y, 0) / rates.length;
      const stdev = Math.sqrt(rates.reduce((s, p) => s + Math.pow(p.y - avgRate, 2), 0) / rates.length);
      const threshold = avgRate - (2 * stdev);
  
      const rateMap = new Map(rates.map(p => [Math.floor(p.x / 86400), p.y]));
  
      for (const node of this.nodes.values()) {
        if (node.type !== 'address' || !node.lastActive) continue;
        
        const day = Math.floor(node.lastActive / 86400);
        const rate = rateMap.get(day);
        
        if (rate && rate < threshold) {
          const deviation = ((threshold - rate) / threshold) * 100;
          leads.push({
            id: `timing_${node.id}_${Date.now()}`,
            type: 'timing_anomaly',
            priority: deviation > 50 ? 'high' : 'medium',
            nodeId: node.id,
            riskScore: Math.min(70, 40 + deviation * 0.6),
            description: `⏰ Timing Anomaly: Transaction during ${deviation.toFixed(0)}% network dip`,
            evidence: {
              txTime: node.lastActive,
              networkRate: rate,
              avgRate: avgRate,
              deviation: deviation.toFixed(2),
              zScore: ((rate - avgRate) / stdev).toFixed(2)
            },
            timestamp: new Date().toISOString(),
            status: 'new'
          });
        }
      }
      return leads;
    }
  
    _detectDustingAttacks() {
      const leads = [];
      for (const node of this.nodes.values()) {
        if (node.type !== 'address' || !node.utxos?.length) continue;
        
        const dust = node.utxos.filter(u => u.value < this.config.dustThreshold);
        const percentage = (dust.length / node.utxos.length) * 100;
        
        if (dust.length >= 10 && percentage > 50) {
          leads.push({
            id: `dusting_${node.id}_${Date.now()}`,
            type: 'dusting_attack',
            priority: dust.length > 50 ? 'high' : 'medium',
            nodeId: node.id,
            riskScore: Math.min(65, 30 + dust.length * 0.7 + percentage * 0.3),
            description: `💨 Dusting: ${dust.length} dust UTXOs (${percentage.toFixed(0)}%)`,
            evidence: {
              totalUTXOs: node.utxos.length,
              dustUTXOs: dust.length,
              dustPercentage: percentage,
              maxDustValue: Math.max(...dust.map(u => u.value)),
              totalDustValue: dust.reduce((s, u) => s + u.value, 0)
            },
            timestamp: new Date().toISOString(),
            status: 'new'
          });
        }
      }
      return leads;
    }
  
    _detectWhales() {
      const leads = [];
      for (const node of this.nodes.values()) {
        if (node.type !== 'address' || node.balance < this.config.whaleThreshold) continue;
        
        const btc = node.balance / 1e8;
        let priority = 'medium';
        let riskScore = 50;
        
        if (node.balance > this.config.megaWhaleThreshold) {
          priority = 'critical';
          riskScore = 85;
        } else if (node.balance > this.config.whaleThreshold * 5) {
          priority = 'high';
          riskScore = 70;
        }
        
        leads.push({
          id: `whale_${node.id}_${Date.now()}`,
          type: 'whale',
          priority,
          nodeId: node.id,
          riskScore,
          description: `🐋 Whale: ${btc.toFixed(2)} BTC`,
          evidence: {
            balance: node.balance,
            btcAmount: btc,
            txCount: node.txCount,
            totalReceived: node.totalReceived,
            totalSent: node.totalSent,
            utxoCount: node.utxos?.length || 0
          },
          timestamp: new Date().toISOString(),
          status: 'new'
        });
      }
      return leads;
    }
  
    _detectRapidConsolidation() {
      const leads = [];
      for (const node of this.nodes.values()) {
        if (node.type !== 'address') continue;
        
        const incoming = (this.incomingMap.get(node.id) || [])
          .filter(e => e.timestamp)
          .sort((a, b) => a.timestamp - b.timestamp);
        
        if (incoming.length < this.config.minConsolidationTx) continue;
        
        for (let i = 0; i <= incoming.length - this.config.minConsolidationTx; i++) {
          const window = incoming.slice(i, i + this.config.minConsolidationTx);
          const timeDiff = window[window.length - 1].timestamp - window[0].timestamp;
          
          if (timeDiff <= this.config.consolidationWindow) {
            const value = window.reduce((s, e) => s + (e.value || 0), 0);
            const rate = window.length / timeDiff * 3600;
            
            leads.push({
              id: `consolidation_${node.id}_${window[0].timestamp}`,
              type: 'rapid_consolidation',
              priority: rate > 20 ? 'critical' : 'high',
              nodeId: node.id,
              riskScore: Math.min(90, 50 + rate * 2 + window.length * 2),
              description: `⚡ Rapid Consolidation: ${window.length} txs in ${(timeDiff / 60).toFixed(0)}min (${rate.toFixed(1)}/hour)`,
              evidence: {
                txCount: window.length,
                timeWindow: timeDiff,
                totalValue: value,
                startTime: window[0].timestamp,
                endTime: window[window.length - 1].timestamp,
                ratePerHour: rate,
                btcValue: value / 1e8
              },
              timestamp: new Date().toISOString(),
              status: 'new'
            });
            break;
          }
        }
      }
      return leads;
    }
  
    _detectCircularFlows() {
      const leads = [];
      const visited = new Set();
      
      const findCycles = (startId, maxDepth) => {
        const cycles = [];
        const path = [];
        const pathSet = new Set();
        
        const dfs = (nodeId, depth) => {
          if (depth > maxDepth) return;
          path.push(nodeId);
          pathSet.add(nodeId);
          
          for (const edge of this.adjacencyList.get(nodeId) || []) {
            if (pathSet.has(edge.target)) {
              const startIdx = path.indexOf(edge.target);
              cycles.push(path.slice(startIdx));
            } else if (!visited.has(edge.target)) {
              dfs(edge.target, depth + 1);
            }
          }
          
          path.pop();
          pathSet.delete(nodeId);
        };
        
        dfs(startId, 0);
        return cycles;
      };
      
      for (const node of this.nodes.values()) {
        if (node.type !== 'address' || visited.has(node.id)) continue;
        
        const cycles = findCycles(node.id, this.config.cycleMaxDepth);
        for (const cycle of cycles) {
          if (cycle.length >= 3) {
            const key = [...cycle].sort().join(',');
            if (!visited.has(`cycle_${key}`)) {
              visited.add(`cycle_${key}`);
              leads.push({
                id: `circular_${node.id}_${Date.now()}_${cycle.length}`,
                type: 'circular_flow',
                priority: cycle.length > 5 ? 'critical' : 'high',
                nodeId: node.id,
                riskScore: Math.min(95, 50 + cycle.length * 8),
                description: `🔁 Circular Flow: ${cycle.length}-hop cycle detected`,
                evidence: {
                  cycleLength: cycle.length,
                  cyclePath: cycle,
                  startNode: node.id,
                  approximateValue: this._getCycleValue(cycle)
                },
                timestamp: new Date().toISOString(),
                status: 'new'
              });
            }
          }
        }
        visited.add(node.id);
      }
      return leads;
    }
  
    _getCycleValue(cycle) {
      let minValue = Infinity;
      for (let i = 0; i < cycle.length; i++) {
        const src = cycle[i];
        const dst = cycle[(i + 1) % cycle.length];
        const edge = (this.adjacencyList.get(src) || []).find(e => e.target === dst);
        if (edge?.value) minValue = Math.min(minValue, edge.value);
      }
      return minValue === Infinity ? 0 : minValue;
    }
  
    _detectFreshOutputs() {
      const leads = [];
      for (const node of this.nodes.values()) {
        if (node.type !== 'address') continue;
        
        const outputs = this.adjacencyList.get(node.id) || [];
        if (outputs.length < 5) continue;
        
        const fresh = outputs.filter(e => {
          const target = this.nodes.get(e.target);
          return target?.type === 'address' && (target.txCount || 0) <= 1;
        });
        
        const percentage = (fresh.length / outputs.length) * 100;
        if (fresh.length >= 5 && percentage >= 70) {
          leads.push({
            id: `fresh_${node.id}_${Date.now()}`,
            type: 'fresh_outputs',
            priority: percentage > 90 ? 'high' : 'medium',
            nodeId: node.id,
            riskScore: Math.min(75, 40 + percentage * 0.4 + fresh.length * 0.5),
            description: `🆕 Fresh Outputs: ${fresh.length}/${outputs.length} (${percentage.toFixed(0)}%) to new addresses`,
            evidence: {
              totalOutputs: outputs.length,
              freshOutputs: fresh.length,
              freshPercentage: percentage,
              totalValue: outputs.reduce((s, e) => s + (e.value || 0), 0)
            },
            timestamp: new Date().toISOString(),
            status: 'new'
          });
        }
      }
      return leads;
    }
  
    _detectPeelChains() {
      const leads = [];
      for (const node of this.nodes.values()) {
        if (node.type !== 'address') continue;
        
        const outputs = this.adjacencyList.get(node.id) || [];
        if (outputs.length !== 2) continue;
        
        const sorted = outputs.sort((a, b) => (b.value || 0) - (a.value || 0));
        if (!sorted[0] || !sorted[1]) continue;
        
        const changeAddr = this.nodes.get(sorted[1].target);
        if (!changeAddr || changeAddr.type !== 'address') continue;
        
        let depth = 1;
        let current = changeAddr;
        const chain = [node.id, current.id];
        
        while (depth < this.config.peelChainDepth) {
          const currentOutputs = this.adjacencyList.get(current.id) || [];
          if (currentOutputs.length !== 2) break;
          
          const currentSorted = currentOutputs.sort((a, b) => (b.value || 0) - (a.value || 0));
          const nextChange = this.nodes.get(currentSorted[1].target);
          if (!nextChange || nextChange.type !== 'address' || chain.includes(nextChange.id)) break;
          
          chain.push(nextChange.id);
          current = nextChange;
          depth++;
        }
        
        if (depth >= this.config.peelChainDepth) {
          leads.push({
            id: `peel_${node.id}_${Date.now()}`,
            type: 'peel_chain',
            priority: 'critical',
            nodeId: node.id,
            riskScore: 92,
            description: `📉 Peel Chain: ${depth + 1}-address sequential chain detected`,
            evidence: {
              chainLength: depth + 1,
              chainPath: chain,
              initialValue: sorted[0].value + sorted[1].value,
              finalValue: sorted[1].value
            },
            timestamp: new Date().toISOString(),
            status: 'new'
          });
        }
      }
      return leads;
    }
  
    _detectStructuring() {
      const leads = [];
      const structuringMap = new Map();
      
      for (const edge of this.timestampSorted) {
        if (!edge.timestamp || !this.nodes.has(edge.source)) continue;
        
        const day = Math.floor(edge.timestamp / this.config.structuringWindow);
        const key = `${edge.source}_${day}`;
        
        if (!structuringMap.has(key)) structuringMap.set(key, { count: 0, total: 0, timestamps: [] });
        structuringMap.get(key).count++;
        structuringMap.get(key).total += edge.value || 0;
        structuringMap.get(key).timestamps.push(edge.timestamp);
      }
      
      for (const [key, data] of structuringMap) {
        if (data.count < 5) continue;
        
        const avgTx = data.total / data.count;
        if (avgTx < this.config.structuringThreshold && avgTx > this.config.dustThreshold) {
          const [nodeId] = key.split('_');
          const node = this.nodes.get(nodeId);
          if (!node || node.type !== 'address') continue;
          
          leads.push({
            id: `structuring_${key}_${Date.now()}`,
            type: 'structuring',
            priority: data.count > 10 ? 'high' : 'medium',
            nodeId: nodeId,
            riskScore: Math.min(80, 40 + data.count * 3 + (data.total / 1e8) * 2),
            description: `🏦 Structuring: ${data.count} txs averaging ${(avgTx / 1e8).toFixed(4)} BTC`,
            evidence: {
              transactionCount: data.count,
              averageValue: avgTx,
              totalValue: data.total,
              timeWindow: this.config.structuringWindow,
              firstTx: Math.min(...data.timestamps),
              lastTx: Math.max(...data.timestamps)
            },
            timestamp: new Date().toISOString(),
            status: 'new'
          });
        }
      }
      return leads;
    }
  
    _detectSleepingWhales() {
      const leads = [];
      const now = Date.now() / 1000;
      
      for (const node of this.nodes.values()) {
        if (node.type !== 'address' || node.balance < this.config.whaleThreshold) continue;
        if (!node.firstSeen || !node.lastActive) continue;
        
        const age = now - node.firstSeen;
        const dormant = now - node.lastActive;
        const dormancyRatio = dormant / age;
        
        if (age > this.config.sleepingWhaleAge && dormant < 86400 && node.txCount <= 2) {
          leads.push({
            id: `sleeping_${node.id}_${Date.now()}`,
            type: 'sleeping_whale',
            priority: 'critical',
            nodeId: node.id,
            riskScore: 88,
            description: `💤 Sleeping Whale: ${(node.balance / 1e8).toFixed(2)} BTC after ${(dormant / 86400).toFixed(0)}d dormancy`,
            evidence: {
              balance: node.balance,
              ageDays: (age / 86400).toFixed(0),
              dormantDays: (dormant / 86400).toFixed(0),
              dormancyRatio: dormancyRatio.toFixed(3),
              txCount: node.txCount
            },
            timestamp: new Date().toISOString(),
            status: 'new'
          });
        }
      }
      return leads;
    }
  
    _detectCoinjoin() {
      const leads = [];
      const txMap = new Map();
      
      for (const edge of this.edges) {
        if (!txMap.has(edge.txId)) txMap.set(edge.txId, { inputs: [], outputs: [] });
        const tx = txMap.get(edge.txId);
        if (this.nodes.has(edge.source) && this.nodes.get(edge.source).type === 'address') tx.inputs.push(edge);
        if (this.nodes.has(edge.target) && this.nodes.get(edge.target).type === 'address') tx.outputs.push(edge);
      }
      
      for (const [txId, tx] of txMap) {
        if (tx.inputs.length < 3 || tx.outputs.length < this.config.coinjoinOutputs) continue;
        
        const outputValues = tx.outputs.map(o => o.value || 0).sort((a, b) => a - b);
        const median = outputValues[Math.floor(outputValues.length / 2)];
        const equalOutputs = outputValues.filter(v => Math.abs(v - median) / median < (1 - this.config.coinjoinEquality));
        
        if (equalOutputs.length >= this.config.coinjoinOutputs) {
          leads.push({
            id: `coinjoin_${txId}_${Date.now()}`,
            type: 'coinjoin',
            priority: 'high',
            nodeId: tx.outputs[0].source,
            riskScore: 78,
            description: `🎲 CoinJoin: ${tx.inputs.length} inputs × ${equalOutputs.length} equal outputs`,
            evidence: {
              transactionId: txId,
              inputCount: tx.inputs.length,
              outputCount: tx.outputs.length,
              equalOutputCount: equalOutputs.length,
              equalOutputValue: median,
              anonymitySet: equalOutputs.length
            },
            timestamp: new Date().toISOString(),
            status: 'new'
          });
        }
      }
      return leads;
    }
  
    _detectBatching() {
      const leads = [];
      const sourceMap = new Map();
      
      for (const edge of this.edges) {
        if (!this.nodes.has(edge.source)) continue;
        const key = `${edge.source}_${Math.floor((edge.timestamp || 0) / 3600)}`;
        if (!sourceMap.has(key)) sourceMap.set(key, []);
        sourceMap.get(key).push(edge);
      }
      
      for (const [key, edges] of sourceMap) {
        if (edges.length < this.config.batchOutputThreshold) continue;
        
        const uniqueOutputs = new Set(edges.map(e => e.target));
        if (uniqueOutputs.size < this.config.batchOutputThreshold) continue;
        
        const [nodeId] = key.split('_');
        const node = this.nodes.get(nodeId);
        if (!node || node.type !== 'address') continue;
        
        leads.push({
          id: `batch_${key}_${Date.now()}`,
          type: 'batching',
          priority: 'medium',
          nodeId: nodeId,
          riskScore: 45 + Math.min(30, uniqueOutputs.size * 0.5),
          description: `📦 Batching: ${uniqueOutputs.size} outputs in 1 hour window`,
          evidence: {
            outputCount: uniqueOutputs.size,
            hourKey: key.split('_')[1],
            totalValue: edges.reduce((s, e) => s + (e.value || 0), 0),
            averageValue: edges.reduce((s, e) => s + (e.value || 0), 0) / edges.length
          },
          timestamp: new Date().toISOString(),
          status: 'new'
        });
      }
      return leads;
    }
  
    _detectLayering() {
      const leads = [];
      const minHops = 5;
      
      for (const node of this.nodes.values()) {
        if (node.type !== 'address') continue;
        
        const paths = [];
        const stack = [{ nodeId: node.id, path: [node.id], value: Infinity, depth: 0 }];
        
        while (stack.length > 0) {
          const { nodeId, path, value, depth } = stack.pop();
          
          if (depth >= minHops) {
            paths.push({ path, minValue: value, length: depth });
            continue;
          }
          
          const outputs = this.adjacencyList.get(nodeId) || [];
          for (const edge of outputs.slice(0, 10)) {
            if (path.includes(edge.target)) continue;
            stack.push({
              nodeId: edge.target,
              path: [...path, edge.target],
              value: Math.min(value, edge.value || Infinity),
              depth: depth + 1
            });
          }
        }
        
        const layeringPaths = paths.filter(p => p.length >= minHops && p.minValue > 0);
        if (layeringPaths.length > 0) {
          const avgLen = layeringPaths.reduce((s, p) => s + p.length, 0) / layeringPaths.length;
          leads.push({
            id: `layering_${node.id}_${Date.now()}`,
            type: 'layering',
            priority: avgLen > 8 ? 'critical' : 'high',
            nodeId: node.id,
            riskScore: Math.min(90, 50 + avgLen * 5 + layeringPaths.length * 2),
            description: `🥞 Layering: ${layeringPaths.length} paths averaging ${avgLen.toFixed(1)} hops`,
            evidence: {
              pathCount: layeringPaths.length,
              averageLength: avgLen,
              shortestPath: Math.min(...layeringPaths.map(p => p.length)),
              longestPath: Math.max(...layeringPaths.map(p => p.length))
            },
            timestamp: new Date().toISOString(),
            status: 'new'
          });
        }
      }
      return leads;
    }
  
    _detectExchangePatterns() {
      const leads = [];
      for (const node of this.nodes.values()) {
        if (node.type !== 'address') continue;
        
        const inputs = this.incomingMap.get(node.id) || [];
        const outputs = this.adjacencyList.get(node.id) || [];
        
        const isDeposit = inputs.length >= 50 && outputs.length === 1 && inputs.length > outputs.length * 20;
        const isWithdrawal = inputs.length === 1 && outputs.length >= 50 && outputs.length > inputs.length * 20;
        
        if (isDeposit || isWithdrawal) {
          leads.push({
            id: `exchange_${node.id}_${Date.now()}`,
            type: 'exchange_pattern',
            priority: 'high',
            nodeId: node.id,
            riskScore: 70,
            description: `🏦 Exchange ${isDeposit ? 'Deposit' : 'Withdrawal'}: ${isDeposit ? inputs.length : outputs.length} addresses`,
            evidence: {
              pattern: isDeposit ? 'deposit' : 'withdrawal',
              inputCount: inputs.length,
              outputCount: outputs.length,
              totalVolume: (isDeposit ? inputs : outputs).reduce((s, e) => s + (e.value || 0), 0)
            },
            timestamp: new Date().toISOString(),
            status: 'new'
          });
        }
      }
      return leads;
    }
  
    _calculateRiskScores() {
      const leads = [];
      for (const node of this.nodes.values()) {
        if (node.type !== 'address') continue;
        
        let score = 0;
        const factors = [];
        
        if (node.betweennessCentrality > this.config.bridgeThreshold) {
          score += 20 * node.betweennessCentrality;
          factors.push('high_betweenness');
        }
        
        const inputs = this.incomingMap.get(node.id) || [];
        const outputs = this.adjacencyList.get(node.id) || [];
        const totalIO = inputs.length + outputs.length;
        
        if (totalIO > 100) {
          score += Math.min(15, totalIO * 0.1);
          factors.push('high_io_volume');
        }
        
        if (node.balance > this.config.whaleThreshold) {
          score += Math.min(20, (node.balance / this.config.megaWhaleThreshold) * 20);
          factors.push('large_balance');
        }
        
        if (node.utxos?.length > 50) {
          score += Math.min(10, node.utxos.length * 0.1);
          factors.push('many_utxos');
        }
        
        const dustRatio = node.utxos?.filter(u => u.value < this.config.dustThreshold).length / (node.utxos?.length || 1);
        if (dustRatio > 0.5) {
          score += dustRatio * 15;
          factors.push('dust_utxos');
        }
        
        if (score > this.config.riskScoreThresholds.medium) {
          const priority = score > this.config.riskScoreThresholds.critical ? 'critical' :
                          score > this.config.riskScoreThresholds.high ? 'high' :
                          score > this.config.riskScoreThresholds.medium ? 'medium' : 'low';
          
          leads.push({
            id: `risk_${node.id}_${Date.now()}`,
            type: 'composite_risk',
            priority,
            nodeId: node.id,
            riskScore: Math.min(100, score),
            description: `📊 Composite Risk: Score ${Math.min(100, score).toFixed(1)}/100`,
            evidence: {
              riskScore: Math.min(100, score),
              riskFactors: factors,
              balance: node.balance,
              txCount: node.txCount,
              betweenness: node.betweennessCentrality,
              ioCount: totalIO
            },
            timestamp: new Date().toISOString(),
            status: 'new'
          });
        }
      }
      return leads;
    }
  }
  
  export function generateLeads(caseFile) {
    const generator = new LeadGenerator();
    return generator.generateLeads(caseFile);
  }
  
  export function getLeadPriorityColor(priority) {
    const colors = { critical: '#dc2626', high: '#f59e0b', medium: '#3b82f6', low: '#6b7280' };
    return colors[priority] || colors.low;
  }
  
  export function getLeadPriorityIcon(priority) {
    const icons = { critical: '🚨', high: '⚠️', medium: 'ℹ️', low: '📌' };
    return icons[priority] || icons.low;
  }
  
  export default { generateLeads, getLeadPriorityColor, getLeadPriorityIcon, LeadGenerator };
