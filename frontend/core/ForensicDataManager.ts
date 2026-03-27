// @ts-nocheck
// frontend/src/core/ForensicDataManager.ts
import blockchainService from '../utils/blockchainAPI';
import { runLeidenDetection } from './LeidenDetector';
import { generateLeads } from './LeadGenerator';
import toast from 'react-hot-toast';

export interface InvestigationOptions {
    fetchNeighbors?: boolean;
    fetchUTXOs?: boolean;
    fetchBlocks?: boolean;
    fetchCharts?: boolean;
    txLimit?: number;
    skipConfirmation?: boolean;
}

/**
 * ForensicDataManager - The Brain of the Investigation Engine
 * 
 * Manages the complete investigation state, orchestrates data fetching,
 * triggers community detection, and generates investigative leads.
 */
class ForensicDataManager {
    constructor() {
        this.currentCaseFile = this.initializeCaseFile();
        this.customCaseName = null;  // For user-defined case names
        this.listeners = new Set();
        this.dataFetchProgress = {
            address: false,
            multiAddress: false,
            unspent: false,
            blocks: false,
            charts: false,
            transactions: false
        };
        this.suspiciousAddresses = this.loadSuspiciousAddresses();
    }

    /**
     * Set a custom case name
     */
    setCaseName(name) {
        this.customCaseName = name;
        if (this.currentCaseFile) {
            this.currentCaseFile.metadata.caseId = name;
            this.currentCaseFile.metadata.lastUpdated = new Date().toISOString();
            this.notifyListeners();
        }
        return name;
    }

    /**
     * Get the current case name
     */
    getCaseName() {
        return this.currentCaseFile?.metadata?.caseId || this.customCaseName || 'Unnamed Case';
    }

    /**
     * Prompt user for case name (returns promise)
     */
    promptCaseName() {
        return new Promise((resolve) => {
            const defaultName = this.customCaseName || `Case-${new Date().toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }).replace(/ /g, '-')}`;
            const name = prompt('Enter a name for this investigation case:', defaultName);
            if (name && name.trim()) {
                resolve(this.setCaseName(name.trim()));
            } else {
                resolve(this.setCaseName(defaultName));
            }
        });
    }

    /**
     * Initialize empty case file structure
     */
    initializeCaseFile() {
        // Generate user-friendly default case name
        const dateStr = new Date().toLocaleDateString('en-US', {
            year: 'numeric', month: 'short', day: 'numeric'
        }).replace(/, /g, '-').replace(/ /g, '-');
        const defaultCaseId = this.customCaseName || `Investigation-${dateStr}`;

        return {
            metadata: {
                caseId: defaultCaseId,
                createdAt: new Date().toISOString(),
                lastUpdated: new Date().toISOString(),
                primaryAddress: null,
                investigatedAddresses: []
            },
            nodes: {
                // address_id: {
                //   id: string,
                //   type: 'address' | 'transaction',
                //   balance: number,
                //   totalReceived: number,
                //   totalSent: number,
                //   txCount: number,
                //   utxos: [],
                //   riskScore: number,
                //   communityId: number,
                //   betweennessCentrality: number,
                //   isSuspicious: boolean,
                //   tags: [],
                //   firstSeen: timestamp,
                //   lastActive: timestamp
                // }
            },
            edges: [
                // {
                //   id: string,
                //   source: string,
                //   target: string,
                //   value: number,
                //   timestamp: number,
                //   txHash: string
                // }
            ],
            transactions: {
                // tx_hash: {
                //   hash: string,
                //   time: number,
                //   blockHash: string,
                //   blockHeight: number,
                //   fee: number,
                //   inputs: [],
                //   outputs: [],
                //   minerPool: string | null
                // }
            },
            blocks: {
                // block_hash: {
                //   hash: string,
                //   height: number,
                //   time: number,
                //   miner: string,
                //   pool: string | null,
                //   txCount: number
                // }
            },
            globalContext: {
                marketPrice: 0,
                networkHashRate: 0,
                networkDifficulty: 0,
                transactionRate: [],
                lastBlockHeight: 0,
                mempoolSize: 0
            },
            detectedCommunities: {
                // communityId: {
                //   id: number,
                //   nodes: [],
                //   size: number,
                //   totalValue: number,
                //   avgRiskScore: number
                // }
            },
            investigativeLeads: [
                // {
                //   id: string,
                //   type: 'bridge_mule' | 'mixer_pattern' | 'timing_anomaly' | 'whale' | 'dusting',
                //   priority: 'low' | 'medium' | 'high' | 'critical',
                //   nodeId: string,
                //   description: string,
                //   evidence: {},
                //   timestamp: string,
                //   status: 'new' | 'investigating' | 'resolved'
                // }
            ],
            suspiciousPatterns: {
                mixerCandidates: [],
                bridgeNodes: [],
                timingAnomalies: [],
                dustingTargets: [],
                whales: []
            }
        };
    }

