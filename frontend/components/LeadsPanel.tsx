"use client";
// frontend/src/components/LeadsPanel.js
import React, { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
    AlertTriangle, ChevronDown, ChevronRight, ExternalLink,
    Shield, ShieldAlert, RefreshCw, Database, Eye
} from 'lucide-react';
import { getLeadPriorityColor, getLeadPriorityIcon } from '../core/LeadGenerator';
import toast from 'react-hot-toast';

const LeadsPanel = ({ leads, onNodeSelect }) => {
    const [expandedLead, setExpandedLead] = useState(null);
    const [filterPriority, setFilterPriority] = useState('all');
    const [threatIntelCache, setThreatIntelCache] = useState({});
    const [loadingThreatIntel, setLoadingThreatIntel] = useState({});
    const [threatIntelAvailable, setThreatIntelAvailable] = useState(true);

    // Check threat intel availability on mount
    useEffect(() => {
        checkThreatIntelStatus();
    }, []);

    const checkThreatIntelStatus = async () => {
        try {
            const response = await fetch('/api/threat-intel/status');
            const data = await response.json();
            setThreatIntelAvailable(data.available || false);
        } catch (error) {
            console.warn('Threat intel status check failed:', error);
            setThreatIntelAvailable(false);
        }
    };

    // Fetch threat intel for a specific address
    const fetchThreatIntel = useCallback(async (address) => {
        if (!address || threatIntelCache[address] || loadingThreatIntel[address]) {
            return;
        }

        setLoadingThreatIntel(prev => ({ ...prev, [address]: true }));

        try {
            const response = await fetch('/api/threat-intel/check', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ address })
            });

            const data = await response.json();

            if (data.success) {
                setThreatIntelCache(prev => ({
                    ...prev,
                    [address]: {
                        blacklisted: data.blacklisted,
                        confidence: data.confidence,
                        risk_level: data.risk_level,
                        sources: data.blacklisted_sources || [],
                        illicit_analysis: data.illicit_activity_analysis,
                        timestamp: new Date().toISOString()
                    }
                }));

                if (data.blacklisted) {
                    toast.error(`⚠️ ${address.substring(0, 12)}... flagged by threat intel!`, {
                        duration: 4000
                    });
                }
            }
        } catch (error) {
            console.error('Threat intel fetch failed:', error);
        } finally {
            setLoadingThreatIntel(prev => ({ ...prev, [address]: false }));
        }
    }, [threatIntelCache, loadingThreatIntel]);

    // Auto-fetch threat intel when a lead is expanded
    const handleLeadToggle = useCallback((leadId, nodeId) => {
        if (expandedLead === leadId) {
            setExpandedLead(null);
        } else {
            setExpandedLead(leadId);
            // Fetch threat intel when expanding a lead
            if (threatIntelAvailable && nodeId) {
                fetchThreatIntel(nodeId);
            }
        }
    }, [expandedLead, threatIntelAvailable, fetchThreatIntel]);

    const filteredLeads = filterPriority === 'all'
        ? leads
        : leads.filter(l => l.priority === filterPriority);

    const priorityCounts = {
        critical: leads.filter(l => l.priority === 'critical').length,
        high: leads.filter(l => l.priority === 'high').length,
        medium: leads.filter(l => l.priority === 'medium').length,
        low: leads.filter(l => l.priority === 'low').length
    };

    return (
        <div className="bg-gray-800/50 backdrop-blur-sm rounded-lg border border-gray-700/50 overflow-hidden forensic-panel">
            {/* Header */}
            <div className="bg-gradient-to-r from-red-900/30 to-orange-900/30 border-b border-red-500/30 px-4 py-3">
                <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-2">
                        <AlertTriangle className="w-5 h-5 text-red-400" />
                        <h3 className="text-sm font-bold text-white uppercase tracking-wide">
                            Investigative Leads & Anomalies
                        </h3>
                    </div>
                    {/* Threat Intel Status Badge */}
                    <div className={`flex items-center space-x-1 px-2 py-1 rounded text-xs ${threatIntelAvailable
                            ? 'bg-green-500/20 text-green-400'
                            : 'bg-gray-500/20 text-gray-400'
                        }`}>
                        <Database className="w-3 h-3" />
                        <span>{threatIntelAvailable ? 'OSINT Active' : 'OSINT Offline'}</span>
                    </div>
                </div>
                <p className="text-xs text-gray-400 mt-1">
                    {filteredLeads.length} {filteredLeads.length === 1 ? 'lead' : 'leads'} detected
                </p>
            </div>

            {/* Priority Filter */}
            <div className="px-4 py-3 border-b border-gray-700/50 bg-gray-900/30">
                <div className="flex flex-wrap gap-2">
                    <button
                        onClick={() => setFilterPriority('all')}
                        className={`px-3 py-1 rounded text-xs font-medium transition-colors ${filterPriority === 'all'
                            ? 'bg-blue-600 text-white'
                            : 'bg-gray-700/50 text-gray-400 hover:bg-gray-700'
                            }`}
                    >
                        All ({leads.length})
                    </button>
                    {priorityCounts.critical > 0 && (
                        <button
                            onClick={() => setFilterPriority('critical')}
                            className={`px-3 py-1 rounded text-xs font-medium transition-colors ${filterPriority === 'critical'
                                ? 'bg-red-600 text-white'
                                : 'bg-gray-700/50 text-gray-400 hover:bg-gray-700'
                                }`}
                        >
                            🚨 Critical ({priorityCounts.critical})
                        </button>
                    )}
                    {priorityCounts.high > 0 && (
                        <button
                            onClick={() => setFilterPriority('high')}
                            className={`px-3 py-1 rounded text-xs font-medium transition-colors ${filterPriority === 'high'
                                ? 'bg-amber-600 text-white'
                                : 'bg-gray-700/50 text-gray-400 hover:bg-gray-700'
                                }`}
                        >
                            ⚠️ High ({priorityCounts.high})
                        </button>
                    )}
                </div>
            </div>

            {/* Leads List */}
            <div className="max-h-[600px] overflow-y-auto">
                {filteredLeads.length === 0 ? (
                    <div className="px-4 py-8 text-center">
                        <AlertTriangle className="w-12 h-12 text-gray-600 mx-auto mb-3" />
                        <p className="text-sm text-gray-400">No leads detected yet</p>
                        <p className="text-xs text-gray-500 mt-1">
                            Start an investigation to generate leads
                        </p>
                    </div>
                ) : (
                    <div className="divide-y divide-gray-700/50">
                        {filteredLeads.map((lead, index) => (
                            <LeadCard
                                key={lead.id}
                                lead={lead}
                                index={index}
                                isExpanded={expandedLead === lead.id}
                                onToggle={() => handleLeadToggle(lead.id, lead.nodeId)}
                                onNodeClick={() => onNodeSelect(lead.nodeId)}
                                threatIntel={threatIntelCache[lead.nodeId]}
                                loadingThreatIntel={loadingThreatIntel[lead.nodeId]}
                                onFetchThreatIntel={() => fetchThreatIntel(lead.nodeId)}
                                threatIntelAvailable={threatIntelAvailable}
                            />
                        ))}
                    </div>
                )}
            </div>

            {/* Legend */}
            {leads.length > 0 && (
                <div className="px-4 py-3 border-t border-gray-700/50 bg-gray-900/30">
                    <p className="text-xs text-gray-500 font-mono">
                        <span className="text-gray-400 font-semibold">STATUS:</span> NEW • INVESTIGATING • RESOLVED
                    </p>
                </div>
            )}
        </div>
    );
};

