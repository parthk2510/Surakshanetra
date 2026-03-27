// @ts-nocheck
"use client";
import React, { useState, useCallback, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Upload, XCircle, FileText, Loader, Download, Settings, Activity, Search, BarChart3, Database, Shield } from 'lucide-react';
import { analyzeTransactions } from './analysis';
import { normalizeGraphData } from '../utils/normalizeGraphData';
import { UPIStorageManager } from './UPIStorageManager';
import UPISettings, { loadUPISettings } from './UPISettings';
import ProfileSettings from './ProfileSettings';
import UPICommunityDetection from './UPICommunityDetection';
import { useTheme } from '../context/ThemeContext';
import usePermissions from '../hooks/usePermissions';

const SIDEBAR_DARK = {
  bg: '#0f172a', panel: '#1e293b', border: '#334155',
  text: '#e2e8f0', textMuted: '#94a3b8', textSecondary: '#cbd5e1',
  input: '#1e293b', inputBorder: '#475569', accent: '#3b82f6',
  success: '#22c55e', error: '#ef4444', warning: '#f59e0b',
};
const SIDEBAR_LIGHT = {
  bg: '#f8fafc', panel: '#ffffff', border: '#e2e8f0',
  text: '#0f172a', textMuted: '#64748b', textSecondary: '#475569',
  input: '#ffffff', inputBorder: '#cbd5e1', accent: '#2563eb',
  success: '#16a34a', error: '#dc2626', warning: '#d97706',
};

const API_BASE = '';

// ── Structured Logger with Backend Sync ──
const _logBuffer = [];
const _LOG_SYNC_INTERVAL_MS = 10000; // Sync every 10 seconds
let _syncTimer = null;

const _flushLogs = async () => {
  if (_logBuffer.length === 0) return;
  const batch = _logBuffer.splice(0, _logBuffer.length);
  try {
    await fetch(`${API_BASE}/api/logs/sync`, {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-TOKEN': document.cookie.match(/(^|;)\s*csrf_access_token\s*=\s*([^;]+)/)?.[2] || ''
      },
      body: JSON.stringify({ logs: batch }),
    });
  } catch {
    // If sync fails, discard — don't block the UI
  }
};

// Start periodic log sync
if (typeof window !== 'undefined' && !_syncTimer) {
  _syncTimer = setInterval(_flushLogs, _LOG_SYNC_INTERVAL_MS);
  window.addEventListener('beforeunload', _flushLogs);
}

const logger = {
  _log(level, msg, meta = {}) {
    const entry = {
      timestamp: new Date().toISOString(),
      level,
      action: `upi.mule_detection.${level.toLowerCase()}`,
      message: msg,
      component: 'UPIMuleDetection',
      ...meta,
    };
    _logBuffer.push(entry);
    const consoleFn = level === 'ERROR' ? console.error : level === 'WARN' ? console.warn : console.log;
    consoleFn(`[UPI_MULE] ${entry.timestamp} ${level}: ${msg}`, meta);
  },
  info: (msg, meta) => logger._log('INFO', msg, meta),
  warn: (msg, meta) => logger._log('WARN', msg, meta),
  error: (msg, meta) => logger._log('ERROR', msg, meta),
  debug: (msg, meta) => logger._log('DEBUG', msg, meta),
};