    /**
     * Load suspicious addresses from localStorage
     */
    loadSuspiciousAddresses() {
        try {
            const stored = localStorage.getItem('chainbreak_suspicious_addresses');
            return stored ? JSON.parse(stored) : [];
        } catch (error) {
            console.error('Failed to load suspicious addresses:', error);
            return [];
        }
    }

    loadCaseFile(caseFileData) {
        this.currentCaseFile = caseFileData;
        this.notifyListeners();
    }

    /**
     * Save suspicious addresses to localStorage
     */
    saveSuspiciousAddresses() {
        try {
            localStorage.setItem(
                'chainbreak_suspicious_addresses',
                JSON.stringify(this.suspiciousAddresses)
            );
        } catch (error) {
            console.error('Failed to save suspicious addresses:', error);
        }
    }

    /**
     * Mark address as suspicious
     */
    markAsSuspicious(address, reason = '') {
        if (!this.suspiciousAddresses.find(a => a.address === address)) {
            this.suspiciousAddresses.push({
                address,
                reason,
                markedAt: new Date().toISOString()
            });
            this.saveSuspiciousAddresses();

            // Update node in case file
            if (this.currentCaseFile.nodes[address]) {
                this.currentCaseFile.nodes[address].isSuspicious = true;
                this.currentCaseFile.nodes[address].tags.push('suspicious');
            }

            this.notifyListeners();
        }
    }

    /**
     * Subscribe to case file updates
     */
    subscribe(callback) {
        this.listeners.add(callback);
        return () => this.listeners.delete(callback);
    }

    /**
     * Notify all listeners of state change
     */
    notifyListeners() {
        this.listeners.forEach(callback => callback(this.currentCaseFile, this.dataFetchProgress));
    }

    /**
     * DEEP FETCH - Orchestrate comprehensive data collection
     */
    async performDeepInvestigation(address: string, options: InvestigationOptions = {}) {
        const {
            fetchNeighbors = true,
            fetchUTXOs = true,
            fetchBlocks = true,
            fetchCharts = true,
            txLimit = 50,
            skipConfirmation = false
        } = options;

        const alreadyInvestigated = this.currentCaseFile.nodes[address] !== undefined;

        if (alreadyInvestigated && !skipConfirmation) {
            const nodeData = this.currentCaseFile.nodes[address];
            toast(`Address already investigated: ${(nodeData.balance / 100000000).toFixed(4)} BTC`, {
                icon: '⚠️',
                duration: 3001
            });
        }

        toast.loading('Starting deep investigation...', { id: 'deep-fetch', duration: 60000 });

        try {
            this.resetProgress();
            this.currentCaseFile.metadata.primaryAddress = address;
            this.currentCaseFile.metadata.lastUpdated = new Date().toISOString();
            if (!this.currentCaseFile.metadata.investigatedAddresses.includes(address)) {
                this.currentCaseFile.metadata.investigatedAddresses.push(address);
            }

            toast.loading('Phase 1/6: Fetching address data...', { id: 'deep-fetch' });
            await this.fetchAddressData(address, txLimit);
            await this.saveCaseToBackend();
            this.notifyListeners();

            if (fetchNeighbors) {
                toast.loading('Phase 2/6: Discovering neighbors...', { id: 'deep-fetch' });
                await this.fetchNeighborsData(address, txLimit);
                await this.saveCaseToBackend();
                this.notifyListeners();
            }

            if (fetchUTXOs) {
                toast.loading('Phase 3/6: Analyzing UTXOs...', { id: 'deep-fetch' });
                await this.fetchUTXOData(address);
                await this.saveCaseToBackend();
                this.notifyListeners();
            }

            if (fetchBlocks) {
                toast.loading('Phase 4/6: Fetching block data...', { id: 'deep-fetch' });
                await this.fetchBlocksData();
                await this.saveCaseToBackend();
                this.notifyListeners();
            }

            if (fetchCharts) {
                toast.loading('Phase 5/6: Loading market context...', { id: 'deep-fetch' });
                await this.fetchGlobalContext();
                await this.saveCaseToBackend();
                this.notifyListeners();
            }

            toast.loading('Phase 6/6: Running community detection...', { id: 'deep-fetch' });
            await this.runCommunityDetection();
            await this.generateInvestigativeLeads();

            await this.saveCaseToBackend();

            const nodeCount = Object.keys(this.currentCaseFile.nodes).length;
            const edgeCount = this.currentCaseFile.edges.length;
            toast.success(`Investigation complete: ${nodeCount} nodes, ${edgeCount} edges`, { id: 'deep-fetch' });

            this.notifyListeners();

            return this.currentCaseFile;

        } catch (error) {
            console.error('Deep investigation failed:', error);
            toast.error(`Investigation failed: ${error.message}`, { id: 'deep-fetch' });
            throw error;
        }
    }

