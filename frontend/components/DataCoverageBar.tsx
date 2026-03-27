// frontend/src/components/DataCoverageBar.js
// Clean data coverage visualization with connected node design
import React from 'react';
import { motion } from 'framer-motion';
import { Check, AlertCircle, Loader2 } from 'lucide-react';

const DataCoverageBar = ({ progress, isInvestigating }) => {
    if (!progress) return null;

    const dataPoints = [
        { key: 'address', label: 'Address Data', sublabel: 'Basic Info', icon: '📍', color: 'emerald' },
        { key: 'multiAddress', label: 'Network Neighbors', sublabel: 'Connected Wallets', icon: '🔗', color: 'blue' },
        { key: 'unspent', label: 'UTXOs', sublabel: 'Unspent Outputs', icon: '💎', color: 'purple' },
        { key: 'transactions', label: 'Transactions', sublabel: 'TX History', icon: '📝', color: 'orange' },
        { key: 'blocks', label: 'Blocks', sublabel: 'Block Data', icon: '⛓️', color: 'gray' },
        { key: 'charts', label: 'Network Context', sublabel: 'Market Data', icon: '📊', color: 'cyan' }
    ];

    const completedCount = Object.values(progress).filter(Boolean).length;
    const totalCount = dataPoints.length;
    const progressPercentage = (completedCount / totalCount) * 100;

    const getStatusColor = (isComplete, colorName) => {
        if (isComplete) {
            return {
                ring: 'ring-emerald-500',
                bg: 'bg-emerald-500/20',
                border: 'border-emerald-500',
                icon: 'text-emerald-400'
            };
        }
        return {
            ring: 'ring-gray-600',
            bg: 'bg-gray-800/50',
            border: 'border-gray-600',
            icon: 'text-gray-500'
        };
    };

    return (
        <div className="bg-gray-800/30 backdrop-blur-sm rounded-xl border border-gray-700/30 p-6">
            <div className="flex items-center justify-between mb-5">
                <h3 className="text-sm font-semibold text-white">Data Coverage</h3>
                <span className="text-xs text-gray-400 bg-gray-700/50 px-2 py-1 rounded">
                    {completedCount}/{totalCount} endpoints synced
                </span>
            </div>

            {/* Visual Pipeline - Connected Nodes Design */}
            <div className="relative flex items-center justify-between mb-6">
                {/* Connection Line Background */}
                <div className="absolute top-1/2 left-0 right-0 h-0.5 bg-gray-700 transform -translate-y-1/2 z-0" />

                {/* Animated Progress Line */}
                <motion.div
                    initial={{ width: 0 }}
                    animate={{ width: `${progressPercentage}%` }}
                    transition={{ duration: 0.8, ease: 'easeOut' }}
                    className="absolute top-1/2 left-0 h-0.5 bg-gradient-to-r from-emerald-500 via-blue-500 to-emerald-500 transform -translate-y-1/2 z-0"
                />

                {/* Data Point Nodes */}
                {dataPoints.map((point, index) => {
                    const isComplete = progress[point.key];
                    const isActive = isInvestigating && !isComplete &&
                        (index === 0 || progress[dataPoints[index - 1]?.key]);
                    const colors = getStatusColor(isComplete, point.color);

                    return (
                        <div key={point.key} className="relative z-10 flex flex-col items-center">
                            {/* Node Circle */}
                            <motion.div
                                initial={{ scale: 0.8, opacity: 0 }}
                                animate={{
                                    scale: 1,
                                    opacity: 1,
                                    boxShadow: isComplete
                                        ? '0 0 20px rgba(16, 185, 129, 0.3)'
                                        : isActive
                                            ? '0 0 20px rgba(59, 130, 246, 0.3)'
                                            : 'none'
                                }}
                                transition={{ delay: index * 0.1 }}
                                className={`w-14 h-14 rounded-full flex items-center justify-center border-2 transition-all duration-300 ${isComplete
                                        ? 'bg-emerald-500/20 border-emerald-500'
                                        : isActive
                                            ? 'bg-blue-500/20 border-blue-500 animate-pulse'
                                            : 'bg-gray-800 border-gray-600'
                                    }`}
                            >
                                {isComplete ? (
                                    <Check className="w-6 h-6 text-emerald-400" />
                                ) : isActive ? (
                                    <Loader2 className="w-6 h-6 text-blue-400 animate-spin" />
                                ) : (
                                    <span className="text-xl">{point.icon}</span>
                                )}
                            </motion.div>

                            {/* Label */}
                            <div className="mt-2 text-center">
                                <span className={`text-xs font-medium block ${isComplete ? 'text-emerald-400' : 'text-gray-400'
                                    }`}>
                                    {point.label}
                                </span>
                                {isComplete && (
                                    <span className="text-[10px] text-gray-500">
                                        Synced
                                    </span>
                                )}
                            </div>
                        </div>
                    );
                })}
            </div>

            {/* Progress Bar */}
            <div className="h-1.5 bg-gray-700 rounded-full overflow-hidden">
                <motion.div
                    initial={{ width: 0 }}
                    animate={{ width: `${progressPercentage}%` }}
                    transition={{ duration: 0.5 }}
                    className="h-full bg-gradient-to-r from-emerald-500 to-blue-500"
                />
            </div>

            {/* Status Message */}
            <div className="mt-3 flex items-center justify-center">
                {progressPercentage === 100 ? (
                    <div className="flex items-center space-x-2 text-emerald-400">
                        <Check className="w-4 h-4" />
                        <span className="text-xs font-medium">Investigation Analysis: 100% Complete</span>
                    </div>
                ) : progressPercentage > 0 ? (
                    <div className="flex items-center space-x-2 text-blue-400">
                        <Loader2 className="w-4 h-4 animate-spin" />
                        <span className="text-xs">
                            Investigation Analysis: {progressPercentage.toFixed(0)}% Complete
                        </span>
                    </div>
                ) : null}
            </div>
        </div>
    );
};

export default DataCoverageBar;
