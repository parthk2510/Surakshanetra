"use client";
import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
    X, Bitcoin, TrendingUp, TrendingDown, Clock, AlertTriangle,
    Layers, Droplets, Wallet, Activity, CheckCircle, XCircle,
    ChevronRight, ExternalLink
} from 'lucide-react';
import blockchainService from '../utils/blockchainAPI';
import { Z } from '../styles/z-layers';
import {
    formatBTC, formatBTCWithUSD, formatNumber, formatHash,
    formatTimeAgo, getRiskColor, getRiskBgColor, getRiskLabel
} from '../utils/formatters';
import toast from 'react-hot-toast';

const isUpiId = (value) => {
    if (!value) return false;
    const s = String(value).trim();
    if (!s) return false;
    const regex = /^[a-zA-Z0-9.\-_]{2,256}@[a-zA-Z]{2,64}$/;
    return regex.test(s);
};

const ForensicInspector = ({ node, isOpen, onClose, btcPrice }) => {
    const [comprehensiveData, setComprehensiveData] = useState(null);
    const [riskMetrics, setRiskMetrics] = useState(null);
    const [loading, setLoading] = useState(false);
    const [activeTab, setActiveTab] = useState('overview');

    useEffect(() => {
        if (isOpen && node && node.type === 'address' && !node.upiId && !isUpiId(node.id)) {
            fetchForensicData();
        }
    }, [isOpen, node]);

    const fetchForensicData = async () => {
        if (!node || node.type !== 'address') return;

        setLoading(true);
        try {
            // Fetch comprehensive data and risk metrics in parallel
            const [comprehensive, metrics] = await Promise.all([
                blockchainService.fetchAddressComprehensive(node.id),
                blockchainService.fetchRiskMetrics(node.id)
            ]);

            setComprehensiveData(comprehensive.data);
            setRiskMetrics(metrics.data);
        } catch (error) {
            console.error('Failed to fetch forensic data:', error);
            toast.error('Failed to load forensic data for this address');
        } finally {
            setLoading(false);
        }
    };

    if (!node) return null;

    const isUpi = !!node.upiId || isUpiId(node.id);

    const basicInfo = comprehensiveData?.basic_info || {};
    const utxos = comprehensiveData?.unspent_outputs || [];
    const transactions = comprehensiveData?.transactions || [];

    const tabs = isUpi ? ['overview', 'risk', 'counterparties'] : ['overview', 'utxo', 'forensics'];

    return (
        <AnimatePresence>
            {isOpen && (
                <>
                    {/* Backdrop */}
                    <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        onClick={onClose}
                        className="fixed inset-0 bg-black/50 backdrop-blur-sm"
                        style={{ zIndex: Z.MODAL_BACKDROP }}
                    />

                    {/* Side Panel */}
                    <motion.div
                        initial={{ x: '100%' }}
                        animate={{ x: 0 }}
                        exit={{ x: '100%' }}
                        transition={{ type: 'spring', damping: 30, stiffness: 300 }}
                        className="fixed right-0 top-0 bottom-0 w-full md:w-2/3 lg:w-1/2 xl:w-2/5 bg-gray-900 border-l border-gray-700 shadow-2xl overflow-hidden flex flex-col"
                        style={{ zIndex: Z.MODAL }}
                    >
                        {/* Header */}
                        <div className="flex items-center justify-between p-6 border-b border-gray-700 bg-gray-800/50">
                            <div className="flex items-center space-x-3">
                                <div className={`p-2 rounded-lg ${isUpi ? 'bg-blue-500/20' : node.category === 'suspect' ? 'bg-red-500/20' :
                                    node.category === 'high_probability_link' ? 'bg-orange-500/20' :
                                        'bg-blue-500/20'
                                    }`}>
                                    <Wallet className={`w-6 h-6 ${isUpi ? 'text-blue-400' : node.category === 'suspect' ? 'text-red-400' :
                                        node.category === 'high_probability_link' ? 'text-orange-400' :
                                            'text-blue-400'
                                        }`} />
                                </div>
                                <div>
                                    <h2 className="text-xl font-bold text-white">{isUpi ? 'UPI Account Inspector' : 'UTXO & Flow Inspector'}</h2>
                                    <p className="text-sm text-gray-400">{isUpi ? 'Payment network forensic analysis' : 'Forensic Analysis'}</p>
                                </div>
                            </div>
                            <button
                                onClick={onClose}
                                className="p-2 hover:bg-gray-700 rounded-lg transition-colors"
                            >
                                <X className="w-6 h-6 text-gray-400" />
                            </button>
                        </div>

                        {/* Tabs */}
                        <div className="flex border-b border-gray-700 bg-gray-800/30">
                            {tabs.map(tab => (
                                <button
                                    key={tab}
                                    onClick={() => setActiveTab(tab)}
                                    className={`flex-1 py-3 px-4 text-sm font-medium transition-colors ${activeTab === tab
                                        ? 'text-blue-400 border-b-2 border-blue-400 bg-gray-800/50'
                                        : 'text-gray-400 hover:text-gray-300'
                                        }`}
                                >
                                    {tab.charAt(0).toUpperCase() + tab.slice(1)}
                                </button>
                            ))}
                        </div>

                        {/* Content */}
                        <div className="flex-1 overflow-y-auto p-6 space-y-6">
                            {loading ? (
                                <div className="flex items-center justify-center h-64">
                                    <div className="flex flex-col items-center space-y-4">
                                        <div className="w-12 h-12 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" />
                                        <p className="text-gray-400">Loading forensic data...</p>
                                    </div>
                                </div>
                            ) : (
                                <>
                                    {/* Address Info Card */}
                                    <div className="bg-gray-800/50 rounded-lg border border-gray-700 p-4">
                                        <div className="flex items-start justify-between mb-3">
                                            <div>
                                                <p className="text-xs text-gray-400 mb-1">
                                                    {isUpi ? 'UPI ID' : 'Bitcoin Address'}
                                                </p>
                                                <p className="text-sm font-mono text-white break-all">
                                                    {isUpi ? (node.upiId || node.id) : node.id}
                                                </p>
                                                {isUpi && node.bank && (
                                                    <p className="text-xs text-gray-400 mt-1">
                                                        Bank: <span className="text-gray-200">{node.bank}</span>
                                                    </p>
                                                )}
                                            </div>
                                            {!isUpi && (
                                                <a
                                                    href={`https://www.blockchain.com/btc/address/${node.id}`}
                                                    target="_blank"
                                                    rel="noopener noreferrer"
                                                    className="p-2 hover:bg-gray-700 rounded-lg transition-colors"
                                                >
                                                    <ExternalLink className="w-4 h-4 text-gray-400" />
                                                </a>
                                            )}
                                        </div>

                                        {!isUpi && node.category && (
                                            <div className={`inline-flex items-center space-x-2 px-3 py-1 rounded-full text-xs font-medium ${node.category === 'suspect' ? 'bg-red-500/20 text-red-400 border border-red-500/50' :
                                                node.category === 'high_probability_link' ? 'bg-orange-500/20 text-orange-400 border border-orange-500/50' :
                                                    'bg-gray-700 text-gray-300'
                                                }`}>
                                                {node.category === 'suspect' && <AlertTriangle className="w-3 h-3" />}
                                                {node.category === 'high_probability_link' && <Activity className="w-3 h-3" />}
                                                <span>
                                                    {node.category === 'suspect' ? 'Suspect Address' :
                                                        node.category === 'high_probability_link' ? `High Probability Link (${node.suspectConnections || 0} connections)` :
                                                            'Connected Address'}
                                                </span>
                                            </div>
                                        )}
                                        {isUpi && (
                                            <div className="flex flex-wrap gap-2 mt-2">
                                                <div className={`inline-flex items-center space-x-2 px-3 py-1 rounded-full text-xs font-medium ${getRiskBgColor(node.riskScore || 0)}`}>
                                                    <Activity className="w-3 h-3 text-white" />
                                                    <span className="text-white">Risk {getRiskLabel(node.riskScore || 0)} ({node.riskScore || 0})</span>
                                                </div>
                                                <div className={`inline-flex items-center space-x-2 px-3 py-1 rounded-full text-xs font-medium ${getRiskBgColor(node.clusterRiskScore || 0)}`}>
                                                    <Layers className="w-3 h-3 text-white" />
                                                    <span className="text-white">Cluster {getRiskLabel(node.clusterRiskScore || 0)} ({node.clusterRiskScore || 0})</span>
                                                </div>
                                            </div>
                                        )}
                                    </div>

                                    {/* Tab Content */}
                                    {activeTab === 'overview' && (
                                        isUpi ? (
                                            <UpiOverviewTab node={node} />
                                        ) : (
                                            <OverviewTab
                                                node={node}
                                                basicInfo={basicInfo}
                                                transactions={transactions}
                                                btcPrice={btcPrice}
                                            />
                                        )
                                    )}

                                    {!isUpi && activeTab === 'utxo' && (
                                        <UTXOTab
                                            utxos={utxos}
                                            riskMetrics={riskMetrics}
                                            btcPrice={btcPrice}
                                        />
                                    )}

                                    {!isUpi && activeTab === 'forensics' && (
                                        <ForensicsTab
                                            node={node}
                                            riskMetrics={riskMetrics}
                                            basicInfo={basicInfo}
                                            transactions={transactions}
                                        />
                                    )}

                                    {isUpi && activeTab === 'risk' && (
                                        <UpiRiskTab node={node} />
                                    )}

                                    {isUpi && activeTab === 'counterparties' && (
                                        <UpiCounterpartiesTab node={node} />
                                    )}
                                </>
                            )}
                        </div>
                    </motion.div>
                </>
            )}
        </AnimatePresence>
    );
};