    async saveCaseToBackend() {
        try {
            await blockchainService.saveCaseFile(this.currentCaseFile);
        } catch (error) {
            console.warn('Save failed:', error);
        }
    }

    /**
     * Phase 1: Fetch address data
     */
    async fetchAddressData(address, txLimit) {
        try {
            toast.loading('Fetching address data...', { id: 'phase-1' });
            let data;

            try {
                // Primary path: use comprehensive backend endpoint (fetches ALL transactions)
                data = await blockchainService.fetchAddressComprehensive(address);
            } catch (primaryError) {
                console.warn('fetchAddressComprehensive failed, falling back to lightweight address fetch:', primaryError);

                // Fallback path: build a compatible structure from simpler endpoints
                try {
                    const [addressResp, utxoResp] = await Promise.all([
                        blockchainService.fetchAddress(address, txLimit || 50),
                        blockchainService.fetchUnspent(address)
                    ]);

                    const addrPayload = addressResp.data || addressResp || {};
                    const utxoPayload = utxoResp.data || utxoResp || {};

                    const basicInfo = {
                        hash160: addrPayload.hash160 || '',
                        n_tx: addrPayload.n_tx || 0,
                        n_unredeemed: addrPayload.n_unredeemed || 0,
                        total_received: addrPayload.total_received || 0,
                        total_sent: addrPayload.total_sent || 0,
                        final_balance: addrPayload.final_balance || 0
                    };

                    data = {
                        success: true,
                        data: {
                            address,
                            basic_info: basicInfo,
                            transactions: addrPayload.txs || [],
                            unspent_outputs: utxoPayload.unspent_outputs || [],
                            balance_details: {
                                final_balance: basicInfo.final_balance,
                                total_received: basicInfo.total_received,
                                total_sent: basicInfo.total_sent,
                                n_tx: basicInfo.n_tx
                            }
                        }
                    };
                } catch (fallbackError) {
                    console.warn('Lightweight address fetch failed, using degraded placeholder:', fallbackError);

                    // Degraded path: allow graph rendering with an empty skeleton node
                    data = {
                        success: true,
                        degraded: true,
                        data: {
                            address,
                            basic_info: {
                                hash160: '',
                                n_tx: 0,
                                n_unredeemed: 0,
                                total_received: 0,
                                total_sent: 0,
                                final_balance: 0
                            },
                            transactions: [],
                            unspent_outputs: [],
                            balance_details: {
                                final_balance: 0,
                                total_received: 0,
                                total_sent: 0,
                                n_tx: 0
                            }
                        },
                        error: fallbackError?.message || 'No response from backend services'
                    };

                    toast.error('Backend unreachable. Rendering minimal graph with limited data.', { id: 'phase-1' });
                }
            }

            if (!data || (!data.success && !data.data)) throw new Error('Failed to fetch address data');

            console.log('[ForensicDataManager] Raw API response:', JSON.stringify(data).substring(0, 500));

            const addressData = data.data;
            console.log('[ForensicDataManager] Extracted addressData keys:', Object.keys(addressData || {}));

            // ================================================================
            // NEW SCHEMA: Backend returns nodes, edges, transactions as dict
            // If present, merge them directly — no redundant client-side building
            // ================================================================
            const hasNewSchema = addressData.nodes && typeof addressData.nodes === 'object' &&
                !Array.isArray(addressData.nodes) &&
                addressData.edges && Array.isArray(addressData.edges);

            if (hasNewSchema) {
                console.log('[ForensicDataManager] Using NEW schema: merging pre-built nodes/edges/transactions');

                // Merge metadata if provided
                if (addressData.metadata) {
                    Object.assign(this.currentCaseFile.metadata, addressData.metadata);
                }

                // Merge nodes directly
                const backendNodes = addressData.nodes || {};
                for (const [nodeId, nodeData] of Object.entries(backendNodes)) {
                    const isSuspicious = this.suspiciousAddresses.some(a => a.address === nodeId);
                    this.currentCaseFile.nodes[nodeId] = {
                        ...nodeData,
                        isSuspicious: isSuspicious || nodeData.isSuspicious || false,
                        tags: nodeData.tags || [],
                    };
                }

                // Merge edges — avoid duplicates
                const existingEdgeIds = new Set(this.currentCaseFile.edges.map(e => e.id));
                for (const edge of (addressData.edges || [])) {
                    if (!existingEdgeIds.has(edge.id)) {
                        this.currentCaseFile.edges.push(edge);
                        existingEdgeIds.add(edge.id);
                    }
                }

                // Merge transactions dict
                const backendTxs = addressData.transactions || {};
                if (typeof backendTxs === 'object' && !Array.isArray(backendTxs)) {
                    for (const [txHash, txData] of Object.entries(backendTxs)) {
                        this.currentCaseFile.transactions[txHash] = txData;
                    }
                }

                // Merge other case file sections if provided
                if (addressData.globalContext) {
                    Object.assign(this.currentCaseFile.globalContext, addressData.globalContext);
                }
                if (addressData.detectedCommunities) {
                    Object.assign(this.currentCaseFile.detectedCommunities, addressData.detectedCommunities);
                }
                if (addressData.suspiciousPatterns) {
                    Object.assign(this.currentCaseFile.suspiciousPatterns, addressData.suspiciousPatterns);
                }
                if (addressData.blocks) {
                    Object.assign(this.currentCaseFile.blocks, addressData.blocks);
                }

                const nodeCount = Object.keys(this.currentCaseFile.nodes).length;
                const edgeCount = this.currentCaseFile.edges.length;
                const txCount = Object.keys(this.currentCaseFile.transactions).length;
                console.log(`[ForensicDataManager] After merge: ${nodeCount} nodes, ${edgeCount} edges, ${txCount} transactions`);

                // Mark progress — the comprehensive endpoint covers address + transactions + UTXOs
                this.dataFetchProgress.address = true;
                this.dataFetchProgress.transactions = true;

                // If unspent_outputs are included, mark UTXO as synced too
                if (addressData.unspent_outputs && addressData.unspent_outputs.length > 0) {
                    this.dataFetchProgress.unspent = true;
                }

                toast.success(`Address data fetched: ${nodeCount} nodes, ${edgeCount} edges`, { id: 'phase-1' });
                return;
            }

            // ================================================================
            // OLD SCHEMA FALLBACK: Process raw transactions array
            // ================================================================
            console.log('[ForensicDataManager] Using OLD schema: processing raw transactions');

            const basicInfo = addressData.basic_info || {};
            const transactions = Array.isArray(addressData.transactions)
                ? addressData.transactions
                : Object.values(addressData.transactions || {});
            const unspentOutputs = addressData.unspent_outputs || [];

            console.log('[ForensicDataManager] basic_info:', JSON.stringify(basicInfo));
            console.log('[ForensicDataManager] transactions count:', transactions.length);
            console.log('[ForensicDataManager] unspentOutputs count:', unspentOutputs.length);

            let finalBalance = basicInfo.final_balance || 0;
            let totalReceived = basicInfo.total_received || 0;
            let totalSent = basicInfo.total_sent || 0;
            let txCount = basicInfo.n_tx || 0;

            const balanceDetails = addressData.balance_details || {};
            if (finalBalance === 0 && balanceDetails.final_balance) {
                finalBalance = balanceDetails.final_balance;
            }
            if (totalReceived === 0 && balanceDetails.total_received) {
                totalReceived = balanceDetails.total_received;
            }
            if (totalSent === 0 && balanceDetails.total_sent) {
                totalSent = balanceDetails.total_sent;
            }
            if (txCount === 0 && balanceDetails.n_tx) {
                txCount = balanceDetails.n_tx;
            }

            if (finalBalance === 0 && unspentOutputs.length > 0) {
                finalBalance = unspentOutputs.reduce((sum, utxo) => sum + (utxo.value || 0), 0);
                console.log(`[ForensicDataManager] Calculated balance from ${unspentOutputs.length} UTXOs: ${finalBalance} satoshis`);
            }

            if (txCount === 0 && transactions.length > 0) {
                txCount = transactions.length;
            }

            if (txCount === 0 && unspentOutputs.length > 0) {
                txCount = unspentOutputs.length;
            }

            console.log(`[ForensicDataManager] Address ${address.substring(0, 16)}... - Balance: ${finalBalance}, TxCount: ${txCount}, UTXOs: ${unspentOutputs.length}, Transactions: ${transactions.length}`);

            this.currentCaseFile.nodes[address] = {
                id: address,
                type: 'address',
                balance: finalBalance,
                totalReceived: totalReceived,
                totalSent: totalSent,
                txCount: txCount,
                utxos: unspentOutputs,
                riskScore: 0,
                communityId: null,
                betweennessCentrality: 0,
                isSuspicious: this.suspiciousAddresses.some(a => a.address === address),
                tags: [],
                firstSeen: null,
                lastActive: null,
                rawData: { ...basicInfo, ...balanceDetails }
            };

            // Process transactions
            let earliestTx = Infinity;
            let latestTx = 0;

            transactions.forEach(tx => {
                const txHash = tx.hash;

                // Store transaction
                this.currentCaseFile.transactions[txHash] = {
                    hash: txHash,
                    time: tx.time,
                    blockHash: tx.block_hash,
                    blockHeight: tx.block_height,
                    fee: tx.fee || 0,
                    inputs: tx.inputs || [],
                    outputs: tx.out || [],
                    minerPool: null,
                    rawData: tx
                };

                // Track timing
                if (tx.time && tx.time < earliestTx) earliestTx = tx.time;
                if (tx.time && tx.time > latestTx) latestTx = tx.time;

                // Create transaction node
                this.currentCaseFile.nodes[txHash] = {
                    id: txHash,
                    type: 'transaction',
                    time: tx.time,
                    fee: tx.fee || 0,
                    communityId: null,
                    rawData: tx
                };

                // Process inputs (edges from addresses to transaction)
                (tx.inputs || []).forEach(input => {
                    const prevAddr = input.prev_out?.addr;
                    if (prevAddr) {
                        this.currentCaseFile.edges.push({
                            id: `${prevAddr}->${txHash}`,
                            source: prevAddr,
                            target: txHash,
                            value: input.prev_out?.value || 0,
                            timestamp: tx.time,
                            txHash: txHash,
                            type: 'input'
                        });

                        if (!this.currentCaseFile.nodes[prevAddr]) {
                            this.currentCaseFile.nodes[prevAddr] = {
                                id: prevAddr,
                                type: 'address',
                                balance: 0,
                                txCount: 0,
                                communityId: null,
                                isSuspicious: this.suspiciousAddresses.some(a => a.address === prevAddr),
                                tags: []
                            };
                        }
                    }
                });

                // Process outputs (edges from transaction to addresses)
                (tx.out || []).forEach(output => {
                    const outAddr = output.addr;
                    if (outAddr) {
                        this.currentCaseFile.edges.push({
                            id: `${txHash}->${outAddr}`,
                            source: txHash,
                            target: outAddr,
                            value: output.value || 0,
                            timestamp: tx.time,
                            txHash: txHash,
                            type: 'output'
                        });

                        if (!this.currentCaseFile.nodes[outAddr]) {
                            this.currentCaseFile.nodes[outAddr] = {
                                id: outAddr,
                                type: 'address',
                                balance: 0,
                                txCount: 0,
                                communityId: null,
                                isSuspicious: this.suspiciousAddresses.some(a => a.address === outAddr),
                                tags: []
                            };
                        }
                    }
                });
            });

            // Update timing
            if (earliestTx !== Infinity) {
                this.currentCaseFile.nodes[address].firstSeen = earliestTx;
            }
            if (latestTx !== 0) {
                this.currentCaseFile.nodes[address].lastActive = latestTx;
            }

            this.dataFetchProgress.address = true;
            this.dataFetchProgress.transactions = true;
            toast.success('Address data fetched', { id: 'phase-1' });

        } catch (error) {
            console.error('Failed to fetch address data:', error);
            throw error;
        }
    }

