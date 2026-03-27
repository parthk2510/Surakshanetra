"use client";
// frontend/src/components/SettingsPanel.js
// ============================================================================
// SETTINGS PANEL - Sliding Side Panel for Investigation Parameters
// ============================================================================
import React, { useCallback, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
    Settings, X, Sliders, Search, Zap, Eye, EyeOff,
    RotateCcw, ChevronRight, Activity, Shield, Database,
    Layers, Clock, Bug, Terminal, Cpu, Monitor, Brain, BarChart2
} from 'lucide-react';
import { useConfig, ANALYSIS_MODES, GRAPH_RENDERER_MODES } from '../context/ConfigContext';
import { Z } from '../styles/z-layers';
import LogViewer from './LogViewer';

/**
 * Slider Component - Reusable range slider with labels
 */
const ConfigSlider = ({ label, value, onChange, min, max, step = 1, unit = '', description }) => {
    return (
        <div className="mb-6">
            <div className="flex items-center justify-between mb-2">
                <label className="text-sm font-medium text-gray-300">{label}</label>
                <span className="text-sm font-mono text-blue-400">
                    {value}{unit}
                </span>
            </div>
            <input
                type="range"
                min={min}
                max={max}
                step={step}
                value={value}
                onChange={(e) => onChange(Number(e.target.value))}
                className="w-full h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer slider-thumb"
                style={{
                    background: `linear-gradient(to right, #3b82f6 0%, #3b82f6 ${((value - min) / (max - min)) * 100}%, #374151 ${((value - min) / (max - min)) * 100}%, #374151 100%)`
                }}
            />
            <div className="flex justify-between mt-1">
                <span className="text-xs text-gray-500">{min}{unit}</span>
                <span className="text-xs text-gray-500">{max}{unit}</span>
            </div>
            {description && (
                <p className="text-xs text-gray-500 mt-1">{description}</p>
            )}
        </div>
    );
};

/**
 * Toggle Component - Reusable toggle switch
 */
const ConfigToggle = ({ label, value, onChange, description, icon: Icon }) => {
    return (
        <div className="mb-4 p-3 bg-gray-800/30 rounded-lg border border-gray-700/50">
            <div className="flex items-center justify-between">
                <div className="flex items-center space-x-3">
                    {Icon && <Icon className="w-4 h-4 text-gray-400" />}
                    <span className="text-sm font-medium text-gray-300">{label}</span>
                </div>
                <button
                    onClick={() => onChange(!value)}
                    className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 focus:ring-offset-gray-900 ${value ? 'bg-blue-600' : 'bg-gray-600'
                        }`}
                >
                    <span
                        className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform duration-200 ${value ? 'translate-x-6' : 'translate-x-1'
                            }`}
                    />
                </button>
            </div>
            {description && (
                <p className="text-xs text-gray-500 mt-2 ml-7">{description}</p>
            )}
        </div>
    );
};

/**
 * Mode Selector Component - Radio-style mode selection
 */
const ModeSelector = ({ value, onChange }) => {
    const modes = [
        {
            id: ANALYSIS_MODES.LITE_EXPLORER,
            name: 'Lite Explorer',
            description: 'Fast exploration with 50 tx limit',
            icon: Zap,
            color: 'green'
        },
        {
            id: ANALYSIS_MODES.FORENSIC_DEEP_DIVE,
            name: 'Forensic Deep Dive',
            description: 'Full investigation up to 2000 txs',
            icon: Shield,
            color: 'purple'
        }
    ];

    return (
        <div className="mb-6">
            <label className="text-sm font-medium text-gray-300 mb-3 block">Analysis Mode</label>
            <div className="space-y-2">
                {modes.map((mode) => {
                    const isSelected = value === mode.id;
                    const Icon = mode.icon;
                    return (
                        <button
                            key={mode.id}
                            onClick={() => onChange(mode.id)}
                            className={`w-full p-4 rounded-lg border-2 transition-all duration-200 text-left ${isSelected
                                ? mode.color === 'green'
                                    ? 'border-green-500 bg-green-500/10'
                                    : 'border-purple-500 bg-purple-500/10'
                                : 'border-gray-700 bg-gray-800/50 hover:border-gray-600'
                                }`}
                        >
                            <div className="flex items-center space-x-3">
                                <div className={`p-2 rounded-lg ${isSelected
                                    ? mode.color === 'green'
                                        ? 'bg-green-500/20'
                                        : 'bg-purple-500/20'
                                    : 'bg-gray-700'
                                    }`}>
                                    <Icon className={`w-5 h-5 ${isSelected
                                        ? mode.color === 'green'
                                            ? 'text-green-400'
                                            : 'text-purple-400'
                                        : 'text-gray-400'
                                        }`} />
                                </div>
                                <div className="flex-1">
                                    <div className={`font-medium ${isSelected ? 'text-white' : 'text-gray-300'
                                        }`}>
                                        {mode.name}
                                    </div>
                                    <div className="text-xs text-gray-500">{mode.description}</div>
                                </div>
                                {isSelected && (
                                    <div className={`w-2 h-2 rounded-full ${mode.color === 'green' ? 'bg-green-500' : 'bg-purple-500'
                                        }`} />
                                )}
                            </div>
                        </button>
                    );
                })}
            </div>
        </div>
    );
};

