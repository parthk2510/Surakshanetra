'use client';
import { useState, useCallback, useMemo } from 'react';
import blockchainService from '../utils/blockchainAPI';
import { formatBTC } from '../utils/formatters';
import toast from 'react-hot-toast';

/**
 * Custom hook for transforming blockchain data into forensic graph visualization
 */
const useForensicGraph = () => {
    const [graphData, setGraphData] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const [suspectAddresses, setSuspectAddresses] = useState([]);
    const [btcPrice, setBtcPrice] = useState(null);

    /**
     * Fetch BTC price for USD conversion
     */
    const fetchBTCPrice = useCallback(async () => {
        try {
            const chartData = await blockchainService.fetchChart('market-price', '1days');
            if (chartData.success && chartData.data?.values?.length > 0) {
                const latestPrice = chartData.data.values[chartData.data.values.length - 1].y;
                setBtcPrice(latestPrice);
                return latestPrice;
            }
        } catch (err) {
            console.warn('Failed to fetch BTC price:', err);
        }
        return null;
    }, []);

    /**
     * Build forensic graph from cluster data (multi-address analysis)
     */
    const buildClusterGraph = useCallback((clusterData, suspectAddressList) => {
        if (!clusterData || !clusterData.data) {
            return { nodes: [], edges: [], meta: {} };
        }

        const data = clusterData.data;
        const addresses = data.addresses || [];
        const transactions = data.txs || [];

        const nodes = new Map();
        const edges = [];
        const suspectSet = new Set(suspectAddressList.map(a => a.toLowerCase()));
        const connectionCount = new Map(); // Track connections to suspects

        // Add suspect addresses as red nodes
        suspectAddressList.forEach(address => {
            const addressData = addresses.find(a => a.address === address);
            const balance = addressData?.final_balance || 0;

            nodes.set(address, {
                id: address,
                label: address.substring(0, 12) + '...',
                type: 'address',
                category: 'suspect',
                color: '#ef4444', // Red
                size: calculateNodeSize(balance),
                balance: balance,
                balanceBTC: formatBTC(balance),
                n_tx: addressData?.n_tx || 0,
                total_received: addressData?.total_received || 0,
                total_sent: addressData?.total_sent || 0
            });
        });

        // Process transactions to find connections
        transactions.forEach(tx => {
            const txId = tx.hash;

            // Add transaction node
            if (!nodes.has(txId)) {
                nodes.set(txId, {
                    id: txId,
                    label: txId.substring(0, 12) + '...',
                    type: 'transaction',
                    category: 'transaction',
                    color: '#6366f1', // Indigo
                    size: 5,
                    time: tx.time,
                    fee: tx.fee
                });
            }

            // Process inputs
            (tx.inputs || []).forEach(input => {
                const addr = input.prev_out?.addr;
                if (!addr) return;

                const addrLower = addr.toLowerCase();
                const isSuspect = suspectSet.has(addrLower);

                // Track connections to suspects
                if (isSuspect) {
                    connectionCount.set(addrLower, (connectionCount.get(addrLower) || 0) + 1);
                }

                // Add address node if not exists
                if (!nodes.has(addr)) {
                    const addressData = addresses.find(a => a.address === addr);
                    const balance = addressData?.final_balance || 0;

                    nodes.set(addr, {
                        id: addr,
                        label: addr.substring(0, 12) + '...',
                        type: 'address',
                        category: isSuspect ? 'suspect' : 'unknown',
                        color: isSuspect ? '#ef4444' : '#9ca3af', // Red or gray
                        size: calculateNodeSize(balance),
                        balance: balance,
                        balanceBTC: formatBTC(balance),
                        n_tx: addressData?.n_tx || 0,
                        total_received: addressData?.total_received || 0,
                        total_sent: addressData?.total_sent || 0,
                        suspectConnections: 0
                    });
                }

                // Add edge from address to transaction
                edges.push({
                    id: `${addr}->${txId}`,
                    source: addr,
                    target: txId,
                    type: 'SENT_FROM',
                    value: input.prev_out?.value || 0,
                    color: '#64748b',
                    size: 1
                });
            });

            // Process outputs
            (tx.out || []).forEach(output => {
                const addr = output.addr;
                if (!addr) return;

                const addrLower = addr.toLowerCase();
                const isSuspect = suspectSet.has(addrLower);

                // Add address node if not exists
                if (!nodes.has(addr)) {
                    const addressData = addresses.find(a => a.address === addr);
                    const balance = addressData?.final_balance || 0;

                    nodes.set(addr, {
                        id: addr,
                        label: addr.substring(0, 12) + '...',
                        type: 'address',
                        category: isSuspect ? 'suspect' : 'unknown',
                        color: isSuspect ? '#ef4444' : '#9ca3af', // Red or gray
                        size: calculateNodeSize(balance),
                        balance: balance,
                        balanceBTC: formatBTC(balance),
                        n_tx: addressData?.n_tx || 0,
                        total_received: addressData?.total_received || 0,
                        total_sent: addressData?.total_sent || 0,
                        suspectConnections: 0
                    });
                }

                // Add edge from transaction to address
                edges.push({
                    id: `${txId}->${addr}`,
                    source: txId,
                    target: addr,
                    type: 'SENT_TO',
                    value: output.value || 0,
                    color: '#64748b',
                    size: 1
                });
            });
        });

        // Count suspect connections for each address
        const addressConnections = new Map();

        edges.forEach(edge => {
            const source = nodes.get(edge.source);
            const target = nodes.get(edge.target);

            if (source?.category === 'suspect') {
                if (target?.type === 'address' && target.category !== 'suspect') {
                    addressConnections.set(edge.target,
                        (addressConnections.get(edge.target) || 0) + 1);
                }
            }

            if (target?.category === 'suspect') {
                if (source?.type === 'address' && source.category !== 'suspect') {
                    addressConnections.set(edge.source,
                        (addressConnections.get(edge.source) || 0) + 1);
                }
            }
        });

        // Highlight addresses with 2+ connections to suspects (High Probability Links)
        addressConnections.forEach((count, address) => {
            const node = nodes.get(address);
            if (node && node.category !== 'suspect') {
                node.suspectConnections = count;
                if (count >= 2) {
                    node.category = 'high_probability_link';
                    node.color = '#f97316'; // Orange
                    node.size = Math.max(node.size, 15); // Make it more visible
                }
            }
        });

        const nodesArray = Array.from(nodes.values());

        return {
            nodes: nodesArray,
            edges: edges,
            meta: {
                total_nodes: nodesArray.length,
                total_edges: edges.length,
                suspect_count: suspectAddressList.length,
                high_probability_links: nodesArray.filter(n => n.category === 'high_probability_link').length,
                transaction_count: transactions.length
            }
        };
    }, []);

    /**
     * Build standard graph from single address data
     */
    const buildStandardGraph = useCallback((addressData) => {
        if (!addressData || !addressData.data) {
            return { nodes: [], edges: [], meta: {} };
        }

        const data = addressData.data;
        const address = data.address || '';
        const transactions = data.txs || [];

        const nodes = new Map();
        const edges = [];

        // Add main address node
        nodes.set(address, {
            id: address,
            label: address.substring(0, 12) + '...',
            type: 'address',
            category: 'main',
            color: '#3b82f6', // Blue
            size: 20,
            balance: data.final_balance || 0,
            balanceBTC: formatBTC(data.final_balance || 0),
            n_tx: data.n_tx || 0,
            total_received: data.total_received || 0,
            total_sent: data.total_sent || 0
        });

        // Process transactions
        transactions.forEach(tx => {
            const txId = tx.hash;

            // Add transaction node
            nodes.set(txId, {
                id: txId,
                label: txId.substring(0, 12) + '...',
                type: 'transaction',
                category: 'transaction',
                color: '#6366f1',
                size: 5,
                time: tx.time,
                fee: tx.fee
            });

            // Process inputs
            (tx.inputs || []).forEach(input => {
                const addr = input.prev_out?.addr;
                if (!addr) return;

                if (!nodes.has(addr)) {
                    nodes.set(addr, {
                        id: addr,
                        label: addr.substring(0, 12) + '...',
                        type: 'address',
                        category: 'connected',
                        color: '#9ca3af',
                        size: 10,
                        balance: 0
                    });
                }

                edges.push({
                    id: `${addr}->${txId}`,
                    source: addr,
                    target: txId,
                    type: 'SENT_FROM',
                    value: input.prev_out?.value || 0,
                    color: '#64748b',
                    size: 1
                });
            });

            // Process outputs
            (tx.out || []).forEach(output => {
                const addr = output.addr;
                if (!addr) return;

                if (!nodes.has(addr)) {
                    nodes.set(addr, {
                        id: addr,
                        label: addr.substring(0, 12) + '...',
                        type: 'address',
                        category: 'connected',
                        color: '#9ca3af',
                        size: 10,
                        balance: 0
                    });
                }

                edges.push({
                    id: `${txId}->${addr}`,
                    source: txId,
                    target: addr,
                    type: 'SENT_TO',
                    value: output.value || 0,
                    color: '#64748b',
                    size: 1
                });
            });
        });

        const nodesArray = Array.from(nodes.values());

        return {
            nodes: nodesArray,
            edges: edges,
            meta: {
                address: address,
                total_nodes: nodesArray.length,
                total_edges: edges.length,
                transaction_count: transactions.length
            }
        };
    }, []);

    /**
     * Fetch and build graph for single address
     */
    const fetchAddressGraph = useCallback(async (address, txLimit = 50) => {
        setLoading(true);
        setError(null);
        setSuspectAddresses([]);

        try {
            // Fetch BTC price first
            await fetchBTCPrice();

            // Fetch pre-built graph data from backend
            const response = await blockchainService.fetchAddressGraph(address, txLimit);

            const graph = response.graph || response.data || response;
            setGraphData(graph);

            toast.success(`Graph built with ${graph.nodes.length} nodes`, {
                duration: 3001
            });

            return graph;
        } catch (err) {
            setError(err.message || 'Failed to fetch address graph');
            setGraphData(null);
            throw err;
        } finally {
            setLoading(false);
        }
    }, [fetchBTCPrice]);

    /**
     * Fetch and build cluster graph for multiple addresses (SUSPECT ANALYSIS)
     */
    const fetchClusterGraph = useCallback(async (addresses, txLimit = 50) => {
        setLoading(true);
        setError(null);
        setSuspectAddresses(addresses);

        try {
            // Fetch BTC price first
            await fetchBTCPrice();

            // Fetch cluster data
            const clusterData = await blockchainService.fetchClusterData(addresses, txLimit);

            // Build graph
            const graph = buildClusterGraph(clusterData, addresses);
            setGraphData(graph);

            toast.success(
                `Cluster graph built: ${graph.meta.high_probability_links} high-probability links found`,
                { duration: 4000 }
            );

            return graph;
        } catch (err) {
            setError(err.message || 'Failed to fetch cluster graph');
            setGraphData(null);
            throw err;
        } finally {
            setLoading(false);
        }
    }, [buildClusterGraph, fetchBTCPrice]);

    /**
     * Clear graph data
     */
    const clearGraph = useCallback(() => {
        setGraphData(null);
        setError(null);
        setSuspectAddresses([]);
    }, []);

    /**
     * Get node statistics
     */
    const nodeStats = useMemo(() => {
        if (!graphData) return null;

        const stats = {
            total: graphData.nodes.length,
            addresses: graphData.nodes.filter(n => n.type === 'address').length,
            transactions: graphData.nodes.filter(n => n.type === 'transaction').length,
            suspects: graphData.nodes.filter(n => n.category === 'suspect').length,
            highProbabilityLinks: graphData.nodes.filter(n => n.category === 'high_probability_link').length,
            totalEdges: graphData.edges.length
        };

        return stats;
    }, [graphData]);

    return {
        graphData,
        loading,
        error,
        suspectAddresses,
        btcPrice,
        nodeStats,
        fetchAddressGraph,
        fetchClusterGraph,
        clearGraph
    };
};

/**
 * Calculate node size based on balance (whale watching)
 */
function calculateNodeSize(balance) {
    if (!balance || balance === 0) return 8;

    const btc = balance / 100000000;

    // Scale: 0-1 BTC = 8-12, 1-10 BTC = 12-18, 10-100 BTC = 18-25, 100+ BTC = 25-40
    if (btc < 1) return 8 + (btc * 4);
    if (btc < 10) return 12 + ((btc - 1) * 0.67);
    if (btc < 100) return 18 + ((btc - 10) * 0.08);
    if (btc < 1000) return 25 + (Math.min(btc - 100, 900) * 0.017);
    return 40; // Max size for whales
}

export default useForensicGraph;