    /**
     * Phase 2: Fetch neighbors data
     */
    async fetchNeighborsData(address, txLimit) {
        try {
            toast.loading('Analyzing network neighbors...', { id: 'phase-2' });

            // Get connected addresses
            const connectedAddresses = new Set();
            Object.values(this.currentCaseFile.nodes).forEach(node => {
                if (node.type === 'address' && node.id !== address) {
                    connectedAddresses.add(node.id);
                }
            });

            const addressArray = Array.from(connectedAddresses).slice(0, 10); // Limit to 10 neighbors

            if (addressArray.length > 0) {
                const multiData = await blockchainService.fetchClusterData(addressArray, txLimit);

                if (multiData.success) {
                    // Update nodes with additional data from multi-address
                    const addresses = multiData.data?.data?.addresses || [];
                    addresses.forEach(addr => {
                        if (this.currentCaseFile.nodes[addr.address]) {
                            this.currentCaseFile.nodes[addr.address].balance = addr.final_balance || 0;
                            this.currentCaseFile.nodes[addr.address].totalReceived = addr.total_received || 0;
                            this.currentCaseFile.nodes[addr.address].totalSent = addr.total_sent || 0;
                            this.currentCaseFile.nodes[addr.address].txCount = addr.n_tx || 0;
                        }
                    });
                }
            }

            // Always mark as complete, even if no neighbors were found
            // This ensures the progress indicator syncs correctly
            this.dataFetchProgress.multiAddress = true;
            this.notifyListeners(); // Notify immediately to update UI
            toast.success('Network neighbors analyzed', { id: 'phase-2' });

        } catch (error) {
            console.error('Failed to fetch neighbors:', error);
            // Even on error, mark as attempted so progress shows correctly
            this.dataFetchProgress.multiAddress = true;
            this.notifyListeners();
            // Don't throw - this is optional
        }
    }