/**
 * Graph Renderer Selector - Choose between D3.js (SVG) and Sigma.js (WebGL)
 */
const GraphRendererSelector = ({ value, onChange, autoSelect, onAutoSelectChange, threshold, onThresholdChange }) => {
    const renderers = [
        {
            id: GRAPH_RENDERER_MODES.D3_SVG,
            name: 'D3.js (SVG)',
            description: 'Best for < 1,000 nodes. CPU-based rendering.',
            icon: Monitor,
            color: 'blue',
            recommended: 'Small graphs'
        },
        {
            id: GRAPH_RENDERER_MODES.WEBGL_SIGMA,
            name: 'Sigma.js (WebGL)',
            description: 'GPU-accelerated. Best for 1,000+ nodes.',
            icon: Cpu,
            color: 'green',
            recommended: 'Large graphs'
        }
    ];

    return (
        <div className="mb-6">
            <label className="text-sm font-medium text-gray-300 mb-3 block">Graph Renderer</label>

            {/* Auto-select toggle */}
            <div className="mb-4 p-3 bg-gray-800/30 rounded-lg border border-gray-700/50">
                <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-3">
                        <Zap className="w-4 h-4 text-yellow-400" />
                        <span className="text-sm font-medium text-gray-300">Auto-select based on graph size</span>
                    </div>
                    <button
                        onClick={() => onAutoSelectChange(!autoSelect)}
                        className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-yellow-500 focus:ring-offset-2 focus:ring-offset-gray-900 ${autoSelect ? 'bg-yellow-600' : 'bg-gray-600'
                            }`}
                    >
                        <span
                            className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform duration-200 ${autoSelect ? 'translate-x-6' : 'translate-x-1'
                                }`}
                        />
                    </button>
                </div>
                {autoSelect && (
                    <div className="mt-3">
                        <div className="flex items-center justify-between mb-1">
                            <span className="text-xs text-gray-500">WebGL threshold</span>
                            <span className="text-xs font-mono text-yellow-400">{threshold} nodes</span>
                        </div>
                        <input
                            type="range"
                            min={100}
                            max={2000}
                            step={100}
                            value={threshold}
                            onChange={(e) => onThresholdChange(Number(e.target.value))}
                            className="w-full h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer"
                            style={{
                                background: `linear-gradient(to right, #eab308 0%, #eab308 ${((threshold - 100) / 1900) * 100}%, #374151 ${((threshold - 100) / 1900) * 100}%, #374151 100%)`
                            }}
                        />
                        <p className="text-xs text-gray-500 mt-1">
                            Switch to WebGL when graph exceeds this size
                        </p>
                    </div>
                )}
            </div>

            {/* Renderer options */}
            <div className={`space-y-2 ${autoSelect ? 'opacity-50 pointer-events-none' : ''}`}>
                {renderers.map((renderer) => {
                    const isSelected = value === renderer.id;
                    const Icon = renderer.icon;
                    return (
                        <button
                            key={renderer.id}
                            onClick={() => onChange(renderer.id)}
                            disabled={autoSelect}
                            className={`w-full p-4 rounded-lg border-2 transition-all duration-200 text-left ${isSelected
                                ? renderer.color === 'green'
                                    ? 'border-green-500 bg-green-500/10'
                                    : 'border-blue-500 bg-blue-500/10'
                                : 'border-gray-700 bg-gray-800/50 hover:border-gray-600'
                                }`}
                        >
                            <div className="flex items-center space-x-3">
                                <div className={`p-2 rounded-lg ${isSelected
                                    ? renderer.color === 'green'
                                        ? 'bg-green-500/20'
                                        : 'bg-blue-500/20'
                                    : 'bg-gray-700'
                                    }`}>
                                    <Icon className={`w-5 h-5 ${isSelected
                                        ? renderer.color === 'green'
                                            ? 'text-green-400'
                                            : 'text-blue-400'
                                        : 'text-gray-400'
                                        }`} />
                                </div>
                                <div className="flex-1">
                                    <div className="flex items-center space-x-2">
                                        <span className={`font-medium ${isSelected ? 'text-white' : 'text-gray-300'}`}>
                                            {renderer.name}
                                        </span>
                                        {renderer.color === 'green' && (
                                            <span className="px-1.5 py-0.5 text-xs font-medium bg-green-500/20 text-green-400 rounded">
                                                GPU
                                            </span>
                                        )}
                                    </div>
                                    <div className="text-xs text-gray-500">{renderer.description}</div>
                                </div>
                                {isSelected && (
                                    <div className={`w-2 h-2 rounded-full ${renderer.color === 'green' ? 'bg-green-500' : 'bg-blue-500'
                                        }`} />
                                )}
                            </div>
                        </button>
                    );
                })}
            </div>
        </div>
    );
};

