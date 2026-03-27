// @ts-nocheck
"use client";
import React, { useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { BarChart3, Users, AlertTriangle, TrendingUp, Download, CheckCircle, XCircle, Eye } from 'lucide-react';
import { chainbreakAPI } from '../utils/api';

const ValidationInterface = ({ validationBatch, summary }) => {
  const [currentAccountIndex, setCurrentAccountIndex] = useState(0);
  const [validations, setValidations] = useState({});

  const currentAccount = validationBatch.accounts[currentAccountIndex];

  const handleValidation = (isSuspicious) => {
    const accountId = currentAccount.account_id;
    setValidations(prev => ({
      ...prev,
      [accountId]: {
        is_suspicious: isSuspicious,
        validated_at: new Date().toISOString(),
        reviewer: 'manual_reviewer'
      }
    }));

    // Move to next account
    if (currentAccountIndex < validationBatch.accounts.length - 1) {
      setCurrentAccountIndex(prev => prev + 1);
    }
  };

  const progress = ((currentAccountIndex + 1) / validationBatch.total_accounts) * 100;

  return (
    <div style={{
      background: 'rgba(30, 41, 59, 0.5)',
      borderRadius: '8px',
      padding: '16px',
      border: '1px solid #334155'
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
        <h4 style={{ fontSize: '14px', fontWeight: '600', color: '#e2e8f0', margin: 0 }}>
          Manual Validation Loop
        </h4>
        <span style={{ fontSize: '12px', color: '#94a3b8' }}>
          {currentAccountIndex + 1} / {validationBatch.total_accounts}
        </span>
      </div>

      {/* Progress Bar */}
      <div style={{ marginBottom: '16px' }}>
        <div style={{
          height: '4px',
          background: '#1e293b',
          borderRadius: '2px',
          overflow: 'hidden'
        }}>
          <motion.div
            initial={{ width: 0 }}
            animate={{ width: `${progress}%` }}
            style={{
              height: '100%',
              background: 'linear-gradient(90deg, #8b5cf6, #6366f1)'
            }}
          />
        </div>
      </div>

      {currentAccount && (
        <div style={{
          background: 'rgba(15, 23, 42, 0.5)',
          borderRadius: '6px',
          padding: '16px',
          marginBottom: '16px'
        }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '12px' }}>
            <div>
              <span style={{ fontSize: '11px', color: '#64748b' }}>Account ID</span>
              <div style={{ fontSize: '13px', fontWeight: '600', color: '#e2e8f0' }}>
                {currentAccount.account_id}
              </div>
            </div>
            <div>
              <span style={{ fontSize: '11px', color: '#64748b' }}>Weighted Score</span>
              <div style={{ fontSize: '13px', fontWeight: '600', color: '#f59e0b' }}>
                {currentAccount.weighted_score?.toFixed(1)}
              </div>
            </div>
            <div>
              <span style={{ fontSize: '11px', color: '#64748b' }}>Risk Score</span>
              <div style={{ fontSize: '13px', fontWeight: '600', color: '#ef4444' }}>
                {currentAccount.risk_score?.toFixed(1)}
              </div>
            </div>
            <div>
              <span style={{ fontSize: '11px', color: '#64748b' }}>In/Out Ratio</span>
              <div style={{ fontSize: '13px', fontWeight: '600', color: '#e2e8f0' }}>
                {currentAccount.in_out_ratio?.toFixed(2)}
              </div>
            </div>
            <div>
              <span style={{ fontSize: '11px', color: '#64748b' }}>Betweenness</span>
              <div style={{ fontSize: '13px', fontWeight: '600', color: '#e2e8f0' }}>
                {currentAccount.betweenness?.toFixed(4)}
              </div>
            </div>
            <div>
              <span style={{ fontSize: '11px', color: '#64748b' }}>Community</span>
              <div style={{ fontSize: '13px', fontWeight: '600', color: '#8b5cf6' }}>
                {currentAccount.community_id}
              </div>
            </div>
          </div>

          {/* Suspicious Indicators */}
          <div style={{ marginBottom: '12px' }}>
            <span style={{ fontSize: '11px', color: '#64748b', display: 'block', marginBottom: '4px' }}>
              Suspicious Indicators
            </span>
            <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
              {Object.entries(currentAccount.suspicious_indicators || {}).map(([indicator, isSuspicious]) => (
                <span
                  key={indicator}
                  style={{
                    fontSize: '10px',
                    padding: '2px 6px',
                    borderRadius: '4px',
                    background: isSuspicious ? 'rgba(239, 68, 68, 0.2)' : 'rgba(16, 185, 129, 0.2)',
                    color: isSuspicious ? '#fca5a5' : '#86efac',
                    border: `1px solid ${isSuspicious ? '#ef4444' : '#10b981'}`
                  }}
                >
                  {indicator.replace('_', ' ').toUpperCase()}
                </span>
              ))}
            </div>
          </div>

          {/* Validation Actions */}
          <div style={{ display: 'flex', gap: '8px' }}>
            <button
              onClick={() => handleValidation(true)}
              style={{
                flex: 1,
                background: 'rgba(239, 68, 68, 0.2)',
                color: '#fca5a5',
                border: '1px solid #ef4444',
                padding: '8px 16px',
                borderRadius: '6px',
                cursor: 'pointer',
                fontSize: '12px',
                fontWeight: '600'
              }}
            >
              <XCircle size={14} style={{ marginRight: '4px', display: 'inline' }} />
              Mark Suspicious
            </button>
            <button
              onClick={() => handleValidation(false)}
              style={{
                flex: 1,
                background: 'rgba(16, 185, 129, 0.2)',
                color: '#86efac',
                border: '1px solid #10b981',
                padding: '8px 16px',
                borderRadius: '6px',
                cursor: 'pointer',
                fontSize: '12px',
                fontWeight: '600'
              }}
            >
              <CheckCircle size={14} style={{ marginRight: '4px', display: 'inline' }} />
              Mark Legitimate
            </button>
          </div>
        </div>
      )}

      {/* Summary Stats */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(3, 1fr)',
        gap: '12px',
        padding: '12px',
        background: 'rgba(15, 23, 42, 0.5)',
        borderRadius: '6px'
      }}>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: '18px', fontWeight: '700', color: '#ef4444' }}>
            {summary?.high_risk_accounts || 0}
          </div>
          <div style={{ fontSize: '11px', color: '#64748b' }}>High Risk</div>
        </div>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: '18px', fontWeight: '700', color: '#f59e0b' }}>
            {summary?.medium_risk_accounts || 0}
          </div>
          <div style={{ fontSize: '11px', color: '#64748b' }}>Medium Risk</div>
        </div>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: '18px', fontWeight: '700', color: '#10b981' }}>
            {summary?.low_risk_accounts || 0}
          </div>
          <div style={{ fontSize: '11px', color: '#64748b' }}>Low Risk</div>
        </div>
      </div>
    </div>
  );
};

