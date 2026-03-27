"use client";
import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Trash2, RefreshCw, Download } from 'lucide-react';
import { UPIStorageManager } from './UPIStorageManager';

const UPIAnalysisList = ({ onAnalysisSelect, currentFileName }) => {
    const [analyses, setAnalyses] = useState([]);
    const [loading, setLoading] = useState(false);

    const loadHistory = () => {
        setLoading(true);
        try {
            const history = UPIStorageManager.getHistory();
            
            // IMPROVED FILTER: Be less restrictive to ensure items show up
            const validHistory = history.filter(analysis => {
                return analysis && analysis.fileName && analysis.timestamp;
            });

            setAnalyses(validHistory.sort((a, b) => b.timestamp - a.timestamp));
        } catch (error) {
            console.error('[UPI_ANALYSIS_LIST] Error loading history:', error);
            setAnalyses([]);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        loadHistory();
        
        // Listen for storage changes from other tabs
        const handleStorageChange = (e) => {
            if (e.key === 'upi_analysis_history') {
                loadHistory();
            }
        };
        
        // Listen for custom events when analysis is saved in this tab
        const handleAnalysisSaved = () => {
            loadHistory();
        };
        
        // Listen for custom events when analysis is deleted in this tab
        const handleAnalysisDeleted = () => {
            loadHistory();
        };
        
        window.addEventListener('storage', handleStorageChange);
        window.addEventListener('upiAnalysisSaved', handleAnalysisSaved);
        window.addEventListener('upiAnalysisDeleted', handleAnalysisDeleted);
        
        return () => {
            window.removeEventListener('storage', handleStorageChange);
            window.removeEventListener('upiAnalysisSaved', handleAnalysisSaved);
            window.removeEventListener('upiAnalysisDeleted', handleAnalysisDeleted);
        };
    }, []);

    const handleDelete = (fileName, e) => {
        e.stopPropagation();
        if (window.confirm(`Delete analysis "${fileName}"?`)) {
            UPIStorageManager.deleteAnalysis(fileName);
            loadHistory();
        }
    };

    const handleDownload = (analysis, e) => {
        e.stopPropagation();
        try {
            // Handle both old and new data structures
            const dataToDownload = analysis.data || analysis;
            const blob = new Blob([JSON.stringify(dataToDownload, null, 2)], {
                type: 'application/json'
            });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `${analysis.fileName.replace('.csv', '')}_analysis.json`;
            a.click();
            URL.revokeObjectURL(url);
        } catch (error) {
            console.error('[UPI_ANALYSIS_LIST] Error downloading:', error);
        }
    };

    const getRiskColor = (riskBand) => {
        switch (riskBand) {
            case 'critical': return 'text-red-400 bg-red-900/20 border-red-500/30';
            case 'high': return 'text-orange-400 bg-orange-900/20 border-orange-500/30';
            case 'medium': return 'text-yellow-400 bg-yellow-900/20 border-yellow-500/30';
            case 'low': return 'text-green-400 bg-green-900/20 border-green-500/30';
            default: return 'text-gray-400 bg-gray-900/20 border-gray-500/30';
        }
    };

    return (
        <div className="w-full">
            <div className="flex items-center justify-between mb-2 px-2">
                <span className="text-xs text-gray-500 font-medium">
                    {analyses.length} Saved {analyses.length === 1 ? 'Item' : 'Items'}
                </span>
                <button
                    onClick={loadHistory}
                    disabled={loading}
                    className="p-1 rounded hover:bg-gray-700 transition-colors"
                >
                    <RefreshCw className={`w-3 h-3 text-gray-400 ${loading ? 'animate-spin' : ''}`} />
                </button>
            </div>

            {analyses.length === 0 ? (
                <div className="text-center py-6 border border-dashed border-gray-700 rounded-lg mx-2">
                    <p className="text-gray-500 text-xs">No saved analyses</p>
                </div>
            ) : (
                <div className="space-y-2 px-2"> {/* Added px-2 to match your UI alignment */}
                    {analyses.map((analysis) => {
                        // Extracting values safely for the UI
                        const riskScore = analysis.metadata?.riskScore ?? analysis.riskScore ?? 0;
                        const riskBand = analysis.metadata?.riskBand ?? analysis.riskBand ?? 'unknown';
                        
                        return (
                            <motion.div
                                key={`${analysis.fileName}-${analysis.timestamp}`}
                                initial={{ opacity: 0, x: -5 }}
                                animate={{ opacity: 1, x: 0 }}
                                className={`p-3 rounded-lg border cursor-pointer transition-all group ${
                                    currentFileName === analysis.fileName
                                        ? 'bg-blue-900/20 border-blue-500/40'
                                        : 'bg-gray-800/40 border-gray-700/50 hover:bg-gray-800 hover:border-gray-600'
                                }`}
                                onClick={() => onAnalysisSelect(analysis.fileName)}
                            >
                                <div className="flex items-start justify-between">
                                    <div className="flex-1 min-w-0">
                                        <p className={`text-sm font-medium truncate ${
                                            currentFileName === analysis.fileName ? 'text-blue-100' : 'text-gray-300'
                                        }`}>
                                            {analysis.fileName}
                                        </p>
                                        <div className="flex items-center gap-2 mt-1.5">
                                            <span className={`text-[10px] px-1.5 py-0.5 rounded border ${getRiskColor(riskBand)}`}>
                                                Score: {riskScore}
                                            </span>
                                            <span className="text-[10px] text-gray-500">
                                                {new Date(analysis.timestamp).toLocaleDateString()}
                                            </span>
                                        </div>
                                    </div>

                                    <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                                        <button
                                            onClick={(e) => handleDownload(analysis, e)}
                                            className="p-1.5 rounded hover:bg-gray-700"
                                        >
                                            <Download className="w-3 h-3 text-gray-400" />
                                        </button>
                                        <button
                                            onClick={(e) => handleDelete(analysis.fileName, e)}
                                            className="p-1.5 rounded hover:bg-red-900/30"
                                        >
                                            <Trash2 className="w-3 h-3 text-red-400" />
                                        </button>
                                    </div>
                                </div>
                            </motion.div>
                        );
                    })}
                </div>
            )}
        </div>
    );
};

export default UPIAnalysisList;
