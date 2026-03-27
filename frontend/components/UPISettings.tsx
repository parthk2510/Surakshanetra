"use client";
import React, { useState, useEffect, useCallback } from 'react';
import { motion } from 'framer-motion';
import { X, Save, RotateCcw, RefreshCw, CheckCircle, Brain, BarChart2, Star, Network, FolderOpen, Clock, User, Database, Download, Trash2, AlertTriangle } from 'lucide-react';
import UPIRecentAnalysisManager from './UPIRecentAnalysisManager';
import usePermissions from '../hooks/usePermissions';
import { useConfig } from '../context/ConfigContext';
import toast from 'react-hot-toast';

const API_BASE = '';

const DEFAULT_UPI_SETTINGS = {
    rules: {
        fanIn: { unique: 8, count: 15, ratio: 2 },
        fanOut: { unique: 8, count: 15, ratio: 2 },
        circular: { minCycleSize: 2 },
        rapidInOut: { maxMinutes: 120, minMatches: 3, minRatio: 0.5 },
        structuring: { threshold: 10000, windowPct: 0.1, minCount: 5, repeatCount: 6, varianceRatio: 0.1 },
        dormantSpike: { dormantDays: 30, burstHours: 24, burstCount: 5 },
        passthrough: { ratioLow: 0.8, ratioHigh: 1.2, maxHoldMinutes: 180, minCount: 3 }
    },
    weights: {
        fanIn: 15,
        fanOut: 15,
        circular: 15,
        rapidInOut: 15,
        structuring: 10,
        dormantSpike: 10,
        passthrough: 20
    },
    limits: {
        maxNodes: 10000,
        maxEdges: 20000,
        maxTxLimit: 1000,
        maxTimelineEvents: 200,
        maxCentralityNodes: 200,
        maxClosenessNodes: 500,
        maxBatchSize: 100
    }
};

const _getUPISettingsKey = () => {
    try {
        const userRaw = localStorage.getItem('chainbreak_user');
        const user = userRaw ? JSON.parse(userRaw) : null;
        return user && user.id ? `upi_detection_settings_${user.id}` : 'upi_detection_settings';
    } catch {
        return 'upi_detection_settings';
    }
};

const RGCNToggle = ({ label, value, onChange, icon: Icon, description }: { label: string; value: boolean; onChange: (v: boolean) => void; icon?: React.ComponentType<{ className?: string }>; description?: string }) => (
    <div className="mb-4 p-3 bg-gray-700/30 rounded-lg border border-gray-600/50">
        <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
                {Icon && <Icon className="w-4 h-4 text-gray-400" />}
                <span className="text-sm font-medium text-gray-300">{label}</span>
            </div>
            <button
                onClick={() => onChange(!value)}
                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors duration-200 focus:outline-none ${value ? 'bg-blue-600' : 'bg-gray-600'}`}
            >
                <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform duration-200 ${value ? 'translate-x-6' : 'translate-x-1'}`} />
            </button>
        </div>
        {description && <p className="text-xs text-gray-500 mt-2 ml-7">{description}</p>}
    </div>
);

const RGCNSlider = ({ label, value, onChange, min, max, step, description }: { label: string; value: number; onChange: (v: number) => void; min: number; max: number; step: number; description?: string }) => (
    <div className="mb-4">
        <div className="flex items-center justify-between mb-1">
            <span className="text-sm text-gray-400">{label}</span>
            <span className="text-xs font-mono text-blue-400">{value}</span>
        </div>
        <input
            type="range" min={min} max={max} step={step} value={value}
            onChange={(e) => onChange(Number(e.target.value))}
            className="w-full h-2 bg-gray-600 rounded-lg appearance-none cursor-pointer"
            style={{ background: `linear-gradient(to right, #3b82f6 0%, #3b82f6 ${((value - min) / (max - min)) * 100}%, #4b5563 ${((value - min) / (max - min)) * 100}%, #4b5563 100%)` }}
        />
        {description && <p className="text-xs text-gray-500 mt-1">{description}</p>}
    </div>
);

