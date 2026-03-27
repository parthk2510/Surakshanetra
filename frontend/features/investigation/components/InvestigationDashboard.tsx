// @ts-nocheck
'use client';
import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
    Activity, FileText, AlertTriangle, BarChart3, Download,
    RefreshCw, Trash2, Eye, EyeOff, Play, Layers, FolderOpen, Camera,
    Maximize2, Minimize2, Shield, Target, Plus, Search, X, ChevronDown,
    ChevronUp, Info, Users, Clock, Flag, Archive, GitCommit, Settings,
    Save, CheckCircle
} from 'lucide-react';
import forensicDataManager from '../../../core/ForensicDataManager';
import { getCommunityColor } from '../../../core/LeidenDetector';
import { useConfig } from '../../../context/ConfigContext';
import { useTheme } from '../../../context/ThemeContext';
import usePermissions from '../../../hooks/usePermissions';
import AdaptiveGraphRenderer from '../../../components/AdaptiveGraphRenderer';
import ProfileSettings from '../../../components/ProfileSettings';
import CaseFileViewer from '../../../components/CaseFileViewer';
import LeadsPanel from '../../../components/LeadsPanel';
import DataCoverageBar from '../../../components/DataCoverageBar';
import EnhancedNodeDetails from '../../../components/EnhancedNodeDetails';
import AlgorithmComparisonTable from '../../../components/AlgorithmComparisonTable';
import TemporalEvolutionPanel from '../../../components/TemporalEvolutionPanel';
import BreadcrumbNav from '../../../components/BreadcrumbNav';
import GraphLegend from '../../../components/GraphLegend';
import AnomalyTimeline from '../../../components/AnomalyTimeline';
import EnhancedLeadCard from '../../../components/EnhancedLeadCard';
import toast from 'react-hot-toast';
import logger from '../../../utils/logger';
import structuredLogger from '../../../utils/structuredLogger';