const UPICommunityComparison = ({ 
  analysisData, 
  onComparisonComplete,
  onValidationDataReady,
  compactMode = false
}) => {
  const [isComparing, setIsComparing] = useState(false);
  const [selectedAlgorithms, setSelectedAlgorithms] = useState(['louvain', 'leiden', 'label_propagation', 'infomap']);
  const [runAllAlgorithms, setRunAllAlgorithms] = useState(true);
  const [generateValidationBatch, setGenerateValidationBatch] = useState(true);
  const [topNValidation, setTopNValidation] = useState(50);
  const [comparisonResults, setComparisonResults] = useState(null);
  const [error, setError] = useState(null);
  const [showValidationInterface, setShowValidationInterface] = useState(false);

  const algorithms = [
    { value: 'louvain', label: 'Louvain', color: '#a855f7' },
    { value: 'leiden', label: 'Leiden', color: '#10b981' },
    { value: 'label_propagation', label: 'Label Propagation', color: '#3b82f6' },
    { value: 'infomap', label: 'Infomap', color: '#f59e0b' }
  ];

  const runComparison = useCallback(async () => {
    if (!analysisData || !analysisData.graph) {
      setError('No analysis data available. Please run UPI analysis first.');
      return;
    }

    setIsComparing(true);
    setError(null);

    try {
      const result = await chainbreakAPI.compareCommunities(analysisData.graph, {
        algorithms: runAllAlgorithms ? undefined : selectedAlgorithms,
        runAll: runAllAlgorithms,
        generateValidationBatch,
        topNValidation,
        exportResults: true,
      });

      const data = result.data;
      setComparisonResults(data);
      onComparisonComplete?.(data);

      if (generateValidationBatch && data.validation_batch) {
        onValidationDataReady?.(data.validation_batch);
      }

    } catch (err) {
      console.error('Community comparison failed:', err);
      setError(err.message);
    } finally {
      setIsComparing(false);
    }
  }, [analysisData, selectedAlgorithms, runAllAlgorithms, generateValidationBatch, topNValidation, onComparisonComplete, onValidationDataReady]);

  const getRankingIcon = (rank) => {
    if (rank === 1) return '🥇';
    if (rank === 2) return '🥈';
    if (rank === 3) return '🥉';
    return `${rank}`;
  };

  const getScoreColor = (score) => {
    if (score >= 0.8) return 'text-green-400';
    if (score >= 0.6) return 'text-yellow-400';
    if (score >= 0.4) return 'text-orange-400';
    return 'text-red-400';
  };

  const downloadResults = useCallback(() => {
    if (!comparisonResults) return;
    
    const blob = new Blob([JSON.stringify(comparisonResults, null, 2)], { 
      type: 'application/json' 
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `upi-community-comparison-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }, [comparisonResults]);

  const renderComparisonTable = () => {
    if (!comparisonResults || !comparisonResults.algorithm_results) return null;

    const { algorithm_results, ranking, stability_metrics } = comparisonResults;

    return (
      <div style={{ overflowX: 'auto' }}>
        <table style={{
          width: '100%',
          borderCollapse: 'collapse',
          fontSize: '12px',
          background: 'rgba(30, 41, 59, 0.5)',
          borderRadius: '8px',
          overflow: 'hidden'
        }}>
          <thead>
            <tr style={{ background: 'rgba(15, 23, 42, 0.8)' }}>
              <th style={{ padding: '12px 8px', textAlign: 'left', borderBottom: '1px solid #334155', color: '#e2e8f0', fontWeight: '600' }}>Rank</th>
              <th style={{ padding: '12px 8px', textAlign: 'left', borderBottom: '1px solid #334155', color: '#e2e8f0', fontWeight: '600' }}>Algorithm</th>
              <th style={{ padding: '12px 8px', textAlign: 'center', borderBottom: '1px solid #334155', color: '#e2e8f0', fontWeight: '600' }}>Communities</th>
              <th style={{ padding: '12px 8px', textAlign: 'center', borderBottom: '1px solid #334155', color: '#e2e8f0', fontWeight: '600' }}>Modularity</th>
              <th style={{ padding: '12px 8px', textAlign: 'center', borderBottom: '1px solid #334155', color: '#e2e8f0', fontWeight: '600' }}>Avg Size</th>
              <th style={{ padding: '12px 8px', textAlign: 'center', borderBottom: '1px solid #334155', color: '#e2e8f0', fontWeight: '600' }}>Stability</th>
              <th style={{ padding: '12px 8px', textAlign: 'center', borderBottom: '1px solid #334155', color: '#e2e8f0', fontWeight: '600' }}>Suspicious</th>
              <th style={{ padding: '12px 8px', textAlign: 'center', borderBottom: '1px solid #334155', color: '#e2e8f0', fontWeight: '600' }}>Score</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(ranking)
              .sort(([,a], [,b]) => b - a)
              .map(([algorithm, score], index) => {
                const result = algorithm_results[algorithm];
                const algorithmInfo = algorithms.find(a => a.value === algorithm);
                
                return (
                  <tr
                    key={algorithm}
                    style={{
                      borderBottom: '1px solid #334155',
                      background: index % 2 === 0 ? 'rgba(30, 41, 59, 0.3)' : 'transparent'
                    }}
                  >
                    <td style={{ padding: '12px 8px', color: '#e2e8f0' }}>
                      <span style={{ fontSize: '16px', marginRight: '4px' }}>
                        {getRankingIcon(index + 1)}
                      </span>
                    </td>
                    <td style={{ padding: '12px 8px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <div style={{
                          width: '8px', height: '8px', borderRadius: '50%',
                          background: algorithmInfo?.color || '#64748b'
                        }} />
                        <span style={{ color: '#e2e8f0', fontWeight: '500' }}>
                          {algorithmInfo?.label || algorithm}
                        </span>
                      </div>
                    </td>
                    <td style={{ padding: '12px 8px', textAlign: 'center', color: '#94a3b8' }}>
                      {result?.num_communities || 0}
                    </td>
                    <td style={{ padding: '12px 8px', textAlign: 'center', color: '#94a3b8' }}>
                      {(result?.modularity || 0).toFixed(4)}
                    </td>
                    <td style={{ padding: '12px 8px', textAlign: 'center', color: '#94a3b8' }}>
                      {(result?.avg_community_size || 0).toFixed(1)}
                    </td>
                    <td style={{ padding: '12px 8px', textAlign: 'center', color: '#94a3b8' }}>
                      {(stability_metrics?.[algorithm] || 0).toFixed(3)}
                    </td>
                    <td style={{ padding: '12px 8px', textAlign: 'center' }}>
                      <span style={{
                        color: result?.suspicious_communities > 0 ? '#f59e0b' : '#10b981',
                        fontWeight: '600'
                      }}>
                        {result?.suspicious_communities || 0}
                      </span>
                    </td>
                    <td style={{ padding: '12px 8px', textAlign: 'center' }}>
                      <span className={getScoreColor(score)} style={{ fontWeight: '600' }}>
                        {(score * 100).toFixed(1)}%
                      </span>
                    </td>
                  </tr>
                );
              })}
          </tbody>
        </table>
      </div>
    );
  };

  return (
    <div className="space-y-4">
      {/* Header */}
      <div style={{
        background: compactMode 
          ? 'linear-gradient(135deg, #1e3a5f 0%, #0f172a 100%)'
          : 'linear-gradient(135deg, #1e3a5f 0%, #0f172a 100%)',
        borderRadius: compactMode ? '8px' : '10px',
        padding: compactMode ? '12px' : '16px',
        border: '1px solid rgba(59,130,246,0.2)'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <div style={{
            width: compactMode ? '24px' : '32px', 
            height: compactMode ? '24px' : '32px', 
            borderRadius: compactMode ? '6px' : '8px',
            background: 'linear-gradient(135deg, #f59e0b, #d97706)',
            display: 'flex', alignItems: 'center', justifyContent: 'center'
          }}>
            <BarChart3 size={compactMode ? 12 : 16} color="#fff" />
          </div>
          <div>
            <h3 style={{ 
              fontSize: compactMode ? '12px' : '14px', 
              fontWeight: '700', 
              color: '#f1f5f9', 
              margin: 0 
            }}>
              Algorithm Comparison
            </h3>
            {!compactMode && (
              <p style={{ fontSize: '11px', color: '#64748b', margin: 0 }}>
                Compare community detection algorithms for fraud detection
              </p>
            )}
          </div>
        </div>
      </div>

      {/* Configuration */}
      <div style={{
        background: 'rgba(30, 41, 59, 0.5)',
        borderRadius: '8px',
        padding: '16px',
        border: '1px solid #334155'
      }}>
        <h4 style={{ fontSize: '12px', fontWeight: '600', color: '#e2e8f0', marginBottom: '12px' }}>
          Comparison Configuration
        </h4>
        
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
          {/* Algorithm Selection */}
          <div>
            <label style={{ fontSize: '11px', color: '#94a3b8', display: 'block', marginBottom: '4px' }}>
              Algorithms
            </label>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              {algorithms.map(algo => (
                <label key={algo.value} style={{ 
                  display: 'flex', alignItems: 'center', gap: '6px',
                  fontSize: '11px', color: '#e2e8f0', cursor: 'pointer'
                }}>
                  <input
                    type="checkbox"
                    checked={runAllAlgorithms || selectedAlgorithms.includes(algo.value)}
                    onChange={(e) => {
                      if (runAllAlgorithms) {
                        setRunAllAlgorithms(false);
                        setSelectedAlgorithms([algo.value]);
                      } else {
                        if (e.target.checked) {
                          setSelectedAlgorithms(prev => [...prev, algo.value]);
                        } else {
                          setSelectedAlgorithms(prev => prev.filter(a => a !== algo.value));
                        }
                      }
                    }}
                    disabled={isComparing}
                  />
                  <div style={{
                    width: '8px', height: '8px', borderRadius: '50%',
                    background: algo.color
                  }} />
                  {algo.label}
                </label>
              ))}
            </div>
            <label style={{ 
              display: 'flex', alignItems: 'center', gap: '6px',
              fontSize: '11px', color: '#8b5cf6', cursor: 'pointer', marginTop: '8px'
            }}>
              <input
                type="checkbox"
                checked={runAllAlgorithms}
                onChange={(e) => setRunAllAlgorithms(e.target.checked)}
                disabled={isComparing}
              />
              Run All Algorithms
            </label>
          </div>

          {/* Validation Settings */}
          <div>
            <label style={{ fontSize: '11px', color: '#94a3b8', display: 'block', marginBottom: '4px' }}>
              Validation Settings
            </label>
            <label style={{ 
              display: 'flex', alignItems: 'center', gap: '6px',
              fontSize: '11px', color: '#e2e8f0', cursor: 'pointer', marginBottom: '8px'
            }}>
              <input
                type="checkbox"
                checked={generateValidationBatch}
                onChange={(e) => setGenerateValidationBatch(e.target.checked)}
                disabled={isComparing}
              />
              Generate Validation Batch
            </label>
            
            {generateValidationBatch && (
              <div>
                <label style={{ fontSize: '11px', color: '#94a3b8', display: 'block', marginBottom: '4px' }}>
                  Top N Accounts: {topNValidation}
                </label>
                <input
                  type="range"
                  min="10"
                  max="200"
                  step="10"
                  value={topNValidation}
                  onChange={(e) => setTopNValidation(parseInt(e.target.value))}
                  disabled={isComparing}
                  style={{ width: '100%' }}
                />
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Error Display */}
      {error && (
        <div style={{
          padding: '10px 12px', background: 'rgba(239, 68, 68, 0.1)',
          border: '1px solid rgba(239, 68, 68, 0.25)', borderRadius: '8px',
          color: '#fca5a5', fontSize: '12px', display: 'flex', gap: '8px',
          alignItems: 'flex-start'
        }}>
          <AlertTriangle size={14} style={{ flexShrink: 0, marginTop: '1px' }} />
          {error}
        </div>
      )}

      {/* Action Button */}
      <button
        onClick={runComparison}
        disabled={isComparing || !analysisData}
        style={{
          width: '100%',
          background: (isComparing || !analysisData)
            ? '#1e293b'
            : 'linear-gradient(135deg, #f59e0b, #d97706)',
          color: (isComparing || !analysisData) ? '#64748b' : '#ffffff',
          fontWeight: '700',
          padding: '12px',
          borderRadius: '8px',
          border: 'none',
          cursor: (isComparing || !analysisData) ? 'not-allowed' : 'pointer',
          fontSize: '13px',
          display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px',
          transition: 'all 0.2s',
          letterSpacing: '0.02em'
        }}
      >
        {isComparing ? (
          <>
            <div style={{
              width: '14px', height: '14px', borderRadius: '50%',
              border: '2px solid #ffffff',
              borderTopColor: 'transparent',
              animation: 'spin 1s linear infinite'
            }} />
            Comparing Algorithms...
          </>
        ) : (
          <>
            <BarChart3 size={14} />
            Run Comparison
          </>
        )}
      </button>

      {/* Results */}
      <AnimatePresence mode="wait">
        {comparisonResults && (
          <motion.div
            key="results"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
          >
            {/* Summary Stats */}
            <div style={{
              background: 'rgba(30, 41, 59, 0.5)',
              borderRadius: '8px',
              padding: '16px',
              border: '1px solid #334155',
              marginBottom: '16px'
            }}>
              <h4 style={{ fontSize: '13px', fontWeight: '600', color: '#e2e8f0', marginBottom: '12px' }}>
                Comparison Summary
              </h4>
              
              <div style={{
                display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
                gap: '12px'
              }}>
                <div style={{ textAlign: 'center' }}>
                  <div style={{ fontSize: '20px', fontWeight: '700', color: '#f59e0b' }}>
                    {Object.keys(comparisonResults.algorithm_results).length}
                  </div>
                  <div style={{ fontSize: '11px', color: '#94a3b8' }}>Algorithms Compared</div>
                </div>
                <div style={{ textAlign: 'center' }}>
                  <div style={{ fontSize: '20px', fontWeight: '700', color: '#10b981' }}>
                    {comparisonResults.graph_metrics?.num_nodes || 0}
                  </div>
                  <div style={{ fontSize: '11px', color: '#94a3b8' }}>Nodes Analyzed</div>
                </div>
                <div style={{ textAlign: 'center' }}>
                  <div style={{ fontSize: '20px', fontWeight: '700', color: '#3b82f6' }}>
                    {comparisonResults.graph_metrics?.num_edges || 0}
                  </div>
                  <div style={{ fontSize: '11px', color: '#94a3b8' }}>Edges Analyzed</div>
                </div>
                <div style={{ textAlign: 'center' }}>
                  <div style={{ fontSize: '20px', fontWeight: '700', color: '#ef4444' }}>
                    {Object.values(comparisonResults.algorithm_results)
                      .reduce((sum, result) => sum + (result.suspicious_communities || 0), 0)}
                  </div>
                  <div style={{ fontSize: '11px', color: '#94a3b8' }}>Suspicious Communities</div>
                </div>
              </div>
            </div>

            {/* Comparison Table */}
            <div style={{
              background: 'rgba(30, 41, 59, 0.5)',
              borderRadius: '8px',
              padding: '16px',
              border: '1px solid #334155',
              marginBottom: '16px'
            }}>
              <h4 style={{ fontSize: '13px', fontWeight: '600', color: '#e2e8f0', marginBottom: '12px' }}>
                Algorithm Performance Comparison
              </h4>
              {renderComparisonTable()}
            </div>

            {/* Actions */}
            <div style={{ display: 'flex', gap: '8px', marginBottom: '16px' }}>
              <button
                onClick={downloadResults}
                style={{
                  flex: 1,
                  background: '#1e293b',
                  color: '#94a3b8',
                  padding: '8px',
                  borderRadius: '6px',
                  border: '1px solid #334155',
                  cursor: 'pointer',
                  fontSize: '11px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '6px'
                }}
              >
                <Download size={12} />
                Export Results
              </button>
              
              {comparisonResults.validation_batch && (
                <button
                  onClick={() => setShowValidationInterface(!showValidationInterface)}
                  style={{
                    flex: 1,
                    background: 'linear-gradient(135deg, #8b5cf6, #6366f1)',
                    color: '#ffffff',
                    padding: '8px',
                    borderRadius: '6px',
                    border: 'none',
                    cursor: 'pointer',
                    fontSize: '11px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: '6px'
                  }}
                >
                  <Eye size={12} />
                  {showValidationInterface ? 'Hide' : 'Show'} Validation
                </button>
              )}
            </div>

            {/* Validation Interface */}
            <AnimatePresence>
              {showValidationInterface && comparisonResults.validation_batch && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  exit={{ opacity: 0, height: 0 }}
                >
                  <ValidationInterface 
                    validationBatch={comparisonResults.validation_batch}
                    summary={comparisonResults.validation_batch?.summary || {}}
                  />
                </motion.div>
              )}
            </AnimatePresence>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Keyframe for loader */}
      <style>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
};

export default UPICommunityComparison;
