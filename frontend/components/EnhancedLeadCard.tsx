"use client";
// src/components/EnhancedLeadCard.js
// Lead card with expandable details, risk indicators, and quick actions
import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
    ChevronDown, ChevronRight, AlertTriangle, AlertCircle, CheckCircle,
    Flag, Archive, Ban, ExternalLink, Clock, Hash, TrendingUp,
    Eye, Copy, Target, Users, Activity
} from 'lucide-react';
import { formatHash, formatTimeAgo, formatBTC } from '../utils/formatters';
import toast from 'react-hot-toast';

const EnhancedLeadCard = ({
    lead,
    onView,
    onFlag,
    onArchive,
    onBlock,
    onNodeSelect,
    isExpanded = false,
    onToggleExpand
}) => {
    const [showDetails, setShowDetails] = useState(isExpanded);

    const getPriorityConfig = (priority) => {
        switch (priority) {
            case 'critical':
                return {
                    bg: 'bg-red-500/20',
                    border: 'border-red-500/50',
                    text: 'text-red-400',
                    icon: AlertTriangle,
                    indicator: 'bg-red-500',
                    label: 'CRITICAL'
                };
            case 'high':
                return {
                    bg: 'bg-orange-500/20',
                    border: 'border-orange-500/50',
                    text: 'text-orange-400',
                    icon: AlertCircle,
                    indicator: 'bg-orange-500',
                    label: 'HIGH'
                };
            case 'medium':
                return {
                    bg: 'bg-yellow-500/20',
                    border: 'border-yellow-500/50',
                    text: 'text-yellow-400',
                    icon: AlertCircle,
                    indicator: 'bg-yellow-500',
                    label: 'MEDIUM'
                };
            default:
                return {
                    bg: 'bg-green-500/20',
                    border: 'border-green-500/50',
                    text: 'text-green-400',
                    icon: CheckCircle,
                    indicator: 'bg-green-500',
                    label: 'LOW'
                };
        }
    };

    const priorityConfig = getPriorityConfig(lead.priority);

    const handleCopyAddress = () => {
        if (lead.nodeId) {
            navigator.clipboard.writeText(lead.nodeId);
            toast.success('Address copied to clipboard');
        }
    };

    return (
        <motion.div
            layout
            className={`rounded-lg border overflow-hidden transition-all duration-200 ${priorityConfig.bg} ${priorityConfig.border} shadow-lg hover:shadow-xl`}
        >
            {/* Traffic Light Indicator */}
            <div className="flex items-stretch">
                <div
                    className={`w-1.5 ${priorityConfig.indicator} ${lead.priority === 'critical' ? 'animate-pulse' : ''}`}
                />

                <div className="flex-1 p-3">
                    {/* Header */}
                    <div
                        className="flex items-start justify-between cursor-pointer"
                        onClick={() => setShowDetails(!showDetails)}
                    >
                        <div className="flex items-start space-x-2 flex-1 min-w-0">
                            {showDetails ? (
                                <ChevronDown className="w-4 h-4 text-gray-400 mt-0.5 flex-shrink-0" />
                            ) : (
                                <ChevronRight className="w-4 h-4 text-gray-400 mt-0.5 flex-shrink-0" />
                            )}
                            <div className="flex-1 min-w-0">
                                <div className="flex items-center space-x-2 mb-1">
                                    <span className={`px-2 py-0.5 rounded text-xs font-bold ${priorityConfig.bg} ${priorityConfig.text} border ${priorityConfig.border}`}>
                                        {priorityConfig.label}
                                    </span>
                                    <span className="px-2 py-0.5 bg-gray-700/50 rounded text-xs text-gray-400 uppercase">
                                        {lead.type?.replace(/_/g, ' ')}
                                    </span>
                                </div>
                                <p className="text-sm text-white font-medium line-clamp-2">
                                    {lead.description}
                                </p>
                                {lead.nodeId && (
                                    <p className="text-xs font-mono text-gray-400 mt-1 truncate">
                                        {formatHash(lead.nodeId, 16, 12)}
                                    </p>
                                )}
                            </div>
                        </div>
                        {lead.type === 'high_volume' ? (
                            <TrendingUp className={`w-5 h-5 ${priorityConfig.text} flex-shrink-0 ml-2`} />
                        ) : lead.type === 'structuring' ? (
                            <Activity className={`w-5 h-5 ${priorityConfig.text} flex-shrink-0 ml-2`} />
                        ) : lead.type === 'suspicious_pattern' ? (
                            <AlertTriangle className={`w-5 h-5 ${priorityConfig.text} flex-shrink-0 ml-2`} />
                        ) : lead.type === 'mixer_connection' ? (
                            <Users className={`w-5 h-5 ${priorityConfig.text} flex-shrink-0 ml-2`} />
                        ) : (
                            <Target className={`w-5 h-5 ${priorityConfig.text} flex-shrink-0 ml-2`} />
                        )}
                    </div>

                    {/* Expanded Details */}
                    <AnimatePresence>
                        {showDetails && (
                            <motion.div
                                initial={{ height: 0, opacity: 0 }}
                                animate={{ height: 'auto', opacity: 1 }}
                                exit={{ height: 0, opacity: 0 }}
                                transition={{ duration: 0.2 }}
                                className="mt-3 pt-3 border-t border-gray-700/50"
                            >
                                {/* Metrics Grid */}
                                {lead.metrics && (
                                    <div className="grid grid-cols-2 gap-2 mb-3">
                                        {lead.metrics.totalValue && (
                                            <div className="bg-gray-800/50 rounded p-2">
                                                <p className="text-xs text-gray-400">Total Value</p>
                                                <p className="text-sm text-emerald-400 font-semibold">
                                                    {formatBTC(lead.metrics.totalValue)} BTC
                                                </p>
                                            </div>
                                        )}
                                        {lead.metrics.txCount && (
                                            <div className="bg-gray-800/50 rounded p-2">
                                                <p className="text-xs text-gray-400">Transactions</p>
                                                <p className="text-sm text-blue-400 font-semibold">
                                                    {lead.metrics.txCount}
                                                </p>
                                            </div>
                                        )}
                                        {lead.metrics.riskScore && (
                                            <div className="bg-gray-800/50 rounded p-2">
                                                <p className="text-xs text-gray-400">Risk Score</p>
                                                <p className={`text-sm font-semibold ${lead.metrics.riskScore > 0.7 ? 'text-red-400' :
                                                        lead.metrics.riskScore > 0.4 ? 'text-yellow-400' : 'text-green-400'
                                                    }`}>
                                                    {(lead.metrics.riskScore * 100).toFixed(0)}%
                                                </p>
                                            </div>
                                        )}
                                        {lead.metrics.connectedAddresses && (
                                            <div className="bg-gray-800/50 rounded p-2">
                                                <p className="text-xs text-gray-400">Connected</p>
                                                <p className="text-sm text-purple-400 font-semibold">
                                                    {lead.metrics.connectedAddresses} addresses
                                                </p>
                                            </div>
                                        )}
                                    </div>
                                )}

                                {/* Evidence/Indicators */}
                                {lead.evidence && lead.evidence.length > 0 && (
                                    <div className="mb-3">
                                        <p className="text-xs text-gray-400 mb-1">Evidence</p>
                                        <ul className="space-y-1">
                                            {lead.evidence.slice(0, 3).map((item, idx) => (
                                                <li key={idx} className="flex items-start space-x-2 text-xs">
                                                    <span className="text-gray-500">•</span>
                                                    <span className="text-gray-300">{item}</span>
                                                </li>
                                            ))}
                                        </ul>
                                    </div>
                                )}

                                {/* Timestamp */}
                                {lead.timestamp && (
                                    <div className="flex items-center space-x-1 text-xs text-gray-500 mb-3">
                                        <Clock className="w-3 h-3" />
                                        <span>{formatTimeAgo(lead.timestamp)}</span>
                                    </div>
                                )}

                                {/* Quick Action Buttons */}
                                <div className="flex items-center space-x-2">
                                    <button
                                        onClick={() => onNodeSelect?.(lead.nodeId)}
                                        className="flex-1 flex items-center justify-center space-x-1 px-3 py-1.5 bg-blue-600/20 border border-blue-500/50 text-blue-400 rounded hover:bg-blue-600/30 transition-colors text-xs"
                                    >
                                        <Eye className="w-3 h-3" />
                                        <span>View</span>
                                    </button>
                                    <button
                                        onClick={() => onFlag?.(lead)}
                                        className="flex items-center justify-center space-x-1 px-3 py-1.5 bg-orange-600/20 border border-orange-500/50 text-orange-400 rounded hover:bg-orange-600/30 transition-colors text-xs"
                                    >
                                        <Flag className="w-3 h-3" />
                                        <span>Flag</span>
                                    </button>
                                    <button
                                        onClick={() => onArchive?.(lead)}
                                        className="flex items-center justify-center space-x-1 px-3 py-1.5 bg-gray-600/20 border border-gray-500/50 text-gray-400 rounded hover:bg-gray-600/30 transition-colors text-xs"
                                    >
                                        <Archive className="w-3 h-3" />
                                        <span>Archive</span>
                                    </button>
                                    <button
                                        onClick={handleCopyAddress}
                                        className="p-1.5 bg-gray-600/20 border border-gray-500/50 text-gray-400 rounded hover:bg-gray-600/30 transition-colors"
                                        title="Copy address"
                                    >
                                        <Copy className="w-3 h-3" />
                                    </button>
                                </div>
                            </motion.div>
                        )}
                    </AnimatePresence>
                </div>
            </div>
        </motion.div>
    );
};

export default EnhancedLeadCard;
