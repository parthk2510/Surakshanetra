"use client";
import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Clock, AlertTriangle, CheckCircle, X, Loader2, Database, Zap } from 'lucide-react';

const InvestigationModal = ({ isOpen, onClose, onConfirm, address, options }) => {
    const [isLoading, setIsLoading] = useState(false);
    const [progress, setProgress] = useState(0);
    const [currentPhase, setCurrentPhase] = useState('');
    const [elapsedTime, setElapsedTime] = useState(0);

    const phases = [
        { id: 'address', label: 'Address Data', weight: 20 },
        { id: 'utxos', label: 'UTXO Analysis', weight: 15 },
        { id: 'neighbors', label: 'Neighbor Discovery', weight: 30 },
        { id: 'blocks', label: 'Block Data', weight: 15 },
        { id: 'charts', label: 'Market Context', weight: 10 },
        { id: 'analysis', label: 'Community Detection', weight: 10 }
    ];

    const estimateTime = () => {
        let apiCalls = 2;
        if (options?.fetchNeighbors) apiCalls += 2;
        if (options?.fetchUTXOs) apiCalls += 1;
        if (options?.fetchBlocks) apiCalls += 1;
        if (options?.fetchCharts) apiCalls += 4;
        const minutes = Math.ceil((apiCalls * 10) / 60);
        return { minutes, apiCalls };
    };

    const { minutes, apiCalls } = estimateTime();

    useEffect(() => {
        let timer;
        if (isLoading) {
            timer = setInterval(() => {
                setElapsedTime(prev => prev + 1);
            }, 1000);
        }
        return () => clearInterval(timer);
    }, [isLoading]);

    const formatTime = (seconds) => {
        const mins = Math.floor(seconds / 60);
        const secs = seconds % 60;
        return `${mins}:${secs.toString().padStart(2, '0')}`;
    };

    const handleConfirm = async () => {
        setIsLoading(true);
        setProgress(0);
        setElapsedTime(0);
        
        try {
            for (let i = 0; i < phases.length; i++) {
                setCurrentPhase(phases[i].label);
                setProgress(phases.slice(0, i).reduce((sum, p) => sum + p.weight, 0));
                await new Promise(resolve => setTimeout(resolve, 500));
            }
            setProgress(100);
            await onConfirm();
        } catch (error) {
            console.error('Investigation failed:', error);
        } finally {
            setIsLoading(false);
        }
    };

    if (!isOpen) return null;

    return (
        <AnimatePresence>
            <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4"
                onClick={onClose}
            >
                <motion.div
                    initial={{ scale: 0.95, opacity: 0 }}
                    animate={{ scale: 1, opacity: 1 }}
                    exit={{ scale: 0.95, opacity: 0 }}
                    className="bg-gray-800 rounded-2xl border border-gray-700 shadow-2xl max-w-lg w-full overflow-hidden"
                    onClick={e => e.stopPropagation()}
                >
                    <div className="p-6 border-b border-gray-700 flex items-center justify-between">
                        <div className="flex items-center space-x-3">
                            <div className="p-2 bg-blue-500/20 rounded-lg">
                                <Database className="w-6 h-6 text-blue-400" />
                            </div>
                            <h2 className="text-xl font-bold text-white">Deep Investigation</h2>
                        </div>
                        {!isLoading && (
                            <button onClick={onClose} className="p-2 hover:bg-gray-700 rounded-lg transition-colors">
                                <X className="w-5 h-5 text-gray-400" />
                            </button>
                        )}
                    </div>

                    <div className="p-6 space-y-6">
                        <div className="bg-gray-900/50 rounded-lg p-4 border border-gray-700">
                            <p className="text-sm text-gray-400 mb-2">Target Address</p>
                            <p className="text-white font-mono text-sm break-all">{address}</p>
                        </div>

                        {!isLoading ? (
                            <>
                                <div className="grid grid-cols-2 gap-4">
                                    <div className="bg-gray-900/50 rounded-lg p-4 border border-gray-700">
                                        <div className="flex items-center space-x-2 mb-2">
                                            <Clock className="w-4 h-4 text-blue-400" />
                                            <span className="text-sm text-gray-400">Est. Time</span>
                                        </div>
                                        <p className="text-2xl font-bold text-white">~{minutes} min</p>
                                    </div>
                                    <div className="bg-gray-900/50 rounded-lg p-4 border border-gray-700">
                                        <div className="flex items-center space-x-2 mb-2">
                                            <Zap className="w-4 h-4 text-yellow-400" />
                                            <span className="text-sm text-gray-400">API Calls</span>
                                        </div>
                                        <p className="text-2xl font-bold text-white">{apiCalls}</p>
                                    </div>
                                </div>

                                <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-lg p-4">
                                    <div className="flex items-start space-x-3">
                                        <AlertTriangle className="w-5 h-5 text-yellow-400 flex-shrink-0 mt-0.5" />
                                        <div>
                                            <p className="text-yellow-400 font-medium">Rate Limiting Active</p>
                                            <p className="text-yellow-300/70 text-sm mt-1">
                                                1 request per 10 seconds to prevent 429 errors. 
                                                All transaction data will be fetched (no limits).
                                            </p>
                                        </div>
                                    </div>
                                </div>

                                <div className="space-y-2">
                                    <p className="text-sm font-medium text-gray-300">Investigation Phases:</p>
                                    <div className="grid grid-cols-2 gap-2">
                                        {phases.map(phase => (
                                            <div key={phase.id} className="flex items-center space-x-2 text-sm text-gray-400">
                                                <CheckCircle className="w-3 h-3 text-gray-600" />
                                                <span>{phase.label}</span>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            </>
                        ) : (
                            <div className="space-y-6">
                                <div className="flex items-center justify-center space-x-3">
                                    <Loader2 className="w-6 h-6 text-blue-400 animate-spin" />
                                    <span className="text-lg text-white">{currentPhase}</span>
                                </div>

                                <div className="space-y-2">
                                    <div className="flex justify-between text-sm">
                                        <span className="text-gray-400">Progress</span>
                                        <span className="text-white">{Math.round(progress)}%</span>
                                    </div>
                                    <div className="h-3 bg-gray-700 rounded-full overflow-hidden">
                                        <motion.div
                                            className="h-full bg-gradient-to-r from-blue-500 to-purple-500"
                                            initial={{ width: 0 }}
                                            animate={{ width: `${progress}%` }}
                                            transition={{ duration: 0.3 }}
                                        />
                                    </div>
                                </div>

                                <div className="text-center">
                                    <p className="text-2xl font-mono text-white">{formatTime(elapsedTime)}</p>
                                    <p className="text-sm text-gray-400">Elapsed Time</p>
                                </div>

                                <div className="grid grid-cols-3 gap-2">
                                    {phases.map(phase => {
                                        const phaseProgress = phases.slice(0, phases.indexOf(phase)).reduce((sum, p) => sum + p.weight, 0);
                                        const isComplete = progress >= phaseProgress + phase.weight;
                                        const isActive = progress >= phaseProgress && progress < phaseProgress + phase.weight;
                                        return (
                                            <div 
                                                key={phase.id} 
                                                className={`p-2 rounded-lg text-xs text-center ${
                                                    isComplete ? 'bg-green-500/20 text-green-400' :
                                                    isActive ? 'bg-blue-500/20 text-blue-400' :
                                                    'bg-gray-700/50 text-gray-500'
                                                }`}
                                            >
                                                {phase.label}
                                            </div>
                                        );
                                    })}
                                </div>
                            </div>
                        )}
                    </div>

                    <div className="p-6 border-t border-gray-700 flex justify-end space-x-3">
                        {!isLoading && (
                            <>
                                <button
                                    onClick={onClose}
                                    className="px-6 py-2.5 bg-gray-700 text-gray-300 rounded-lg hover:bg-gray-600 transition-colors font-medium"
                                >
                                    Cancel
                                </button>
                                <button
                                    onClick={handleConfirm}
                                    className="px-6 py-2.5 bg-gradient-to-r from-blue-600 to-purple-600 text-white rounded-lg hover:from-blue-700 hover:to-purple-700 transition-all font-medium"
                                >
                                    Start Investigation
                                </button>
                            </>
                        )}
                    </div>
                </motion.div>
            </motion.div>
        </AnimatePresence>
    );
};

export default InvestigationModal;