/**
 * Settings Section - Collapsible section with header
 */
const SettingsSection = ({ title, icon: Icon, children, defaultOpen = true }) => {
    const [isOpen, setIsOpen] = React.useState(defaultOpen);

    return (
        <div className="mb-6">
            <button
                onClick={() => setIsOpen(!isOpen)}
                className="w-full flex items-center justify-between p-3 bg-gray-800/50 rounded-lg hover:bg-gray-800/70 transition-colors"
            >
                <div className="flex items-center space-x-2">
                    {Icon && <Icon className="w-4 h-4 text-blue-400" />}
                    <span className="text-sm font-semibold text-white">{title}</span>
                </div>
                <ChevronRight className={`w-4 h-4 text-gray-400 transition-transform duration-200 ${isOpen ? 'rotate-90' : ''
                    }`} />
            </button>
            <AnimatePresence>
                {isOpen && (
                    <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: 'auto', opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ duration: 0.2 }}
                        className="overflow-hidden"
                    >
                        <div className="pt-4 px-1">
                            {children}
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    );
};

/**
 * RGCN / Decision Engine section
 * Validates that the three weights always sum to exactly 1.00.
 */
const RGCNSection = ({ config, setConfig }) => {
    // When a weight slider moves, clamp the remaining two proportionally
    const handleWeightChange = (changed: 'rgcnWeight' | 'communityWeight' | 'traditionalWeight', rawPct: number) => {
        const newVal = Math.round(rawPct) / 100;
        const clamped = Math.min(1, Math.max(0, newVal));
        const keys = ['rgcnWeight', 'communityWeight', 'traditionalWeight'] as const;
        const others = keys.filter(k => k !== changed);
        const remaining = 1 - clamped;
        const sumOthers = others.reduce((s, k) => s + (config[k] as number), 0);
        const updates: Record<string, number> = { [changed]: clamped };
        if (sumOthers === 0) {
            updates[others[0]] = Math.round((remaining / 2) * 100) / 100;
            updates[others[1]] = Math.round((remaining - updates[others[0]]) * 100) / 100;
        } else {
            others.forEach(k => {
                updates[k] = Math.round(((config[k] as number) / sumOthers) * remaining * 100) / 100;
            });
        }
        // Batch update all three to avoid momentary inconsistency
        Object.entries(updates).forEach(([k, v]) => setConfig(k as never, v));
    };

    const total = Math.round((config.rgcnWeight + config.communityWeight + config.traditionalWeight) * 100);
    const sumOk = total === 100;

    return (
        <>
            {/* Master toggles */}
            <ConfigToggle
                label="Enable RGCN Scoring"
                value={config.enableRGCN}
                onChange={(v) => setConfig('enableRGCN', v)}
                icon={Brain}
                description="Use Relational Graph Convolutional Networks for AI-driven risk scores"
            />
            <ConfigToggle
                label="Enable Decision Engine"
                value={config.enableDecisionEngine}
                onChange={(v) => setConfig('enableDecisionEngine', v)}
                icon={BarChart2}
                description="Show the Decision Engine panel when a node is selected"
            />
            <ConfigToggle
                label="Show Confidence Score"
                value={config.showConfidenceScore}
                onChange={(v) => setConfig('showConfidenceScore', v)}
                icon={Eye}
                description="Display the model's confidence percentage in risk labels"
            />

            {/* Weight sliders */}
            <div className={`mt-2 transition-opacity ${config.enableRGCN ? '' : 'opacity-40 pointer-events-none'}`}>
                <div className="flex items-center justify-between mb-3">
                    <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
                        Risk Weight Distribution
                    </span>
                    <span className={`text-xs font-mono px-2 py-0.5 rounded ${sumOk ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}`}>
                        {total}% {sumOk ? '✓' : '≠ 100'}
                    </span>
                </div>

                <ConfigSlider
                    label="RGCN Model"
                    value={Math.round(config.rgcnWeight * 100)}
                    onChange={(v) => handleWeightChange('rgcnWeight', v)}
                    min={0}
                    max={100}
                    unit="%"
                    description="Graph neural network score contribution"
                />
                <ConfigSlider
                    label="Community Detection"
                    value={Math.round(config.communityWeight * 100)}
                    onChange={(v) => handleWeightChange('communityWeight', v)}
                    min={0}
                    max={100}
                    unit="%"
                    description="Cluster / network topology contribution"
                />
                <ConfigSlider
                    label="Traditional Heuristics"
                    value={Math.round(config.traditionalWeight * 100)}
                    onChange={(v) => handleWeightChange('traditionalWeight', v)}
                    min={0}
                    max={100}
                    unit="%"
                    description="Rule-based scoring contribution"
                />

                {/* Visual weight breakdown bar */}
                <div className="mt-1 mb-6 h-2 rounded-full overflow-hidden flex">
                    <div style={{ width: `${config.rgcnWeight * 100}%`, background: '#6366f1' }} className="transition-all duration-200" />
                    <div style={{ width: `${config.communityWeight * 100}%`, background: '#8b5cf6' }} className="transition-all duration-200" />
                    <div style={{ width: `${config.traditionalWeight * 100}%`, background: '#a78bfa' }} className="transition-all duration-200" />
                </div>
                <div className="flex text-xs gap-3 text-gray-500 mb-4">
                    <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-indigo-500 inline-block" />RGCN</span>
                    <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-violet-500 inline-block" />Community</span>
                    <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-violet-300 inline-block" />Heuristics</span>
                </div>
            </div>

            {/* Node size metric */}
            <div className="mb-4">
                <label className="text-sm font-medium text-gray-300 mb-2 block">Node Size Metric</label>
                <div className="flex gap-2">
                    {(['volume', 'risk'] as const).map(metric => (
                        <button
                            key={metric}
                            onClick={() => setConfig('nodeSizeMetric', metric)}
                            className={`flex-1 py-2 px-3 rounded-lg border text-sm font-medium capitalize transition-all ${
                                config.nodeSizeMetric === metric
                                    ? 'border-blue-500 bg-blue-500/15 text-blue-300'
                                    : 'border-gray-700 bg-gray-800/50 text-gray-400 hover:border-gray-600'
                            }`}
                        >
                            {metric}
                        </button>
                    ))}
                </div>
                <p className="text-xs text-gray-500 mt-1">
                    {config.nodeSizeMetric === 'risk'
                        ? 'Node diameter scales with risk score (0–100)'
                        : 'Node diameter scales with transaction volume'}
                </p>
            </div>
        </>
    );
};