    /**
     * Phase 3: Fetch UTXO data and RECALCULATE BALANCE
     * 
     * CRITICAL FIX: The comprehensive endpoint often fails, but UTXOs succeed.
     * Therefore we MUST recalculate balance from UTXOs here.
     */
    async fetchUTXOData(address) {
        try {
            toast.loading('Analyzing UTXOs...', { id: 'phase-3' });

            const utxoData = await blockchainService.fetchUnspent(address);

            if (utxoData.success && this.currentCaseFile.nodes[address]) {
                const utxos = utxoData.data?.unspent_outputs || [];
                this.currentCaseFile.nodes[address].utxos = utxos;

                // ================================================================
                // CRITICAL FIX: Recalculate balance from UTXOs
                // AND CREATE GRAPH EDGES from UTXOs
                // ================================================================
                if (utxos.length > 0) {
                    const calculatedBalance = utxos.reduce((sum, utxo) => sum + (utxo.value || 0), 0);

                    // Update balance if currently 0
                    const node = this.currentCaseFile.nodes[address];
                    if (node.balance === 0 || node.balance === undefined) {
                        node.balance = calculatedBalance;
                        console.log(`[ForensicDataManager] UTXO Phase: Calculated balance from ${utxos.length} UTXOs: ${calculatedBalance} satoshis (${(calculatedBalance / 100000000).toFixed(8)} BTC)`);
                    }

                    // Update txCount if still 0
                    if (node.txCount === 0 || node.txCount === undefined) {
                        node.txCount = utxos.length;
                        console.log(`[ForensicDataManager] UTXO Phase: Estimated ${utxos.length} transactions from UTXOs`);
                    }

                    // Estimate totalReceived from UTXOs if still 0
                    if (node.totalReceived === 0 || node.totalReceived === undefined) {
                        node.totalReceived = calculatedBalance;
                    }

                    // ================================================================
                    // CREATE EDGES AND TRANSACTION NODES FROM UTXOs
                    // This allows graph rendering and Louvain algorithm to work
                    // ================================================================
                    let edgesCreated = 0;
                    let txNodesCreated = 0;

                    utxos.forEach((utxo, index) => {
                        const txHash = utxo.tx_hash_big_endian || utxo.tx_hash;

                        if (!txHash) return;

                        // Create transaction node if it doesn't exist
                        if (!this.currentCaseFile.nodes[txHash]) {
                            this.currentCaseFile.nodes[txHash] = {
                                id: txHash,
                                type: 'transaction',
                                hash: txHash,
                                confirmations: utxo.confirmations || 0,
                                value: utxo.value || 0,
                                output_n: utxo.tx_output_n,
                                // Minimal transaction data from UTXO
                                time: null,  // Unknown from UTXO alone
                                blockHash: null,
                                blockHeight: null,
                                fee: 0,
                                riskScore: 0,
                                communityId: null,
                                betweennessCentrality: 0
                            };
                            txNodesCreated++;
                        }

                        // Store in transactions collection as well
                        if (!this.currentCaseFile.transactions[txHash]) {
                            this.currentCaseFile.transactions[txHash] = {
                                hash: txHash,
                                time: null,
                                blockHash: null,
                                blockHeight: null,
                                confirmations: utxo.confirmations || 0,
                                fee: 0,
                                inputs: [],  // Unknown from UTXO
                                outputs: [{
                                    addr: address,
                                    value: utxo.value || 0,
                                    n: utxo.tx_output_n
                                }],
                                minerPool: null,
                                rawData: utxo
                            };
                        }

                        // Create edge: transaction -> address (UTXO flow)
                        const edgeId = `${txHash}->${address}-${utxo.tx_output_n}`;

                        // Check if edge already exists
                        const edgeExists = this.currentCaseFile.edges.some(e => e.id === edgeId);

                        if (!edgeExists) {
                            this.currentCaseFile.edges.push({
                                id: edgeId,
                                source: txHash,
                                target: address,
                                value: utxo.value || 0,
                                label: `${(utxo.value / 100000000).toFixed(8)} BTC`,
                                type: 'utxo',  // Mark as UTXO-derived edge
                                confirmations: utxo.confirmations || 0,
                                output_n: utxo.tx_output_n
                            });
                            edgesCreated++;
                        }
                    });

                    console.log(`[ForensicDataManager] UTXO Phase: Created ${txNodesCreated} transaction nodes and ${edgesCreated} edges from UTXOs`);
                    toast.success(
                        `UTXO graph: ${utxos.length} UTXOs → ${txNodesCreated} tx nodes, ${edgesCreated} edges | ${(calculatedBalance / 100000000).toFixed(4)} BTC`,
                        { id: 'phase-3', duration: 4000 }
                    );
                } else {
                    toast.success('UTXO analysis complete (no unspent outputs)', { id: 'phase-3' });
                }
            }

            this.dataFetchProgress.unspent = true;

        } catch (error) {
            console.error('Failed to fetch UTXOs:', error);
            toast.error('UTXO fetch failed', { id: 'phase-3', duration: 2000 });
            // Don't throw - this is optional
        }
    }