const CasesTab = ({ onLoadCase }: { onLoadCase?: (data: any, name: string) => void }) => {
    const [cases, setCases] = useState<any[]>([]);
    const [loading, setLoading] = useState(false);

    const csrf = () => document.cookie.match(/(^|;)\s*csrf_access_token\s*=\s*([^;]+)/)?.[2] || '';

    const loadCases = useCallback(async () => {
        setLoading(true);
        try {
            const r = await fetch('/api/upi-cases', { credentials: 'include', headers: { 'X-CSRF-TOKEN': csrf() } });
            if (!r.ok) throw new Error();
            const d = await r.json();
            setCases(d.cases || []);
        } catch {
            toast.error('Failed to load cases');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { loadCases(); }, [loadCases]);

    const handleLoad = async (fileName: string) => {
        try {
            const r = await fetch(`/api/upi-cases/${encodeURIComponent(fileName.replace('.json', ''))}`, { credentials: 'include' });
            if (!r.ok) throw new Error('Load failed');
            const d = await r.json();
            onLoadCase?.(d, fileName);
            toast.success(`Loaded: ${fileName}`);
        } catch {
            toast.error('Failed to load case');
        }
    };

    const handleDelete = async (fileName: string, e: React.MouseEvent) => {
        e.stopPropagation();
        if (!confirm(`Delete case "${fileName}"?`)) return;
        try {
            const r = await fetch(`/api/upi-cases/${encodeURIComponent(fileName.replace('.json', ''))}`, {
                method: 'DELETE', credentials: 'include', headers: { 'X-CSRF-TOKEN': csrf() }
            });
            if (!r.ok) throw new Error();
            toast.success('Case deleted');
            setCases(prev => prev.filter(c => c.fileName !== fileName));
        } catch {
            toast.error('Delete failed');
        }
    };

    const handleDownload = async (c: any, e: React.MouseEvent) => {
        e.stopPropagation();
        try {
            const r = await fetch(`/api/upi-cases/${encodeURIComponent(c.caseId)}`, { credentials: 'include' });
            const d = await r.json();
            const blob = new Blob([JSON.stringify(d, null, 2)], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url; a.download = c.fileName; a.click();
            URL.revokeObjectURL(url);
        } catch { toast.error('Download failed'); }
    };

    const riskBadge = (band: string) => {
        const m: Record<string, string> = {
            critical: 'text-red-400 bg-red-900/20 border-red-500/30',
            high: 'text-orange-400 bg-orange-900/20 border-orange-500/30',
            medium: 'text-yellow-400 bg-yellow-900/20 border-yellow-500/30',
            low: 'text-green-400 bg-green-900/20 border-green-500/30',
        };
        return m[band] || 'text-gray-400 bg-gray-900/20 border-gray-500/30';
    };

    const fmt = (bytes: number) => bytes < 1048576 ? `${(bytes / 1024).toFixed(1)} KB` : `${(bytes / 1048576).toFixed(1)} MB`;
    const fmtDate = (ts: any) => {
        if (!ts) return 'Unknown';
        try { return new Date(typeof ts === 'number' ? ts * 1000 : ts).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }); } catch { return 'Unknown'; }
    };

    return (
        <div className="space-y-3">
            <div className="flex items-center justify-between mb-2">
                <span className="text-xs text-gray-400">{cases.length} saved analysis files</span>
                <button onClick={loadCases} disabled={loading} className="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-200">
                    <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} />
                    Refresh
                </button>
            </div>

            {cases.length === 0 && !loading && (
                <div className="text-center py-10 border border-dashed border-gray-700 rounded-lg">
                    <FolderOpen className="w-10 h-10 text-gray-600 mx-auto mb-2" />
                    <p className="text-gray-500 text-sm">No saved UPI analysis files</p>
                    <p className="text-gray-600 text-xs mt-1">Run an analysis and save it to see it here</p>
                </div>
            )}

            <div className="space-y-2 max-h-[420px] overflow-y-auto pr-1">
                {cases.map(c => (
                    <div
                        key={c.fileName}
                        onClick={() => handleLoad(c.fileName)}
                        className="p-3 bg-gray-700/30 border border-gray-600/40 rounded-lg hover:bg-gray-700/60 hover:border-gray-500 transition-all cursor-pointer group"
                    >
                        <div className="flex items-start justify-between gap-2">
                            <div className="flex-1 min-w-0">
                                <p className="text-sm font-medium text-gray-200 truncate mb-1.5">{c.caseId || c.fileName}</p>
                                <div className="flex flex-wrap items-center gap-2 mb-2">
                                    <span className={`text-[10px] px-1.5 py-0.5 rounded border ${riskBadge(c.riskBand)}`}>
                                        {c.riskBand || 'unknown'} · {c.riskScore || 0}
                                    </span>
                                    <span className="text-[10px] text-gray-500 flex items-center gap-1">
                                        <Clock className="w-2.5 h-2.5" />{fmtDate(c.createdAt || c.timestamp)}
                                    </span>
                                    <span className="text-[10px] text-gray-500 flex items-center gap-1">
                                        <User className="w-2.5 h-2.5" />{c.createdBy || 'unknown'}
                                    </span>
                                </div>
                                <div className="grid grid-cols-3 gap-2 text-[10px] text-gray-400">
                                    <div className="flex items-center gap-1"><Database className="w-2.5 h-2.5" />{c.totalAccounts ?? '—'} accts</div>
                                    <div>{c.totalTransactions ?? '—'} txns</div>
                                    <div>{c.highRiskCount ? `${c.highRiskCount} high-risk` : fmt(c.fileSize || 0)}</div>
                                </div>
                            </div>
                            <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
                                <button onClick={e => handleDownload(c, e)} className="p-1 rounded hover:bg-gray-600" title="Download">
                                    <Download className="w-3 h-3 text-gray-400" />
                                </button>
                                <button onClick={e => handleDelete(c.fileName, e)} className="p-1 rounded hover:bg-red-900/30" title="Delete">
                                    <Trash2 className="w-3 h-3 text-red-400" />
                                </button>
                            </div>
                        </div>
                    </div>
                ))}
            </div>

            <div className="p-3 bg-blue-900/20 border border-blue-500/30 rounded-lg">
                <div className="flex items-start gap-2">
                    <AlertTriangle className="w-3.5 h-3.5 text-blue-400 mt-0.5 shrink-0" />
                    <p className="text-xs text-blue-300">Case files store complete UPI analysis data including graph structure, risk scores, community detection results, and forensic insights. Click a case to reload it.</p>
                </div>
            </div>
        </div>
    );
};