/**
 * SettingsPanel - Main sliding panel component
 */
const SettingsPanel = () => {
    const {
        config,
        setConfig,
        resetConfig,
        isSettingsPanelOpen,
        closeSettingsPanel,
        getEffectiveFetchLimit,
        isForensicMode
    } = useConfig();

    const handleReset = useCallback(() => {
        if (window.confirm('Reset all settings to defaults?')) {
            resetConfig();
        }
    }, [resetConfig]);

    return (
        <AnimatePresence>
            {isSettingsPanelOpen && (
                    <motion.div
                        key="settings-panel"
                        initial={{ x: '100%' }}
                        animate={{ x: 0 }}
                        exit={{ x: '100%' }}
                        transition={{ type: 'spring', damping: 25, stiffness: 200 }}
                        className="fixed right-0 top-0 h-full w-96 bg-gray-900/95 border-l border-gray-700 shadow-2xl overflow-hidden flex flex-col"
                        style={{ zIndex: Z.SETTINGS_PANEL, backdropFilter: 'blur(12px)' }}
                    >
                        {/* Header */}
                        <div className="flex items-center justify-between p-4 border-b border-gray-700 bg-gray-800/50">
                            <div className="flex items-center space-x-3">
                                <div className="p-2 bg-blue-500/20 rounded-lg">
                                    <Settings className="w-5 h-5 text-blue-400" />
                                </div>
                                <div>
                                    <h2 className="text-lg font-semibold text-white">Settings</h2>
                                    <p className="text-xs text-gray-400">Configure investigation parameters</p>
                                </div>
                            </div>
                            <button
                                onClick={closeSettingsPanel}
                                className="p-2 hover:bg-gray-700 rounded-lg transition-colors"
                            >
                                <X className="w-5 h-5 text-gray-400" />
                            </button>
                        </div>

                        {/* Current Mode Indicator */}
                        <div className={`px-4 py-3 border-b border-gray-700 ${isForensicMode() ? 'bg-purple-500/10' : 'bg-green-500/10'
                            }`}>
                            <div className="flex items-center justify-between">
                                <div className="flex items-center space-x-2">
                                    {isForensicMode() ? (
                                        <Shield className="w-4 h-4 text-purple-400" />
                                    ) : (
                                        <Zap className="w-4 h-4 text-green-400" />
                                    )}
                                    <span className={`text-sm font-medium ${isForensicMode() ? 'text-purple-300' : 'text-green-300'
                                        }`}>
                                        {isForensicMode() ? 'Forensic Mode' : 'Lite Mode'}
                                    </span>
                                </div>
                                <span className="text-xs text-gray-400">
                                    Max {getEffectiveFetchLimit()} txs
                                </span>
                            </div>
                        </div>

                        {/* Scrollable Content */}
                        <div className="flex-1 overflow-y-auto p-4">
                            {/* Analysis Mode */}
                            <SettingsSection title="Analysis Mode" icon={Activity} defaultOpen={true}>
                                <ModeSelector
                                    value={config.analysisMode}
                                    onChange={(value) => setConfig('analysisMode', value)}
                                />
                            </SettingsSection>

                            {/* Graph Renderer - NEW */}
                            <SettingsSection title="Graph Renderer" icon={Cpu} defaultOpen={true}>
                                <GraphRendererSelector
                                    value={config.graphRenderer}
                                    onChange={(value) => setConfig('graphRenderer', value)}
                                    autoSelect={config.autoSelectRenderer}
                                    onAutoSelectChange={(value) => setConfig('autoSelectRenderer', value)}
                                    threshold={config.webglNodeThreshold}
                                    onThresholdChange={(value) => setConfig('webglNodeThreshold', value)}
                                />

                                {/* WebGL Performance Info */}
                                <div className="mt-4 p-3 bg-green-500/10 border border-green-500/30 rounded-lg">
                                    <div className="flex items-start space-x-2">
                                        <Cpu className="w-4 h-4 text-green-400 mt-0.5" />
                                        <div>
                                            <p className="text-sm text-green-300 font-medium">WebGL GPU Acceleration</p>
                                            <p className="text-xs text-green-400/70 mt-1">
                                                Sigma.js uses your integrated GPU to render large graphs (10,000+ nodes)
                                                without freezing the UI. Recommended for forensic deep-dive analysis.
                                            </p>
                                        </div>
                                    </div>
                                </div>
                            </SettingsSection>

                            {/* Fetch Parameters */}
                            <SettingsSection title="Fetch Parameters" icon={Database} defaultOpen={true}>
                                <ConfigSlider
                                    label="Transaction Limit"
                                    value={config.fetchLimit}
                                    onChange={(value) => setConfig('fetchLimit', value)}
                                    min={10}
                                    max={isForensicMode() ? 10000 : 50}
                                    step={isForensicMode() ? 100 : 10}
                                    description={isForensicMode()
                                        ? "Deep dive: up to 10000 transactions (comprehensive analysis)"
                                        : "Lite mode: capped at 50 for speed"
                                    }
                                />

                                <ConfigSlider
                                    label="Search Depth"
                                    value={config.searchDepth}
                                    onChange={(value) => setConfig('searchDepth', value)}
                                    min={1}
                                    max={3}
                                    step={1}
                                    unit=" hops"
                                    description="How many address levels to explore"
                                />

                                <ConfigSlider
                                    label="Dust Threshold"
                                    value={config.dustThreshold}
                                    onChange={(value) => setConfig('dustThreshold', value)}
                                    min={100}
                                    max={10000}
                                    step={100}
                                    unit=" sats"
                                    description="Transactions below this are considered dust"
                                />
                            </SettingsSection>

                            {/* Display Options */}
                            <SettingsSection title="Display Options" icon={Eye} defaultOpen={false}>
                                <ConfigToggle
                                    label="Show Dust Transactions"
                                    value={config.showDust}
                                    onChange={(value) => setConfig('showDust', value)}
                                    icon={config.showDust ? Eye : EyeOff}
                                    description="Include very small transactions in analysis"
                                />

                                <ConfigToggle
                                    label="Show Raw JSON Data"
                                    value={config.showRawData}
                                    onChange={(value) => setConfig('showRawData', value)}
                                    icon={Database}
                                    description="Display raw API data in inspector"
                                />
                            </SettingsSection>

                            {/* Performance */}
                            <SettingsSection title="Performance" icon={Zap} defaultOpen={false}>
                                <ConfigToggle
                                    label="Parallel Fetching"
                                    value={config.enableParallelFetch}
                                    onChange={(value) => setConfig('enableParallelFetch', value)}
                                    icon={Layers}
                                    description="Fetch multiple addresses simultaneously"
                                />

                                <ConfigSlider
                                    label="Max Concurrent Requests"
                                    value={config.maxConcurrentRequests}
                                    onChange={(value) => setConfig('maxConcurrentRequests', value)}
                                    min={1}
                                    max={10}
                                    step={1}
                                    description="Parallel request limit (higher = faster but more load)"
                                />

                                <ConfigSlider
                                    label="Rate Limit Delay"
                                    value={config.rateLimitDelay}
                                    onChange={(value) => setConfig('rateLimitDelay', value)}
                                    min={100}
                                    max={1000}
                                    step={50}
                                    unit="ms"
                                    description="Delay between sequential API calls"
                                />
                            </SettingsSection>

                            {/* AI Risk Scoring (RGCN) */}
                            <SettingsSection title="AI Risk Scoring (RGCN)" icon={Brain} defaultOpen={false}>
                                <RGCNSection config={config} setConfig={setConfig} />
                            </SettingsSection>

                            {/* Developer */}
                            <SettingsSection title="Developer" icon={Bug} defaultOpen={false}>
                                <ConfigToggle
                                    label="Debug Logging"
                                    value={config.enableDebugLogs}
                                    onChange={(value) => setConfig('enableDebugLogs', value)}
                                    icon={Bug}
                                    description="Verbose console output for debugging"
                                />

                                <ConfigSlider
                                    label="Auto-Refresh Interval"
                                    value={config.autoRefreshInterval}
                                    onChange={(value) => setConfig('autoRefreshInterval', value)}
                                    min={0}
                                    max={60000}
                                    step={5000}
                                    unit="ms"
                                    description="0 = disabled. Auto-refresh mempool data"
                                />
                            </SettingsSection>

                            <SettingsSection title="System Logs" icon={Terminal} defaultOpen={false}>
                                <LogViewer />
                            </SettingsSection>
                        </div>

                        {/* Footer */}
                        <div className="p-4 border-t border-gray-700 bg-gray-800/50">
                            <div className="flex items-center justify-between">
                                <button
                                    onClick={handleReset}
                                    className="flex items-center space-x-2 px-4 py-2 text-gray-400 hover:text-white hover:bg-gray-700 rounded-lg transition-colors"
                                >
                                    <RotateCcw className="w-4 h-4" />
                                    <span className="text-sm">Reset Defaults</span>
                                </button>

                                <button
                                    onClick={closeSettingsPanel}
                                    className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors font-medium text-sm"
                                >
                                    Done
                                </button>
                            </div>
                        </div>
                    </motion.div>
            )}
        </AnimatePresence>
    );
};

export default SettingsPanel;