    /**
     * Phase 4: Fetch block data
     * FIXED: Always sets progress to true, handles empty scenarios gracefully
     */
    async fetchBlocksData() {
        try {
            toast.loading('Fetching block data...', { id: 'phase-4' });
            console.log('[ForensicDataManager] Phase 4: Starting block data fetch');

            const uniqueBlocks = new Set();
            Object.values(this.currentCaseFile.transactions).forEach(tx => {
                if (tx.blockHash) uniqueBlocks.add(tx.blockHash);
            });

            console.log(`[ForensicDataManager] Found ${uniqueBlocks.size} unique blocks to fetch`);

            let fetchedCount = 0;
            const blockArray = Array.from(uniqueBlocks).slice(0, 20); // Limit to 20 blocks

            for (const blockHash of blockArray) {
                try {
                    const blockData = await blockchainService.fetchBlock(blockHash);

                    if (blockData.success) {
                        const block = blockData.data;
                        this.currentCaseFile.blocks[blockHash] = {
                            hash: blockHash,
                            height: block.height,
                            time: block.time,
                            miner: block.miner || 'Unknown',
                            pool: this.identifyMiningPool(block),
                            txCount: block.n_tx || 0,
                            rawData: block
                        };

                        // Update transaction with pool info
                        Object.values(this.currentCaseFile.transactions).forEach(tx => {
                            if (tx.blockHash === blockHash) {
                                tx.minerPool = this.currentCaseFile.blocks[blockHash].pool;
                            }
                        });

                        fetchedCount++;
                    }
                } catch (error) {
                    console.warn(`[ForensicDataManager] Failed to fetch block ${blockHash}:`, error.message);
                }
            }

            // CRITICAL FIX: Always set progress to true
            this.dataFetchProgress.blocks = true;
            this.notifyListeners();

            if (fetchedCount > 0) {
                toast.success(`Fetched ${fetchedCount} blocks`, { id: 'phase-4' });
            } else if (blockArray.length === 0) {
                toast.success('Block analysis complete (no blocks required)', { id: 'phase-4' });
            } else {
                toast.success('Block data synced', { id: 'phase-4' });
            }

            console.log(`[ForensicDataManager] Phase 4 complete: ${fetchedCount}/${blockArray.length} blocks fetched`);

        } catch (error) {
            console.error('[ForensicDataManager] Failed to fetch blocks:', error);
            // CRITICAL: Still set progress to true to prevent UI from getting stuck
            this.dataFetchProgress.blocks = true;
            this.notifyListeners();
            toast.error('Block sync failed, continuing...', { id: 'phase-4', duration: 2000 });
        }
    }

