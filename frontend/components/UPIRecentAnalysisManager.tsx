"use client";
import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Clock, Save, Download, Trash2, RefreshCw, FileText, AlertTriangle, TrendingUp, TrendingDown, Activity } from 'lucide-react';
import { UPICaseManager } from '../utils/upiCaseManager';
import usePermissions from '../hooks/usePermissions';
import toast from 'react-hot-toast';
import { formatNumber } from '../utils/formatters';

const UPIRecentAnalysisManager = ({ 
    currentAnalysis, 
    onAnalysisSelect, 
    onAnalysisSave,
    className = '' 
}) => {
    const { role } = usePermissions();
    const canSave = role !== 'viewer';
    const [recentUPICases, setRecentUPICases] = useState([]);
    const [loading, setLoading] = useState(false);
    const [saving, setSaving] = useState(false);

    // Load recent UPI cases on component mount
    useEffect(() => {
        loadRecentUPICases();
        
        // Listen for UPI case file events
        const handleUPICaseSaved = (event) => {
            loadRecentUPICases();
            toast.success(`UPI case saved: ${event.detail.fileName}`);
        };
        
        const handleUPICaseDeleted = () => {
            loadRecentUPICases();
        };
        
        window.addEventListener('upiCaseSaved', handleUPICaseSaved);
        window.addEventListener('upiCaseDeleted', handleUPICaseDeleted);
        
        return () => {
            window.removeEventListener('upiCaseSaved', handleUPICaseSaved);
            window.removeEventListener('upiCaseDeleted', handleUPICaseDeleted);
        };
    }, []);

    const loadRecentUPICases = async () => {
        setLoading(true);
        try {
            const upiCases = await UPICaseManager.listUPICases();
            const rawCases = upiCases.cases || [];
            const normalized = rawCases.map(c => ({
                fileName: c.fileName || c.filename,
                caseId: c.caseId,
                timestamp: c.timestamp || c.metadata?.timestamp || 0,
                riskScore: c.riskScore ?? c.metadata?.riskScore ?? 0,
                riskBand: c.riskBand || c.metadata?.riskBand || 'unknown',
                fileSize: c.fileSize || 0,
                upiAnalysis: c.upiAnalysis || {}
            }));
            setRecentUPICases(normalized);
        } catch (error) {
            console.error('[UPI_RECENT_ANALYSIS_MANAGER] Error loading UPI cases:', error);
            toast.error('Failed to load recent UPI cases');
        } finally {
            setLoading(false);
        }
    };

    const handleSaveCurrentAnalysis = async () => {
        if (!currentAnalysis) {
            toast.error('No UPI analysis data to save');
            return;
        }

        setSaving(true);
        try {
            const fileName = UPICaseManager.generateUPICaseFileName('UPI-Mule-Analysis');
            const success = await UPICaseManager.saveUPICase(fileName, currentAnalysis);
            
            if (success) {
                toast.success(`UPI analysis saved as ${fileName}`);
                onAnalysisSave && onAnalysisSave(fileName);
                await loadRecentUPICases(); // Refresh list
            }
        } catch (error) {
            console.error('[UPI_RECENT_ANALYSIS_MANAGER] Error saving UPI analysis:', error);
            toast.error('Failed to save UPI analysis');
        } finally {
            setSaving(false);
        }
    };

    const handleLoadUPICase = async (fileName) => {
        try {
            const upiCaseData = await UPICaseManager.loadUPICase(fileName);
            if (upiCaseData) {
                onAnalysisSelect && onAnalysisSelect(upiCaseData.data, fileName);
                toast.success(`Loaded UPI case: ${fileName}`);
            }
        } catch (error) {
            console.error('[UPI_RECENT_ANALYSIS_MANAGER] Error loading UPI case:', error);
            toast.error('Failed to load UPI case');
        }
    };

    const handleDeleteUPICase = async (fileName, event) => {
        event.stopPropagation();
        
        if (!window.confirm(`Delete UPI case "${fileName}"? This action cannot be undone.`)) {
            return;
        }

        try {
            const success = await UPICaseManager.deleteUPICase(fileName);
            if (success) {
                toast.success(`UPI case deleted: ${fileName}`);
                await loadRecentUPICases(); // Refresh list
            }
        } catch (error) {
            console.error('[UPI_RECENT_ANALYSIS_MANAGER] Error deleting UPI case:', error);
            toast.error('Failed to delete UPI case');
        }
    };

    const handleDownloadUPICase = (upiCaseData, fileName, event) => {
        event.stopPropagation();
        try {
            const blob = new Blob([JSON.stringify(upiCaseData, null, 2)], {
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
            console.error('[UPI_RECENT_ANALYSIS_MANAGER] Error downloading UPI case:', error);
            toast.error('Failed to download UPI case');
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
        <div className={className}>
            {/* Header */}
            <div style={{
                background: '#0b1220',
                border: '1px solid #1f2a3a',
                borderRadius: '10px',
                padding: '10px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                marginBottom: '10px'
            }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', minWidth: 0 }}>
                    <div style={{
                        width: '28px',
                        height: '28px',
                        borderRadius: '8px',
                        background: 'rgba(59,130,246,0.15)',
                        border: '1px solid rgba(59,130,246,0.25)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        flexShrink: 0
                    }}>
                        <Clock size={14} color="#60a5fa" />
                    </div>
                    <div style={{ minWidth: 0 }}>
                        <div style={{ fontSize: '13px', fontWeight: '700', color: '#e2e8f0', lineHeight: 1.1 }}>
                            UPI Recent Analysis
                        </div>
                        <div style={{ fontSize: '11px', color: '#94a3b8', marginTop: '2px' }}>
                            {recentUPICases.length} saved {recentUPICases.length === 1 ? 'case' : 'cases'}
                        </div>
                    </div>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    {canSave && (
                    <button
                        onClick={handleSaveCurrentAnalysis}
                        disabled={saving || !currentAnalysis}
                        style={{
                            background: saving || !currentAnalysis ? '#1e293b' : 'linear-gradient(135deg, #3b82f6, #6366f1)',
                            color: saving || !currentAnalysis ? '#64748b' : '#ffffff',
                            fontWeight: '700',
                            padding: '8px 10px',
                            borderRadius: '8px',
                            border: saving || !currentAnalysis ? '1px solid #334155' : '1px solid rgba(99,102,241,0.35)',
                            cursor: saving || !currentAnalysis ? 'not-allowed' : 'pointer',
                            fontSize: '11px',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '6px',
                            whiteSpace: 'nowrap'
                        }}
                    >
                        <Save size={12} /> {saving ? 'Saving' : 'Save'}
                    </button>
                    )}

                    <button
                        onClick={loadRecentUPICases}
                        disabled={loading}
                        style={{
                            background: '#1e293b',
                            color: '#94a3b8',
                            padding: '8px 10px',
                            borderRadius: '8px',
                            border: '1px solid #334155',
                            cursor: loading ? 'not-allowed' : 'pointer',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center'
                        }}
                        title="Refresh"
                    >
                        <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
                    </button>
                </div>
            </div>

            {/* List */}
            {recentUPICases.length === 0 ? (
                <div style={{
                    textAlign: 'center',
                    padding: '14px 10px',
                    border: '1px dashed #334155',
                    borderRadius: '10px',
                    color: '#64748b',
                    fontSize: '12px'
                }}>
                    No saved UPI cases
                </div>
            ) : (
                <div style={{ display: 'grid', gap: '8px', maxHeight: '380px', overflowY: 'auto', paddingRight: '4px' }}>
                    {recentUPICases.map((upiCase) => {
                        const inflow = upiCase.upiAnalysis?.totalInAmount || 0;
                        const outflow = upiCase.upiAnalysis?.totalOutAmount || 0;
                        const component = upiCase.upiAnalysis?.componentSize || 0;
                        return (
                            <motion.div
                                key={upiCase.fileName}
                                initial={{ opacity: 0, x: -6 }}
                                animate={{ opacity: 1, x: 0 }}
                                transition={{ duration: 0.18 }}
                                style={{
                                    background: 'rgba(15, 23, 42, 0.55)',
                                    border: '1px solid rgba(51, 65, 85, 0.65)',
                                    borderRadius: '10px',
                                    padding: '10px',
                                    cursor: 'pointer'
                                }}
                                onClick={() => handleLoadUPICase(upiCase.fileName)}
                            >
                                <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '8px' }}>
                                    <div style={{ minWidth: 0, flex: 1 }}>
                                        <div style={{
                                            fontSize: '12px',
                                            fontWeight: '700',
                                            color: '#e2e8f0',
                                            overflow: 'hidden',
                                            textOverflow: 'ellipsis',
                                            whiteSpace: 'nowrap',
                                            marginBottom: '6px'
                                        }}>
                                            {upiCase.fileName}
                                        </div>

                                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                                            <span className={`text-[10px] px-1.5 py-0.5 rounded border ${getRiskColor(upiCase.riskBand)}`}>
                                                Risk: {upiCase.riskScore}
                                            </span>
                                            <span style={{ fontSize: '10px', color: '#94a3b8' }}>{formatDate(upiCase.timestamp)}</span>
                                            <span style={{ fontSize: '10px', color: '#94a3b8' }}>{formatFileSize(upiCase.fileSize)}</span>
                                        </div>
                                    </div>

                                    <div style={{ display: 'flex', gap: '6px', flexShrink: 0 }}>
                                        <button
                                            onClick={(e) => handleDownloadUPICase(upiCase, upiCase.fileName, e)}
                                            style={{
                                                background: '#1e293b',
                                                border: '1px solid #334155',
                                                borderRadius: '8px',
                                                padding: '6px',
                                                cursor: 'pointer',
                                                color: '#94a3b8'
                                            }}
                                            title="Download"
                                        >
                                            <Download size={12} />
                                        </button>
                                        <button
                                            onClick={(e) => handleDeleteUPICase(upiCase.fileName, e)}
                                            style={{
                                                background: 'rgba(239, 68, 68, 0.10)',
                                                border: '1px solid rgba(239, 68, 68, 0.25)',
                                                borderRadius: '8px',
                                                padding: '6px',
                                                cursor: 'pointer',
                                                color: '#fca5a5'
                                            }}
                                            title="Delete"
                                        >
                                            <Trash2 size={12} />
                                        </button>
                                    </div>
                                </div>

                                <div style={{
                                    marginTop: '10px',
                                    display: 'grid',
                                    gridTemplateColumns: '1fr 1fr',
                                    gap: '8px'
                                }}>
                                    <div style={{
                                        background: '#0b1220',
                                        border: '1px solid #1f2a3a',
                                        borderRadius: '8px',
                                        padding: '8px'
                                    }}>
                                        <div style={{ fontSize: '10px', color: '#94a3b8', marginBottom: '2px' }}>In / Out</div>
                                        <div style={{ fontSize: '11px', fontWeight: '700', color: '#e2e8f0' }}>
                                            ₹{formatNumber(inflow)} <span style={{ color: '#64748b' }}>/</span> ₹{formatNumber(outflow)}
                                        </div>
                                    </div>
                                    <div style={{
                                        background: '#0b1220',
                                        border: '1px solid #1f2a3a',
                                        borderRadius: '8px',
                                        padding: '8px'
                                    }}>
                                        <div style={{ fontSize: '10px', color: '#94a3b8', marginBottom: '2px' }}>Component</div>
                                        <div style={{ fontSize: '11px', fontWeight: '700', color: '#e2e8f0' }}>{formatNumber(component)} accounts</div>
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

export default UPIRecentAnalysisManager;
