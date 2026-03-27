"use client";
// src/components/GraphLegend.js
// Mini-legend showing community colors and node type meanings
import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
    Info, ChevronDown, ChevronUp, Circle, AlertTriangle,
    Wallet, GitCommit, Shield, Users
} from 'lucide-react';
import { getCommunityColor } from '../core/LeidenDetector';

const GraphLegend = ({
    communities = {},
    showAnomalies = true,
    maliciousCount = 0,
    onToggle
}) => {
    const [isExpanded, setIsExpanded] = useState(true);

    const nodeTypes = [
        {
            label: 'Address',
            color: '#10b981',
            icon: Wallet,
            description: 'Bitcoin wallet address'
        },
        {
            label: 'Transaction',
            color: '#3b82f6',
            icon: GitCommit,
            description: 'Bitcoin transaction'
        },
        {
            label: 'Malicious',
            color: '#ef4444',
            icon: Shield,
            description: 'Flagged by threat intel',
            pulse: true
        },
        {
            label: 'Anomalous',
            color: '#f59e0b',
            icon: AlertTriangle,
            description: 'Unusual behavior detected',
            pulse: true
        }
    ];

    const communityColors = Object.keys(communities).slice(0, 8).map((cid, idx) => ({
        id: cid,
        color: getCommunityColor(parseInt(cid)),
        size: communities[cid]?.members?.length || communities[cid]?.size || 0,
        label: `Community ${parseInt(cid) + 1}`
    }));

    const edgeTypes = [
        { label: 'Incoming', color: '#10b981', description: 'Receiving funds' },
        { label: 'Outgoing', color: '#ef4444', description: 'Sending funds' },
        { label: 'Internal', color: '#64748b', description: 'Within network' }
    ];

    return (
        <motion.div
            className="absolute bottom-4 left-4 z-20 bg-gray-900/90 backdrop-blur-sm rounded-lg border border-gray-700/50 shadow-xl max-w-xs overflow-hidden"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
        >
            {/* Header */}
            <button
                onClick={() => setIsExpanded(!isExpanded)}
                className="w-full flex items-center justify-between px-3 py-2 bg-gray-800/50 hover:bg-gray-700/50 transition-colors"
            >
                <div className="flex items-center space-x-2">
                    <Info className="w-4 h-4 text-blue-400" />
                    <span className="text-xs font-semibold text-white uppercase tracking-wide">Legend</span>
                </div>
                {isExpanded ? (
                    <ChevronDown className="w-4 h-4 text-gray-400" />
                ) : (
                    <ChevronUp className="w-4 h-4 text-gray-400" />
                )}
            </button>

            <AnimatePresence>
                {isExpanded && (
                    <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: 'auto', opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        className="px-3 py-2 space-y-3"
                    >
                        {/* Node Types */}
                        <div>
                            <p className="text-xs text-gray-400 font-medium mb-1.5">Node Types</p>
                            <div className="space-y-1">
                                {nodeTypes.map((type) => (
                                    <div key={type.label} className="flex items-center space-x-2 group">
                                        <div
                                            className={`w-3 h-3 rounded-full ${type.pulse ? 'animate-pulse' : ''}`}
                                            style={{ backgroundColor: type.color }}
                                        />
                                        <span className="text-xs text-gray-300">{type.label}</span>
                                        <span className="text-xs text-gray-500 hidden group-hover:inline">
                                            — {type.description}
                                        </span>
                                    </div>
                                ))}
                            </div>
                        </div>

                        {/* Edge Types */}
                        <div>
                            <p className="text-xs text-gray-400 font-medium mb-1.5">Edge Types</p>
                            <div className="space-y-1">
                                {edgeTypes.map((type) => (
                                    <div key={type.label} className="flex items-center space-x-2">
                                        <div className="w-4 h-0.5" style={{ backgroundColor: type.color }} />
                                        <span className="text-xs text-gray-300">{type.label}</span>
                                    </div>
                                ))}
                            </div>
                        </div>

                        {/* Communities */}
                        {communityColors.length > 0 && (
                            <div>
                                <p className="text-xs text-gray-400 font-medium mb-1.5 flex items-center">
                                    <Users className="w-3 h-3 mr-1" />
                                    Communities ({Object.keys(communities).length})
                                </p>
                                <div className="flex flex-wrap gap-1">
                                    {communityColors.map((comm) => (
                                        <div
                                            key={comm.id}
                                            className="flex items-center space-x-1 px-1.5 py-0.5 bg-gray-800/50 rounded"
                                            title={`${comm.label}: ${comm.size} nodes`}
                                        >
                                            <div
                                                className="w-2 h-2 rounded-full"
                                                style={{ backgroundColor: comm.color }}
                                            />
                                            <span className="text-xs text-gray-400">{comm.size}</span>
                                        </div>
                                    ))}
                                    {Object.keys(communities).length > 8 && (
                                        <span className="text-xs text-gray-500 px-1">
                                            +{Object.keys(communities).length - 8} more
                                        </span>
                                    )}
                                </div>
                            </div>
                        )}

                        {/* Node Sizing */}
                        <div>
                            <p className="text-xs text-gray-400 font-medium mb-1.5">Node Size = Transaction Volume</p>
                            <div className="flex items-center space-x-2">
                                <div className="w-2 h-2 rounded-full bg-gray-400" />
                                <div className="flex-1 h-0.5 bg-gradient-to-r from-gray-600 to-gray-400 rounded" />
                                <div className="w-4 h-4 rounded-full bg-gray-400" />
                            </div>
                            <div className="flex justify-between mt-0.5">
                                <span className="text-xs text-gray-500">Low</span>
                                <span className="text-xs text-gray-500">High</span>
                            </div>
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>
        </motion.div>
    );
};

export default GraphLegend;