    /**
     * Phase 5: Fetch global context (Network Context)
     * FIXED: Always sets progress to true and notifies listeners
     */
    async fetchGlobalContext() {
        try {
            toast.loading('Fetching network context...', { id: 'phase-5' });
            console.log('[ForensicDataManager] Phase 5: Starting network context fetch');

            let successCount = 0;

            // Fetch market price
            try {
                const priceData = await blockchainService.fetchChart('market-price', '7days');
                if (priceData.success && priceData.data?.values) {
                    const values = priceData.data.values;
                    this.currentCaseFile.globalContext.marketPrice = values[values.length - 1]?.y || 0;
                    successCount++;
                    console.log(`[ForensicDataManager] Market price: $${this.currentCaseFile.globalContext.marketPrice}`);
                }
            } catch (e) { console.warn('[ForensicDataManager] Failed to fetch price:', e.message); }

            // Fetch hash rate
            try {
                const hashData = await blockchainService.fetchChart('hash-rate', '7days');
                if (hashData.success && hashData.data?.values) {
                    const values = hashData.data.values;
                    this.currentCaseFile.globalContext.networkHashRate = values[values.length - 1]?.y || 0;
                    successCount++;
                }
            } catch (e) { console.warn('[ForensicDataManager] Failed to fetch hash rate:', e.message); }

            // Fetch difficulty
            try {
                const diffData = await blockchainService.fetchChart('difficulty', '7days');
                if (diffData.success && diffData.data?.values) {
                    const values = diffData.data.values;
                    this.currentCaseFile.globalContext.networkDifficulty = values[values.length - 1]?.y || 0;
                    successCount++;
                }
            } catch (e) { console.warn('[ForensicDataManager] Failed to fetch difficulty:', e.message); }

            // Fetch transaction rate
            try {
                const txRateData = await blockchainService.fetchChart('n-transactions', '30days');
                if (txRateData.success && txRateData.data?.values) {
                    this.currentCaseFile.globalContext.transactionRate = txRateData.data.values;
                    successCount++;
                }
            } catch (e) { console.warn('[ForensicDataManager] Failed to fetch tx rate:', e.message); }

            // Fetch latest block
            try {
                const latestBlock = await blockchainService.fetchLatestBlock();
                if (latestBlock.success) {
                    this.currentCaseFile.globalContext.lastBlockHeight = latestBlock.data?.height || 0;
                    successCount++;
                }
            } catch (e) { console.warn('[ForensicDataManager] Failed to fetch latest block:', e.message); }

            // CRITICAL FIX: Always set progress to true
            this.dataFetchProgress.charts = true;
            this.notifyListeners();

            console.log(`[ForensicDataManager] Phase 5 complete: ${successCount}/5 context items fetched`);
            toast.success(`Network context synced (${successCount}/5 items)`, { id: 'phase-5' });

        } catch (error) {
            console.error('[ForensicDataManager] Failed to fetch global context:', error);
            // CRITICAL: Still set progress to true to prevent UI from getting stuck
            this.dataFetchProgress.charts = true;
            this.notifyListeners();
            toast.error('Network context partial sync', { id: 'phase-5', duration: 2000 });
        }
    }

