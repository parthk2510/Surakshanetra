'use client';
// DecisionPanel – shows the combined RGCN + community + heuristic verdict
import React, { useEffect, useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
    Brain, Shield, AlertTriangle, CheckCircle, XCircle,
    BarChart2, Network, Cpu, ChevronDown, ChevronUp,
    RefreshCw, Star
} from 'lucide-react';
import { useConfig } from '../context/ConfigContext';
import apiService from '../utils/api';

// ── Types ────────────────────────────────────────────────────────────────────
interface EngineRGCN {
    fraud_probability: number;
    anomaly_score: number;
    final_risk_score: number;
    predicted_fraud: number;
    flag_source: string;
    model_risk_tier: string;
}

interface EngineCommunity {
    community_id: number;
    community_size: number;
    flagged_members: number;
    flag_rate: number;
    avg_community_risk: number;
    community_risk_tier: string;
}

interface EngineTraditional {
    risk_score: number;
    signals: string[];
}

interface DecisionResult {
    account_id: string;
    final_score: number;
    risk_tier: string;
    confidence: number;
    recommended_action: string;
    signals_used: string[];
    engine_count: number;
    engines: {
        rgcn?: EngineRGCN;
        community?: EngineCommunity;
        traditional?: EngineTraditional;
    };
}

// ── Helpers ──────────────────────────────────────────────────────────────────
const TIER_CONFIG: Record<string, { color: string; bg: string; border: string; icon: React.ElementType }> = {
    Critical: { color: '#ef4444', bg: 'rgba(239,68,68,0.1)',   border: 'rgba(239,68,68,0.3)',   icon: XCircle },
    High:     { color: '#f97316', bg: 'rgba(249,115,22,0.1)',  border: 'rgba(249,115,22,0.3)',  icon: AlertTriangle },
    Medium:   { color: '#eab308', bg: 'rgba(234,179,8,0.1)',   border: 'rgba(234,179,8,0.3)',   icon: AlertTriangle },
    Low:      { color: '#22c55e', bg: 'rgba(34,197,94,0.1)',   border: 'rgba(34,197,94,0.3)',   icon: CheckCircle },
};

const ScoreBar = ({ value, color }: { value: number; color: string }) => (
    <div className="w-full h-1.5 rounded-full overflow-hidden" style={{ background: 'rgba(255,255,255,0.08)' }}>
        <motion.div
            initial={{ width: 0 }}
            animate={{ width: `${Math.round(value * 100)}%` }}
            transition={{ duration: 0.8, ease: 'easeOut' }}
            className="h-full rounded-full"
            style={{ background: color }}
        />
    </div>
);

const ConfidenceRing = ({ value }: { value: number }) => {
    const pct = Math.round(value * 100);
    const level = pct >= 80 ? 'High' : pct >= 55 ? 'Medium' : 'Low';
    const colors = { High: '#22c55e', Medium: '#eab308', Low: '#ef4444' };
    const color = colors[level];
    const r = 22, circ = 2 * Math.PI * r;
    return (
        <div className="flex flex-col items-center gap-1">
            <svg width="60" height="60" viewBox="0 0 60 60">
                <circle cx="30" cy="30" r={r} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="4" />
                <motion.circle
                    cx="30" cy="30" r={r}
                    fill="none"
                    stroke={color}
                    strokeWidth="4"
                    strokeLinecap="round"
                    strokeDasharray={circ}
                    initial={{ strokeDashoffset: circ }}
                    animate={{ strokeDashoffset: circ - (value * circ) }}
                    transition={{ duration: 1, ease: 'easeOut' }}
                    transform="rotate(-90 30 30)"
                />
                <text x="30" y="34" textAnchor="middle" fontSize="13" fontWeight="bold" fill={color}>
                    {pct}%
                </text>
            </svg>
            <span className="text-xs font-medium" style={{ color }}>
                {level} Confidence
            </span>
        </div>
    );
};

// ── Main component ────────────────────────────────────────────────────────────
interface DecisionPanelProps {
    identifier: string | null;
    traditionalRiskScore?: number;
    className?: string;
}

