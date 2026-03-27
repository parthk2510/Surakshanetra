// @ts-nocheck
"use client";
import React, { useState, useMemo } from 'react';
import { motion } from 'framer-motion';
import {
    X, Bitcoin, TrendingUp, TrendingDown, Clock, AlertTriangle,
    Layers, Users, Hash, Calendar, DollarSign, Activity, Tag,
    ChevronDown, ChevronRight, ExternalLink, Flag, Shield, Target,
    Zap, GitBranch, AlertCircle, CheckCircle, Network
} from 'lucide-react';
import { formatBTC, formatHash, formatTimeAgo } from '../utils/formatters';
import { getCommunityColor } from '../core/LeidenDetector';

const EnhancedNodeDetails = ({ node, caseFile, onClose, onMarkSuspicious, onRunCommunityDetection }) => {
    const [expandedSections, setExpandedSections] = useState(new Set(['overview', 'forensics', 'threat']));

    const threatLevel = useMemo(() => {
        if (!node) return null;

        const riskScore = node.riskScore || 0;
        const isMalicious = node.isMalicious || node.threatIntel?.isMalicious;
        const betweenness = node.betweennessCentrality || 0;

        if (isMalicious || riskScore > 0.8) return { level: 'critical', color: '#ef4444', label: 'CRITICAL' };
        if (riskScore > 0.6 || betweenness > 0.5) return { level: 'high', color: '#f97316', label: 'HIGH' };
        if (riskScore > 0.4 || betweenness > 0.3) return { level: 'medium', color: '#eab308', label: 'MEDIUM' };
        if (riskScore > 0.2) return { level: 'low', color: '#22c55e', label: 'LOW' };
        return { level: 'safe', color: '#10b981', label: 'SAFE' };
    }, [node]);

    if (!node) return null;

    const toggleSection = (section) => {
        const newExpanded = new Set(expandedSections);
        if (newExpanded.has(section)) {
            newExpanded.delete(section);
        } else {
            newExpanded.add(section);
        }
        setExpandedSections(newExpanded);
    };

    const isAddress = node.type === 'address';
    const communityColor = node.communityId !== null ? getCommunityColor(node.communityId) : null;

    const relatedTransactions = isAddress && caseFile
        ? Object.values(caseFile.transactions || {}).filter((tx: any) =>
            tx.inputs?.some((i: any) => i.prev_out?.addr === node.id) ||
            tx.outputs?.some((o: any) => o.addr === node.id)
        )
        : [];

    const communityInfo = node.communityId !== null && caseFile
        ? caseFile.detectedCommunities?.[node.communityId]
        : null;

    const relatedLeads = caseFile
        ? (caseFile.investigativeLeads || []).filter(lead => lead.nodeId === node.id)
        : [];

    const threatIntelData = node.threatIntel || null;

    return (
        <motion.div
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: 20 }}
            className="bg-gray-800/50 backdrop-blur-sm rounded-lg border border-gray-700/50 overflow-hidden max-h-[calc(100vh-120px)] flex flex-col"
        >
            <div className="bg-gradient-to-r from-blue-900/30 to-purple-900/30 border-b border-blue-500/30 px-4 py-4 flex-shrink-0">
                <div className="flex items-start justify-between">
                    <div className="flex-1 min-w-0">
                        <div className="flex items-center space-x-2 mb-2">
                            {isAddress ? (
                                <Bitcoin className="w-5 h-5 text-blue-400" />
                            ) : (
                                <Activity className="w-5 h-5 text-purple-400" />
                            )}
                            <h3 className="text-sm font-bold text-white uppercase tracking-wide">
                                {isAddress ? 'Address Details' : 'Transaction Details'}
                            </h3>
                            {threatLevel && (
                                <span
                                    className="px-2 py-0.5 rounded text-xs font-bold uppercase"
                                    style={{
                                        backgroundColor: `${threatLevel.color}20`,
                                        color: threatLevel.color,
                                        border: `1px solid ${threatLevel.color}50`
                                    }}
                                >
                                    {threatLevel.label}
                                </span>
                            )}
                        </div>
                        <p className="text-xs font-mono text-gray-400 break-all">
                            {node.id}
                        </p>
                        <div className="flex flex-wrap items-center gap-2 mt-2">
                            {node.isSuspicious && (
                                <span className="px-2 py-0.5 bg-red-500/20 border border-red-500/50 rounded text-xs text-red-400 font-medium">
                                    🚨 Suspicious
                                </span>
                            )}
                            {node.isMalicious && (
                                <span className="px-2 py-0.5 bg-red-600/30 border border-red-600/70 rounded text-xs text-red-300 font-bold animate-pulse">
                                    ☠️ MALICIOUS
                                </span>
                            )}
                            {node.communityId !== null && (
                                <span
                                    className="px-2 py-0.5 rounded text-xs font-medium border"
                                    style={{
                                        backgroundColor: `${communityColor}20`,
                                        borderColor: `${communityColor}50`,
                                        color: communityColor
                                    }}
                                >
                                    Community #{node.communityId}
                                </span>
                            )}
                            {relatedLeads.length > 0 && (
                                <span className="px-2 py-0.5 bg-amber-500/20 border border-amber-500/50 rounded text-xs text-amber-400 font-medium">
                                    ⚠️ {relatedLeads.length} Lead{relatedLeads.length > 1 ? 's' : ''}
                                </span>
                            )}
                        </div>
                    </div>
                    <button
                        onClick={(e) => {
                            e.stopPropagation();
                            onClose();
                        }}
                        className="p-1 hover:bg-gray-700 rounded transition-colors flex-shrink-0"
                    >
                        <X className="w-5 h-5 text-gray-400" />
                    </button>
                </div>
            </div>

            <div className="flex-1 overflow-y-auto p-4 space-y-4">
                {isAddress && (
                    <Section
                        title="Overview"
                        icon={Activity}
                        isExpanded={expandedSections.has('overview')}
                        onToggle={() => toggleSection('overview')}
                    >
                        <div className="grid grid-cols-2 gap-3">
                            <StatCard
                                label="Balance"
                                value={formatBTC(node.balance || 0) + ' BTC'}
                                icon={Bitcoin}
                                color="blue"
                            />
                            <StatCard
                                label="Transactions"
                                value={(node.txCount || 0).toLocaleString()}
                                icon={Activity}
                                color="purple"
                            />
                            <StatCard
                                label="Total Received"
                                value={formatBTC(node.totalReceived || 0) + ' BTC'}
                                icon={TrendingUp}
                                color="green"
                            />
                            <StatCard
                                label="Total Sent"
                                value={formatBTC(node.totalSent || 0) + ' BTC'}
                                icon={TrendingDown}
                                color="red"
                            />
                        </div>

                        {node.firstSeen && (
                            <div className="mt-3 p-3 bg-gray-900/50 rounded border border-gray-700/50">
                                <div className="flex justify-between text-xs">
                                    <span className="text-gray-400">First Seen:</span>
                                    <span className="text-gray-300">
                                        {formatTimeAgo(node.firstSeen)}
                                    </span>
                                </div>
                                {node.lastActive && (
                                    <div className="flex justify-between text-xs mt-1">
                                        <span className="text-gray-400">Last Active:</span>
                                        <span className="text-gray-300">
                                            {formatTimeAgo(node.lastActive)}
                                        </span>
                                    </div>
                                )}
                            </div>
                        )}
                    </Section>
                )}

                {isAddress && (
                    <Section
                        title="Threat Intelligence"
                        icon={Shield}
                        isExpanded={expandedSections.has('threat')}
                        onToggle={() => toggleSection('threat')}
                        highlight={node.isMalicious || threatLevel?.level === 'critical'}
                    >
                        <div className="space-y-3">
                            <div className="p-3 rounded border" style={{
                                backgroundColor: `${threatLevel?.color}10`,
                                borderColor: `${threatLevel?.color}30`
                            }}>
                                <div className="flex items-center justify-between mb-2">
                                    <span className="text-xs text-gray-400">Risk Assessment</span>
                                    <span className="text-sm font-bold" style={{ color: threatLevel?.color }}>
                                        {threatLevel?.label}
                                    </span>
                                </div>
                                <div className="w-full bg-gray-700 rounded-full h-2">
                                    <div
                                        className="h-2 rounded-full transition-all duration-500"
                                        style={{
                                            width: `${(node.riskScore || 0) * 100}%`,
                                            backgroundColor: threatLevel?.color
                                        }}
                                    />
                                </div>
                                <div className="text-xs text-gray-500 mt-1 text-right">
                                    {((node.riskScore || 0) * 100).toFixed(1)}% Risk Score
                                </div>
                            </div>

                            {threatIntelData && (
                                <>
                                    {threatIntelData.sources && threatIntelData.sources.length > 0 && (
                                        <div className="p-2 bg-gray-900/50 rounded">
                                            <span className="text-xs text-gray-400">Intelligence Sources:</span>
                                            <div className="flex flex-wrap gap-1 mt-1">
                                                {threatIntelData.sources.map((src, idx) => (
                                                    <span key={idx} className="px-2 py-0.5 bg-blue-500/20 rounded text-xs text-blue-400">
                                                        {src}
                                                    </span>
                                                ))}
                                            </div>
                                        </div>
                                    )}

                                    {threatIntelData.activityType && (
                                        <div className="p-2 bg-red-900/20 rounded border border-red-500/30">
                                            <span className="text-xs text-gray-400">Activity Type:</span>
                                            <p className="text-sm text-red-400 font-medium mt-1">
                                                {threatIntelData.activityType.replace(/_/g, ' ').toUpperCase()}
                                            </p>
                                        </div>
                                    )}

                                    {threatIntelData.indicators && threatIntelData.indicators.length > 0 && (
                                        <div className="p-2 bg-gray-900/50 rounded">
                                            <span className="text-xs text-gray-400">Risk Indicators:</span>
                                            <ul className="mt-1 space-y-1">
                                                {threatIntelData.indicators.slice(0, 5).map((ind, idx) => (
                                                    <li key={idx} className="flex items-start space-x-2 text-xs">
                                                        <AlertCircle className="w-3 h-3 text-amber-400 mt-0.5 flex-shrink-0" />
                                                        <span className="text-gray-300">{ind}</span>
                                                    </li>
                                                ))}
                                            </ul>
                                        </div>
                                    )}
                                </>
                            )}

                            {!threatIntelData && (
                                <div className="text-center py-4 text-gray-500 text-xs">
                                    No threat intelligence data available.
                                    <br />
                                    Run threat scan to gather intel.
                                </div>
                            )}
                        </div>
                    </Section>
                )}

                {isAddress && (
                    <Section
                        title="Forensic Metrics"
                        icon={Hash}
                        isExpanded={expandedSections.has('forensics')}
                        onToggle={() => toggleSection('forensics')}
                    >
                        <div className="space-y-3">
                            <div className="grid grid-cols-2 gap-2">
                                <div className="p-2 bg-gray-900/50 rounded border border-gray-700/50">
                                    <div className="flex items-center space-x-1 mb-1">
                                        <Target className="w-3 h-3 text-blue-400" />
                                        <span className="text-xs text-gray-400">Risk Score</span>
                                    </div>
                                    <p className="text-lg font-bold text-white">
                                        {((node.riskScore || 0) * 100).toFixed(1)}%
                                    </p>
                                </div>
                                <div className="p-2 bg-gray-900/50 rounded border border-gray-700/50">
                                    <div className="flex items-center space-x-1 mb-1">
                                        <Network className="w-3 h-3 text-purple-400" />
                                        <span className="text-xs text-gray-400">Betweenness</span>
                                    </div>
                                    <p className={`text-lg font-bold ${(node.betweennessCentrality || 0) > 0.3 ? 'text-amber-400' : 'text-white'}`}>
                                        {((node.betweennessCentrality || 0) * 100).toFixed(2)}%
                                    </p>
                                </div>
                            </div>

                            <div className="grid grid-cols-2 gap-2">
                                <div className="p-2 bg-gray-900/50 rounded border border-gray-700/50">
                                    <div className="flex items-center space-x-1 mb-1">
                                        <GitBranch className="w-3 h-3 text-green-400" />
                                        <span className="text-xs text-gray-400">Degree</span>
                                    </div>
                                    <p className="text-sm font-semibold text-white">
                                        {node.degree || node.connectionCount || 0}
                                    </p>
                                </div>
                                <div className="p-2 bg-gray-900/50 rounded border border-gray-700/50">
                                    <div className="flex items-center space-x-1 mb-1">
                                        <Zap className="w-3 h-3 text-yellow-400" />
                                        <span className="text-xs text-gray-400">Closeness</span>
                                    </div>
                                    <p className="text-sm font-semibold text-white">
                                        {((node.closenessCentrality || 0) * 100).toFixed(2)}%
                                    </p>
                                </div>
                            </div>

                            {node.pageRank !== undefined && (
                                <InfoRow
                                    label="PageRank"
                                    value={node.pageRank.toFixed(6)}
                                />
                            )}

                            {node.clusteringCoefficient !== undefined && (
                                <InfoRow
                                    label="Clustering Coefficient"
                                    value={`${(node.clusteringCoefficient * 100).toFixed(2)}%`}
                                />
                            )}

                            {node.tags && node.tags.length > 0 && (
                                <div className="mt-2">
                                    <p className="text-xs text-gray-400 mb-1">Tags:</p>
                                    <div className="flex flex-wrap gap-1">
                                        {node.tags.map((tag, idx) => (
                                            <span
                                                key={idx}
                                                className="px-2 py-0.5 bg-gray-700/50 rounded text-xs text-gray-300"
                                            >
                                                {tag}
                                            </span>
                                        ))}
                                    </div>
                                </div>
                            )}
                        </div>
                    </Section>
                )}

                {communityInfo && (
                    <Section
                        title="Community Analysis"
                        icon={Users}
                        isExpanded={expandedSections.has('community')}
                        onToggle={() => toggleSection('community')}
                    >
                        <div className="space-y-2">
                            <InfoRow label="Community ID" value={`#${node.communityId}`} />
                            <InfoRow label="Community Size" value={`${communityInfo.size} nodes`} />
                            <InfoRow
                                label="Total Value"
                                value={`${formatBTC(communityInfo.totalValue)} BTC`}
                            />
                            <InfoRow
                                label="Density"
                                value={`${(communityInfo.density * 100).toFixed(1)}%`}
                            />
                            <InfoRow
                                label="External Connections"
                                value={communityInfo.externalConnections}
                            />
                            {communityInfo.riskScore && (
                                <InfoRow
                                    label="Community Risk"
                                    value={`${(communityInfo.riskScore * 100).toFixed(1)}%`}
                                    highlight={communityInfo.riskScore > 0.5}
                                />
                            )}
                        </div>
                    </Section>
                )}

                {isAddress && node.utxos && node.utxos.length > 0 && (
                    <Section
                        title={`UTXOs (${node.utxos.length})`}
                        icon={Layers}
                        isExpanded={expandedSections.has('utxos')}
                        onToggle={() => toggleSection('utxos')}
                    >
                        <div className="space-y-2 max-h-60 overflow-y-auto">
                            {node.utxos.slice(0, 20).map((utxo, idx) => (
                                <div
                                    key={idx}
                                    className="p-2 bg-gray-900/50 rounded border border-gray-700/50"
                                >
                                    <div className="flex justify-between text-xs mb-1">
                                        <span className="text-gray-400 font-mono">
                                            {formatHash(utxo.tx_hash_big_endian || utxo.tx_hash, 8, 4)}
                                        </span>
                                        <span className="text-green-400 font-semibold">
                                            {formatBTC(utxo.value)} BTC
                                        </span>
                                    </div>
                                    <div className="text-xs text-gray-500">
                                        {utxo.confirmations || 0} confirmations
                                    </div>
                                </div>
                            ))}
                            {node.utxos.length > 20 && (
                                <p className="text-xs text-gray-500 text-center py-2">
                                    + {node.utxos.length - 20} more UTXOs
                                </p>
                            )}
                        </div>
                    </Section>
                )}

                {relatedLeads.length > 0 && (
                    <Section
                        title={`Investigative Leads (${relatedLeads.length})`}
                        icon={AlertTriangle}
                        isExpanded={expandedSections.has('leads')}
                        onToggle={() => toggleSection('leads')}
                    >
                        <div className="space-y-2">
                            {relatedLeads.map((lead) => (
                                <div
                                    key={lead.id}
                                    className="p-3 bg-red-500/10 border border-red-500/30 rounded"
                                >
                                    <div className="flex items-start justify-between mb-2">
                                        <span className="text-xs font-bold text-red-400 uppercase">
                                            {lead.priority}
                                        </span>
                                        <span className="text-xs text-gray-400">
                                            {lead.type.replace('_', ' ').toUpperCase()}
                                        </span>
                                    </div>
                                    <p className="text-xs text-gray-300 leading-relaxed">
                                        {lead.description}
                                    </p>
                                </div>
                            ))}
                        </div>
                    </Section>
                )}

                {relatedTransactions.length > 0 && (
                    <Section
                        title={`Related Transactions (${relatedTransactions.length})`}
                        icon={Activity}
                        isExpanded={expandedSections.has('transactions')}
                        onToggle={() => toggleSection('transactions')}
                    >
                        <div className="space-y-2 max-h-60 overflow-y-auto">
                            {relatedTransactions.slice(0, 10).map((tx) => (
                                <div
                                    key={tx.hash}
                                    className="p-2 bg-gray-900/50 rounded border border-gray-700/50"
                                >
                                    <div className="flex justify-between text-xs mb-1">
                                        <span className="text-gray-400 font-mono">
                                            {formatHash(tx.hash)}
                                        </span>
                                        <a
                                            href={`https://www.blockchain.com/btc/tx/${tx.hash}`}
                                            target="_blank"
                                            rel="noopener noreferrer"
                                            className="text-blue-400 hover:text-blue-300"
                                            onClick={(e) => e.stopPropagation()}
                                        >
                                            <ExternalLink className="w-3 h-3" />
                                        </a>
                                    </div>
                                    <div className="flex justify-between text-xs">
                                        <span className="text-gray-500">
                                            {formatTimeAgo(tx.time)}
                                        </span>
                                        {tx.minerPool && (
                                            <span className="text-gray-400">
                                                Pool: {tx.minerPool}
                                            </span>
                                        )}
                                    </div>
                                </div>
                            ))}
                            {relatedTransactions.length > 10 && (
                                <p className="text-xs text-gray-500 text-center py-2">
                                    + {relatedTransactions.length - 10} more transactions
                                </p>
                            )}
                        </div>
                    </Section>
                )}

                <Section
                    title="Raw Data (JSON)"
                    icon={Hash}
                    isExpanded={expandedSections.has('raw')}
                    onToggle={() => toggleSection('raw')}
                >
                    <pre className="text-xs font-mono text-gray-400 bg-gray-900/50 p-3 rounded overflow-x-auto max-h-60">
                        {JSON.stringify(node, null, 2)}
                    </pre>
                </Section>
            </div>

            <div className="border-t border-gray-700/50 p-3 flex-shrink-0 bg-gray-900/30">
                <div className="flex items-center space-x-2">
                    {isAddress && !node.isSuspicious && (
                        <button
                            onClick={(e) => {
                                e.stopPropagation();
                                onMarkSuspicious(node.id);
                            }}
                            className="flex-1 flex items-center justify-center space-x-2 px-3 py-2 bg-red-600/20 border border-red-500/50 text-red-400 rounded hover:bg-red-600/30 transition-colors text-xs font-medium"
                        >
                            <Flag className="w-3 h-3" />
                            <span>Mark Suspicious</span>
                        </button>
                    )}
                    {isAddress && onRunCommunityDetection && (
                        <button
                            onClick={(e) => {
                                e.stopPropagation();
                                onRunCommunityDetection(node.id);
                            }}
                            className="flex-1 flex items-center justify-center space-x-2 px-3 py-2 bg-purple-600/20 border border-purple-500/50 text-purple-400 rounded hover:bg-purple-600/30 transition-colors text-xs font-medium"
                        >
                            <Users className="w-3 h-3" />
                            <span>Find Community</span>
                        </button>
                    )}
                    <a
                        href={`https://www.blockchain.com/btc/${isAddress ? 'address' : 'tx'}/${node.id}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex-1 flex items-center justify-center space-x-2 px-3 py-2 bg-blue-600/20 border border-blue-500/50 text-blue-400 rounded hover:bg-blue-600/30 transition-colors text-xs font-medium"
                        onClick={(e) => e.stopPropagation()}
                    >
                        <ExternalLink className="w-3 h-3" />
                        <span>View on Explorer</span>
                    </a>
                </div>
            </div>
        </motion.div>
    );
};

const Section = ({ title, icon: Icon, isExpanded, onToggle, children, highlight = false }) => (
    <div className={`border rounded-lg overflow-hidden ${highlight ? 'border-red-500/50 bg-red-500/5' : 'border-gray-700/50'}`}>
        <button
            onClick={(e) => {
                e.stopPropagation();
                onToggle();
            }}
            className="w-full px-3 py-2 flex items-center justify-between bg-gray-700/30 hover:bg-gray-700/50 transition-colors"
        >
            <div className="flex items-center space-x-2">
                <Icon className={`w-4 h-4 ${highlight ? 'text-red-400' : 'text-blue-400'}`} />
                <span className={`text-sm font-medium ${highlight ? 'text-red-300' : 'text-gray-300'}`}>{title}</span>
            </div>
            {isExpanded ? (
                <ChevronDown className="w-4 h-4 text-gray-400" />
            ) : (
                <ChevronRight className="w-4 h-4 text-gray-400" />
            )}
        </button>
        {isExpanded && (
            <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: 'auto', opacity: 1 }}
                className="p-3"
            >
                {children}
            </motion.div>
        )}
    </div>
);

const StatCard = ({ label, value, icon: Icon, color }) => {
    const colorClasses = {
        blue: 'bg-blue-500/10 border-blue-500/30 text-blue-400',
        purple: 'bg-purple-500/10 border-purple-500/30 text-purple-400',
        green: 'bg-green-500/10 border-green-500/30 text-green-400',
        red: 'bg-red-500/10 border-red-500/30 text-red-400'
    };

    return (
        <div className={`p-3 border rounded ${colorClasses[color] || colorClasses.blue}`}>
            <div className="flex items-center space-x-2 mb-1">
                <Icon className="w-4 h-4" />
                <span className="text-xs text-gray-400">{label}</span>
            </div>
            <p className="text-sm font-semibold text-white">{value}</p>
        </div>
    );
};

const InfoRow = ({ label, value, highlight = false }) => (
    <div className={`flex justify-between text-xs ${highlight ? 'text-red-400' : ''}`}>
        <span className={highlight ? 'text-red-400 font-semibold' : 'text-gray-400'}>{label}:</span>
        <span className={highlight ? 'text-red-400 font-semibold' : 'text-gray-300'}>{value}</span>
    </div>
);

export default EnhancedNodeDetails;