    /**
     * Phase 6: Run community detection
     */
    async runCommunityDetection() {
        try {
            toast.loading('Running Leiden community detection...', { id: 'leiden' });

            const result = await runLeidenDetection(
                this.currentCaseFile.nodes,
                this.currentCaseFile.edges
            );

            if (result.success) {
                // Update nodes with community IDs
                Object.keys(result.communities).forEach(nodeId => {
                    if (this.currentCaseFile.nodes[nodeId]) {
                        this.currentCaseFile.nodes[nodeId].communityId = result.communities[nodeId];
                    }
                });

                // Store community metadata
                this.currentCaseFile.detectedCommunities = result.communityMetadata || {};

                toast.success(
                    `Detected ${Object.keys(this.currentCaseFile.detectedCommunities).length} communities`,
                    { id: 'leiden' }
                );
            }

        } catch (error) {
            console.error('Community detection failed:', error);
            toast.error('Community detection failed', { id: 'leiden' });
        }
    }

    /**
     * Phase 7: Generate investigative leads
     */
    async generateInvestigativeLeads() {
        try {
            toast.loading('Generating investigative leads...', { id: 'leads' });

            const leads = await generateLeads(this.currentCaseFile);

            this.currentCaseFile.investigativeLeads = leads;
            this.currentCaseFile.suspiciousPatterns = this.extractPatterns(leads);

            const highPriorityCount = leads.filter(l => l.priority === 'high' || l.priority === 'critical').length;

            toast.success(
                `Generated ${leads.length} leads (${highPriorityCount} high priority)`,
                { id: 'leads', duration: 5000 }
            );

        } catch (error) {
            console.error('Lead generation failed:', error);
            toast.error('Lead generation failed', { id: 'leads' });
        }
    }

    /**
     * Extract pattern categories from leads
     */
    extractPatterns(leads) {
        return {
            mixerCandidates: leads.filter(l => l.type === 'mixer_pattern').map(l => l.nodeId),
            bridgeNodes: leads.filter(l => l.type === 'bridge_mule').map(l => l.nodeId),
            timingAnomalies: leads.filter(l => l.type === 'timing_anomaly').map(l => l.nodeId),
            dustingTargets: leads.filter(l => l.type === 'dusting').map(l => l.nodeId),
            whales: leads.filter(l => l.type === 'whale').map(l => l.nodeId)
        };
    }

    /**
     * Identify mining pool from block data
     */
    identifyMiningPool(block) {
        const knownPools = {
            'Foundry USA': /foundry|foundrydigital/i,
            'AntPool': /antpool/i,
            'F2Pool': /f2pool/i,
            'ViaBTC': /viabtc/i,
            'Binance Pool': /binance/i,
            'Poolin': /poolin/i,
            'BTC.com': /btc\.com/i,
            'Slush Pool': /slush|braiins/i
        };

        const coinbaseTx = block.tx?.[0];
        if (!coinbaseTx) return null;

        const scriptSig = coinbaseTx.inputs?.[0]?.script;
        if (!scriptSig) return null;

        for (const [poolName, pattern] of Object.entries(knownPools)) {
            if (pattern.test(scriptSig)) {
                return poolName;
            }
        }

        return 'Unknown';
    }

    /**
     * Reset progress indicators
     */
    resetProgress() {
        Object.keys(this.dataFetchProgress).forEach(key => {
            this.dataFetchProgress[key] = false;
        });
    }

    /**
     * Get case file
     */
    getCaseFile() {
        return this.currentCaseFile;
    }

    /**
     * Get progress
     */
    getProgress() {
        return this.dataFetchProgress;
    }

    /**
     * Export case file
     */
    exportCaseFile() {
        const dataStr = JSON.stringify(this.currentCaseFile, null, 2);
        const dataUri = 'data:application/json;charset=utf-8,' + encodeURIComponent(dataStr);

        const exportFileDefaultName = `case_${this.currentCaseFile.metadata.caseId}.json`;

        const linkElement = document.createElement('a');
        linkElement.setAttribute('href', dataUri);
        linkElement.setAttribute('download', exportFileDefaultName);
        linkElement.click();

        toast.success('Case file exported');
    }

    /**
     * Clear case file
     */
    clearCaseFile() {
        this.currentCaseFile = this.initializeCaseFile();
        this.resetProgress();
        this.notifyListeners();
        toast.success('Case file cleared');
    }
}

// Singleton instance
const forensicDataManager = new ForensicDataManager();

export default forensicDataManager;