const LeadCard = ({
    lead,
    index,
    isExpanded,
    onToggle,
    onNodeClick,
    threatIntel,
    loadingThreatIntel,
    onFetchThreatIntel,
    threatIntelAvailable
}) => {
    const priorityColor = getLeadPriorityColor(lead.priority);
    const priorityIcon = getLeadPriorityIcon(lead.priority);

    // Determine if threat intel indicates blacklisting
    const isBlacklisted = threatIntel?.blacklisted || false;
    const threatConfidence = threatIntel?.confidence || 0;

    return (
        <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: index * 0.05 }}
            className={`px-4 py-3 hover:bg-gray-700/30 transition-colors cursor-pointer ${isBlacklisted ? 'border-l-4 border-red-500' : ''
                }`}
            onClick={onToggle}
        >
            {/* Lead Header */}
            <div className="flex items-start justify-between">
                <div className="flex-1 min-w-0">
                    <div className="flex items-center space-x-2 mb-1">
                        <span className="text-lg">{priorityIcon}</span>
                        <span
                            className="text-xs font-bold uppercase tracking-wider"
                            style={{ color: priorityColor }}
                        >
                            {lead.priority}
                        </span>
                        <span className="text-xs text-gray-500">•</span>
                        <span className="text-xs text-gray-400 font-mono">
                            {lead.type.replace('_', ' ').toUpperCase()}
                        </span>

                        {/* Threat Intel Badge */}
                        {isBlacklisted && (
                            <span className="flex items-center space-x-1 px-1.5 py-0.5 bg-red-500/20 rounded text-xs text-red-400">
                                <ShieldAlert className="w-3 h-3" />
                                <span>FLAGGED</span>
                            </span>
                        )}
                        {threatIntel && !isBlacklisted && (
                            <span className="flex items-center space-x-1 px-1.5 py-0.5 bg-green-500/20 rounded text-xs text-green-400">
                                <Shield className="w-3 h-3" />
                                <span>CLEAN</span>
                            </span>
                        )}
                    </div>
                    <p className="text-sm text-gray-300 leading-relaxed">
                        {lead.description}
                    </p>
                    <div className="mt-2 flex items-center space-x-3 text-xs text-gray-500">
                        <span className="font-mono">{lead.nodeId.substring(0, 12)}...</span>
                        <span>•</span>
                        <span>{new Date(lead.timestamp).toLocaleTimeString()}</span>
                    </div>
                </div>
                <div className="flex items-center space-x-2 ml-3">
                    {/* Threat Intel Lookup Button */}
                    {threatIntelAvailable && !threatIntel && (
                        <button
                            onClick={(e) => {
                                e.stopPropagation();
                                onFetchThreatIntel();
                            }}
                            disabled={loadingThreatIntel}
                            className="p-1.5 hover:bg-purple-500/20 rounded transition-colors"
                            title="Check Threat Intelligence"
                        >
                            {loadingThreatIntel ? (
                                <RefreshCw className="w-4 h-4 text-purple-400 animate-spin" />
                            ) : (
                                <Database className="w-4 h-4 text-purple-400" />
                            )}
                        </button>
                    )}
                    <button
                        onClick={(e) => {
                            e.stopPropagation();
                            onNodeClick();
                        }}
                        className="p-1.5 hover:bg-blue-500/20 rounded transition-colors"
                        title="View Node"
                    >
                        <ExternalLink className="w-4 h-4 text-blue-400" />
                    </button>
                    {isExpanded ? (
                        <ChevronDown className="w-5 h-5 text-gray-400" />
                    ) : (
                        <ChevronRight className="w-5 h-5 text-gray-400" />
                    )}
                </div>
            </div>

            {/* Expanded Evidence */}
            <AnimatePresence>
                {isExpanded && (
                    <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: 'auto', opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        className="mt-3 pt-3 border-t border-gray-700/50"
                    >
                        {/* Threat Intelligence Section */}
                        {threatIntel && (
                            <div className={`mb-3 rounded-lg p-3 ${isBlacklisted
                                    ? 'bg-red-900/30 border border-red-500/30'
                                    : 'bg-green-900/20 border border-green-500/20'
                                }`}>
                                <div className="flex items-center space-x-2 mb-2">
                                    {isBlacklisted ? (
                                        <ShieldAlert className="w-4 h-4 text-red-400" />
                                    ) : (
                                        <Shield className="w-4 h-4 text-green-400" />
                                    )}
                                    <p className="text-xs font-semibold text-white uppercase tracking-wide">
                                        Threat Intelligence Results
                                    </p>
                                </div>

                                <div className="space-y-1 text-xs">
                                    <div className="flex justify-between">
                                        <span className="text-gray-400">Status:</span>
                                        <span className={isBlacklisted ? 'text-red-400 font-bold' : 'text-green-400'}>
                                            {isBlacklisted ? '⚠️ BLACKLISTED' : '✓ CLEAN'}
                                        </span>
                                    </div>
                                    <div className="flex justify-between">
                                        <span className="text-gray-400">Confidence:</span>
                                        <span className={`font-mono ${threatConfidence >= 0.8 ? 'text-red-400' :
                                                threatConfidence >= 0.5 ? 'text-yellow-400' :
                                                    'text-gray-300'
                                            }`}>
                                            {(threatConfidence * 100).toFixed(1)}%
                                        </span>
                                    </div>
                                    <div className="flex justify-between">
                                        <span className="text-gray-400">Risk Level:</span>
                                        <span className={`uppercase font-bold ${threatIntel.risk_level === 'critical' ? 'text-red-400' :
                                                threatIntel.risk_level === 'high' ? 'text-orange-400' :
                                                    threatIntel.risk_level === 'medium' ? 'text-yellow-400' :
                                                        'text-gray-400'
                                            }`}>
                                            {threatIntel.risk_level}
                                        </span>
                                    </div>
                                    {threatIntel.sources && threatIntel.sources.length > 0 && (
                                        <div className="pt-1 mt-1 border-t border-gray-700/50">
                                            <span className="text-gray-400">Flagged by: </span>
                                            <span className="text-red-400 font-mono">
                                                {threatIntel.sources.join(', ')}
                                            </span>
                                        </div>
                                    )}
                                    {threatIntel.illicit_analysis?.primary_activity_type && (
                                        <div className="pt-1 mt-1 border-t border-gray-700/50">
                                            <span className="text-gray-400">Activity Type: </span>
                                            <span className="text-red-400 uppercase font-bold">
                                                {threatIntel.illicit_analysis.primary_activity_type}
                                            </span>
                                        </div>
                                    )}
                                </div>
                            </div>
                        )}

                        {/* Original Evidence Section */}
                        <div className="bg-gray-900/50 rounded-lg p-3">
                            <p className="text-xs font-semibold text-gray-400 mb-2 uppercase tracking-wide">
                                Evidence
                            </p>
                            <div className="space-y-1">
                                {Object.entries(lead.evidence).map(([key, value]) => (
                                    <div key={key} className="flex justify-between text-xs">
                                        <span className="text-gray-500 font-mono">
                                            {key.replace(/([A-Z])/g, ' $1').trim()}:
                                        </span>
                                        <span className="text-gray-300 font-mono">
                                            {typeof value === 'object' ? JSON.stringify(value) : value.toString()}
                                        </span>
                                    </div>
                                ))}
                            </div>
                        </div>

                        {/* Status Badge */}
                        <div className="mt-2 flex items-center space-x-2">
                            <span className="text-xs text-gray-500">Status:</span>
                            <span
                                className={`px-2 py-0.5 rounded text-xs font-medium ${lead.status === 'new'
                                    ? 'bg-blue-500/20 text-blue-400'
                                    : lead.status === 'investigating'
                                        ? 'bg-yellow-500/20 text-yellow-400'
                                        : 'bg-green-500/20 text-green-400'
                                    }`}
                            >
                                {lead.status.toUpperCase()}
                            </span>
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>
        </motion.div>
    );
};

export default LeadsPanel;