const RGCNTab = () => {
    const { config, setConfig } = useConfig();

    return (
        <div className="space-y-4">
            <RGCNToggle label="Enable RGCN Risk Scoring" value={config.enableRGCN} onChange={(v) => setConfig('enableRGCN', v)} icon={Brain} description="Use Relational GCN model for fraud probability scoring" />
            <RGCNToggle label="Enable Decision Engine" value={config.enableDecisionEngine} onChange={(v) => setConfig('enableDecisionEngine', v)} icon={BarChart2} description="Combine RGCN + community detection + heuristics into one verdict" />
            <RGCNToggle label="Show Confidence Score" value={config.showConfidenceScore} onChange={(v) => setConfig('showConfidenceScore', v)} icon={Star} description="Display ML model confidence alongside risk scores" />

            {config.enableDecisionEngine && (
                <div className="mt-2 p-3 bg-gray-700/30 rounded-lg border border-gray-600/50 space-y-3">
                    <p className="text-xs font-semibold text-gray-400">Engine Weights (must sum ≤ 1.0)</p>
                    <RGCNSlider label="RGCN Weight" value={config.rgcnWeight} onChange={(v) => setConfig('rgcnWeight', v)} min={0} max={1} step={0.05} description="Weight of RGCN fraud probability in final score" />
                    <RGCNSlider label="Community Weight" value={config.communityWeight} onChange={(v) => setConfig('communityWeight', v)} min={0} max={1} step={0.05} description="Weight of community-level risk in final score" />
                    <RGCNSlider label="Traditional Weight" value={config.traditionalWeight} onChange={(v) => setConfig('traditionalWeight', v)} min={0} max={1} step={0.05} description="Weight of heuristic risk signals in final score" />
                    <div className="p-2 bg-blue-500/10 border border-blue-500/20 rounded text-xs text-blue-400">
                        Total: {Math.round((config.rgcnWeight + config.communityWeight + config.traditionalWeight) * 100)}%
                        {(config.rgcnWeight + config.communityWeight + config.traditionalWeight) > 1.01 && (
                            <span className="text-yellow-400 ml-2">⚠ Weights normalised automatically</span>
                        )}
                    </div>
                </div>
            )}

            <div className="p-3 bg-gray-700/30 rounded-lg border border-gray-600/50">
                <p className="text-xs font-semibold text-gray-400 mb-2">Node Size Based On</p>
                <div className="flex gap-2">
                    {(['volume', 'risk'] as const).map(metric => (
                        <button
                            key={metric}
                            onClick={() => setConfig('nodeSizeMetric', metric)}
                            className={`flex-1 py-2 rounded-lg text-xs font-medium border transition-all ${config.nodeSizeMetric === metric ? 'border-blue-500 bg-blue-500/15 text-blue-300' : 'border-gray-600 bg-gray-700/50 text-gray-400 hover:border-gray-500'}`}
                        >
                            {metric === 'volume' ? 'Tx Volume' : 'Risk Score'}
                        </button>
                    ))}
                </div>
            </div>

            <RGCNToggle label="Edge Bundling" value={config.enableEdgeBundling} onChange={(v) => setConfig('enableEdgeBundling', v)} icon={Network} description="Curve edges to reduce visual clutter in the graph" />
            <RGCNToggle label="Show Connected Devices" value={config.showUPIDevices} onChange={(v) => setConfig('showUPIDevices', v)} icon={Network} description="Render device-infrastructure nodes and their edges in the UPI transaction graph" />
        </div>
    );
};

