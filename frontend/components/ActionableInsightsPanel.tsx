// @ts-nocheck
import React from 'react';
import { motion } from 'framer-motion';
import { AlertCircle, TrendingUp, Users, DollarSign, Shield, AlertTriangle } from 'lucide-react';

/**
 * ActionableInsightsPanel Component
 * Displays actionable intelligence derived from community detection
 * and fraud analysis, with clear recommendations for investigators.
 */
const ActionableInsightsPanel = ({ comparisonResults, graphData, className = '' }) => {
    if (!comparisonResults || !comparisonResults.algorithm_results) {
        return (
            <div className={className} style={{
                padding: '20px',
                background: 'rgba(30, 41, 59, 0.5)',
                borderRadius: '12px',
                border: '1px solid #334155',
                textAlign: 'center'
            }}>
                <div style={{ fontSize: '12px', color: '#94a3b8' }}>
                    Run community comparison to see actionable insights
                </div>
            </div>
        );
    }

    // Extract insights
    const bestAlgorithm = Object.keys(comparisonResults.ranking)[0];
    const bestResult = comparisonResults.algorithm_results[bestAlgorithm];

    const totalSuspiciousCommunities = Object.values(comparisonResults.algorithm_results)
        .reduce((sum, result) => sum + (result.suspicious_communities || 0), 0);

    const totalNodes = comparisonResults.graph_metrics?.num_nodes || graphData?.nodes?.length || 0;
    const totalEdges = comparisonResults.graph_metrics?.num_edges || graphData?.edges?.length || 0;

    const topSuspiciousAccounts = bestResult?.top_suspicious_accounts || [];
    const criticalAccounts = topSuspiciousAccounts.filter(acc => acc.weighted_score >= 80);
    const highRiskAccounts = topSuspiciousAccounts.filter(acc => acc.weighted_score >= 60 && acc.weighted_score < 80);

    // Calculate total money movement
    const totalVolume = (graphData?.edges || []).reduce((sum, e) => sum + (e.amount || e.value || 0), 0);

    // Priority actions
    const priorityActions = [];

    if (criticalAccounts.length > 0) {
        priorityActions.push({
            priority: 'CRITICAL',
            icon: AlertCircle,
            color: '#ef4444',
            bg: 'rgba(239, 68, 68, 0.1)',
            border: 'rgba(239, 68, 68, 0.3)',
            title: 'Immediate Freeze Required',
            description: `${criticalAccounts.length} accounts with critical risk scores detected`,
            action: 'Freeze accounts immediately and notify law enforcement'
        });
    }

    if (highRiskAccounts.length > 0) {
        priorityActions.push({
            priority: 'HIGH',
            icon: AlertTriangle,
            color: '#f97316',
            bg: 'rgba(249, 115, 22, 0.1)',
            border: 'rgba(249, 115, 22, 0.3)',
            title: 'Enhanced Monitoring',
            description: `${highRiskAccounts.length} accounts require enhanced oversight`,
            action: 'Implement real-time transaction monitoring'
        });
    }

    if (totalSuspiciousCommunities > 0) {
        priorityActions.push({
            priority: 'MEDIUM',
            icon: Users,
            color: '#eab308',
            bg: 'rgba(234, 179, 8, 0.1)',
            border: 'rgba(234, 179, 8, 0.3)',
            title: 'MTL Network Detected',
            description: `${totalSuspiciousCommunities} suspicious communities identified`,
            action: 'Prepare Suspicious Transaction Reports (STRs)'
        });
    }

    // Key findings
    const keyFindings = [
        {
            icon: Shield,
            label: 'Best Detection',
            value: bestAlgorithm?.toUpperCase(),
            subtext: `${(comparisonResults.ranking[bestAlgorithm] * 100).toFixed(1)}% accuracy`,
            color: '#22c55e'
        },
        {
            icon: Users,
            label: 'Network Size',
            value: totalNodes.toLocaleString(),
            subtext: `${totalEdges.toLocaleString()} transactions`,
            color: '#3b82f6'
        },
        {
            icon: DollarSign,
            label: 'Total Volume',
            value: `₹${(totalVolume / 1000).toFixed(1)}K`,
            subtext: `Avg ₹${(totalVolume / Math.max(totalEdges, 1)).toFixed(0)}/tx`,
            color: '#8b5cf6'
        },
        {
            icon: TrendingUp,
            label: 'Risk Score',
            value: `${topSuspiciousAccounts[0]?.weighted_score.toFixed(0) || 'N/A'}`,
            subtext: 'Highest detected',
            color: '#ef4444'
        }
    ];

    return (
        <div className={className} style={{
            background: 'rgba(15, 23, 42, 0.95)',
            borderRadius: '12px',
            padding: '20px',
            border: '1px solid rgba(51, 65, 85, 0.8)'
        }}>
            {/* Header */}
            <div style={{
                display: 'flex',
                alignItems: 'center',
                gap: '10px',
                marginBottom: '20px',
                paddingBottom: '16px',
                borderBottom: '1px solid rgba(51, 65, 85, 0.6)'
            }}>
                <div style={{
                    width: '10px',
                    height: '10px',
                    borderRadius: '50%',
                    background: 'linear-gradient(135deg, #ef4444, #f97316)',
                    boxShadow: '0 0 10px rgba(239, 68, 68, 0.5)'
                }} />
                <h3 style={{
                    fontSize: '15px',
                    fontWeight: '700',
                    color: '#f1f5f9',
                    margin: 0,
                    letterSpacing: '0.02em'
                }}>
                    Actionable Insights
                </h3>
            </div>

            {/* Key Findings Grid */}
            <div style={{
                display: 'grid',
                gridTemplateColumns: '1fr 1fr',
                gap: '12px',
                marginBottom: '20px'
            }}>
                {keyFindings.map((finding, index) => {
                    const Icon = finding.icon;
                    return (
                        <motion.div
                            key={finding.label}
                            initial={{ opacity: 0, y: 10 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ delay: index * 0.05 }}
                            style={{
                                background: 'rgba(30, 41, 59, 0.5)',
                                borderRadius: '8px',
                                padding: '12px',
                                border: '1px solid rgba(51, 65, 85, 0.6)'
                            }}
                        >
                            <div style={{ display: 'flex', alignItems: 'start', gap: '10px' }}>
                                <Icon size={16} color={finding.color} style={{ flexShrink: 0, marginTop: '2px' }} />
                                <div style={{ flex: 1 }}>
                                    <div style={{ fontSize: '10px', color: '#94a3b8', marginBottom: '4px' }}>
                                        {finding.label}
                                    </div>
                                    <div style={{ fontSize: '16px', fontWeight: '700', color: finding.color, marginBottom: '2px' }}>
                                        {finding.value}
                                    </div>
                                    <div style={{ fontSize: '9px', color: '#64748b' }}>
                                        {finding.subtext}
                                    </div>
                                </div>
                            </div>
                        </motion.div>
                    );
                })}
            </div>

            {/* Priority Actions */}
            <div>
                <div style={{
                    fontSize: '11px',
                    fontWeight: '600',
                    color: '#94a3b8',
                    textTransform: 'uppercase',
                    letterSpacing: '0.08em',
                    marginBottom: '12px'
                }}>
                    Priority Actions
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                    {priorityActions.length > 0 ? priorityActions.map((action, index) => {
                        const Icon = action.icon;
                        return (
                            <motion.div
                                key={action.title}
                                initial={{ opacity: 0, x: -10 }}
                                animate={{ opacity: 1, x: 0 }}
                                transition={{ delay: index * 0.1 }}
                                style={{
                                    background: action.bg,
                                    border: `1px solid ${action.border}`,
                                    borderRadius: '8px',
                                    padding: '12px',
                                    transition: 'all 0.2s'
                                }}
                            >
                                <div style={{ display: 'flex', gap: '10px', alignItems: 'start' }}>
                                    <Icon size={16} color={action.color} style={{ flexShrink: 0, marginTop: '2px' }} />
                                    <div style={{ flex: 1 }}>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                                            <span style={{
                                                fontSize: '9px',
                                                fontWeight: '700',
                                                color: action.color,
                                                background: `${action.color}20`,
                                                padding: '2px 6px',
                                                borderRadius: '4px',
                                                textTransform: 'uppercase'
                                            }}>
                                                {action.priority}
                                            </span>
                                            <span style={{ fontSize: '12px', fontWeight: '600', color: action.color }}>
                                                {action.title}
                                            </span>
                                        </div>
                                        <div style={{ fontSize: '11px', color: '#e2e8f0', marginBottom: '6px' }}>
                                            {action.description}
                                        </div>
                                        <div style={{
                                            fontSize: '10px',
                                            color: '#94a3b8',
                                            fontStyle: 'italic',
                                            paddingLeft: '12px',
                                            borderLeft: `2px solid ${action.color}`
                                        }}>
                                            → {action.action}
                                        </div>
                                    </div>
                                </div>
                            </motion.div>
                        );
                    }) : (
                        <div style={{
                            padding: '20px',
                            textAlign: 'center',
                            color: '#64748b',
                            fontSize: '11px'
                        }}>
                            No immediate actions required
                        </div>
                    )}
                </div>
            </div>

            {/* Investigation Tips */}
            <div style={{
                marginTop: '20px',
                padding: '12px',
                background: 'rgba(59, 130, 246, 0.05)',
                border: '1px solid rgba(59, 130, 246, 0.2)',
                borderRadius: '8px'
            }}>
                <div style={{
                    fontSize: '10px',
                    fontWeight: '600',
                    color: '#60a5fa',
                    marginBottom: '8px',
                    textTransform: 'uppercase',
                    letterSpacing: '0.08em'
                }}>
                    Investigation Tips
                </div>
                <ul style={{
                    margin: 0,
                    paddingLeft: '20px',
                    fontSize: '10px',
                    color: '#94a3b8',
                    lineHeight: '1.6'
                }}>
                    <li>Focus on high betweenness nodes - they&apos;re likely layering accounts</li>
                    <li>Check transaction timing patterns for coordinated behavior</li>
                    <li>Verify account holder KYC information for connected accounts</li>
                    <li>Cross-reference with known fraud databases</li>
                </ul>
            </div>
        </div>
    );
};

export default ActionableInsightsPanel;