const UPIMuleDetection = ({
  onSubmit,
  onClusterSubmit,
  isLoading: externalLoading,
  onUPIAnalysisComplete,
  onUPIAnalysisClear
}) => {
  const { isDark } = useTheme();
  const SC = isDark ? SIDEBAR_DARK : SIDEBAR_LIGHT;
  const { isAdmin } = usePermissions();
  const [showProfileSettings, setShowProfileSettings] = useState(false);
  const [csvFile, setCsvFile] = useState(null);
  const [uploadStatus, setUploadStatus] = useState('idle');
  const [analysisData, setAnalysisData] = useState(null);
  const [error, setError] = useState(null);
  const [dragActive, setDragActive] = useState(false);
  const [progress, setProgress] = useState(0);
  const [progressLabel, setProgressLabel] = useState('');
  const [currentFileName, setCurrentFileName] = useState(null);
  const [showSettings, setShowSettings] = useState(false);
  const [backendAvailable, setBackendAvailable] = useState(null); // null=unknown, true/false
  const [neo4jAvailable, setNeo4jAvailable] = useState(false);
  const [showCommunityDetection, setShowCommunityDetection] = useState(false);
  const [communityResults, setCommunityResults] = useState(null);
  const [neo4jLoading, setNeo4jLoading] = useState(false);
  const mountedRef = useRef(true);
  const fileInputRef = useRef(null);
  const fileContentRef = useRef<string | null>(null);
  const analyzeViaFrontendRef = useRef<((content: string, settings: unknown) => Promise<unknown>) | null>(null);

  // ── Check UPI backend health on mount ──
  useEffect(() => {
    mountedRef.current = true;
    const checkHealth = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/upi/health`, { method: 'GET' });
        if (res.ok) {
          const json = await res.json();
          if (mountedRef.current) {
            const available = json?.data?.available === true;
            setBackendAvailable(available);
            setNeo4jAvailable(json?.data?.neo4j_connected === true);
            logger.info('UPI backend health check passed', { available, neo4j: json?.data?.neo4j_connected });
          }
        } else {
          if (mountedRef.current) { setBackendAvailable(false); setNeo4jAvailable(false); }
          logger.warn('UPI backend health check returned non-OK status');
        }
      } catch (err) {
        if (mountedRef.current) { setBackendAvailable(false); setNeo4jAvailable(false); }
        logger.warn('UPI backend unreachable, will use frontend-only analysis', { error: err.message });
      }
    };
    checkHealth();
    return () => { mountedRef.current = false; };
  }, []);

  useEffect(() => {
    const handleSettingsChanged = async () => {
      const content = fileContentRef.current;
      const fn = analyzeViaFrontendRef.current;
      if (!content || !fn) return;
      const customSettings = loadUPISettings();
      try {
        const result = await fn(content, customSettings);
        if (!mountedRef.current) return;
        setAnalysisData(result as any);
        if (onUPIAnalysisComplete) onUPIAnalysisComplete(result);
      } catch {
        // silent — keep previous result
      }
    };
    window.addEventListener('upi-settings-changed', handleSettingsChanged);
    return () => window.removeEventListener('upi-settings-changed', handleSettingsChanged);
  }, [onUPIAnalysisComplete]);

  // -- Handlers --
  const handleDrag = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  }, []);

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);

    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const file = e.dataTransfer.files[0];
      if (file.name.endsWith('.csv')) {
        setCsvFile(file);
        setError(null);
        logger.info(`CSV file dropped: ${file.name}`, { size: file.size });
      } else {
        setError('Only CSV files are supported');
      }
    }
  }, []);

  const handleFileChange = useCallback((e) => {
    const file = e.target.files?.[0];
    if (file) {
      setCsvFile(file);
      setError(null);
      logger.info(`CSV file selected: ${file.name}`, { size: file.size });
    }
  }, []);

  const parseCSVLocally = useCallback((content) => {
    const lines = content.trim().split('\n');
    if (lines.length < 2) throw new Error('CSV file is empty or has no data rows');
    const headers = lines[0].split(',').map(h => h.trim().toLowerCase());
    const getIndex = (name) => headers.findIndex(h => h.includes(name));
    const transactions = [];
    for (let i = 1; i < lines.length; i++) {
      const values = lines[i].split(',').map(v => v.trim());
      if (values.length < 3) continue;
      const senderUpi = values[getIndex('sender_upi')] || values[getIndex('sender')] || values[1];
      const receiverUpi = values[getIndex('receiver_upi')] || values[getIndex('receiver')] || values[2];
      const amount = parseFloat(values[getIndex('amount')] || values[3] || '0');
      const timestamp = values[getIndex('timestamp')] || values[4] || new Date().toISOString();
      if (!senderUpi || !receiverUpi) continue;
      transactions.push({
        id: values[getIndex('tx_id')] || `tx_${i}`,
        from: senderUpi, to: receiverUpi, amount, timestamp,
        status: values[getIndex('status')] || 'completed',
        pattern: values[getIndex('pattern')] || '',
        label: values[getIndex('label')] || ''
      });
    }
    return transactions;
  }, []);

  const analyzeViaBackend = useCallback(async (fileContent, settings) => {
    const formData = new FormData();
    formData.append('file', csvFile);
    if (settings) formData.append('settings', JSON.stringify(settings));

    logger.info('Sending CSV to backend for analysis...', { fileName: csvFile?.name, size: csvFile?.size });

    const response = await fetch(`${API_BASE}/api/upi/analyze`, {
      method: 'POST',
      body: formData,
      credentials: 'include',
      headers: {
        'X-CSRF-TOKEN': document.cookie.match(/(^|;)\s*csrf_access_token\s*=\s*([^;]+)/)?.[2] || ''
      }
    });

    if (!response.ok) {
      let errorMessage = `Backend returned ${response.status}`;
      try {
        const errBody = await response.json();
        errorMessage = errBody?.error || errorMessage;
      } catch { /* ignore parse error */ }
      logger.error('Backend analysis failed', { status: response.status, error: errorMessage });
      throw new Error(errorMessage);
    }

    const responseJson = await response.json();

    // Backend wraps result in { success: true, data: { graph, risk, metadata } }
    if (responseJson.success && responseJson.data) {
      logger.info('Backend analysis succeeded', {
        nodes: responseJson.data?.graph?.nodes?.length,
        edges: responseJson.data?.graph?.edges?.length,
        clusterRisk: responseJson.data?.risk?.clusterRiskScore
      });
      return responseJson.data;
    } else if (responseJson.success === false) {
      throw new Error(responseJson.error || 'Backend analysis returned failure');
    }

    // Fallback: return raw response (shouldn't happen with proper API)
    return responseJson;
  }, [csvFile]);

  const analyzeViaFrontend = useCallback(async (fileContent, settings) => {
    setProgressLabel('Parsing CSV rows…');
    const transactions = parseCSVLocally(fileContent);
    if (!Array.isArray(transactions) || transactions.length === 0) {
      throw new Error('No valid transactions found in CSV');
    }
    logger.info(`Parsed ${transactions.length} transactions locally`);
    setProgress(45);
    setProgressLabel('Extracting UPI identities…');

    // Extract unique UPI IDs from transactions to pass as focusUpiIds (1st arg)
    const uniqueUpiIds = [
      ...new Set(transactions.flatMap(tx => [tx.from, tx.to].filter(Boolean)))
    ];
    logger.debug(`Extracted ${uniqueUpiIds.length} unique UPI IDs`);

    setProgress(60);
    setProgressLabel('Running heuristic risk scoring…');
    // analyzeTransactions(focusUpiIds, transactions, options, nodeAttributes)
    const rawResult = analyzeTransactions(uniqueUpiIds, transactions, settings ?? {});
    setProgress(78);
    setProgressLabel('Building graph structure…');

    // Run through adapter to guarantee safe structure
    return normalizeGraphData(rawResult);
  }, [parseCSVLocally]);

  analyzeViaFrontendRef.current = analyzeViaFrontend;

  const analyzeCSV = useCallback(async () => {
    if (!csvFile) return;
    setUploadStatus('processing');
    setError(null);
    setProgress(5);
    setProgressLabel('Reading file…');

    const analysisStart = performance.now();

    try {
      const fileContent = await csvFile.text();
      fileContentRef.current = fileContent;
      const customSettings = loadUPISettings();
      logger.debug('Loaded custom settings', { hasSettings: !!customSettings });
      setProgress(15);
      setProgressLabel('Loading settings…');

      let analysisResult;
      let analysisSource = 'unknown';

      // Try backend first (if health check passed)
      if (backendAvailable !== false) {
        try {
          setProgress(25);
          setProgressLabel('Sending to analysis engine…');
          const backendResponse = await analyzeViaBackend(fileContent, customSettings);
          analysisSource = 'backend';
          logger.info('Backend analysis completed successfully');
          setProgress(70);
          setProgressLabel('Normalizing graph data…');
          // Normalize backend response through adapter
          analysisResult = normalizeGraphData(backendResponse);
        } catch (backendErr) {
          logger.warn(`Backend analysis failed, falling back to frontend: ${backendErr.message}`);
          // Show user-friendly error message
          if (backendErr.message.includes('No valid transactions found')) {
            setError(`CSV parsing failed: ${backendErr.message}. Please check your CSV format and ensure it has valid UPI addresses and amounts.`);
          } else if (backendErr.message.includes('Missing required CSV columns')) {
            setError(`CSV format error: ${backendErr.message}. Required columns: sender_upi, receiver_upi, amount_inr, timestamp.`);
          } else {
            setError(`Backend error: ${backendErr.message}. Falling back to frontend analysis...`);
          }
          // Fall through to frontend analysis
        }
      }

      // Fallback to frontend-only analysis
      if (!analysisResult) {
        analysisSource = 'frontend';
        logger.info('Running frontend-only analysis (backend unavailable)');
        setProgress(30);
        setProgressLabel('Parsing transactions…');
        try {
          analysisResult = await analyzeViaFrontend(fileContent, customSettings);
          // Clear any previous backend errors if frontend succeeds
          setError(null);
          setProgress(75);
          setProgressLabel('Computing risk scores…');
        } catch (frontendErr) {
          logger.error('Frontend analysis also failed', { error: frontendErr.message });
          setError(`Analysis failed: ${frontendErr.message}. Please check your CSV file format.`);
          setUploadStatus('error');
          setProgress(0);
          setProgressLabel('');
          _flushLogs();
          return;
        }
      }

      setProgress(88);
      setProgressLabel('Building graph…');
      setAnalysisData(analysisResult);
      setCurrentFileName(csvFile.name);
      if (onUPIAnalysisComplete) {
        onUPIAnalysisComplete(analysisResult);
      }

      // Persist to local storage
      try {
        setProgress(95);
        setProgressLabel('Saving to history…');
        UPIStorageManager.saveAnalysis(csvFile.name, analysisResult);
      } catch (storageErr) {
        logger.warn('Failed to save analysis to storage', { error: storageErr.message });
      }

      setProgress(100);
      setProgressLabel('Complete');
      setUploadStatus('success');

      const elapsed = Math.round(performance.now() - analysisStart);
      logger.info('Analysis completed successfully', {
        source: analysisSource,
        durationMs: elapsed,
        nodes: analysisResult?.metadata?.totalNodes,
        edges: analysisResult?.metadata?.totalEdges,
        clusterRisk: analysisResult?.risk?.clusterRiskScore,
        fileName: csvFile.name
      });

      // Flush logs immediately after analysis
      _flushLogs();

    } catch (err) {
      logger.error('Analysis failed completely', { error: err.message, fileName: csvFile?.name });
      setError(err.message || 'Analysis failed');
      setUploadStatus('error');
      setProgress(0);
      setProgressLabel('');
      _flushLogs();
    }
  }, [csvFile, analyzeViaBackend, analyzeViaFrontend, backendAvailable, onUPIAnalysisComplete]);

  const handleLoadAnalysis = useCallback((caseData, fileName) => {
    try {
      // Handle both old format (fileName only) and new format (caseData, fileName)
      let data;
      let name;

      if (typeof caseData === 'string') {
        // Old format - load from localStorage
        data = UPIStorageManager.loadAnalysis(caseData);
        name = caseData;
      } else {
        // New format - use provided caseData
        data = caseData;
        name = fileName;
      }

      if (data) {
        // Normalize stored data through adapter (may be stale format)
        const normalizedData = normalizeGraphData(data);
        setAnalysisData(normalizedData);
        setCurrentFileName(name);
        setError(null);
        setUploadStatus('success');
        if (onUPIAnalysisComplete) {
          onUPIAnalysisComplete(normalizedData);
        }
      }
    } catch (err) {
      setError('Failed to load analysis: ' + err.message);
    }
  }, [onUPIAnalysisComplete]);

  const downloadResults = useCallback(() => {
    if (!analysisData) return;
    const results = {
      metadata: analysisData.metadata,
      nodes: analysisData.graph.nodes,
      edges: analysisData.graph.edges,
      risk: analysisData.risk,
      timestamp: new Date().toISOString()
    };
    const blob = new Blob([JSON.stringify(results, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `upi-mule-analysis-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }, [analysisData]);

  const resetAnalysis = useCallback(() => {
    setCsvFile(null);
    setUploadStatus('idle');
    setAnalysisData(null);
    setCurrentFileName(null);
    setError(null);
    setProgress(0);
    setProgressLabel('');
    setCommunityResults(null);
    setShowCommunityDetection(false);
    // Reset the file input so the same file can be re-selected
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
    if (onUPIAnalysisClear) {
      onUPIAnalysisClear();
    }
  }, [onUPIAnalysisClear]);


  const handleCommunityDetectionComplete = useCallback((results) => {
    setCommunityResults(results);
    logger.info('Community detection completed', {
      algorithm: results.algorithm,
      communities: results.summary?.total_communities,
      modularity: results.community_detection?.modularity,
      suspiciousCommunities: results.suspicious_communities?.length || 0
    });
  }, []);

  const handleSuspiciousCommunitiesFound = useCallback((suspiciousCommunities) => {
    logger.warn(`Found ${suspiciousCommunities.length} suspicious communities`, {
      highRisk: suspiciousCommunities.filter(c => c.riskLevel === 'high').length,
      criticalRisk: suspiciousCommunities.filter(c => c.riskLevel === 'critical').length
    });
  }, []);

  // ---- RENDER: Compact sidebar widget ----
  return (
    <>
      {/* UPI SIDEBAR WIDGET */}
      <div className="space-y-0">

        {/* Mode Banner */}
        <div style={{
          background: isDark ? 'linear-gradient(135deg, #1e3a5f 0%, #0f172a 100%)' : 'linear-gradient(135deg, #dbeafe 0%, #f0f9ff 100%)',
          borderRadius: '10px',
          padding: '16px 18px',
          marginBottom: '16px',
          border: `1px solid ${isDark ? 'rgba(59,130,246,0.2)' : 'rgba(59,130,246,0.3)'}`
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '8px' }}>
            <div style={{
              width: '32px', height: '32px', borderRadius: '8px',
              background: 'linear-gradient(135deg, #3b82f6, #6366f1)',
              display: 'flex', alignItems: 'center', justifyContent: 'center'
            }}>
              <Activity size={16} color="#fff" />
            </div>
            <div>
              <h3 style={{ fontSize: '14px', fontWeight: '700', color: SC.text, margin: 0 }}>UPI Mule Detection</h3>
              <p style={{ fontSize: '11px', color: SC.textMuted, margin: 0 }}>Upload CSV to analyze fraud networks</p>
            </div>
          </div>
        </div>

        {/* Upload Zone */}
        <div
          onDragEnter={handleDrag} onDragLeave={handleDrag} onDragOver={handleDrag} onDrop={handleDrop}
          style={{
            position: 'relative',
            border: `2px dashed ${dragActive ? SC.accent : SC.border}`,
            borderRadius: '10px',
            padding: '24px 16px',
            textAlign: 'center',
            transition: 'all 0.25s ease',
            backgroundColor: dragActive ? `${SC.accent}14` : `${SC.panel}80`,
            cursor: 'pointer',
            marginBottom: '12px'
          }}
        >
          <input
            ref={fileInputRef}
            type="file" accept=".csv" onChange={handleFileChange}
            style={{ position: 'absolute', inset: 0, opacity: 0, cursor: 'pointer' }}
            disabled={uploadStatus === 'processing'}
          />
          <AnimatePresence mode="wait">
            {csvFile ? (
              <motion.div
                key="file-selected"
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.95 }}
                style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}
              >
                <div style={{
                  width: '44px', height: '44px', borderRadius: '50%',
                  background: 'rgba(34, 197, 94, 0.15)', border: '1px solid rgba(34, 197, 94, 0.3)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: '10px'
                }}>
                  <FileText size={20} color="#22c55e" />
                </div>
                <p style={{ color: SC.text, fontSize: '13px', fontWeight: '600', maxWidth: '200px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{csvFile.name}</p>
                <p style={{ color: SC.textMuted, fontSize: '11px', marginTop: '2px' }}>{(csvFile.size / 1024).toFixed(1)} KB</p>
              </motion.div>
            ) : (
              <motion.div
                key="no-file"
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.95 }}
                style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}
              >
                <div style={{
                  width: '44px', height: '44px', borderRadius: '50%',
                  background: 'rgba(100, 116, 139, 0.15)', border: '1px solid rgba(100, 116, 139, 0.3)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: '10px'
                }}>
                  <Upload size={20} color="#94a3b8" />
                </div>
                <p style={{ color: SC.text, fontSize: '13px', fontWeight: '600' }}>Drop CSV Here</p>
                <p style={{ color: SC.textMuted, fontSize: '11px', marginTop: '2px' }}>or click to browse files</p>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* Error Display */}
        {error && (
          <div style={{
            padding: '10px 12px', background: 'rgba(239, 68, 68, 0.1)',
            border: '1px solid rgba(239, 68, 68, 0.25)', borderRadius: '8px',
            color: '#fca5a5', fontSize: '12px', display: 'flex', gap: '8px',
            alignItems: 'flex-start', marginBottom: '12px'
          }}>
            <XCircle size={14} style={{ flexShrink: 0, marginTop: '1px' }} /> {error}
          </div>
        )}

        {/* Analysis Progress Bar */}
        {uploadStatus === 'processing' && (
          <div style={{ marginBottom: '12px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
              <span style={{ fontSize: '11px', color: '#94a3b8', display: 'flex', alignItems: 'center', gap: '5px' }}>
                <motion.span
                  animate={{ opacity: [1, 0.4, 1] }}
                  transition={{ duration: 1.2, repeat: Infinity }}
                  style={{ display: 'inline-block', width: '5px', height: '5px', borderRadius: '50%', background: '#3b82f6', flexShrink: 0 }}
                />
                {progressLabel || 'Analyzing…'}
              </span>
              <span style={{ fontSize: '11px', color: '#3b82f6', fontWeight: '600' }}>{progress}%</span>
            </div>
            <div style={{ height: '4px', background: 'var(--surface-2, #1e293b)', borderRadius: '2px', overflow: 'hidden' }}>
              <motion.div
                animate={{ width: `${progress}%` }}
                transition={{ duration: 0.4, ease: 'easeOut' }}
                style={{ height: '100%', background: 'linear-gradient(90deg, #3b82f6, #6366f1)', borderRadius: '2px' }}
              />
            </div>
          </div>
        )}


        {/* Action Buttons */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginBottom: '16px' }}>
          <button
            onClick={analyzeCSV}
            disabled={!csvFile || uploadStatus === 'processing'}
            style={{
              width: '100%',
              background: (!csvFile || uploadStatus === 'processing')
                ? '#1e293b'
                : 'linear-gradient(135deg, #2563eb, #4f46e5)',
              color: (!csvFile || uploadStatus === 'processing') ? '#475569' : '#ffffff',
              fontWeight: '700',
              padding: '12px',
              borderRadius: '8px',
              border: 'none',
              cursor: (!csvFile || uploadStatus === 'processing') ? 'not-allowed' : 'pointer',
              fontSize: '13px',
              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px',
              transition: 'all 0.2s',
              letterSpacing: '0.02em',
              boxShadow: (csvFile && uploadStatus !== 'processing') ? '0 4px 12px rgba(37, 99, 235, 0.3)' : 'none'
            }}
          >
            {uploadStatus === 'processing' ? (
              <><Loader size={14} style={{ animation: 'spin 1s linear infinite' }} /> Analyzing...</>
            ) : (
              <><Search size={14} /> Analyze Transactions</>
            )}
          </button>

          <div style={{ display: 'flex', gap: '8px' }}>
            {analysisData && (
              <>
                <button
                  onClick={downloadResults}
                  style={{
                    flex: 1, background: SC.panel, color: SC.textMuted,
                    fontWeight: '500', padding: '9px', borderRadius: '8px',
                    border: `1px solid ${SC.border}`, cursor: 'pointer', fontSize: '12px',
                    display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px',
                    transition: 'all 0.2s'
                  }}
                >
                  <Download size={12} /> Export
                </button>
                <button
                  onClick={resetAnalysis}
                  style={{
                    flex: 1, background: SC.panel, color: SC.textMuted,
                    fontWeight: '500', padding: '9px', borderRadius: '8px',
                    border: `1px solid ${SC.border}`, cursor: 'pointer', fontSize: '12px',
                    transition: 'all 0.2s'
                  }}
                >
                  Clear
                </button>
              </>
            )}
            <button
              onClick={() => setShowSettings(true)}
              style={{
                background: SC.panel, color: SC.textMuted,
                padding: '9px 12px', borderRadius: '8px',
                border: `1px solid ${SC.border}`, cursor: 'pointer',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                transition: 'all 0.2s'
              }}
              title="Analysis Settings"
            >
              <Settings size={14} />
            </button>
          </div>

        </div>

        {/* Analysis Result Status */}
        {analysisData && (
          <div style={{
            background: 'rgba(34, 197, 94, 0.06)',
            border: '1px solid rgba(34, 197, 94, 0.2)',
            borderRadius: '8px',
            padding: '12px',
            marginBottom: '16px'
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
              <span style={{ fontSize: '12px', fontWeight: '600', color: '#4ade80' }}>Analysis Complete</span>
              <span style={{
                fontSize: '10px', padding: '3px 8px', borderRadius: '4px',
                fontWeight: '700',
                background: analysisData.risk?.clusterRiskScore >= 80 ? 'rgba(239, 68, 68, 0.2)' :
                  analysisData.risk?.clusterRiskScore >= 60 ? 'rgba(249, 115, 22, 0.2)' : 'rgba(234, 179, 8, 0.2)',
                color: analysisData.risk?.clusterRiskScore >= 80 ? '#f87171' :
                  analysisData.risk?.clusterRiskScore >= 60 ? '#fb923c' : '#facc15',
                border: `1px solid ${analysisData.risk?.clusterRiskScore >= 80 ? 'rgba(239,68,68,0.3)' :
                  analysisData.risk?.clusterRiskScore >= 60 ? 'rgba(249,115,22,0.3)' : 'rgba(234,179,8,0.3)'}`
              }}>
                Risk: {analysisData.risk?.clusterRiskScore}
              </span>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px' }}>
              <div style={{ fontSize: '11px', color: '#94a3b8' }}>
                Nodes: <span style={{ color: '#e2e8f0', fontWeight: '600' }}>{analysisData.metadata?.totalNodes}</span>
              </div>
              <div style={{ fontSize: '11px', color: '#94a3b8' }}>
                Edges: <span style={{ color: '#e2e8f0', fontWeight: '600' }}>{analysisData.metadata?.totalEdges}</span>
              </div>
            </div>
          </div>
        )}

      </div>

      <UPISettings
        isOpen={showSettings}
        onClose={() => setShowSettings(false)}
        onLoadCase={handleLoadAnalysis}
        currentAnalysis={analysisData}
      />
      {showProfileSettings && (
        <ProfileSettings
          isOpen={showProfileSettings}
          onClose={() => setShowProfileSettings(false)}
          user={null}
          initialTab="users"
        />
      )}

      {/* Community Detection Section */}
      {analysisData && (
        <div style={{ marginTop: '16px' }}>
          <button
            onClick={() => setShowCommunityDetection(!showCommunityDetection)}
            style={{
              width: '100%',
              background: 'linear-gradient(135deg, #8b5cf6, #6366f1)',
              color: '#ffffff',
              fontWeight: '600',
              padding: '12px',
              borderRadius: '8px',
              border: 'none',
              cursor: 'pointer',
              fontSize: '12px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '8px',
              transition: 'all 0.2s'
            }}
          >
            <BarChart3 size={14} />
            {showCommunityDetection ? 'Hide Community Detection' : 'Show Community Detection'}
          </button>
        </div>
      )}

      {showCommunityDetection && analysisData && (
        <div style={{ marginTop: '16px' }}>
          <UPICommunityDetection
            analysisData={analysisData}
            onCommunityDetectionComplete={handleCommunityDetectionComplete}
            onSuspiciousCommunitiesFound={handleSuspiciousCommunitiesFound}
          />
        </div>
      )}

      {/* Keyframe for loader spin */}
      <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
    </>
  );
};

export default UPIMuleDetection;