const UPISettings = ({ isOpen, onClose, onLoadCase = undefined, currentAnalysis = undefined }: { isOpen: boolean; onClose: () => void; onLoadCase?: (data: any, name: string) => void; currentAnalysis?: any }) => {
    const { isAdmin } = usePermissions();
    const [settings, setSettings] = useState(DEFAULT_UPI_SETTINGS);
    const [activeTab, setActiveTab] = useState('rules');
    const [loadingFromBackend, setLoadingFromBackend] = useState(false);
    const [saveStatus, setSaveStatus] = useState(null); // null | 'saved' | 'error'

    // Load settings: backend first, localStorage fallback
    useEffect(() => {
        if (!isOpen) return;
        loadSettings();
    }, [isOpen]);

    const loadSettings = async () => {
        setLoadingFromBackend(true);
        try {
            const res = await fetch(`${API_BASE}/api/upi/settings`, {
                credentials: 'include',
                headers: {
                    'X-CSRF-TOKEN': document.cookie.match(/(^|;)\s*csrf_access_token\s*=\s*([^;]+)/)?.[2] || ''
                }
            });
            if (res.ok) {
                const json = await res.json();
                if (json.success && json.data) {
                    // Merge backend defaults with any local overrides
                    const local = _loadLocal();
                    const merged = _deepMerge(json.data, local);
                    setSettings(merged);
                    console.log('[UPI_SETTINGS] Loaded from backend, merged with local overrides');
                    return;
                }
            }
        } catch {
            // Backend not reachable — fall back to localStorage
        } finally {
            setLoadingFromBackend(false);
        }
        // Fallback: localStorage
        const local = _loadLocal();
        setSettings(local);
        console.log('[UPI_SETTINGS] Loaded from localStorage (backend unavailable)');
    };

    const _loadLocal = () => {
        try {
            const saved = localStorage.getItem(_getUPISettingsKey());
            return saved ? JSON.parse(saved) : DEFAULT_UPI_SETTINGS;
        } catch {
            return DEFAULT_UPI_SETTINGS;
        }
    };

    /** Deep-merge: target provides base, source overrides leaf values */
    const _deepMerge = (target, source) => {
        if (!source || typeof source !== 'object') return target;
        const out = { ...target };
        for (const key of Object.keys(source)) {
            if (source[key] && typeof source[key] === 'object' && !Array.isArray(source[key])) {
                out[key] = _deepMerge(target[key] || {}, source[key]);
            } else {
                out[key] = source[key];
            }
        }
        return out;
    };

    const saveSettings = () => {
        try {
            localStorage.setItem(_getUPISettingsKey(), JSON.stringify(settings));
            setSaveStatus('saved');
            setTimeout(() => setSaveStatus(null), 2000);
            window.dispatchEvent(new CustomEvent('upi-settings-changed', { detail: settings }));
        } catch {
            setSaveStatus('error');
            setTimeout(() => setSaveStatus(null), 2000);
        }
    };

    const resetToDefaults = () => {
        if (window.confirm('Reset all settings to defaults?')) {
            setSettings(DEFAULT_UPI_SETTINGS);
            localStorage.removeItem(_getUPISettingsKey());
        }
    };

    const updateRule = (ruleName, key, value) => {
        setSettings(prev => ({
            ...prev,
            rules: {
                ...prev.rules,
                [ruleName]: {
                    ...prev.rules[ruleName],
                    [key]: parseFloat(value) || 0
                }
            }
        }));
    };

    const updateWeight = (weightName, value) => {
        setSettings(prev => ({
            ...prev,
            weights: {
                ...prev.weights,
                [weightName]: parseFloat(value) || 0
            }
        }));
    };

    const updateLimit = (limitName, value) => {
        setSettings(prev => ({
            ...prev,
            limits: {
                ...prev.limits,
                [limitName]: parseInt(value) || 0
            }
        }));
    };

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <motion.div
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.95 }}
                className="bg-gray-800 rounded-xl border border-gray-700 max-w-4xl w-full max-h-[90vh] overflow-hidden"
            >
                <div className="flex items-center justify-between p-6 border-b border-gray-700">
                    <div className="flex items-center gap-3">
                        <h2 className="text-2xl font-bold text-white">UPI Mule Detection Settings</h2>
                        {loadingFromBackend && (
                            <RefreshCw size={14} className="text-blue-400 animate-spin" />
                        )}
                    </div>
                    <button onClick={onClose} className="p-2 rounded-lg hover:bg-gray-700 transition-colors">
                        <X className="w-5 h-5 text-gray-400" />
                    </button>
                </div>

                <div className="flex border-b border-gray-700 overflow-x-auto">
                    {['rules', 'weights', 'limits', 'rgcn', 'cases'].map((tab) => (
                        <button
                            key={tab}
                            onClick={() => setActiveTab(tab)}
                            className={`px-5 py-3 font-medium text-sm transition-colors whitespace-nowrap ${activeTab === tab
                                ? 'text-blue-400 border-b-2 border-blue-400'
                                : 'text-gray-400 hover:text-gray-300'
                                }`}
                        >
                            {tab === 'rgcn' ? 'RGCN' : tab.charAt(0).toUpperCase() + tab.slice(1)}
                        </button>
                    ))}
                </div>

                <div className="p-6 overflow-y-auto max-h-[calc(90vh-200px)]">
                    {activeTab === 'rules' && (
                        <div className="space-y-6">
                            {Object.keys(DEFAULT_UPI_SETTINGS.rules)
                              .filter(ruleName => {
                                const ruleConfig = (settings.rules || {})[ruleName];
                                return (
                                  ruleConfig !== null &&
                                  ruleConfig !== undefined &&
                                  typeof ruleConfig === 'object' &&
                                  !Array.isArray(ruleConfig) &&
                                  Object.keys(ruleConfig).length > 0 &&
                                  Object.values(ruleConfig).every(v => typeof v === 'number')
                                );
                              })
                              .map(ruleName => {
                                const ruleConfig = (settings.rules || {})[ruleName];
                                const seenKeys = new Set<string>();
                                return (
                                  <div key={ruleName} className="bg-gray-700/30 rounded-lg p-4">
                                    <h3 className="text-white font-semibold mb-3 capitalize">
                                        {ruleName.replace(/([A-Z])/g, ' $1').trim()}
                                    </h3>
                                    <div className="grid grid-cols-2 gap-4">
                                        {Object.entries(ruleConfig || {})
                                          .filter(([key]) => {
                                            if (seenKeys.has(key)) return false;
                                            seenKeys.add(key);
                                            return true;
                                          })
                                          .map(([key, value]) => (
                                            <div key={key}>
                                                <label className="block text-sm text-gray-400 mb-1 capitalize">
                                                    {key.replace(/([A-Z])/g, ' $1').trim()}
                                                </label>
                                                <input
                                                    type="number"
                                                    value={value as number}
                                                    onChange={(e) => updateRule(ruleName, key, e.target.value)}
                                                    className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                                                />
                                            </div>
                                        ))}
                                    </div>
                                  </div>
                                );
                              })}
                        </div>
                    )}

                    {activeTab === 'weights' && (
                        <div className="grid grid-cols-2 gap-4">
                            {Object.keys(DEFAULT_UPI_SETTINGS.weights)
                              .filter((weightName, idx, arr) => arr.indexOf(weightName) === idx)
                              .map(weightName => {
                                const value = (settings.weights || {})[weightName] ?? DEFAULT_UPI_SETTINGS.weights[weightName];
                                return (
                                  <div key={weightName}>
                                    <label className="block text-sm text-gray-400 mb-1 capitalize">
                                        {weightName.replace(/([A-Z])/g, ' $1').trim()}
                                    </label>
                                    <input
                                        type="number"
                                        value={value}
                                        onChange={(e) => updateWeight(weightName, e.target.value)}
                                        className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                                        min="0"
                                        max="100"
                                    />
                                  </div>
                                );
                              })}
                        </div>
                    )}

                    {activeTab === 'limits' && (
                        <div className="grid grid-cols-2 gap-4">
                            {Object.keys(DEFAULT_UPI_SETTINGS.limits)
                              .filter((limitName, idx, arr) => arr.indexOf(limitName) === idx)
                              .map(limitName => {
                                const value = (settings.limits || {})[limitName] ?? DEFAULT_UPI_SETTINGS.limits[limitName];
                                return (
                                  <div key={limitName}>
                                    <label className="block text-sm text-gray-400 mb-1 capitalize">
                                        {limitName.replace(/([A-Z])/g, ' $1').trim()}
                                    </label>
                                    <input
                                        type="number"
                                        value={value}
                                        onChange={(e) => updateLimit(limitName, e.target.value)}
                                        className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                                        min="1"
                                    />
                                  </div>
                                );
                              })}
                        </div>
                    )}

                    {activeTab === 'rgcn' && <RGCNTab />}
                    {activeTab === 'cases' && (
                        <UPIRecentAnalysisManager
                            currentAnalysis={currentAnalysis}
                            onAnalysisSelect={onLoadCase}
                            onAnalysisSave={(fileName) => { /* saved */ }}
                        />
                    )}
                </div>

                {activeTab !== 'rgcn' && activeTab !== 'cases' && (
                <div className="flex items-center justify-between p-6 border-t border-gray-700">
                    <div className="flex items-center gap-3">
                        <button
                            onClick={resetToDefaults}
                            className="flex items-center space-x-2 px-4 py-2 bg-gray-700 text-white rounded-lg hover:bg-gray-600 transition-colors"
                        >
                            <RotateCcw className="w-4 h-4" />
                            <span>Reset to Defaults</span>
                        </button>
                        <button
                            onClick={loadSettings}
                            disabled={loadingFromBackend}
                            className="flex items-center space-x-2 px-4 py-2 bg-gray-700 text-gray-300 rounded-lg hover:bg-gray-600 transition-colors disabled:opacity-50"
                        >
                            <RefreshCw className={`w-4 h-4 ${loadingFromBackend ? 'animate-spin' : ''}`} />
                            <span>Reload from Backend</span>
                        </button>
                    </div>
                    <div className="flex items-center gap-3">
                        {saveStatus === 'saved' && (
                            <span className="flex items-center gap-1 text-green-400 text-sm">
                                <CheckCircle size={14} /> Saved
                            </span>
                        )}
                        {saveStatus === 'error' && (
                            <span className="text-red-400 text-sm">Save failed</span>
                        )}
                        <button
                            onClick={saveSettings}
                            className="flex items-center space-x-2 px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
                        >
                            <Save className="w-4 h-4" />
                            <span>Save Settings</span>
                        </button>
                    </div>
                </div>
                )}
            </motion.div>
        </div>
    );
};

export default UPISettings;

export const loadUPISettings = () => {
    try {
        const saved = localStorage.getItem(_getUPISettingsKey());
        return saved ? JSON.parse(saved) : DEFAULT_UPI_SETTINGS;
    } catch {
        return DEFAULT_UPI_SETTINGS;
    }
};
