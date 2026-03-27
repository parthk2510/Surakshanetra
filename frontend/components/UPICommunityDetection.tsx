// @ts-nocheck
"use client";
import React, { useState, useCallback, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Network, Users, AlertTriangle, Settings, Download, BarChart3 } from 'lucide-react';
import { chainbreakAPI } from '../utils/api';

const API_BASE = '';

const UPICommunityDetection = ({
  analysisData,
  onCommunityDetectionComplete,
  onSuspiciousCommunitiesFound
}) => {
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [selectedAlgorithm, setSelectedAlgorithm] = useState('louvain');
  const [resolution, setResolution] = useState(1.0);
  const [minRiskScore, setMinRiskScore] = useState(60.0);
  const [minMembers, setMinMembers] = useState(3);
  const [useNeo4j, setUseNeo4j] = useState(false);
  const [results, setResults] = useState(null);
  const [error, setError] = useState(null);
  const cacheRef = useRef({});
  const lastAnalysisRef = useRef(null);

  // Clear cache when analysisData changes
  if (analysisData !== lastAnalysisRef.current) {
    lastAnalysisRef.current = analysisData;
    cacheRef.current = {};
  }

  // In-memory algorithms (standard /api/upi/communities/detect)
  const memoryAlgorithms = [
    { value: 'louvain', label: 'Louvain', description: 'Fast modularity optimization' },
    { value: 'label_propagation', label: 'Label Propagation', description: 'Fast, near-linear algorithm' },
    { value: 'leiden', label: 'Leiden', description: 'Guaranteed quality communities' },
    { value: 'infomap', label: 'Infomap', description: 'Information-theoretic approach' },
  ];
  // Neo4j algorithms (POST /api/upi/neo4j/community-detect)
  const neo4jAlgorithms = [
    { value: 'greedy_modularity', label: 'Greedy Modularity', description: 'Clauset-Newman-Moore (NetworkX)' },
    { value: 'label_prop', label: 'Label Propagation', description: 'Fast, near-linear algorithm' },
    { value: 'wcc', label: 'WCC', description: 'Weakly Connected Components' },
  ];
  const algorithms = useNeo4j ? neo4jAlgorithms : memoryAlgorithms;

  const detectCommunities = useCallback(async () => {
    // Neo4j mode doesn't require in-memory analysis data
    if (!useNeo4j && (!analysisData || !analysisData.graph)) {
      setError('No analysis data available. Please run UPI analysis first.');
      return;
    }

    const nodeCount = analysisData?.graph?.nodes?.length || 0;
    const edgeCount = analysisData?.graph?.edges?.length || 0;
    const cacheKey = `${useNeo4j ? 'neo4j' : 'mem'}_${selectedAlgorithm}_${resolution}_${nodeCount}_${edgeCount}`;

    if (cacheRef.current[cacheKey]) {
      const cached = cacheRef.current[cacheKey];
      setResults(cached);
      onCommunityDetectionComplete?.(cached);
      if (cached.suspicious_communities?.length > 0) {
        onSuspiciousCommunitiesFound?.(cached.suspicious_communities);
      }
      return;
    }

    setIsAnalyzing(true);
    setError(null);

    try {
      let data;

      if (useNeo4j) {
        // ── Neo4j-backed community detection ─────────────────────────────
        const res = await fetch(`${API_BASE}/api/upi/neo4j/community-detect`, {
          method: 'POST',
          credentials: 'include',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRF-TOKEN': document.cookie.match(/(^|;)\s*csrf_access_token\s*=\s*([^;]+)/)?.[2] || ''
          },
          body: JSON.stringify({
            algorithm: selectedAlgorithm,
            resolution,
            run_fingerprinting: false,
          }),
        });
        const json = await res.json();
        if (!json.success) throw new Error(json.error || 'Neo4j community detection failed');
        const cd = json.data?.communityDetection ?? json.data ?? {};
        data = {
          summary: {
            total_communities: cd.numCommunities ?? 0,
            high_risk_communities: (cd.communities ?? []).filter(c => c.riskLevel === 'critical' || c.riskLevel === 'high').length,
          },
          community_detection: {
            algorithm: cd.algorithm,
            modularity: cd.modularity ?? 0,
            num_communities: cd.numCommunities ?? 0,
          },
          suspicious_communities: (cd.communities ?? []).filter(c => c.muleCount > 0 || c.avgRiskScore >= 60).map(c => ({
            communityId: c.communityId,
            memberCount: c.memberCount,
            muleCount: c.muleCount,
            avgRiskScore: c.avgRiskScore,
            riskLevel: c.riskLevel,
          })),
          source: 'neo4j',
        };
      } else {
        // ── In-memory community detection ────────────────────────────────
        const result = await chainbreakAPI.detectCommunities(
          analysisData.graph,
          selectedAlgorithm,
          resolution,
          { minRiskScore, exportResults: true }
        );
        data = result.data;
      }

      setResults(data);
      cacheRef.current[cacheKey] = data;
      onCommunityDetectionComplete?.(data);
      if (data.suspicious_communities?.length > 0) {
        onSuspiciousCommunitiesFound?.(data.suspicious_communities);
      }

    } catch (err) {
      console.error('Community detection failed:', err);
      setError(err.message || 'Community detection failed');
    } finally {
      setIsAnalyzing(false);
    }
  }, [analysisData, selectedAlgorithm, resolution, minRiskScore, useNeo4j, onCommunityDetectionComplete, onSuspiciousCommunitiesFound]);

  const getRiskColor = (riskLevel) => {
    switch (riskLevel) {
      case 'critical': return 'text-red-400 bg-red-900/20 border-red-500/30';
      case 'high': return 'text-orange-400 bg-orange-900/20 border-orange-500/30';
      case 'medium': return 'text-yellow-400 bg-yellow-900/20 border-yellow-500/30';
      case 'low': return 'text-green-400 bg-green-900/20 border-green-500/30';
      default: return 'text-gray-400 bg-gray-900/20 border-gray-500/30';
    }
  };

  const downloadResults = useCallback(() => {
    if (!results) return;

    const blob = new Blob([JSON.stringify(results, null, 2)], {
      type: 'application/json'
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `upi-communities-${selectedAlgorithm}-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }, [results, selectedAlgorithm]);

  return (
    <div className="space-y-4">
      {/* Header */}
      <div style={{
        background: 'linear-gradient(135deg, #1e3a5f 0%, #0f172a 100%)',
        borderRadius: '10px',
        padding: '16px',
        border: '1px solid rgba(59,130,246,0.2)'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <div style={{
            width: '32px', height: '32px', borderRadius: '8px',
            background: 'linear-gradient(135deg, #8b5cf6, #6366f1)',
            display: 'flex', alignItems: 'center', justifyContent: 'center'
          }}>
            <Network size={16} color="#fff" />
          </div>
          <div>
            <h3 style={{ fontSize: '14px', fontWeight: '700', color: '#f1f5f9', margin: 0 }}>
              Community Detection
            </h3>
            <p style={{ fontSize: '11px', color: '#64748b', margin: 0 }}>
              Identify fraud networks using graph algorithms
            </p>
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
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
          <h4 style={{ fontSize: '12px', fontWeight: '600', color: '#e2e8f0', margin: 0 }}>
            Configuration
          </h4>
          {/* Neo4j mode toggle */}
          <label style={{
            display: 'flex', alignItems: 'center', gap: '6px', cursor: 'pointer',
            fontSize: '11px', color: useNeo4j ? '#4ade80' : '#94a3b8', fontWeight: '600'
          }}>
            <input
              type="checkbox"
              checked={useNeo4j}
              onChange={e => {
                setUseNeo4j(e.target.checked);
                setSelectedAlgorithm(e.target.checked ? 'greedy_modularity' : 'louvain');
                setResults(null);
              }}
              style={{ accentColor: '#4ade80', cursor: 'pointer' }}
            />
            Neo4j Mode
          </label>
        </div>

        {useNeo4j && (
          <div style={{
            marginBottom: '12px', padding: '8px 10px',
            background: 'rgba(34,197,94,0.08)', border: '1px solid rgba(34,197,94,0.2)',
            borderRadius: '6px', fontSize: '11px', color: '#86efac'
          }}>
            Running community detection directly on the Neo4j graph database.
            Analysis data upload is not required.
          </div>
        )}

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
          {/* Algorithm Selection */}
          <div>
            <label style={{ fontSize: '11px', color: '#94a3b8', display: 'block', marginBottom: '4px' }}>
              Algorithm
            </label>
            <select
              value={selectedAlgorithm}
              onChange={(e) => setSelectedAlgorithm(e.target.value)}
              disabled={isAnalyzing}
              style={{
                width: '100%',
                padding: '8px',
                background: '#1e293b',
                border: '1px solid #334155',
                borderRadius: '6px',
                color: '#e2e8f0',
                fontSize: '12px'
              }}
            >
              {algorithms.map(algo => (
                <option key={algo.value} value={algo.value}>
                  {algo.label} - {algo.description}
                </option>
              ))}
            </select>
          </div>

          {/* Resolution */}
          <div>
            <label style={{ fontSize: '11px', color: '#94a3b8', display: 'block', marginBottom: '4px' }}>
              Resolution: {resolution.toFixed(1)}
            </label>
            <input
              type="range"
              min="0.1"
              max="2.0"
              step="0.1"
              value={resolution}
              onChange={(e) => setResolution(parseFloat(e.target.value))}
              disabled={isAnalyzing}
              style={{ width: '100%' }}
            />
            <div style={{ fontSize: '10px', color: '#64748b', marginTop: '2px' }}>
              <span style={{ float: 'left' }}>Small communities</span>
              <span style={{ float: 'right' }}>Large communities</span>
            </div>
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginTop: '12px' }}>
          {/* Min Risk Score */}
          <div>
            <label style={{ fontSize: '11px', color: '#94a3b8', display: 'block', marginBottom: '4px' }}>
              Min Risk Score for Suspicious: {minRiskScore.toFixed(0)}
            </label>
            <input
              type="range"
              min="0"
              max="100"
              step="5"
              value={minRiskScore}
              onChange={(e) => setMinRiskScore(parseFloat(e.target.value))}
              disabled={isAnalyzing}
              style={{ width: '100%' }}
            />
          </div>

          {/* Min Members */}
          <div>
            <label style={{ fontSize: '11px', color: '#94a3b8', display: 'block', marginBottom: '4px' }}>
              Min Community Size: {minMembers}
            </label>
            <input
              type="range"
              min="2"
              max="20"
              step="1"
              value={minMembers}
              onChange={(e) => setMinMembers(parseInt(e.target.value))}
              disabled={isAnalyzing}
              style={{ width: '100%' }}
            />
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
        onClick={detectCommunities}
        disabled={isAnalyzing || (!useNeo4j && !analysisData)}
        style={{
          width: '100%',
          background: (isAnalyzing || (!useNeo4j && !analysisData))
            ? '#1e293b'
            : 'linear-gradient(135deg, #8b5cf6, #6366f1)',
          color: (isAnalyzing || (!useNeo4j && !analysisData)) ? '#64748b' : '#ffffff',
          fontWeight: '700',
          padding: '12px',
          borderRadius: '8px',
          border: 'none',
          cursor: (isAnalyzing || !analysisData) ? 'not-allowed' : 'pointer',
          fontSize: '13px',
          display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px',
          transition: 'all 0.2s',
          letterSpacing: '0.02em'
        }}
      >
        {isAnalyzing ? (
          <>
            <div style={{
              width: '14px', height: '14px', borderRadius: '50%',
              border: '2px solid #ffffff',
              borderTopColor: 'transparent',
              animation: 'spin 1s linear infinite'
            }} />
            Detecting Communities...
          </>
        ) : (
          <>
            <Network size={14} />
            Detect Communities
          </>
        )}
      </button>

      {/* Results */}
      <AnimatePresence mode="wait">
        {results && (
          <motion.div
            key="results"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            style={{
              background: 'rgba(30, 41, 59, 0.5)',
              borderRadius: '8px',
              padding: '16px',
              border: '1px solid #334155'
            }}
          >
            <h4 style={{ fontSize: '13px', fontWeight: '600', color: '#e2e8f0', marginBottom: '12px' }}>
              Community Detection Results
            </h4>

            {/* Summary */}
            <div style={{
              display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
              gap: '12px', marginBottom: '16px'
            }}>
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontSize: '20px', fontWeight: '700', color: '#8b5cf6' }}>
                  {results.summary?.total_communities || 0}
                </div>
                <div style={{ fontSize: '11px', color: '#94a3b8' }}>Communities</div>
              </div>
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontSize: '20px', fontWeight: '700', color: '#10b981' }}>
                  {(results.community_detection?.modularity || 0).toFixed(3)}
                </div>
                <div style={{ fontSize: '11px', color: '#94a3b8' }}>Modularity</div>
              </div>
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontSize: '20px', fontWeight: '700', color: '#f59e0b' }}>
                  {results.summary?.high_risk_communities || 0}
                </div>
                <div style={{ fontSize: '11px', color: '#94a3b8' }}>High Risk Communities</div>
              </div>
            </div>

            {/* Suspicious Communities */}
            {results.suspicious_communities && results.suspicious_communities.length > 0 && (
              <div style={{ marginBottom: '16px' }}>
                <h5 style={{
                  fontSize: '12px',
                  fontWeight: '600',
                  color: '#f59e0b',
                  marginBottom: '8px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px'
                }}>
                  <AlertTriangle size={14} />
                  Suspicious Communities ({results.suspicious_communities.length})
                </h5>

                <div style={{ spaceY: '8px' }}>
                  {results.suspicious_communities.slice(0, 3).map((community, index) => (
                    <div
                      key={community.communityId}
                      style={{
                        background: 'rgba(245, 158, 11, 0.1)',
                        border: '1px solid rgba(245, 158, 11, 0.3)',
                        borderRadius: '6px',
                        padding: '12px'
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                        <span style={{ fontSize: '11px', fontWeight: '600', color: '#f59e0b' }}>
                          Community {community.communityId}
                        </span>
                        <span className={`text-[10px] px-2 py-1 rounded border ${getRiskColor(community.riskLevel)}`}>
                          {community.riskLevel.toUpperCase()}
                        </span>
                      </div>
                      <div style={{ fontSize: '11px', color: '#94a3b8' }}>
                        <div>Members: {community.memberCount}</div>
                        <div>Avg Risk: {community.avgRiskScore?.toFixed(1)}</div>
                        <div>Total Amount: ₹{community.totalAmount?.toLocaleString()}</div>
                      </div>
                    </div>
                  ))}
                </div>

                {results.suspicious_communities.length > 3 && (
                  <div style={{ textAlign: 'center', marginTop: '8px' }}>
                    <span style={{ fontSize: '11px', color: '#64748b' }}>
                      ... and {results.suspicious_communities.length - 3} more
                    </span>
                  </div>
                )}
              </div>
            )}

            {/* Actions */}
            <div style={{ display: 'flex', gap: '8px' }}>
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
            </div>
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

export default UPICommunityDetection;
