"use client";
import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Clock, Save, Download, Trash2, RefreshCw, FileText, AlertTriangle } from 'lucide-react';
import { CaseFileManager } from '../utils/caseFileManager';
import toast from 'react-hot-toast';

const RecentAnalysisManager = ({ 
    currentAnalysis, 
    onAnalysisSelect, 
    onAnalysisSave,
    className = '' 
}) => {
    const [recentCases, setRecentCases] = useState([]);
    const [loading, setLoading] = useState(false);
    const [saving, setSaving] = useState(false);

    // Load recent cases on component mount
    useEffect(() => {
        loadRecentCases();
        
        // Listen for case file events
        const handleCaseFileSaved = (event) => {
            loadRecentCases();
            toast.success(`Case saved: ${event.detail.fileName}`);
        };
        
        const handleCaseFileDeleted = () => {
            loadRecentCases();
        };
        
        window.addEventListener('caseFileSaved', handleCaseFileSaved);
        window.addEventListener('caseFileDeleted', handleCaseFileDeleted);
        
        return () => {
            window.removeEventListener('caseFileSaved', handleCaseFileSaved);
            window.removeEventListener('caseFileDeleted', handleCaseFileDeleted);
        };
    }, []);

    const loadRecentCases = async () => {
        setLoading(true);
        try {
            const cases = await CaseFileManager.listCaseFiles();
            setRecentCases(cases.cases || []);
        } catch (error) {
            console.error('[RECENT_ANALYSIS_MANAGER] Error loading cases:', error);
            toast.error('Failed to load recent cases');
        } finally {
            setLoading(false);
        }
    };

    const handleSaveCurrentAnalysis = async () => {
        if (!currentAnalysis) {
            toast.error('No analysis data to save');
            return;
        }

        setSaving(true);
        try {
            const fileName = CaseFileManager.generateCaseFileName('UPI-Analysis');
            const success = await CaseFileManager.saveCaseFile(fileName, currentAnalysis);
            
            if (success) {
                toast.success(`Analysis saved as ${fileName}`);
                onAnalysisSave && onAnalysisSave(fileName);
                await loadRecentCases(); // Refresh the list
            }
        } catch (error) {
            console.error('[RECENT_ANALYSIS_MANAGER] Error saving analysis:', error);
            toast.error('Failed to save analysis');
        } finally {
            setSaving(false);
        }
    };

    const handleLoadCase = async (fileName) => {
        try {
            const caseData = await CaseFileManager.loadCaseFile(fileName);
            if (caseData) {
                onAnalysisSelect && onAnalysisSelect(caseData.data, fileName);
                toast.success(`Loaded case: ${fileName}`);
            }
        } catch (error) {
            console.error('[RECENT_ANALYSIS_MANAGER] Error loading case:', error);
            toast.error('Failed to load case');
        }
    };

    const handleDeleteCase = async (fileName, event) => {
        event.stopPropagation();
        
        if (!window.confirm(`Delete case "${fileName}"? This action cannot be undone.`)) {
            return;
        }

        try {
            const success = await CaseFileManager.deleteCaseFile(fileName);
            if (success) {
                toast.success(`Case deleted: ${fileName}`);
                await loadRecentCases(); // Refresh the list
            }
        } catch (error) {
            console.error('[RECENT_ANALYSIS_MANAGER] Error deleting case:', error);
            toast.error('Failed to delete case');
        }
    };

    const handleDownloadCase = async (caseData, fileName, event) => {
        event.stopPropagation();
        try {
            const blob = new Blob([JSON.stringify(caseData, null, 2)], {
                type: 'application/json'
            });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = fileName;
            a.click();
            URL.revokeObjectURL(url);
            toast.success(`Downloaded: ${fileName}`);
        } catch (error) {
            console.error('[RECENT_ANALYSIS_MANAGER] Error downloading case:', error);
            toast.error('Failed to download case');
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

    const formatFileSize = (bytes) => {
        if (bytes < 1024) return `${bytes} B`;
        if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
        return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    };

    const formatDate = (timestamp) => {
        const date = new Date(timestamp);
        return date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    };

    return (
        <div className={`space-y-4 ${className}`}>
            {/* Header with Save Current Analysis */}
            <div className="flex items-center justify-between p-4 bg-gray-800/50 rounded-lg border border-gray-700">
                <div className="flex items-center space-x-3">
                    <Clock className="w-5 h-5 text-blue-400" />
                    <div>
                        <h3 className="text-sm font-semibold text-white">Recent Analysis</h3>
                        <p className="text-xs text-gray-400">
                            {recentCases.length} saved {recentCases.length === 1 ? 'case' : 'cases'}
                        </p>
                    </div>
                </div>
                
                <div className="flex items-center space-x-2">
                    <button
                        onClick={handleSaveCurrentAnalysis}
                        disabled={saving || !currentAnalysis}
                        className="flex items-center space-x-2 px-3 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-700 disabled:text-gray-400 text-white text-sm rounded-lg transition-colors"
                    >
                        <Save className="w-4 h-4" />
                        <span>{saving ? 'Saving...' : 'Save Current'}</span>
                    </button>
                    
                    <button
                        onClick={loadRecentCases}
                        disabled={loading}
                        className="p-2 hover:bg-gray-700 rounded-lg transition-colors"
                    >
                        <RefreshCw className={`w-4 h-4 text-gray-400 ${loading ? 'animate-spin' : ''}`} />
                    </button>
                </div>
            </div>

            {/* Recent Cases List */}
            {recentCases.length === 0 ? (
                <div className="text-center py-8 border border-dashed border-gray-700 rounded-lg">
                    <FileText className="w-12 h-12 text-gray-600 mx-auto mb-3" />
                    <p className="text-gray-500 text-sm">No saved cases found</p>
                    <p className="text-gray-600 text-xs mt-1">
                        Save your current analysis to see it here
                    </p>
                </div>
            ) : (
                <div className="space-y-2 max-h-96 overflow-y-auto">
                    {recentCases.map((caseItem) => (
                        <motion.div
                            key={caseItem.fileName}
                            initial={{ opacity: 0, x: -10 }}
                            animate={{ opacity: 1, x: 0 }}
                            className="p-3 bg-gray-800/40 border border-gray-700/50 rounded-lg hover:bg-gray-800 hover:border-gray-600 transition-all cursor-pointer group"
                            onClick={() => handleLoadCase(caseItem.fileName)}
                        >
                            <div className="flex items-start justify-between">
                                <div className="flex-1 min-w-0">
                                    <div className="flex items-center space-x-2 mb-1">
                                        <FileText className="w-4 h-4 text-gray-400 flex-shrink-0" />
                                        <p className="text-sm font-medium text-gray-200 truncate">
                                            {caseItem.fileName}
                                        </p>
                                    </div>
                                    
                                    <div className="flex items-center space-x-3 mb-2">
                                        <span className={`text-[10px] px-1.5 py-0.5 rounded border ${getRiskColor(caseItem.riskBand)}`}>
                                            Risk: {caseItem.riskScore}
                                        </span>
                                        <span className="text-[10px] text-gray-500">
                                            {formatDate(caseItem.timestamp)}
                                        </span>
                                        <span className="text-[10px] text-gray-500">
                                            {formatFileSize(caseItem.fileSize)}
                                        </span>
                                    </div>
                                    
                                    <div className="grid grid-cols-3 gap-2 text-[10px] text-gray-400">
                                        <div>
                                            <span className="text-gray-500">Accounts:</span> {caseItem.totalAccounts}
                                        </div>
                                        <div>
                                            <span className="text-gray-500">Transactions:</span> {caseItem.totalTransactions}
                                        </div>
                                        <div>
                                            <span className="text-gray-500">Risk:</span> {caseItem.riskBand}
                                        </div>
                                    </div>
                                </div>

                                <div className="flex items-center space-x-1 opacity-0 group-hover:opacity-100 transition-opacity ml-3">
                                    <button
                                        onClick={(e) => handleDownloadCase(caseItem, caseItem.fileName, e)}
                                        className="p-1.5 rounded hover:bg-gray-700"
                                        title="Download case file"
                                    >
                                        <Download className="w-3 h-3 text-gray-400" />
                                    </button>
                                    <button
                                        onClick={(e) => handleDeleteCase(caseItem.fileName, e)}
                                        className="p-1.5 rounded hover:bg-red-900/30"
                                        title="Delete case file"
                                    >
                                        <Trash2 className="w-3 h-3 text-red-400" />
                                    </button>
                                </div>
                            </div>
                        </motion.div>
                    ))}
                </div>
            )}

            {/* Info Section */}
            <div className="p-3 bg-blue-900/20 border border-blue-500/30 rounded-lg">
                <div className="flex items-start space-x-2">
                    <AlertTriangle className="w-4 h-4 text-blue-400 mt-0.5 flex-shrink-0" />
                    <div className="text-xs text-blue-200">
                        <p className="font-medium mb-1">About UPI-Case Files</p>
                        <p className="text-blue-300">
                            Case files are stored in the data/cases folder and contain complete analysis data including 
                            graph structure, risk assessments, and forensic insights. They can be loaded later for 
                            further investigation or sharing with team members.
                        </p>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default RecentAnalysisManager;