const OverviewTab = ({ node, basicInfo, transactions, btcPrice }) => {
    const utxos = node.utxos || [];

    let balance = basicInfo.final_balance || node.balance || 0;
    let totalReceived = basicInfo.total_received || node.totalReceived || 0;
    const totalSent = basicInfo.total_sent || node.totalSent || 0;
    let txCount = basicInfo.n_tx || node.txCount || 0;
    const utxoCount = basicInfo.n_unredeemed || utxos.length || 0;

    // Calculate from UTXOs if balance is still 0
    if (balance === 0 && utxos.length > 0) {
        balance = utxos.reduce((sum, utxo) => sum + (utxo.value || 0), 0);
    }

    // Estimate txCount from UTXOs if still 0
    if (txCount === 0 && utxos.length > 0) {
        txCount = utxos.length;
    }

    // Estimate totalReceived if still 0
    if (totalReceived === 0 && balance > 0) {
        totalReceived = balance;
    }

    return (
        <div className="space-y-4">
            {/* Balance Card */}
            <div className="bg-gradient-to-br from-blue-600/20 to-purple-600/20 rounded-lg border border-blue-500/30 p-4">
                <div className="flex items-center space-x-2 mb-3">
                    <Bitcoin className="w-5 h-5 text-blue-400" />
                    <h3 className="text-sm font-semibold text-white">Current Balance</h3>
                    {utxos.length > 0 && balance === utxos.reduce((s, u) => s + (u.value || 0), 0) && (
                        <span className="text-xs bg-green-500/20 text-green-400 px-2 py-0.5 rounded-full">
                            Calculated from {utxos.length} UTXOs
                        </span>
                    )}
                </div>
                <p className="text-3xl font-bold text-white mb-1">
                    {formatBTC(balance)} BTC
                </p>
                {btcPrice && (
                    <p className="text-sm text-gray-300">
                        ≈ ${(balance / 100000000 * btcPrice).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} USD
                    </p>
                )}
            </div>

            {/* Stats Grid */}
            <div className="grid grid-cols-2 gap-4">
                <StatCard
                    icon={TrendingUp}
                    label="Total Received"
                    value={formatBTC(totalReceived) + ' BTC'}
                    color="green"
                />
                <StatCard
                    icon={TrendingDown}
                    label="Total Sent"
                    value={formatBTC(totalSent) + ' BTC'}
                    color="red"
                />
                <StatCard
                    icon={Activity}
                    label="Transactions"
                    value={formatNumber(txCount)}
                    color="blue"
                />
                <StatCard
                    icon={Layers}
                    label="Unspent Outputs"
                    value={formatNumber(utxoCount)}
                    color="purple"
                />
            </div>

            {/* Recent Transactions */}
            {transactions.length > 0 && (
                <div className="bg-gray-800/50 rounded-lg border border-gray-700 p-4">
                    <h3 className="text-sm font-semibold text-white mb-3">Recent Transactions</h3>
                    <div className="space-y-2">
                        {transactions.slice(0, 5).map((tx, idx) => (
                            <div key={idx} className="flex items-center justify-between py-2 border-b border-gray-700/50 last:border-0">
                                <div className="flex-1 min-w-0">
                                    <p className="text-xs font-mono text-gray-400 truncate">
                                        {formatHash(tx.hash)}
                                    </p>
                                    <p className="text-xs text-gray-500">
                                        {formatTimeAgo(tx.time)}
                                    </p>
                                </div>
                                <div className="text-right ml-4">
                                    <p className="text-xs text-gray-300">
                                        {formatBTC(tx.result || 0)} BTC
                                    </p>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {/* UTXO Summary if no transactions but UTXOs exist */}
            {transactions.length === 0 && utxos.length > 0 && (
                <div className="bg-gray-800/50 rounded-lg border border-gray-700 p-4">
                    <h3 className="text-sm font-semibold text-white mb-3">
                        UTXO Summary ({utxos.length} unspent outputs)
                    </h3>
                    <div className="space-y-2 max-h-48 overflow-y-auto">
                        {utxos.slice(0, 5).map((utxo, idx) => (
                            <div key={idx} className="flex items-center justify-between py-2 px-3 bg-gray-900/50 rounded border border-gray-700/50">
                                <div className="flex-1 min-w-0">
                                    <p className="text-xs font-mono text-gray-400 truncate">
                                        {formatHash(utxo.tx_hash_big_endian || utxo.tx_hash)}
                                    </p>
                                    <p className="text-xs text-gray-500">
                                        {utxo.confirmations || 0} confirmations
                                    </p>
                                </div>
                                <div className="text-right ml-4">
                                    <p className="text-xs font-semibold text-green-400">
                                        {formatBTC(utxo.value)} BTC
                                    </p>
                                </div>
                            </div>
                        ))}
                        {utxos.length > 5 && (
                            <p className="text-xs text-gray-500 text-center py-2">
                                + {utxos.length - 5} more UTXOs
                            </p>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
};

const UpiOverviewTab = ({ node }) => {
    const totalIn = node.totalInAmount || 0;
    const totalOut = node.totalOutAmount || 0;
    const net = totalIn - totalOut;
    const riskScore = typeof node.riskScore === 'number' ? node.riskScore : 0;
    
    // Improved Cluster Exposure calculation
    let clusterRiskScore = typeof node.clusterRiskScore === 'number' ? node.clusterRiskScore : 0;
    
    // If clusterRiskScore is 0, try to calculate it from available data
    if (clusterRiskScore === 0) {
        // Try multiple data sources for component size
        const componentSize = node.componentSize || node.communitySize || node.cluster_size || 0;
        
        // Try multiple data sources for transaction counts
        const inTxCount = node.inTxCount || node.in_tx_count || node.inbound_tx || 0;
        const outTxCount = node.outTxCount || node.out_tx_count || node.outbound_tx || 0;
        const totalTxCount = inTxCount + outTxCount;
        
        // Try multiple data sources for counterparties
        const inCounterparties = node.inUniqueCounterparties || node.in_unique_counterparties || 0;
        const outCounterparties = node.outUniqueCounterparties || node.out_unique_counterparties || 0;
        const totalCounterparties = inCounterparties + outCounterparties;
        
        // Calculate cluster risk score if we have meaningful data
        if (componentSize > 1 || totalTxCount > 0 || totalCounterparties > 0) {
            // Base score from component size (more accounts = higher risk)
            const sizeScore = Math.min(40, componentSize * 1.5);
            
            // Add risk from transaction volume (more transactions = higher risk)
            const transactionScore = Math.min(35, totalTxCount * 0.3);
            
            // Add risk from unique counterparties (more counterparties = higher risk)
            const counterpartiesScore = Math.min(25, totalCounterparties * 0.5);
            
            // Add bonus risk for high transaction velocity
            const velocityScore = Math.min(15, (totalTxCount / Math.max(componentSize, 1)) * 2);
            
            clusterRiskScore = Math.min(100, Math.round(sizeScore + transactionScore + counterpartiesScore + velocityScore));
            
            console.log(`[CLUSTER_EXPOSURE] Calculated score: ${clusterRiskScore} (size: ${sizeScore}, tx: ${transactionScore}, cp: ${counterpartiesScore}, vel: ${velocityScore})`);
        } else {
            // If no meaningful data, set a minimal score based on account risk
            clusterRiskScore = Math.min(15, Math.round(riskScore * 0.3));
            console.log(`[CLUSTER_EXPOSURE] Using fallback score: ${clusterRiskScore} based on account risk: ${riskScore}`);
        }
    }
    
    const inCount = node.inTxCount || 0;
    const outCount = node.outTxCount || 0;
    return (
        <div className="space-y-4">
            <div className={`rounded-lg border p-4 ${getRiskBgColor(riskScore)}`}>
                <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center space-x-2">
                        <Activity className="w-5 h-5 text-white" />
                        <h3 className="text-sm font-semibold text-white">Account Risk</h3>
                    </div>
                    <span className={`text-2xl font-bold ${getRiskColor(riskScore)}`}>
                        {riskScore}
                    </span>
                </div>
                <p className="text-xs text-gray-300">
                    {getRiskLabel(riskScore)} risk based on UPI transaction patterns and mule detection rules.
                </p>
            </div>
            <div className="grid grid-cols-2 gap-4">
                <StatCard
                    icon={TrendingUp}
                    label="Total Inflow (₹)"
                    value={formatNumber(totalIn)}
                    color="green"
                />
                <StatCard
                    icon={TrendingDown}
                    label="Total Outflow (₹)"
                    value={formatNumber(totalOut)}
                    color="red"
                />
                <StatCard
                    icon={Activity}
                    label="Inbound Transactions"
                    value={formatNumber(inCount)}
                    color="blue"
                />
                <StatCard
                    icon={Activity}
                    label="Outbound Transactions"
                    value={formatNumber(outCount)}
                    color="purple"
                />
            </div>
            <div className="bg-gray-800/50 rounded-lg border border-gray-700 p-4">
                <h3 className="text-sm font-semibold text-white mb-2">Net Position (₹)</h3>
                <p className={`text-2xl font-bold ${net >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                    {formatNumber(net)}
                </p>
                <p className="text-xs text-gray-400 mt-1">
                    {net >= 0 
                        ? 'Net inflow - potential mule account receiving funds' 
                        : 'Net outflow - possible layering or cash-out activity'
                    }
                </p>
            </div>
            <div className="bg-gray-800/50 rounded-lg border border-gray-700 p-4">
                <h3 className="text-sm font-semibold text-white mb-2">Cluster Exposure</h3>
                <div className="flex items-center justify-between">
                    <div>
                        <p className="text-xs text-gray-400 mb-1">Cluster Risk Score</p>
                        <p className="text-2xl font-bold text-white">
                            {clusterRiskScore}
                        </p>
                        {clusterRiskScore > 0 && (
                            <p className="text-xs text-gray-500 mt-1">
                                Calculated from {node.componentSize || 1} accounts
                            </p>
                        )}
                    </div>
                    <div className="flex-1 ml-4">
                        <div className="w-full bg-gray-700 rounded-full h-2">
                            <div
                                className="bg-purple-500 h-2 rounded-full transition-all duration-300"
                                style={{ width: `${Math.min(clusterRiskScore, 100)}%` }}
                            />
                        </div>
                        <p className="text-xs text-gray-400 mt-1">
                            {clusterRiskScore === 0 
                                ? 'Insufficient data for cluster analysis'
                                : `Aggregated risk across ${node.componentSize || 1} connected accounts`
                            }
                        </p>
                    </div>
                </div>
            </div>
        </div>
    );
};

const UTXOTab = ({ utxos, riskMetrics, btcPrice }) => (
    <div className="space-y-4">
        {/* Liquidity Card */}
        <div className="bg-gradient-to-br from-green-600/20 to-emerald-600/20 rounded-lg border border-green-500/30 p-4">
            <div className="flex items-center space-x-2 mb-3">
                <Droplets className="w-5 h-5 text-green-400" />
                <h3 className="text-sm font-semibold text-white">Available Liquidity</h3>
            </div>
            <p className="text-3xl font-bold text-white mb-1">
                {formatBTC(riskMetrics?.liquidity_satoshis || 0)} BTC
            </p>
            {btcPrice && riskMetrics && (
                <p className="text-sm text-gray-300">
                    ≈ ${(riskMetrics.liquidity_btc * btcPrice).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} USD
                </p>
            )}
            <p className="text-xs text-gray-400 mt-2">
                Total value of unspent outputs available for immediate movement
            </p>
        </div>

        {/* Fragmentation Score */}
        {riskMetrics && (
            <div className={`rounded-lg border p-4 ${getRiskBgColor(riskMetrics.fragmentation_score)}`}>
                <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center space-x-2">
                        <Layers className="w-5 h-5 text-white" />
                        <h3 className="text-sm font-semibold text-white">Fragmentation Score</h3>
                    </div>
                    <span className={`text-2xl font-bold ${getRiskColor(riskMetrics.fragmentation_score)}`}>
                        {riskMetrics.fragmentation_score}
                    </span>
                </div>
                <p className="text-sm text-white mb-2">{riskMetrics.fragmentation_label}</p>
                <div className="w-full bg-gray-700 rounded-full h-2">
                    <div
                        className={`h-2 rounded-full transition-all ${riskMetrics.fragmentation_score >= 80 ? 'bg-red-500' :
                            riskMetrics.fragmentation_score >= 60 ? 'bg-orange-500' :
                                riskMetrics.fragmentation_score >= 40 ? 'bg-yellow-500' :
                                    'bg-green-500'
                            }`}
                        style={{ width: `${riskMetrics.fragmentation_score}%` }}
                    />
                </div>

                {riskMetrics.dust_activity && (
                    <div className="mt-3 p-2 bg-yellow-900/30 border border-yellow-500/30 rounded">
                        <p className="text-xs text-yellow-300">
                            <AlertTriangle className="w-3 h-3 inline mr-1" />
                            High dust activity detected ({riskMetrics.dust_percentage}% dust UTXOs)
                        </p>
                    </div>
                )}
            </div>
        )}

        {/* UTXO Stats */}
        <div className="grid grid-cols-2 gap-4">
            <StatCard
                icon={Layers}
                label="Total UTXOs"
                value={formatNumber(utxos.length)}
                color="blue"
            />
            <StatCard
                icon={Droplets}
                label="Dust Count"
                value={formatNumber(riskMetrics?.dust_count || 0)}
                color="yellow"
            />
        </div>

        {/* UTXO List */}
        {utxos.length > 0 && (
            <div className="bg-gray-800/50 rounded-lg border border-gray-700 p-4">
                <h3 className="text-sm font-semibold text-white mb-3">
                    Unspent Outputs ({utxos.length})
                </h3>
                <div className="space-y-2 max-h-96 overflow-y-auto">
                    {utxos.slice(0, 50).map((utxo, idx) => (
                        <div key={idx} className="flex items-center justify-between py-2 px-3 bg-gray-900/50 rounded border border-gray-700/50">
                            <div className="flex-1 min-w-0">
                                <p className="text-xs font-mono text-gray-400 truncate">
                                    {formatHash(utxo.tx_hash_big_endian || utxo.tx_hash)}
                                </p>
                                <p className="text-xs text-gray-500">
                                    {utxo.confirmations || 0} confirmations
                                </p>
                            </div>
                            <div className="text-right ml-4">
                                <p className="text-xs font-semibold text-green-400">
                                    {formatBTC(utxo.value)} BTC
                                </p>
                                {utxo.value < 1000 && (
                                    <span className="text-xs text-yellow-500">Dust</span>
                                )}
                            </div>
                        </div>
                    ))}
                    {utxos.length > 50 && (
                        <p className="text-xs text-gray-500 text-center py-2">
                            + {utxos.length - 50} more UTXOs
                        </p>
                    )}
                </div>
            </div>
        )}
    </div>
);

const ForensicsTab = ({ node, riskMetrics, basicInfo, transactions }) => (
    <div className="space-y-4">
        {/* Holding Time */}
        {riskMetrics && (
            <div className="bg-gray-800/50 rounded-lg border border-gray-700 p-4">
                <div className="flex items-center space-x-2 mb-3">
                    <Clock className="w-5 h-5 text-purple-400" />
                    <h3 className="text-sm font-semibold text-white">Holding Time Analysis</h3>
                </div>
                <div className="grid grid-cols-2 gap-4">
                    <div>
                        <p className="text-xs text-gray-400 mb-1">Oldest UTXO Age</p>
                        <p className="text-2xl font-bold text-white">
                            {riskMetrics.holding_time_days.toFixed(0)} days
                        </p>
                    </div>
                    <div>
                        <p className="text-xs text-gray-400 mb-1">Average UTXO Age</p>
                        <p className="text-2xl font-bold text-white">
                            {riskMetrics.avg_holding_time_days.toFixed(0)} days
                        </p>
                    </div>
                </div>
                <p className="text-xs text-gray-500 mt-3">
                    Longer holding times may indicate dormant funds or long-term holding strategies
                </p>
            </div>
        )}

        {/* Address Classification */}
        <div className="bg-gray-800/50 rounded-lg border border-gray-700 p-4">
            <h3 className="text-sm font-semibold text-white mb-3">Address Classification</h3>
            <div className="space-y-2">
                <ClassificationItem
                    label="Suspect Status"
                    value={node.category === 'suspect' ? 'Confirmed Suspect' : 'Not a Suspect'}
                    status={node.category === 'suspect'}
                />
                <ClassificationItem
                    label="High Probability Link"
                    value={node.category === 'high_probability_link' ? `Yes (${node.suspectConnections} connections)` : 'No'}
                    status={node.category === 'high_probability_link'}
                />
                <ClassificationItem
                    label="Dust Activity"
                    value={riskMetrics?.dust_activity ? 'Detected' : 'None'}
                    status={riskMetrics?.dust_activity}
                />
            </div>
        </div>

        {/* Transaction Patterns */}
        <div className="bg-gray-800/50 rounded-lg border border-gray-700 p-4">
            <h3 className="text-sm font-semibold text-white mb-3">Transaction Patterns</h3>
            <div className="space-y-3">
                <div>
                    <p className="text-xs text-gray-400 mb-1">Activity Level</p>
                    <div className="flex items-center space-x-2">
                        <div className="flex-1 bg-gray-700 rounded-full h-2">
                            <div
                                className="bg-blue-500 h-2 rounded-full"
                                style={{ width: `${Math.min((basicInfo.n_tx || 0) / 100 * 100, 100)}%` }}
                            />
                        </div>
                        <span className="text-xs text-gray-400">{basicInfo.n_tx || 0} txs</span>
                    </div>
                </div>

                <div>
                    <p className="text-xs text-gray-400 mb-1">Transaction Volume</p>
                    <p className="text-lg font-semibold text-white">
                        {formatBTC((basicInfo.total_received || 0) + (basicInfo.total_sent || 0))} BTC
                    </p>
                    <p className="text-xs text-gray-500">Total volume (received + sent)</p>
                </div>
            </div>
        </div>

        {/* Forensic Insights */}
        <div className="bg-gradient-to-br from-purple-600/10 to-pink-600/10 rounded-lg border border-purple-500/30 p-4">
            <h3 className="text-sm font-semibold text-white mb-3">Forensic Insights</h3>
            <div className="space-y-2 text-sm text-gray-300">
                {generateForensicInsights(node, riskMetrics, basicInfo).map((insight, idx) => (
                    <div key={idx} className="flex items-start space-x-2">
                        <ChevronRight className="w-4 h-4 text-purple-400 mt-0.5 flex-shrink-0" />
                        <p>{insight}</p>
                    </div>
                ))}
            </div>
        </div>
    </div>
);

const StatCard = ({ icon: Icon, label, value, color }) => (
    <div className="bg-gray-800/50 rounded-lg border border-gray-700 p-4">
        <div className="flex items-center space-x-2 mb-2">
            <Icon className={`w-4 h-4 text-${color}-400`} />
            <p className="text-xs text-gray-400">{label}</p>
        </div>
        <p className="text-lg font-semibold text-white">{value}</p>
    </div>
);

const ClassificationItem = ({ label, value, status }) => (
    <div className="flex items-center justify-between py-2 px-3 bg-gray-900/50 rounded">
        <span className="text-sm text-gray-300">{label}</span>
        <div className="flex items-center space-x-2">
            <span className={`text-sm font-medium ${status ? 'text-red-400' : 'text-green-400'}`}>
                {value}
            </span>
            {status ? (
                <XCircle className="w-4 h-4 text-red-400" />
            ) : (
                <CheckCircle className="w-4 h-4 text-green-400" />
            )}
        </div>
    </div>
);

const generateForensicInsights = (node, riskMetrics, basicInfo) => {
    const insights = [];

    if (node.category === 'suspect') {
        insights.push('This address has been marked as a suspect for investigation.');
    }

    if (node.category === 'high_probability_link') {
        insights.push(`This address has transacted with ${node.suspectConnections} suspect addresses, indicating a high probability of connection.`);
    }

    if (riskMetrics?.fragmentation_score >= 80) {
        insights.push('Extreme fragmentation detected. This pattern is typical of mining pool payouts or potential dusting attacks.');
    }

    if (riskMetrics?.dust_activity) {
        insights.push(`${riskMetrics.dust_percentage}% of UTXOs are dust. High dust activity may indicate tracking attempts or spam.`);
    }

    if (riskMetrics?.holding_time_days > 365) {
        insights.push(`Funds have been dormant for over ${Math.floor(riskMetrics.holding_time_days / 365)} year(s). This may indicate long-term holding or abandoned wallet.`);
    }

    if (basicInfo.n_tx && basicInfo.n_tx > 1000) {
        insights.push('High transaction count suggests this may be an exchange, service, or very active trader.');
    }

    const balance = basicInfo.final_balance || node.balance || 0;
    const btc = balance / 100000000;
    if (btc > 100) {
        insights.push(`This is a whale address holding ${btc.toFixed(2)} BTC. Movements should be closely monitored.`);
    }

    if (insights.length === 0) {
        insights.push('No significant forensic indicators detected. Continue monitoring for unusual patterns.');
    }

    return insights;
};

const UpiRiskTab = ({ node }) => {
    const ruleContributions = node.ruleContributions || {};
    const reasonCodes = node.reasonCodes || [];
    const inTxCount = Number(node.inTxCount || 0);
    const outTxCount = Number(node.outTxCount || 0);
    const inUniqueCounterparties = Number(node.inUniqueCounterparties || 0);
    const outUniqueCounterparties = Number(node.outUniqueCounterparties || 0);
    const cycleSize = Number(node.componentSize || 0);
    const matchedFlowCount = Math.min(inTxCount, outTxCount);
    const rules = [
        {
            key: 'fanIn',
            reasonCode: 'FAN_IN',
            label: 'Fan-In Detection',
            count: inUniqueCounterparties,
            countLabel: 'inbound counterparties',
            signal: `Inbound tx: ${formatNumber(inTxCount)}`
        },
        {
            key: 'fanOut',
            reasonCode: 'FAN_OUT',
            label: 'Fan-Out Detection',
            count: outUniqueCounterparties,
            countLabel: 'outbound counterparties',
            signal: `Outbound tx: ${formatNumber(outTxCount)}`
        },
        {
            key: 'circular',
            reasonCode: 'CIRCULAR_FLOW',
            label: 'Circular Movement',
            count: cycleSize,
            countLabel: 'component size',
            signal: 'Cycle-linked movement detected in this component'
        },
        {
            key: 'rapidInOut',
            reasonCode: 'RAPID_IN_OUT',
            label: 'Rapid In-Out Velocity',
            count: matchedFlowCount,
            countLabel: 'in/out overlap tx',
            signal: 'Fast value turnover between inbound and outbound flows'
        },
        {
            key: 'structuring',
            reasonCode: 'AMOUNT_STRUCTURING',
            label: 'Amount Structuring',
            count: outTxCount,
            countLabel: 'outbound tx analyzed',
            signal: 'Repeated near-threshold transaction amounts observed'
        },
        {
            key: 'dormantSpike',
            reasonCode: 'DORMANT_SPIKE',
            label: 'Dormant-to-Active Spike',
            count: inTxCount + outTxCount,
            countLabel: 'total tx reviewed',
            signal: 'Dormancy followed by burst activity'
        },
        {
            key: 'passthrough',
            reasonCode: 'PASSTHROUGH',
            label: 'Passthrough Funds',
            count: matchedFlowCount,
            countLabel: 'matched in/out tx',
            signal: 'Funds move through quickly with low retention'
        }
    ];
    return (
        <div className="space-y-4">
            <div className="bg-gray-800/50 rounded-lg border border-gray-700 p-4">
                <h3 className="text-sm font-semibold text-white mb-2">Triggered Rules</h3>
                {reasonCodes.length === 0 ? (
                    <p className="text-xs text-gray-400">No mule detection rules have fired for this account.</p>
                ) : (
                    <ul className="list-disc list-inside text-xs text-gray-300 space-y-1">
                        {reasonCodes.map((code, idx) => (
                            <li key={idx}>{code}</li>
                        ))}
                    </ul>
                )}
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {rules.map(rule => {
                    const contribution = Number(ruleContributions[rule.key] || 0);
                    const score = Math.max(0, Math.min(100, Math.round(contribution)));
                    const triggered = reasonCodes.includes(rule.reasonCode) || contribution > 0;
                    
                    // Traffic light color scheme for risk values
                    const getTrafficLightColor = (value) => {
                        if (value === 0) return 'text-green-400'; // Green for zero/low risk
                        if (value > 0 && value <= 29) return 'text-yellow-400'; // Yellow for medium risk
                        return 'text-red-400'; // Red for high risk (30+)
                    };
                    
                    return (
                        <div
                            key={rule.key}
                            className={`rounded-lg border p-4 ${getRiskBgColor(score)}`}
                        >
                            <div className="flex items-center justify-between mb-2">
                                <h4 className="text-sm font-semibold text-white">{rule.label}</h4>
                                <span className={`text-lg font-bold ${getTrafficLightColor(score)}`}>
                                    {formatNumber(Math.max(0, rule.count || 0))}
                                </span>
                            </div>
                            <div className="flex items-center space-x-2 mb-2">
                                {triggered ? (
                                    <>
                                        <AlertTriangle className="w-4 h-4 text-red-400" />
                                        <span className="text-xs text-red-300">{rule.signal}</span>
                                    </>
                                ) : (
                                    <>
                                        <CheckCircle className="w-4 h-4 text-green-400" />
                                        <span className="text-xs text-green-300">No strong signal ({rule.countLabel}: {formatNumber(Math.max(0, rule.count || 0))})</span>
                                    </>
                                )}
                            </div>
                            <p className="text-xs text-gray-200">
                                Count: {formatNumber(Math.max(0, rule.count || 0))} {rule.countLabel}
                            </p>
                        </div>
                    );
                })}
            </div>
        </div>
    );
};

const UpiCounterpartiesTab = ({ node }) => {
    const counterparties = Array.isArray(node.counterparties) ? node.counterparties : [];
    const sorted = [...counterparties].sort(
        (a, b) =>
            (b.inAmount || 0) + (b.outAmount || 0) - ((a.inAmount || 0) + (a.outAmount || 0))
    ).slice(0, 30);
    if (sorted.length === 0) {
        return (
            <div className="bg-gray-800/50 rounded-lg border border-gray-700 p-4">
                <p className="text-sm text-gray-300">No counterparty summary available for this account.</p>
            </div>
        );
    }
    return (
        <div className="space-y-4">
            <div className="bg-gray-800/50 rounded-lg border border-gray-700 p-4">
                <h3 className="text-sm font-semibold text-white mb-3">Top Counterparties</h3>
                <div className="max-h-96 overflow-y-auto">
                    <table className="w-full text-xs text-left">
                        <thead>
                            <tr className="text-gray-400 border-b border-gray-700">
                                <th className="py-2 pr-2">UPI ID</th>
                                <th className="py-2 pr-2 text-right">In</th>
                                <th className="py-2 pr-2 text-right">Out</th>
                                <th className="py-2 pr-2 text-right">In Amt</th>
                                <th className="py-2 pr-2 text-right">Out Amt</th>
                            </tr>
                        </thead>
                        <tbody>
                            {sorted.map(cp => (
                                <tr key={cp.counterparty} className="border-b border-gray-800">
                                    <td className="py-2 pr-2">
                                        <span className="font-mono text-gray-200 break-all">
                                            {cp.counterparty}
                                        </span>
                                    </td>
                                    <td className="py-2 pr-2 text-right text-gray-200">
                                        {formatNumber(cp.inCount || 0)}
                                    </td>
                                    <td className="py-2 pr-2 text-right text-gray-200">
                                        {formatNumber(cp.outCount || 0)}
                                    </td>
                                    <td className="py-2 pr-2 text-right text-green-400">
                                        {formatNumber(cp.inAmount || 0)}
                                    </td>
                                    <td className="py-2 pr-2 text-right text-red-400">
                                        {formatNumber(cp.outAmount || 0)}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    );
};

export default ForensicInspector;