const DecisionPanel: React.FC<DecisionPanelProps> = ({
    identifier,
    traditionalRiskScore = 0,
    className = '',
}) => {
    const { config } = useConfig();
    const [result, setResult] = useState<DecisionResult | null>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [expanded, setExpanded] = useState<Record<string, boolean>>({
        rgcn: true, community: true, traditional: false,
    });

    const fetchDecision = useCallback(async () => {
        if (!identifier || !config.enableDecisionEngine) return;
        setLoading(true);
        setError(null);
        try {
            const params = new URLSearchParams({
                traditional_risk_score: String(traditionalRiskScore),
                rgcn_weight: String(config.rgcnWeight ?? 0.55),
                community_weight: String(config.communityWeight ?? 0.20),
                traditional_weight: String(config.traditionalWeight ?? 0.25),
            });
            const resp = await apiService.get(
                `/api/decision/${encodeURIComponent(identifier)}?${params}`
            );
            if (resp.success) {
                setResult(resp.data);
            } else {
                setError(resp.error || 'Decision engine unavailable');
            }
        } catch (err: any) {
            setError(err?.response?.data?.error || err?.message || 'Failed to fetch decision');
        } finally {
            setLoading(false);
        }
    }, [identifier, config.enableDecisionEngine, config.rgcnWeight, config.communityWeight, config.traditionalWeight, traditionalRiskScore]);

    useEffect(() => { fetchDecision(); }, [fetchDecision]);

    if (!config.enableDecisionEngine) return null;
    if (!identifier) return null;

    const tierCfg = result ? (TIER_CONFIG[result.risk_tier] ?? TIER_CONFIG.Low) : null;
    const TierIcon = tierCfg?.icon ?? Shield;

    return (
        <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className={`rounded-xl border overflow-hidden ${className}`}
            style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
        >
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-3 border-b" style={{ borderColor: 'var(--border)', background: 'var(--surface-2)' }}>
                <div className="flex items-center gap-2">
                    <Brain className="w-5 h-5 text-violet-400" />
                    <span className="font-semibold text-sm" style={{ color: 'var(--text-primary)' }}>
                        Decision Engine
                    </span>
                    <span className="text-xs px-1.5 py-0.5 rounded-full font-medium"
                        style={{ background: 'rgba(139,92,246,0.15)', color: '#c4b5fd' }}>
                        RGCN + Community + Heuristics
                    </span>
                </div>
                <button
                    onClick={fetchDecision}
                    disabled={loading}
                    className="p-1.5 rounded-lg hover:bg-gray-700/50 transition-colors"
                    title="Refresh analysis"
                >
                    <RefreshCw className={`w-4 h-4 text-gray-400 ${loading ? 'animate-spin' : ''}`} />
                </button>
            </div>

            <div className="p-4">
                {/* Loading */}
                {loading && (
                    <div className="flex items-center justify-center gap-2 py-6">
                        <RefreshCw className="w-5 h-5 animate-spin text-violet-400" />
                        <span className="text-sm text-gray-400">Analysing with all engines…</span>
                    </div>
                )}

                {/* Error */}
                {!loading && error && (
                    <div className="flex items-center gap-2 py-4 text-sm text-yellow-400">
                        <AlertTriangle className="w-4 h-4 flex-shrink-0" />
                        <span>{error}</span>
                    </div>
                )}

                {/* Result */}
                {!loading && result && tierCfg && (
                    <div className="space-y-4">
                        {/* Verdict row */}
                        <div className="flex items-start justify-between gap-4">
                            <div
                                className="flex-1 rounded-xl p-4 border"
                                style={{ background: tierCfg.bg, borderColor: tierCfg.border }}
                            >
                                <div className="flex items-center gap-2 mb-2">
                                    <TierIcon className="w-5 h-5" style={{ color: tierCfg.color }} />
                                    <span className="font-bold text-base" style={{ color: tierCfg.color }}>
                                        {result.risk_tier} Risk
                                    </span>
                                    <span className="text-lg font-mono font-bold ml-auto" style={{ color: tierCfg.color }}>
                                        {Math.round(result.final_score * 100)}
                                    </span>
                                    <span className="text-xs text-gray-500">/100</span>
                                </div>
                                <ScoreBar value={result.final_score} color={tierCfg.color} />
                                <p className="mt-2 text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>
                                    {result.recommended_action}
                                </p>
                            </div>

                            {/* Confidence ring */}
                            {config.showConfidenceScore && (
                                <ConfidenceRing value={result.confidence} />
                            )}
                        </div>

                        {/* Signals used */}
                        <div className="flex flex-wrap gap-1.5">
                            {result.signals_used.map(sig => (
                                <span key={sig} className="text-xs px-2 py-0.5 rounded-full border font-medium"
                                    style={{
                                        background: 'rgba(139,92,246,0.1)',
                                        borderColor: 'rgba(139,92,246,0.3)',
                                        color: '#c4b5fd'
                                    }}>
                                    {sig === 'rgcn' ? '🧠 RGCN' : sig === 'community' ? '🕸 Community' : '📊 Heuristics'}
                                </span>
                            ))}
                            <span className="text-xs px-2 py-0.5 rounded-full border"
                                style={{ borderColor: 'var(--border)', color: 'var(--text-muted)' }}>
                                {result.engine_count} engine{result.engine_count !== 1 ? 's' : ''} active
                            </span>
                        </div>

                        {/* Per-engine breakdown */}

                        {/* RGCN */}
                        {result.engines.rgcn && (
                            <div className="rounded-lg border overflow-hidden" style={{ borderColor: 'var(--border)' }}>
                                <button
                                    className="w-full flex items-center justify-between px-3 py-2 text-sm"
                                    style={{ background: 'var(--surface-2)' }}
                                    onClick={() => setExpanded(p => ({ ...p, rgcn: !p.rgcn }))}
                                >
                                    <div className="flex items-center gap-2">
                                        <Cpu className="w-4 h-4 text-violet-400" />
                                        <span style={{ color: 'var(--text-primary)' }}>RGCN Model</span>
                                        <span className="text-xs font-mono" style={{ color: 'var(--text-muted)' }}>
                                            {Math.round(result.engines.rgcn.final_risk_score * 100)}/100
                                        </span>
                                    </div>
                                    {expanded.rgcn ? <ChevronUp className="w-4 h-4 text-gray-500" /> : <ChevronDown className="w-4 h-4 text-gray-500" />}
                                </button>
                                <AnimatePresence>
                                    {expanded.rgcn && (
                                        <motion.div
                                            initial={{ height: 0 }} animate={{ height: 'auto' }} exit={{ height: 0 }}
                                            className="overflow-hidden"
                                        >
                                            <div className="p-3 space-y-2 text-xs" style={{ color: 'var(--text-secondary)' }}>
                                                <div className="grid grid-cols-2 gap-2">
                                                    <div>
                                                        <p className="text-gray-500 mb-1">Fraud Probability</p>
                                                        <ScoreBar value={result.engines.rgcn.fraud_probability} color="#ef4444" />
                                                        <p className="mt-0.5 font-mono">{(result.engines.rgcn.fraud_probability * 100).toFixed(1)}%</p>
                                                    </div>
                                                    <div>
                                                        <p className="text-gray-500 mb-1">Anomaly Score</p>
                                                        <ScoreBar value={result.engines.rgcn.anomaly_score} color="#f97316" />
                                                        <p className="mt-0.5 font-mono">{(result.engines.rgcn.anomaly_score * 100).toFixed(1)}%</p>
                                                    </div>
                                                </div>
                                                <div className="flex gap-2 pt-1">
                                                    <span className="px-2 py-0.5 rounded border text-xs"
                                                        style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)' }}>
                                                        {result.engines.rgcn.predicted_fraud === 1 ? '🚩 Predicted Fraud' : '✅ Not Fraud'}
                                                    </span>
                                                    <span className="px-2 py-0.5 rounded border text-xs"
                                                        style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)' }}>
                                                        Source: {result.engines.rgcn.flag_source}
                                                    </span>
                                                </div>
                                            </div>
                                        </motion.div>
                                    )}
                                </AnimatePresence>
                            </div>
                        )}

                        {/* Community */}
                        {result.engines.community && (
                            <div className="rounded-lg border overflow-hidden" style={{ borderColor: 'var(--border)' }}>
                                <button
                                    className="w-full flex items-center justify-between px-3 py-2 text-sm"
                                    style={{ background: 'var(--surface-2)' }}
                                    onClick={() => setExpanded(p => ({ ...p, community: !p.community }))}
                                >
                                    <div className="flex items-center gap-2">
                                        <Network className="w-4 h-4 text-blue-400" />
                                        <span style={{ color: 'var(--text-primary)' }}>Community Analysis</span>
                                        <span className="text-xs font-mono" style={{ color: 'var(--text-muted)' }}>
                                            Community #{result.engines.community.community_id}
                                        </span>
                                    </div>
                                    {expanded.community ? <ChevronUp className="w-4 h-4 text-gray-500" /> : <ChevronDown className="w-4 h-4 text-gray-500" />}
                                </button>
                                <AnimatePresence>
                                    {expanded.community && (
                                        <motion.div
                                            initial={{ height: 0 }} animate={{ height: 'auto' }} exit={{ height: 0 }}
                                            className="overflow-hidden"
                                        >
                                            <div className="p-3 grid grid-cols-3 gap-2 text-xs" style={{ color: 'var(--text-secondary)' }}>
                                                <div className="text-center p-2 rounded" style={{ background: 'var(--surface-3)' }}>
                                                    <p className="text-gray-500">Size</p>
                                                    <p className="font-bold text-base mt-0.5" style={{ color: 'var(--text-primary)' }}>
                                                        {result.engines.community.community_size}
                                                    </p>
                                                </div>
                                                <div className="text-center p-2 rounded" style={{ background: 'var(--surface-3)' }}>
                                                    <p className="text-gray-500">Flagged</p>
                                                    <p className="font-bold text-base mt-0.5 text-red-400">
                                                        {result.engines.community.flagged_members}
                                                    </p>
                                                </div>
                                                <div className="text-center p-2 rounded" style={{ background: 'var(--surface-3)' }}>
                                                    <p className="text-gray-500">Flag Rate</p>
                                                    <p className="font-bold text-base mt-0.5 text-orange-400">
                                                        {(result.engines.community.flag_rate * 100).toFixed(0)}%
                                                    </p>
                                                </div>
                                            </div>
                                        </motion.div>
                                    )}
                                </AnimatePresence>
                            </div>
                        )}

                        {/* Traditional */}
                        {result.engines.traditional && (
                            <div className="rounded-lg border overflow-hidden" style={{ borderColor: 'var(--border)' }}>
                                <button
                                    className="w-full flex items-center justify-between px-3 py-2 text-sm"
                                    style={{ background: 'var(--surface-2)' }}
                                    onClick={() => setExpanded(p => ({ ...p, traditional: !p.traditional }))}
                                >
                                    <div className="flex items-center gap-2">
                                        <BarChart2 className="w-4 h-4 text-green-400" />
                                        <span style={{ color: 'var(--text-primary)' }}>Heuristic Analysis</span>
                                        <span className="text-xs font-mono" style={{ color: 'var(--text-muted)' }}>
                                            {Math.round(result.engines.traditional.risk_score * 100)}/100
                                        </span>
                                    </div>
                                    {expanded.traditional ? <ChevronUp className="w-4 h-4 text-gray-500" /> : <ChevronDown className="w-4 h-4 text-gray-500" />}
                                </button>
                                <AnimatePresence>
                                    {expanded.traditional && (
                                        <motion.div
                                            initial={{ height: 0 }} animate={{ height: 'auto' }} exit={{ height: 0 }}
                                            className="overflow-hidden"
                                        >
                                            <div className="p-3 text-xs" style={{ color: 'var(--text-secondary)' }}>
                                                <ScoreBar value={result.engines.traditional.risk_score} color="#22c55e" />
                                                {result.engines.traditional.signals.length > 0 && (
                                                    <ul className="mt-2 space-y-1">
                                                        {result.engines.traditional.signals.map((s, i) => (
                                                            <li key={i} className="flex items-center gap-1.5">
                                                                <span className="w-1.5 h-1.5 rounded-full bg-yellow-500 flex-shrink-0" />
                                                                {s}
                                                            </li>
                                                        ))}
                                                    </ul>
                                                )}
                                            </div>
                                        </motion.div>
                                    )}
                                </AnimatePresence>
                            </div>
                        )}
                    </div>
                )}
            </div>
        </motion.div>
    );
};

export default DecisionPanel;