const InvestigationDashboard = () => {
    const { config, openSettingsPanel } = useConfig();
    const { isDark } = useTheme();
    const { isAdmin } = usePermissions();
    const displayLimit = config?.fetchLimit || 100;

    const [caseFile, setCaseFile] = useState(null);
    const [dataProgress, setDataProgress] = useState(null);
    const [selectedNode, setSelectedNode] = useState(null);
    const [investigating, setInvestigating] = useState(false);
    const [showCaseFile, setShowCaseFile] = useState(false);
    const [activePanel, setActivePanel] = useState('leads');
    const [isGraphFullscreen, setIsGraphFullscreen] = useState(false);
    const [graphHeight, setGraphHeight] = useState(600);

    // Case manager modal state
    const [showCaseManager, setShowCaseManager] = useState(false);
    const [showProfileSettings, setShowProfileSettings] = useState(false);
    const [serverCases, setServerCases] = useState([]);
    const [casesLoading, setCasesLoading] = useState(false);
    const [savingCase, setSavingCase] = useState(false);

    const [multiAddressInput, setMultiAddressInput] = useState('');
    const [addressQueue, setAddressQueue] = useState([]);
    const [processingAddresses, setProcessingAddresses] = useState(false);

    const [maliciousAddresses, setMaliciousAddresses] = useState([]);
    const [threatIntelResults, setThreatIntelResults] = useState(null);
    const [showThreatPanel, setShowThreatPanel] = useState(false);

    const inputRef = useRef(null);
    const graphContainerRef = useRef(null);
    const resizeHandleRef = useRef(null);

    const [algorithmResults, setAlgorithmResults] = useState({
        louvain: null,
        leiden: null,
        labelPropagation: null,
        infomap: null
    });

    const [savedSnapshots, setSavedSnapshots] = useState([]);
    const [highlightedNodes, setHighlightedNodes] = useState([]);

    useEffect(() => {
        const unsubscribe = forensicDataManager.subscribe((updatedCaseFile, updatedProgress) => {
            setCaseFile(updatedCaseFile);
            setDataProgress(updatedProgress);
        });

        setCaseFile(forensicDataManager.getCaseFile());
        setDataProgress(forensicDataManager.getProgress());

        return unsubscribe;
    }, []);

    const handleInvestigate = async (address) => {
        if (!address || !address.trim()) {
            toast.error('Please enter a Bitcoin address');
            return;
        }

        setInvestigating(true);
        structuredLogger.investigation('started', address);
        try {
            await forensicDataManager.performDeepInvestigation(address, {
                fetchNeighbors: true,
                fetchUTXOs: true,
                fetchBlocks: true,
                fetchCharts: true,
                txLimit: 50
            });
            structuredLogger.investigation('completed', address);
        } catch (error) {
            console.error('Investigation failed:', error);
            structuredLogger.error('investigation.failed', error.message, { error });
        } finally {
            setInvestigating(false);
        }
    };

    const handleMultiAddressSubmit = async () => {
        const addresses = multiAddressInput
            .split(/[\n,;]+/)
            .map(a => a.trim())
            .filter(a => a.length > 25 && a.length < 65);

        if (addresses.length === 0) {
            toast.error('No valid addresses found');
            return;
        }

        setAddressQueue(addresses);
        setMultiAddressInput('');
        setProcessingAddresses(true);

        toast.success(`Processing ${addresses.length} addresses...`);

        for (let i = 0; i < addresses.length; i++) {
            const addr = addresses[i];
            toast.loading(`Investigating ${i + 1}/${addresses.length}: ${addr.substring(0, 12)}...`, { id: 'multi-progress' });

            try {
                await forensicDataManager.performDeepInvestigation(addr, {
                    fetchNeighbors: true,
                    fetchUTXOs: true,
                    fetchBlocks: false,
                    fetchCharts: false,
                    txLimit: 30
                });
            } catch (error) {
                console.error(`Failed to investigate ${addr}:`, error);
            }

            setAddressQueue(prev => prev.filter(a => a !== addr));
        }

        toast.success(`Completed investigation of ${addresses.length} addresses`, { id: 'multi-progress' });
        setProcessingAddresses(false);
    };

    const handleThreatScan = async () => {
        if (!caseFile || Object.keys(caseFile.nodes).length === 0) {
            toast.error('No addresses to scan');
            return;
        }

        const addresses = Object.values(caseFile.nodes)
            .filter(n => n.type === 'address')
            .map(n => n.id);

        toast.loading('Running threat intelligence scan...', { id: 'threat-scan' });

        try {
            const response = await fetch('/api/threat-intel/batch', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ addresses: addresses.slice(0, 50) })
            });

            if (!response.ok) throw new Error('Threat scan failed');

            const result = await response.json();

            if (result.success && result.data) {
                // Backend returns {address: result} dict — convert to array for UI
                const dataArray = Object.entries(result.data).map(([addr, info]: [string, any]) => ({
                    address: addr,
                    ...(typeof info === 'object' ? info : {}),
                }));
                const malicious = dataArray.filter(r => r.is_malicious || r.risk_level === 'high' || r.risk_level === 'critical');
                setMaliciousAddresses(malicious.map(m => m.address));
                setThreatIntelResults(dataArray);

                if (malicious.length > 0) {
                    toast.error(`Found ${malicious.length} potentially malicious addresses!`, { id: 'threat-scan' });
                } else {
                    toast.success('No malicious addresses detected', { id: 'threat-scan' });
                }
            }
        } catch (error) {
            console.error('Threat scan error:', error);
            toast.error('Threat intelligence scan failed', { id: 'threat-scan' });
        }
    };

    const handleRunCommunityOnMalicious = async () => {
        if (maliciousAddresses.length === 0) {
            toast.error('No malicious addresses identified. Run threat scan first.');
            return;
        }

        toast.loading('Running community detection on malicious network...', { id: 'community-malicious' });

        try {
            const response = await fetch('/api/louvain', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    nodes: graphData.nodes.map(n => ({ id: n.id, label: n.label || n.id })),
                    edges: graphData.edges.map(e => ({
                        source: typeof e.source === 'object' ? e.source.id : e.source,
                        target: typeof e.target === 'object' ? e.target.id : e.target
                    })),
                    resolution: 1.0
                })
            });

            if (!response.ok) throw new Error('Community detection failed');

            const result = await response.json();

            if (result.success) {
                const maliciousCommunities = new Set();
                maliciousAddresses.forEach(addr => {
                    const communityId = result.data.partition[addr];
                    if (communityId !== undefined) {
                        maliciousCommunities.add(communityId);
                    }
                });

                const nodesInMaliciousCommunities = Object.entries(result.data.partition)
                    .filter(([_, cid]) => maliciousCommunities.has(cid))
                    .map(([nodeId, _]) => nodeId);

                toast.success(
                    `Found ${maliciousCommunities.size} communities containing malicious addresses (${nodesInMaliciousCommunities.length} total nodes)`,
                    { id: 'community-malicious', duration: 8000 }
                );

                setAlgorithmResults(prev => ({
                    ...prev,
                    louvain: {
                        ...result.data,
                        maliciousCommunities: Array.from(maliciousCommunities),
                        nodesInMaliciousCommunities
                    }
                }));
            }
        } catch (error) {
            console.error('Community detection error:', error);
            toast.error('Community detection failed', { id: 'community-malicious' });
        }
    };

    const handleNodeClick = useCallback((nodeData) => {
        if (!nodeData || typeof nodeData !== 'object') {
            setSelectedNode(null);
            return;
        }

        if (!nodeData.id) {
            logger.warn('NodeData missing id property:', nodeData);
            setSelectedNode(nodeData);
            return;
        }

        try {
            const fullNodeData = caseFile?.nodes?.[nodeData.id];
            const isMalicious = maliciousAddresses.includes(nodeData.id);
            const threatData = threatIntelResults?.find(t => t.address === nodeData.id);

            const enrichedNode = {
                ...(fullNodeData || nodeData),
                isMalicious,
                threatIntel: threatData ? {
                    sources: threatData.sources,
                    activityType: threatData.illicit_activity_analysis?.primary_activity_type,
                    indicators: threatData.illicit_activity_analysis?.risk_indicators,
                    confidence: threatData.confidence
                } : null
            };

            setSelectedNode(enrichedNode);
        } catch (error) {
            logger.error('Error handling node click:', error, nodeData);
            setSelectedNode(nodeData);
        }
    }, [caseFile, maliciousAddresses, threatIntelResults]);

    const handleAlgorithmResult = (algorithmKey, result) => {
        setAlgorithmResults(prev => ({
            ...prev,
            [algorithmKey]: result
        }));
    };

    const handleExportCase = () => {
        forensicDataManager.exportCaseFile();
    };

    const fetchServerCases = useCallback(async () => {
        setCasesLoading(true);
        try {
            const response = await fetch('/api/cases');
            if (!response.ok) throw new Error(`Server responded with ${response.status}`);
            const data = await response.json();
            setServerCases(data.cases || []);
        } catch (error) {
            console.error('Fetch cases error:', error);
            toast.error('Could not load case list from server');
        } finally {
            setCasesLoading(false);
        }
    }, []);

    const handleLoadCase = useCallback(() => {
        fetchServerCases();
        setShowCaseManager(true);
    }, [fetchServerCases]);

    const handleLoadCaseFromServer = useCallback(async (filename) => {
        try {
            const detailResponse = await fetch(`/api/cases/${filename}`);
            if (!detailResponse.ok) throw new Error('Could not fetch case file');
            const fullCaseData = await detailResponse.json();
            if (!fullCaseData.nodes || typeof fullCaseData.nodes !== 'object') {
                throw new Error('Invalid case file format');
            }
            if (!Array.isArray(fullCaseData.edges)) fullCaseData.edges = [];
            if (!fullCaseData.metadata) {
                fullCaseData.metadata = {
                    caseId: filename.replace('.json', ''),
                    createdAt: new Date().toISOString(),
                    lastUpdated: new Date().toISOString()
                };
            }
            forensicDataManager.loadCaseFile(fullCaseData);
            setShowCaseManager(false);
            toast.success(`Case loaded: ${fullCaseData.metadata?.caseId || filename}`);
        } catch (error) {
            toast.error(`Load error: ${error.message}`);
        }
    }, []);

    const handleSaveCaseToServer = useCallback(async () => {
        if (!caseFile) { toast.error('No case data to save'); return; }
        setSavingCase(true);
        try {
            const response = await fetch('/api/cases', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ case_data: caseFile })
            });
            const result = await response.json();
            if (!result.success) throw new Error(result.error || 'Save failed');
            toast.success(`Case saved: ${result.caseId}`);
        } catch (error) {
            toast.error(`Save error: ${error.message}`);
        } finally {
            setSavingCase(false);
        }
    }, [caseFile]);

    const handleDeleteCase = useCallback(async (caseId) => {
        if (!window.confirm(`Delete case ${caseId}?`)) return;
        try {
            const response = await fetch(`/api/cases/${caseId}`, { method: 'DELETE' });
            const result = await response.json();
            if (!result.success) throw new Error(result.error || 'Delete failed');
            toast.success(`Case ${caseId} deleted`);
            // Refresh list
            setServerCases(prev => prev.filter(c => c.caseId !== caseId));
        } catch (error) {
            toast.error(`Delete error: ${error.message}`);
        }
    }, []);

    const handleClearCase = () => {
        if (window.confirm('Clear current case?')) {
            forensicDataManager.clearCaseFile();
            setSelectedNode(null);
            setMaliciousAddresses([]);
            setThreatIntelResults(null);
        }
    };

    const handleMarkSuspicious = (address) => {
        const reason = prompt('Enter reason for marking as suspicious:');
        if (reason !== null) {
            forensicDataManager.markAsSuspicious(address, reason);
            toast.success('Address marked as suspicious');
        }
    };

    const handleSaveSnapshot = () => {
        if (!graphData || graphData.nodes.length === 0) {
            toast.error('No graph data to save');
            return;
        }

        const defaultName = `Snapshot-${new Date().toLocaleString('en-US', {
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        }).replace(/, /g, '-').replace(/:/g, '')}`;

        const snapshotName = prompt('Enter snapshot name:', defaultName);
        if (!snapshotName) return;

        const snapshot = {
            id: Date.now(),
            name: snapshotName,
            nodes: graphData.nodes,
            edges: graphData.edges,
            timestamp: new Date().toISOString(),
            meta: graphData.meta,
            caseId: caseFile?.metadata?.caseId
        };

        // Update state
        const newSnapshots = [...savedSnapshots, snapshot];
        setSavedSnapshots(newSnapshots);

        // Persist to localStorage
        try {
            localStorage.setItem('chainbreak_snapshots', JSON.stringify(newSnapshots));
            structuredLogger.userAction('snapshot_saved', snapshotName, {
                nodeCount: graphData.nodes.length,
                edgeCount: graphData.edges.length
            });
            toast.success(`Snapshot "${snapshotName}" saved successfully!`);
        } catch (error) {
            console.error('Failed to persist snapshot:', error);
            toast.error('Snapshot saved to session only (storage full)');
        }
    };

    // Load snapshots from localStorage on mount
    useEffect(() => {
        try {
            const stored = localStorage.getItem('chainbreak_snapshots');
            if (stored) {
                const parsed = JSON.parse(stored);
                if (Array.isArray(parsed)) {
                    setSavedSnapshots(parsed);
                }
            }
        } catch (error) {
            console.warn('Failed to load snapshots:', error);
        }
    }, []);

    const handleNodeHighlight = (nodeIds) => {
        setHighlightedNodes(nodeIds);
        setTimeout(() => setHighlightedNodes([]), 5000);
    };

    const handleResizeStart = useCallback((e) => {
        e.preventDefault();
        const startY = e.clientY;
        const startHeight = graphHeight;

        const handleMouseMove = (e) => {
            const delta = e.clientY - startY;
            const newHeight = Math.max(400, Math.min(window.innerHeight - 200, startHeight + delta));
            setGraphHeight(newHeight);
        };

        const handleMouseUp = () => {
            document.removeEventListener('mousemove', handleMouseMove);
            document.removeEventListener('mouseup', handleMouseUp);
        };

        document.addEventListener('mousemove', handleMouseMove);
        document.addEventListener('mouseup', handleMouseUp);
    }, [graphHeight]);

    const normalizeNodeData = (node) => {
        const utxos = node.utxos || [];
        let balance = node.balance || 0;
        let totalReceived = node.totalReceived || 0;
        let txCount = node.txCount || 0;

        if (balance === 0 && utxos.length > 0) {
            balance = utxos.reduce((sum, utxo) => sum + (utxo.value || 0), 0);
        }

        if (txCount === 0 && utxos.length > 0) {
            txCount = utxos.length;
        }

        if (totalReceived === 0 && utxos.length > 0) {
            totalReceived = balance;
        }

        return {
            ...node,
            balance,
            totalReceived,
            totalSent: node.totalSent || 0,
            txCount
        };
    };

    const graphData = useMemo(() => {
        if (!caseFile) return null;

        const nodesRaw = caseFile?.nodes || {};
        const normalizedNodes = Object.values(nodesRaw).map(normalizeNodeData);

        const totalBalance = normalizedNodes.reduce((sum, n) =>
            n?.type === 'address' ? sum + (n.balance || 0) : sum, 0
        );

        const totalTxCount = normalizedNodes.reduce((sum, n) =>
            n?.type === 'address' ? sum + (n.txCount || 0) : sum, 0
        );

        const totalUtxos = normalizedNodes.reduce((sum, n) =>
            (n?.type === 'address' && n.utxos) ? sum + n.utxos.length : sum, 0
        );

        const nodesToDisplay = normalizedNodes;
        const edgesToDisplay = (caseFile?.edges || []);

        return {
            nodes: nodesToDisplay.map(node => {
                const isMalicious = maliciousAddresses.includes(node.id);
                return {
                    ...node,
                    isMalicious,
                    displayBalance: node?.balance || 0,
                    displayBtc: ((node?.balance || 0) / 100000000).toFixed(8),
                    size: node?.type === 'address'
                        ? Math.max(15, Math.min(50, Math.log10((node?.balance || 0) + 1) * 8 + 15))
                        : 8,
                    color: isMalicious ? '#ef4444' : (node.type === 'transaction' ? '#3b82f6' : undefined)
                };
            }),
            edges: edgesToDisplay.map(edge => ({
                ...edge,
                color: '#64748b',
                size: Math.max(1, Math.min(5, ((edge?.value || 0) / 100000000) * 0.5 + 1))
            })),
            meta: {
                address: caseFile.metadata?.primaryAddress || "Unknown",
                total_nodes: normalizedNodes.length,
                total_edges: (caseFile?.edges || []).length,
                displayed_nodes: nodesToDisplay.length,
                displayed_edges: edgesToDisplay.length,
                display_limit: displayLimit,
                total_balance: totalBalance,
                total_balance_btc: (totalBalance / 100000000).toFixed(8),
                total_tx_count: totalTxCount,
                total_utxos: totalUtxos
            }
        };
    }, [caseFile, displayLimit, maliciousAddresses]);

    const leads = caseFile?.investigativeLeads || [];
    const highPriorityLeads = leads.filter(l => l.priority === 'high' || l.priority === 'critical');

    return (
        <div className="min-h-screen" style={{ background: 'var(--background)' }}>
            {/* Breadcrumb Navigation */}
            <BreadcrumbNav
                caseId={caseFile?.metadata?.caseId}
                currentView="dashboard"
                selectedNode={selectedNode}
                onNavigate={(path) => {
                    // Navigate back to dashboard - clear selection
                    setSelectedNode(null);
                }}
                onClearSelection={() => setSelectedNode(null)}
                onRenameCase={async () => {
                    const newName = prompt('Enter new case name:', caseFile?.metadata?.caseId || 'New Case');
                    if (newName) {
                        try {
                            await forensicDataManager.setCaseName(newName);
                            toast.success(`Case renamed to: ${newName}`);
                        } catch (error) {
                            toast.error('Failed to rename case');
                        }
                    }
                }}
            />

            <header className="backdrop-blur-sm border-b sticky top-0 z-30" style={{ background: 'var(--header-bg)', borderColor: 'var(--border)' }}>
                <div className="max-w-[1920px] mx-auto px-6 py-3">
                    <div className="flex items-center justify-between">
                        {/* Left: Title - simplified since breadcrumb shows case name */}
                        <div className="flex items-center space-x-3">
                            <Activity className="w-6 h-6 text-emerald-500" />
                            <h1 className="text-lg font-semibold" style={{ color: 'var(--text-primary)' }}>Investigation Dashboard</h1>
                        </div>

                        {/* Right: Action Buttons - Consolidated */}
                        <div className="flex items-center space-x-3">
                            {/* Alert badges */}
                            {highPriorityLeads.length > 0 && (
                                <div className="flex items-center space-x-1.5 px-3 py-1.5 bg-amber-500/10 border border-amber-500/30 rounded-lg">
                                    <AlertTriangle className="w-4 h-4 text-amber-400" />
                                    <span className="text-xs font-medium text-amber-400">
                                        {highPriorityLeads.length} High Priority
                                    </span>
                                </div>
                            )}

                            {/* New Scan Button */}
                            <button
                                onClick={handleThreatScan}
                                className="flex items-center space-x-2 px-4 py-2 bg-gradient-to-r from-emerald-600 to-teal-600 text-white rounded-lg hover:from-emerald-500 hover:to-teal-500 transition-all shadow-lg shadow-emerald-500/20"
                            >
                                <RefreshCw className="w-4 h-4" />
                                <span className="text-sm font-medium">Threat Scan </span>
                            </button>

                            {/* Manage Case Dropdown */}
                            <div className="relative group">
                                <button className="flex items-center space-x-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-500 transition-colors">
                                    <span className="text-sm font-medium">Manage Case</span>
                                    <ChevronDown className="w-4 h-4" />
                                </button>
                                <div className="absolute right-0 mt-1 w-48 rounded-lg shadow-xl opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all border" style={{ background: 'var(--surface-2)', borderColor: 'var(--border-2)', zIndex: 35 }}>
                                    <button
                                        onClick={handleExportCase}
                                        className="w-full flex items-center space-x-2 px-4 py-2.5 hover:bg-gray-700/50 hover:text-white transition-colors first:rounded-t-lg"
                                        style={{ color: 'var(--text-secondary)' }}
                                    >
                                        <Download className="w-4 h-4" />
                                        <span className="text-sm">Export</span>
                                    </button>
                                    <button
                                        onClick={handleSaveSnapshot}
                                        disabled={!graphData || graphData.nodes?.length === 0}
                                        className="w-full flex items-center space-x-2 px-4 py-2.5 hover:bg-gray-700/50 hover:text-white transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                                        style={{ color: 'var(--text-secondary)' }}
                                    >
                                        <Camera className="w-4 h-4" />
                                        <span className="text-sm">Snapshot</span>
                                    </button>
                                    <button
                                        onClick={handleLoadCase}
                                        className="w-full flex items-center space-x-2 px-4 py-2.5 hover:bg-gray-700/50 hover:text-white transition-colors"
                                        style={{ color: 'var(--text-secondary)' }}
                                    >
                                        <FolderOpen className="w-4 h-4" />
                                        <span className="text-sm">Load from Server</span>
                                    </button>
                                    <button
                                        onClick={handleSaveCaseToServer}
                                        disabled={!caseFile || savingCase}
                                        className="w-full flex items-center space-x-2 px-4 py-2.5 hover:bg-gray-700/50 hover:text-white transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                                        style={{ color: 'var(--text-secondary)' }}
                                    >
                                        {savingCase ? (
                                            <RefreshCw className="w-4 h-4 animate-spin" />
                                        ) : (
                                            <Save className="w-4 h-4" />
                                        )}
                                        <span className="text-sm">{savingCase ? 'Saving...' : 'Save to Server'}</span>
                                    </button>
                                    <div className="border-t border-theme my-1" />
                                    <button
                                        onClick={handleClearCase}
                                        className="w-full flex items-center space-x-2 px-4 py-2.5 text-red-400 hover:bg-red-500/10 hover:text-red-300 transition-colors last:rounded-b-lg"
                                    >
                                        <Trash2 className="w-4 h-4" />
                                        <span className="text-sm">Clear Case</span>
                                    </button>
                                </div>
                            </div>

                            {isAdmin && (
                                <button
                                    onClick={() => setShowProfileSettings(true)}
                                    className="flex items-center space-x-2 px-3 py-2 bg-red-900/30 border border-red-700/50 text-red-400 rounded-lg hover:bg-red-900/50 hover:text-red-300 transition-all"
                                    title="Admin Panel"
                                >
                                    <Shield className="w-4 h-4" />
                                    <span className="text-sm font-medium">Admin</span>
                                </button>
                            )}

                            {/* Settings Button */}
                            <button
                                onClick={openSettingsPanel}
                                className="flex items-center space-x-2 px-3 py-2 rounded-lg transition-all border"
                                style={{ background: 'var(--surface-2)', borderColor: 'var(--border)', color: 'var(--text-secondary)' }}
                                title="Investigation Settings"
                            >
                                <Settings className="w-4 h-4" />
                            </button>

                            {/* System Status Indicator */}
                            <div className="flex items-center space-x-2 px-3 py-1.5 rounded-lg border" style={{ background: 'var(--surface-2)', borderColor: 'var(--border)' }}>
                                <div className={`w-2 h-2 rounded-full ${investigating ? 'bg-amber-400 animate-pulse' : 'bg-emerald-400'}`} />
                                <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
                                    {investigating ? 'Analyzing...' : 'Ready'}
                                </span>
                            </div>
                        </div>
                    </div>
                </div>
            </header>

            <main className="max-w-[1920px] mx-auto px-6 py-4">
                {dataProgress && (
                    <div className="mb-4">
                        <DataCoverageBar progress={dataProgress} isInvestigating={investigating} />
                    </div>
                )}

                <div className="grid grid-cols-12 gap-4">
                    <div className="col-span-12 lg:col-span-3 space-y-4">
                        <div className="flex rounded-lg p-1" style={{ background: 'var(--surface-2)' }}>
                            <button
                                onClick={() => setActivePanel('leads')}
                                className={`flex-1 flex items-center justify-center space-x-2 px-4 py-2 rounded-md transition-colors ${activePanel === 'leads'
                                    ? 'bg-blue-600 text-white'
                                    : 'text-theme-secondary hover:text-gray-300'
                                    }`}
                            >
                                <AlertTriangle className="w-4 h-4" />
                                <span className="text-sm font-medium">Leads</span>
                                {leads.length > 0 && (
                                    <span className="px-2 py-0.5 bg-red-500/30 rounded-full text-xs">
                                        {leads.length}
                                    </span>
                                )}
                            </button>
                            <button
                                onClick={() => setActivePanel('casefile')}
                                className={`flex-1 flex items-center justify-center space-x-2 px-4 py-2 rounded-md transition-colors ${activePanel === 'casefile'
                                    ? 'bg-blue-600 text-white'
                                    : 'text-theme-secondary hover:text-gray-300'
                                    }`}
                            >
                                <FileText className="w-4 h-4" />
                                <span className="text-sm font-medium">Case</span>
                            </button>
                            <button
                                onClick={() => setActivePanel('threat')}
                                className={`flex-1 flex items-center justify-center space-x-2 px-4 py-2 rounded-md transition-colors ${activePanel === 'threat'
                                    ? 'bg-red-600 text-white'
                                    : 'text-theme-secondary hover:text-gray-300'
                                    }`}
                            >
                                <Shield className="w-4 h-4" />
                                <span className="text-sm font-medium">Threat</span>
                            </button>
                        </div>

                        {activePanel === 'leads' && (
                            <LeadsPanel
                                leads={leads}
                                onNodeSelect={(nodeId) => {
                                    const node = caseFile?.nodes[nodeId];
                                    if (node) setSelectedNode(node);
                                }}
                            />
                        )}

                        {activePanel === 'casefile' && (
                            <CaseFileViewer caseFile={caseFile} />
                        )}

                        {activePanel === 'threat' && (
                            <div className="backdrop-blur-sm rounded-lg border p-4" style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}>
                                <h3 className="text-sm font-semibold mb-3 flex items-center" style={{ color: 'var(--text-primary)' }}>
                                    <Shield className="w-4 h-4 mr-2 text-red-400" />
                                    Threat Intelligence
                                </h3>

                                {maliciousAddresses.length > 0 ? (
                                    <div className="space-y-3">
                                        <div className="p-3 bg-red-500/10 border border-red-500/30 rounded">
                                            <p className="text-sm text-red-400 font-medium">
                                                {maliciousAddresses.length} Malicious Addresses Detected
                                            </p>
                                        </div>

                                        <div className="max-h-60 overflow-y-auto space-y-2">
                                            {maliciousAddresses.map((addr, idx) => (
                                                <div
                                                    key={idx}
                                                    className="p-2 rounded border border-red-500/30 cursor-pointer hover:bg-red-500/10" style={{ background: 'var(--surface-2)' }}
                                                    onClick={() => {
                                                        const node = caseFile?.nodes[addr];
                                                        if (node) handleNodeClick(node);
                                                    }}
                                                >
                                                    <p className="text-xs font-mono text-red-400 truncate">
                                                        {addr}
                                                    </p>
                                                </div>
                                            ))}
                                        </div>

                                        <button
                                            onClick={handleRunCommunityOnMalicious}
                                            className="w-full px-4 py-2 bg-purple-600/20 border border-purple-500/50 text-purple-400 rounded hover:bg-purple-600/30 transition-colors text-sm"
                                        >
                                            Run Community Detection
                                        </button>
                                    </div>
                                ) : (
                                    <div className="text-center py-6 text-sm" style={{ color: 'var(--text-muted)' }}>
                                        <Shield className="w-8 h-8 mx-auto mb-2" style={{ color: 'var(--text-muted)' }} />
                                        <p>No threat intel data yet.</p>
                                        <p className="text-xs mt-1">Run a threat scan to identify malicious addresses.</p>
                                    </div>
                                )}
                            </div>
                        )}

                        {caseFile && (
                            <div className="backdrop-blur-sm rounded-lg border p-4" style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}>
                                <h3 className="text-sm font-semibold mb-3 flex items-center" style={{ color: 'var(--text-primary)' }}>
                                    <BarChart3 className="w-4 h-4 mr-2" />
                                    Stats
                                </h3>
                                <div className="space-y-2 text-sm">
                                    <div className="flex justify-between">
                                        <span style={{ color: 'var(--text-secondary)' }}>Addresses</span>
                                        <span className="font-semibold" style={{ color: 'var(--text-primary)' }}>
                                            {Object.values(caseFile.nodes).filter(n => n.type === 'address').length}
                                        </span>
                                    </div>
                                    <div className="flex justify-between">
                                        <span style={{ color: 'var(--text-secondary)' }}>Transactions</span>
                                        <span className="font-semibold" style={{ color: 'var(--text-primary)' }}>
                                            {graphData?.meta?.total_tx_count || Object.keys(caseFile.transactions).length}
                                        </span>
                                    </div>
                                    <div className="flex justify-between">
                                        <span style={{ color: 'var(--text-secondary)' }}>Communities</span>
                                        <span className="font-semibold" style={{ color: 'var(--text-primary)' }}>
                                            {Object.keys(caseFile.detectedCommunities || {}).length}
                                        </span>
                                    </div>
                                    <div className="flex justify-between">
                                        <span style={{ color: 'var(--text-secondary)' }}>UTXOs</span>
                                        <span className="text-green-400 font-semibold">
                                            {graphData?.meta?.total_utxos || 0}
                                        </span>
                                    </div>
                                    <div className="flex justify-between">
                                        <span style={{ color: 'var(--text-secondary)' }}>Total Value</span>
                                        <span className="text-emerald-400 font-bold">
                                            {graphData?.meta?.total_balance_btc || '0.00000000'} BTC
                                        </span>
                                    </div>
                                </div>
                            </div>
                        )}

                        <TemporalEvolutionPanel
                            currentGraphData={graphData}
                            savedSnapshots={savedSnapshots}
                            onSnapshotSelect={(snapshot) => { }}
                            onNodeHighlight={handleNodeHighlight}
                        />

                        {/* Anomaly Timeline */}
                        <AnomalyTimeline
                            leads={leads}
                            transactions={caseFile?.transactions || {}}
                            onEventClick={(event) => {
                                if (event.nodeId) {
                                    const node = caseFile?.nodes?.[event.nodeId];
                                    if (node) handleNodeClick(node);
                                }
                            }}
                        />
                    </div>

                    <div className="col-span-12 lg:col-span-6 space-y-4">
                        <div className="backdrop-blur-sm rounded-lg border p-4" style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}>
                            <div className="space-y-3">
                                <div className="flex items-center space-x-3">
                                    <input
                                        ref={inputRef}
                                        type="text"
                                        value={multiAddressInput}
                                        onChange={(e) => setMultiAddressInput(e.target.value)}
                                        placeholder="Enter Bitcoin addresses (one per line or comma-separated)"
                                        className="flex-1 px-4 py-3 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                                        style={{ background: 'var(--input-bg)', borderColor: 'var(--border)', color: 'var(--text-primary)' }}
                                        onKeyPress={(e) => {
                                            if (e.key === 'Enter' && multiAddressInput.trim()) {
                                                handleMultiAddressSubmit();
                                            }
                                        }}
                                        disabled={processingAddresses}
                                    />
                                    <button
                                        onClick={handleMultiAddressSubmit}
                                        disabled={processingAddresses || !multiAddressInput.trim()}
                                        className="flex items-center space-x-2 px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                                    >
                                        {processingAddresses ? (
                                            <>
                                                <RefreshCw className="w-5 h-5 animate-spin" />
                                                <span>Processing...</span>
                                            </>
                                        ) : (
                                            <>
                                                <Play className="w-5 h-5" />
                                                <span>Investigate</span>
                                            </>
                                        )}
                                    </button>
                                </div>

                                {addressQueue.length > 0 && (
                                    <div className="flex flex-wrap gap-2">
                                        {addressQueue.map((addr, idx) => (
                                            <span key={idx} className="px-2 py-1 bg-blue-500/20 border border-blue-500/50 rounded text-xs text-blue-400">
                                                {addr.substring(0, 12)}...
                                            </span>
                                        ))}
                                    </div>
                                )}
                            </div>
                        </div>

                        <div
                            ref={graphContainerRef}
                            className={`backdrop-blur-sm rounded-lg border overflow-hidden ${isGraphFullscreen ? 'fixed inset-4' : ''}`}
                            style={isGraphFullscreen ? { zIndex: 48 } : undefined}
                            style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
                        >
                            <div className="px-4 py-3 border-b" style={{ background: 'var(--surface-2)', borderColor: 'var(--border)' }}>
                                <div className="flex items-center justify-between">
                                    <h2 className="text-lg font-semibold flex items-center" style={{ color: 'var(--text-primary)' }}>
                                        <Layers className="w-5 h-5 mr-2" />
                                        Network Graph
                                    </h2>
                                    <div className="flex items-center space-x-3">
                                        {graphData && (
                                            <span className="text-sm" style={{ color: 'var(--text-muted)' }}>
                                                {graphData.nodes.length} nodes • {graphData.edges.length} edges
                                            </span>
                                        )}
                                        <button
                                            onClick={() => setIsGraphFullscreen(!isGraphFullscreen)}
                                            className="p-2 rounded transition-colors hover:bg-gray-600"
                                        >
                                            {isGraphFullscreen ? (
                                                <Minimize2 className="w-4 h-4" style={{ color: 'var(--text-muted)' }} />
                                            ) : (
                                                <Maximize2 className="w-4 h-4" style={{ color: 'var(--text-muted)' }} />
                                            )}
                                        </button>
                                    </div>
                                </div>
                            </div>

                            <div
                                className="p-4 relative"
                                style={{ height: isGraphFullscreen ? 'calc(100% - 56px)' : `${graphHeight}px` }}
                            >
                                {graphData && graphData.nodes.length > 0 ? (
                                    <>
                                        <AdaptiveGraphRenderer
                                            graphData={graphData}
                                            onNodeClick={handleNodeClick}
                                            className="w-full h-full"
                                            onAlgorithmResult={handleAlgorithmResult}
                                            illicitAddresses={maliciousAddresses}
                                        />
                                        {/* Graph Legend Overlay */}
                                        <GraphLegend
                                            communities={caseFile?.detectedCommunities || {}}
                                            maliciousCount={maliciousAddresses.length}
                                            showAnomalies={leads.length > 0}
                                        />
                                    </>
                                ) : (
                                    <div className="flex flex-col items-center justify-center h-full text-center">
                                        <Activity className="w-16 h-16 mb-4" style={{ color: 'var(--text-muted)' }} />
                                        <h3 className="text-lg font-medium mb-2" style={{ color: 'var(--text-secondary)' }}>
                                            No Investigation Active
                                        </h3>
                                        <p className="max-w-md" style={{ color: 'var(--text-muted)' }}>
                                            Enter Bitcoin addresses above to start investigation.
                                        </p>
                                    </div>
                                )}
                            </div>

                            {!isGraphFullscreen && (
                                <div
                                    ref={resizeHandleRef}
                                    onMouseDown={handleResizeStart}
                                    className="h-2 hover:bg-blue-600/50 cursor-ns-resize transition-colors flex items-center justify-center"
                                    style={{ background: 'var(--surface-2)' }}
                                >
                                    <div className="w-12 h-1 rounded" style={{ background: 'var(--border)' }} />
                                </div>
                            )}
                        </div>

                        <div className="mt-4">
                            <AlgorithmComparisonTable results={algorithmResults} />
                        </div>
                    </div>

                    <div className="col-span-12 lg:col-span-3">
                        {selectedNode ? (
                            <EnhancedNodeDetails
                                node={selectedNode}
                                caseFile={caseFile}
                                onClose={() => setSelectedNode(null)}
                                onMarkSuspicious={handleMarkSuspicious}
                                onRunCommunityDetection={(nodeId) => {
                                    toast.loading('Running community detection...', { id: 'node-community' });
                                }}
                            />
                        ) : (
                            <div className="backdrop-blur-sm rounded-lg border p-6 text-center" style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}>
                                <FileText className="w-12 h-12 mx-auto mb-3" style={{ color: 'var(--text-muted)' }} />
                                <h3 className="text-sm font-medium mb-2" style={{ color: 'var(--text-secondary)' }}>
                                    No Node Selected
                                </h3>
                                <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
                                    Click on any node in the graph to view detailed analysis
                                </p>
                            </div>
                        )}
                    </div>
                </div>
            </main>

            {/* Case Manager Modal */}
            <AnimatePresence>
                {showCaseManager && (
                    <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        className="fixed inset-0 flex items-center justify-center bg-black/60 backdrop-blur-sm"
                        style={{ zIndex: 48 }}
                        onClick={(e) => { if (e.target === e.currentTarget) setShowCaseManager(false); }}
                    >
                        <motion.div
                            initial={{ scale: 0.95, opacity: 0 }}
                            animate={{ scale: 1, opacity: 1 }}
                            exit={{ scale: 0.95, opacity: 0 }}
                            className="rounded-xl shadow-2xl w-full max-w-lg mx-4 overflow-hidden border"
                            style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
                        >
                            {/* Header */}
                            <div className="flex items-center justify-between px-5 py-4 border-b" style={{ borderColor: 'var(--border)' }}>
                                <div className="flex items-center space-x-2">
                                    <FolderOpen className="w-5 h-5 text-blue-400" />
                                    <h2 className="text-base font-semibold" style={{ color: 'var(--text-primary)' }}>Server Cases</h2>
                                    {serverCases.length > 0 && (
                                        <span className="px-2 py-0.5 bg-blue-500/20 border border-blue-500/30 rounded-full text-xs text-blue-400">
                                            {serverCases.length}
                                        </span>
                                    )}
                                </div>
                                <button
                                    onClick={() => setShowCaseManager(false)}
                                    className="p-1.5 rounded-lg hover:text-white hover:bg-gray-700 transition-colors"
                                    style={{ color: 'var(--text-muted)' }}
                                >
                                    <X className="w-4 h-4" />
                                </button>
                            </div>

                            {/* Body */}
                            <div className="p-4 max-h-96 overflow-y-auto">
                                {casesLoading ? (
                                    <div className="flex items-center justify-center py-12">
                                        <RefreshCw className="w-6 h-6 text-blue-400 animate-spin mr-3" />
                                        <span className="text-sm" style={{ color: 'var(--text-muted)' }}>Loading cases...</span>
                                    </div>
                                ) : serverCases.length === 0 ? (
                                    <div className="text-center py-12">
                                        <Archive className="w-10 h-10 mx-auto mb-3" style={{ color: 'var(--text-muted)' }} />
                                        <p className="text-sm font-medium" style={{ color: 'var(--text-secondary)' }}>No cases found</p>
                                        <p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>Save a case to the server to see it here.</p>
                                    </div>
                                ) : (
                                    <div className="space-y-2">
                                        {serverCases.map((c) => {
                                            const caseId = c.caseId || c.filename || 'Unknown';
                                            const updated = c.lastUpdated
                                                ? new Date(c.lastUpdated).toLocaleString()
                                                : (c.createdAt ? new Date(c.createdAt).toLocaleString() : '—');
                                            const ownedByMe = c.userId === undefined || isAdmin || true; // backend already filters non-admin to own cases

                                            return (
                                                <div
                                                    key={caseId}
                                                    className="flex items-center justify-between p-3 rounded-lg border hover:border-blue-500/50 transition-colors group"
                                                style={{ background: 'var(--surface-2)', borderColor: 'var(--border)' }}
                                                >
                                                    <div className="flex-1 min-w-0 mr-3">
                                                        <p className="text-sm font-medium truncate" style={{ color: 'var(--text-primary)' }}>{caseId}</p>
                                                        <p className="text-xs mt-0.5" style={{ color: 'var(--text-secondary)' }}>{updated}</p>
                                                        {c.nodeCount !== undefined && (
                                                            <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
                                                                {c.nodeCount} nodes · {c.edgeCount || 0} edges
                                                            </p>
                                                        )}
                                                    </div>
                                                    <div className="flex items-center space-x-2 shrink-0">
                                                        <button
                                                            onClick={() => handleLoadCaseFromServer(caseId)}
                                                            className="flex items-center space-x-1 px-3 py-1.5 bg-blue-600/20 border border-blue-500/40 text-blue-400 rounded-lg hover:bg-blue-600/30 transition-colors text-xs"
                                                        >
                                                            <FolderOpen className="w-3.5 h-3.5" />
                                                            <span>Load</span>
                                                        </button>
                                                        {(isAdmin || ownedByMe) && (
                                                            <button
                                                                onClick={() => handleDeleteCase(caseId)}
                                                                className="flex items-center space-x-1 px-3 py-1.5 bg-red-500/10 border border-red-500/30 text-red-400 rounded-lg hover:bg-red-500/20 transition-colors text-xs"
                                                            >
                                                                <Trash2 className="w-3.5 h-3.5" />
                                                                <span>Delete</span>
                                                            </button>
                                                        )}
                                                    </div>
                                                </div>
                                            );
                                        })}
                                    </div>
                                )}
                            </div>

                            {/* Footer */}
                            <div className="flex items-center justify-between px-5 py-3 border-t" style={{ borderColor: 'var(--border)', background: 'var(--surface-2)' }}>
                                <button
                                    onClick={fetchServerCases}
                                    disabled={casesLoading}
                                    className="flex items-center space-x-1.5 text-xs hover:text-white transition-colors disabled:opacity-50"
                                    style={{ color: 'var(--text-muted)' }}
                                >
                                    <RefreshCw className={`w-3.5 h-3.5 ${casesLoading ? 'animate-spin' : ''}`} />
                                    <span>Refresh</span>
                                </button>
                                <button
                                    onClick={handleSaveCaseToServer}
                                    disabled={!caseFile || savingCase}
                                    className="flex items-center space-x-1.5 px-4 py-2 bg-emerald-600 text-white rounded-lg hover:bg-emerald-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors text-sm"
                                >
                                    {savingCase ? (
                                        <RefreshCw className="w-4 h-4 animate-spin" />
                                    ) : (
                                        <Save className="w-4 h-4" />
                                    )}
                                    <span>{savingCase ? 'Saving...' : 'Save Current Case'}</span>
                                </button>
                            </div>
                        </motion.div>
                    </motion.div>
                )}
            </AnimatePresence>

            <AnimatePresence>
                {showProfileSettings && (
                    <ProfileSettings
                        isOpen={showProfileSettings}
                        onClose={() => setShowProfileSettings(false)}
                        user={null}
                        initialTab="users"
                    />
                )}
            </AnimatePresence>
        </div >
    );
};

export default InvestigationDashboard;
