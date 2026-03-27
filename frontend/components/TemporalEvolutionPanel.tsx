"use client";
/**
 * TemporalEvolutionPanel - Community Evolution Analysis UI
 * 
 * Interactive panel for analyzing community structure changes between
 * two temporal snapshots of Bitcoin transaction networks.
 * 
 * Features:
 * - Compare current graph with saved snapshot
 * - NMI score and stability metrics
 * - Visual transition detection (splits, merges, emergences, dissolutions)
 * - Interactive drill-down into community changes
 */

import React, { useState, useCallback, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
    GitCompare, TrendingUp, TrendingDown, AlertTriangle, CheckCircle,
    RefreshCw, Download, ChevronDown, ChevronUp, GitMerge,
    GitBranch, Sparkles, X, ArrowRight, Clock, Activity
} from 'lucide-react';
import toast from 'react-hot-toast';
import structuredLogger from '../utils/structuredLogger';

// API base URL
const API_BASE = '';

const TemporalEvolutionPanel = ({
    currentGraphData,
    savedSnapshots = [],
    onSnapshotSelect,
    onNodeHighlight
}) => {
    const [isExpanded, setIsExpanded] = useState(false);
    const [isAnalyzing, setIsAnalyzing] = useState(false);
    const [analysisResult, setAnalysisResult] = useState(null);
    const [selectedSnapshot, setSelectedSnapshot] = useState(null);
    const [algorithm, setAlgorithm] = useState('louvain');
    const [resolution, setResolution] = useState(1.0);
    const [showDetails, setShowDetails] = useState(null);
    const [temporalStatus, setTemporalStatus] = useState(null);

    // Check temporal analysis availability on mount
    useEffect(() => {
        const checkStatus = async () => {
            try {
                const response = await fetch(`${API_BASE}/api/temporal/status`);
                const data = await response.json();
                if (data.success) {
                    setTemporalStatus(data.data);
                }
            } catch (error) {
                console.warn('Temporal analysis status check failed:', error);
            }
        };
        checkStatus();
    }, []);

    // Run temporal analysis
    const runAnalysis = useCallback(async (snapshotT1) => {
        if (!currentGraphData || !snapshotT1) {
            toast.error('Both current and comparison snapshots are required');
            return;
        }

        setIsAnalyzing(true);
        structuredLogger.temporalAnalysis('started', {
            algorithm,
            nodes_current: currentGraphData.nodes?.length
        });

        const timer = structuredLogger.startTimer('temporal_analysis');

        try {
            const response = await fetch(`${API_BASE}/api/temporal/analyze`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    snapshot_t1: {
                        nodes: snapshotT1.nodes || [],
                        edges: snapshotT1.edges || [],
                        timestamp: snapshotT1.timestamp
                    },
                    snapshot_t2: {
                        nodes: currentGraphData.nodes || [],
                        edges: currentGraphData.edges || [],
                        timestamp: new Date().toISOString()
                    },
                    algorithm,
                    resolution
                })
            });

            const result = await response.json();

            if (result.success) {
                setAnalysisResult(result.data);
                structuredLogger.endTimer(timer, 'success', `NMI: ${result.data.summary.nmi_score}`);
                toast.success(`Analysis complete! NMI: ${result.data.summary.nmi_score.toFixed(4)}`);
            } else {
                throw new Error(result.error || 'Analysis failed');
            }
        } catch (error) {
            structuredLogger.error('temporal.analyze', error.message, { error });
            toast.error(`Analysis failed: ${error.message}`);
        } finally {
            setIsAnalyzing(false);
        }
    }, [currentGraphData, algorithm, resolution]);

    // Run demo analysis
    const runDemo = useCallback(async () => {
        setIsAnalyzing(true);
        structuredLogger.temporalAnalysis('demo_started');

        try {
            const response = await fetch(`${API_BASE}/api/temporal/demo`);
            const result = await response.json();

            if (result.success) {
                toast.success('Demo analysis complete!');
                structuredLogger.temporalAnalysis('demo_completed', result.data.summary);
            }
        } catch (error) {
            toast.error('Demo failed');
        } finally {
            setIsAnalyzing(false);
        }
    }, []);

    // Handle snapshot selection
    const handleSnapshotSelect = (snapshot) => {
        setSelectedSnapshot(snapshot);
        structuredLogger.userAction('snapshot_selected', snapshot.id || 'unnamed');
        if (onSnapshotSelect) onSnapshotSelect(snapshot);
    };

    // Highlight nodes in a community
    const highlightCommunity = (communityId, source) => {
        structuredLogger.graphInteraction('highlight_community', { communityId, source });
        if (onNodeHighlight && analysisResult) {
            const partition = source === 't1'
                ? analysisResult.community_t1.partition
                : analysisResult.community_t2.partition;
            const nodes = Object.entries(partition)
                .filter(([_, cid]) => cid === communityId)
                .map(([nodeId]) => nodeId);
            onNodeHighlight(nodes);
        }
    };

    // Render NMI gauge
    const renderNMIGauge = (score) => {
        const percentage = score * 100;
        const color = score >= 0.8 ? '#10b981' : score >= 0.5 ? '#f59e0b' : '#ef4444';
        const label = score >= 0.8 ? 'Stable' : score >= 0.5 ? 'Moderate' : 'Unstable';

        return (
            <div className="relative w-32 h-32 mx-auto">
                <svg className="w-full h-full transform -rotate-90">
                    <circle
                        cx="64"
                        cy="64"
                        r="56"
                        fill="none"
                        stroke="#374151"
                        strokeWidth="8"
                    />
                    <circle
                        cx="64"
                        cy="64"
                        r="56"
                        fill="none"
                        stroke={color}
                        strokeWidth="8"
                        strokeDasharray={`${percentage * 3.51} 351`}
                        strokeLinecap="round"
                        className="transition-all duration-1000"
                    />
                </svg>
                <div className="absolute inset-0 flex flex-col items-center justify-center">
                    <span className="text-2xl font-bold text-white">{score.toFixed(2)}</span>
                    <span className="text-xs text-gray-400">{label}</span>
                </div>
            </div>
        );
    };

    // Render transition card
    const renderTransitionCard = (type, items, icon, colorScheme) => {
        if (!items || items.length === 0) return null;

        // Concrete color classes to ensure Tailwind compiles them
        const colorClasses = {
            orange: { border: 'border-orange-500/30', bg: 'bg-orange-500/20', text: 'text-orange-400' },
            blue: { border: 'border-blue-500/30', bg: 'bg-blue-500/20', text: 'text-blue-400' },
            green: { border: 'border-green-500/30', bg: 'bg-green-500/20', text: 'text-green-400' },
            red: { border: 'border-red-500/30', bg: 'bg-red-500/20', text: 'text-red-400' }
        };
        const colors = colorClasses[colorScheme] || colorClasses.blue;

        return (
            <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                className={`bg-gray-800/50 rounded-lg border ${colors.border} p-4`}
            >
                <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center space-x-2">
                        {icon}
                        <span className="text-sm font-semibold text-white capitalize">{type}</span>
                    </div>
                    <span className={`px-2 py-1 rounded-full text-xs font-medium ${colors.bg} ${colors.text}`}>
                        {items.length}
                    </span>
                </div>
                <div className="space-y-2">
                    {items.slice(0, 3).map((item, idx) => (
                        <div
                            key={idx}
                            className="text-xs text-gray-400 bg-gray-900/50 rounded px-2 py-1 cursor-pointer hover:bg-gray-800/50 transition-colors"
                            onClick={() => setShowDetails({ type, item })}
                        >
                            {type === 'splits' && (
                                <span>Community {item.source} → {item.targets.join(', ')} (ratio: {item.ratio})</span>
                            )}
                            {type === 'merges' && (
                                <span>Communities {item.sources.join(', ')} → {item.target} (ratio: {item.ratio})</span>
                            )}
                            {type === 'emergences' && (
                                <span>New Community {item.community_id} (size: {item.size})</span>
                            )}
                            {type === 'dissolutions' && (
                                <span>Community {item.community_id} dissolved (was: {item.size})</span>
                            )}
                        </div>
                    ))}
                    {items.length > 3 && (
                        <span className="text-xs text-gray-500">+{items.length - 3} more</span>
                    )}
                </div>
            </motion.div>
        );
    };

    return (
        <div className="bg-gray-800/50 backdrop-blur-sm rounded-lg border border-gray-700/50 overflow-hidden">
            {/* Header */}
            <button
                onClick={() => setIsExpanded(!isExpanded)}
                className="w-full px-4 py-3 flex items-center justify-between hover:bg-gray-700/30 transition-colors"
            >
                <div className="flex items-center space-x-3">
                    <GitCompare className="w-5 h-5 text-purple-400" />
                    <div className="text-left">
                        <h3 className="text-sm font-semibold text-white">Temporal Evolution Analysis</h3>
                        <p className="text-xs text-gray-400">Compare community structures over time</p>
                    </div>
                </div>
                <div className="flex items-center space-x-2">
                    {temporalStatus?.available ? (
                        <span className="px-2 py-1 rounded-full text-xs bg-green-500/20 text-green-400">
                            Available
                        </span>
                    ) : (
                        <span className="px-2 py-1 rounded-full text-xs bg-yellow-500/20 text-yellow-400">
                            Loading...
                        </span>
                    )}
                    {isExpanded ? <ChevronUp className="w-5 h-5 text-gray-400" /> : <ChevronDown className="w-5 h-5 text-gray-400" />}
                </div>
            </button>

            {/* Expanded Content */}
            <AnimatePresence>
                {isExpanded && (
                    <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: 'auto', opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        className="border-t border-gray-700/50"
                    >
                        <div className="p-4 space-y-4">
                            {/* Configuration */}
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="block text-xs text-gray-400 mb-1">Algorithm</label>
                                    <select
                                        value={algorithm}
                                        onChange={(e) => setAlgorithm(e.target.value)}
                                        className="w-full px-3 py-2 bg-gray-700/50 border border-gray-600/50 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
                                    >
                                        <option value="louvain">Louvain</option>
                                        <option value="leiden">Leiden</option>
                                        <option value="label_propagation">Label Propagation</option>
                                    </select>
                                </div>
                                <div>
                                    <label className="block text-xs text-gray-400 mb-1">Resolution</label>
                                    <input
                                        type="number"
                                        value={resolution}
                                        onChange={(e) => setResolution(parseFloat(e.target.value) || 1.0)}
                                        step="0.1"
                                        min="0.1"
                                        max="3.0"
                                        className="w-full px-3 py-2 bg-gray-700/50 border border-gray-600/50 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
                                    />
                                </div>
                            </div>

                            {/* Snapshot Selection */}
                            {savedSnapshots.length > 0 && (
                                <div>
                                    <label className="block text-xs text-gray-400 mb-2">Compare with snapshot:</label>
                                    <div className="space-y-2 max-h-32 overflow-y-auto">
                                        {savedSnapshots.map((snapshot, idx) => (
                                            <button
                                                key={idx}
                                                onClick={() => handleSnapshotSelect(snapshot)}
                                                className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-sm transition-colors ${selectedSnapshot === snapshot
                                                    ? 'bg-purple-500/20 border border-purple-500/50 text-purple-300'
                                                    : 'bg-gray-700/30 hover:bg-gray-700/50 text-gray-300'
                                                    }`}
                                            >
                                                <div className="flex items-center space-x-2">
                                                    <Clock className="w-4 h-4" />
                                                    <span>{snapshot.name || `Snapshot ${idx + 1}`}</span>
                                                </div>
                                                <span className="text-xs text-gray-500">
                                                    {snapshot.nodes?.length || 0} nodes
                                                </span>
                                            </button>
                                        ))}
                                    </div>
                                </div>
                            )}

                            {/* Action Buttons */}
                            <div className="flex space-x-2">
                                <button
                                    onClick={() => selectedSnapshot && runAnalysis(selectedSnapshot)}
                                    disabled={isAnalyzing || !selectedSnapshot || !currentGraphData}
                                    className="flex-1 flex items-center justify-center space-x-2 px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                                >
                                    {isAnalyzing ? (
                                        <>
                                            <RefreshCw className="w-4 h-4 animate-spin" />
                                            <span>Analyzing...</span>
                                        </>
                                    ) : (
                                        <>
                                            <GitCompare className="w-4 h-4" />
                                            <span>Compare</span>
                                        </>
                                    )}
                                </button>
                                <button
                                    onClick={runDemo}
                                    disabled={isAnalyzing}
                                    className="px-4 py-2 bg-gray-700 text-white rounded-lg hover:bg-gray-600 disabled:opacity-50 transition-colors"
                                >
                                    Demo
                                </button>
                            </div>

                            {/* Results Section */}
                            {analysisResult && (
                                <motion.div
                                    initial={{ opacity: 0 }}
                                    animate={{ opacity: 1 }}
                                    className="space-y-4 pt-4 border-t border-gray-700/50"
                                >
                                    {/* Summary Header */}
                                    <div className="flex items-center justify-between">
                                        <h4 className="text-sm font-semibold text-white">Analysis Results</h4>
                                        <span className="text-xs text-gray-400">
                                            {analysisResult.algorithm} | {new Date(analysisResult.timestamp).toLocaleTimeString()}
                                        </span>
                                    </div>

                                    {/* NMI Score and Key Metrics */}
                                    <div className="grid grid-cols-3 gap-4">
                                        <div className="col-span-1">
                                            {renderNMIGauge(analysisResult.summary.nmi_score)}
                                            <p className="text-center text-xs text-gray-400 mt-2">NMI Score</p>
                                        </div>
                                        <div className="col-span-2 grid grid-cols-2 gap-2">
                                            <div className="bg-gray-900/50 rounded-lg p-3">
                                                <div className="flex items-center justify-between">
                                                    <span className="text-xs text-gray-400">Communities</span>
                                                    {analysisResult.summary.delta_communities > 0 ? (
                                                        <TrendingUp className="w-4 h-4 text-green-400" />
                                                    ) : analysisResult.summary.delta_communities < 0 ? (
                                                        <TrendingDown className="w-4 h-4 text-red-400" />
                                                    ) : (
                                                        <Activity className="w-4 h-4 text-gray-400" />
                                                    )}
                                                </div>
                                                <div className="flex items-baseline space-x-2 mt-1">
                                                    <span className="text-lg font-bold text-white">
                                                        {analysisResult.summary.communities_t1}
                                                    </span>
                                                    <ArrowRight className="w-3 h-3 text-gray-500" />
                                                    <span className="text-lg font-bold text-white">
                                                        {analysisResult.summary.communities_t2}
                                                    </span>
                                                </div>
                                            </div>
                                            <div className="bg-gray-900/50 rounded-lg p-3">
                                                <span className="text-xs text-gray-400">Stability</span>
                                                <div className="flex items-center space-x-2 mt-1">
                                                    {analysisResult.summary.is_stable ? (
                                                        <CheckCircle className="w-4 h-4 text-green-400" />
                                                    ) : (
                                                        <AlertTriangle className="w-4 h-4 text-yellow-400" />
                                                    )}
                                                    <span className="text-sm font-medium text-white">
                                                        {analysisResult.summary.nodes_unchanged_pct.toFixed(1)}% unchanged
                                                    </span>
                                                </div>
                                            </div>
                                            <div className="bg-gray-900/50 rounded-lg p-3">
                                                <span className="text-xs text-gray-400">Modularity T1</span>
                                                <span className="block text-lg font-bold text-white">
                                                    {analysisResult.summary.modularity_t1.toFixed(4)}
                                                </span>
                                            </div>
                                            <div className="bg-gray-900/50 rounded-lg p-3">
                                                <span className="text-xs text-gray-400">Modularity T2</span>
                                                <span className="block text-lg font-bold text-white">
                                                    {analysisResult.summary.modularity_t2.toFixed(4)}
                                                </span>
                                            </div>
                                        </div>
                                    </div>

                                    {/* Transitions Grid */}
                                    <div className="grid grid-cols-2 gap-3">
                                        {renderTransitionCard(
                                            'splits',
                                            analysisResult.transitions.splits,
                                            <GitBranch className="w-4 h-4 text-orange-400" />,
                                            'orange'
                                        )}
                                        {renderTransitionCard(
                                            'merges',
                                            analysisResult.transitions.merges,
                                            <GitMerge className="w-4 h-4 text-blue-400" />,
                                            'blue'
                                        )}
                                        {renderTransitionCard(
                                            'emergences',
                                            analysisResult.transitions.emergences,
                                            <Sparkles className="w-4 h-4 text-green-400" />,
                                            'green'
                                        )}
                                        {renderTransitionCard(
                                            'dissolutions',
                                            analysisResult.transitions.dissolutions,
                                            <X className="w-4 h-4 text-red-400" />,
                                            'red'
                                        )}
                                    </div>

                                    {/* Stable Communities */}
                                    {analysisResult.transitions.stable.length > 0 && (
                                        <div className="bg-gray-900/50 rounded-lg p-3">
                                            <div className="flex items-center space-x-2 mb-2">
                                                <CheckCircle className="w-4 h-4 text-green-400" />
                                                <span className="text-sm font-semibold text-white">
                                                    Stable Communities ({analysisResult.transitions.stable.length})
                                                </span>
                                            </div>
                                            <div className="flex flex-wrap gap-2">
                                                {analysisResult.transitions.stable.slice(0, 10).map((cid) => (
                                                    <button
                                                        key={cid}
                                                        onClick={() => highlightCommunity(cid, 't2')}
                                                        className="px-2 py-1 bg-green-500/20 rounded text-xs text-green-300 hover:bg-green-500/30 transition-colors"
                                                    >
                                                        C{cid}
                                                    </button>
                                                ))}
                                                {analysisResult.transitions.stable.length > 10 && (
                                                    <span className="text-xs text-gray-500">
                                                        +{analysisResult.transitions.stable.length - 10} more
                                                    </span>
                                                )}
                                            </div>
                                        </div>
                                    )}

                                    {/* Export Button */}
                                    <button
                                        onClick={() => {
                                            const blob = new Blob([JSON.stringify(analysisResult, null, 2)], { type: 'application/json' });
                                            const url = URL.createObjectURL(blob);
                                            const a = document.createElement('a');
                                            a.href = url;
                                            a.download = `temporal-analysis-${Date.now()}.json`;
                                            a.click();
                                            URL.revokeObjectURL(url);
                                            structuredLogger.userAction('export_temporal_analysis');
                                        }}
                                        className="w-full flex items-center justify-center space-x-2 px-4 py-2 bg-gray-700/50 text-gray-300 rounded-lg hover:bg-gray-700 transition-colors"
                                    >
                                        <Download className="w-4 h-4" />
                                        <span>Export Results</span>
                                    </button>
                                </motion.div>
                            )}
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* Detail Modal */}
            <AnimatePresence>
                {showDetails && (
                    <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
                        onClick={() => setShowDetails(null)}
                    >
                        <motion.div
                            initial={{ scale: 0.9 }}
                            animate={{ scale: 1 }}
                            exit={{ scale: 0.9 }}
                            className="bg-gray-800 rounded-xl border border-gray-700 p-6 max-w-md w-full mx-4"
                            onClick={(e) => e.stopPropagation()}
                        >
                            <div className="flex items-center justify-between mb-4">
                                <h3 className="text-lg font-semibold text-white capitalize">
                                    {showDetails.type} Details
                                </h3>
                                <button
                                    onClick={() => setShowDetails(null)}
                                    className="text-gray-400 hover:text-white"
                                >
                                    <X className="w-5 h-5" />
                                </button>
                            </div>
                            <pre className="bg-gray-900 rounded-lg p-4 text-xs text-gray-300 overflow-auto max-h-64">
                                {JSON.stringify(showDetails.item, null, 2)}
                            </pre>
                            <div className="mt-4 flex space-x-2">
                                {showDetails.type === 'splits' && (
                                    <button
                                        onClick={() => highlightCommunity(showDetails.item.source, 't1')}
                                        className="flex-1 px-3 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700"
                                    >
                                        Highlight Source
                                    </button>
                                )}
                                {showDetails.type === 'merges' && (
                                    <button
                                        onClick={() => highlightCommunity(showDetails.item.target, 't2')}
                                        className="flex-1 px-3 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700"
                                    >
                                        Highlight Target
                                    </button>
                                )}
                            </div>
                        </motion.div>
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    );
};

export default TemporalEvolutionPanel;
