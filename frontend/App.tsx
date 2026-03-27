'use client';
import React, { useState, useEffect, useCallback } from 'react';
import { Toaster } from 'react-hot-toast';
import usePermissions from './hooks/usePermissions';
import { Activity, XCircle, Eye, EyeOff, Search, LogOut, Shield, Globe, Sun, Moon, Home, Menu } from 'lucide-react';
import { Z } from './styles/z-layers';
import logger from './utils/logger';
import apiService, { chainbreakAPI, clearSession } from './utils/api';
import { setConfigGetter } from './utils/blockchainAPI';
import UPIMuleDetection from './components/UPIAddressInput';
import UPIGraphRenderer from './components/UPIGraphRenderer';
import GraphRenderer from './components/GraphRenderer';
import ForensicInspector from './components/ForensicInspector';
import InvestigationDashboard from './features/investigation/components/InvestigationDashboard';
import SettingsPanel from './components/SettingsPanel';
import LoginPage from './components/LoginPage';
import ProfileSettings from './components/ProfileSettings';
import AlgorithmComparisonTable from './components/AlgorithmComparisonTable';
import LogViewer from './components/LogViewer';
import { GraphErrorBoundary, InspectorErrorBoundary } from './components/ErrorBoundary';
import { ConfigProvider, useConfig } from './context/ConfigContext';
import { ThemeProvider, useTheme } from './context/ThemeContext';
import useForensicGraph from './hooks/useForensicGraph';
import useMempoolMonitor from './hooks/useMempoolMonitor';
import toast from 'react-hot-toast';
import './styles/forensic.css';

interface User {
  id?: string;
  username: string;
  email?: string;
  role: string;
}

interface BackendMode {
  backend_mode: string;
  neo4j_available: boolean;
  [key: string]: unknown;
}

interface AlgorithmResults {
  louvain: unknown;
  leiden: unknown;
  labelPropagation: unknown;
  infomap: unknown;
}

const DARK_COLORS = {
  bg: '#0a0f1a',
  sidebar: '#0f1628',
  sidebarBorder: '#1a2340',
  panel: '#111827',
  panelHover: '#1a2035',
  panelBorder: '#1e293b',
  headerBg: '#0d1424',
  headerBorder: '#1a2340',
  accent: '#2563eb',
  accentGlow: 'rgba(37, 99, 235, 0.15)',
  textPrimary: '#f1f5f9',
  textSecondary: '#94a3b8',
  textMuted: '#475569',
  textDim: '#334155',
  success: '#22c55e',
  danger: '#ef4444',
  warning: '#f59e0b',
  graphBg: '#030712',
};

const LIGHT_COLORS = {
  bg: '#f8fafc',
  sidebar: '#f1f5f9',
  sidebarBorder: '#e2e8f0',
  panel: '#ffffff',
  panelHover: '#f8fafc',
  panelBorder: '#e2e8f0',
  headerBg: '#f1f5f9',
  headerBorder: '#e2e8f0',
  accent: '#2563eb',
  accentGlow: 'rgba(37, 99, 235, 0.08)',
  textPrimary: '#0f172a',
  textSecondary: '#334155',
  textMuted: '#64748b',
  textDim: '#94a3b8',
  success: '#16a34a',
  danger: '#dc2626',
  warning: '#d97706',
  graphBg: '#ffffff',
};

const App = () => {
  const { isAdmin } = usePermissions();
  const { isDark, toggleTheme } = useTheme();
  const COLORS = isDark ? DARK_COLORS : LIGHT_COLORS;
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [currentUser, setCurrentUser] = useState<User | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [backendMode, setBackendMode] = useState<BackendMode | null>(null);
  const [systemStatus, setSystemStatus] = useState<unknown>(null);
  const [currentGraph, setCurrentGraph] = useState<unknown>(null);
  const [selectedNode, setSelectedNode] = useState<unknown>(null);
  const [availableGraphs, setAvailableGraphs] = useState<unknown[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [threatIntelData, setThreatIntelData] = useState<unknown>(null);
  const [viewMode, setViewMode] = useState('graph');
  const [profileOpen, setProfileOpen] = useState(false);
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const [inspectorNode, setInspectorNode] = useState<unknown>(null);
  const [clusterAddresses, setClusterAddresses] = useState<string[]>([]);
  const [algorithmResults, setAlgorithmResults] = useState<AlgorithmResults>({
    louvain: null,
    leiden: null,
    labelPropagation: null,
    infomap: null
  });
  const [upiAnalysisData, setUpiAnalysisData] = useState<unknown>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const {
    graphData: forensicGraphData,
    loading: forensicLoading,
    suspectAddresses,
    btcPrice,
    nodeStats,
    fetchAddressGraph,
    fetchClusterGraph,
  } = useForensicGraph();

  const {
    isMonitoring,
    activeAddressCount,
    startMonitoring,
    stopMonitoring,
    refreshMempool,
  } = useMempoolMonitor(clusterAddresses, clusterAddresses.length > 0);

  const clearWorkspaceState = useCallback(() => {
    setCurrentGraph(null);
    setSelectedNode(null);
    setUpiAnalysisData(null);
    setClusterAddresses([]);
    setAlgorithmResults({ louvain: null, leiden: null, labelPropagation: null, infomap: null });
    setThreatIntelData(null);
    setInspectorNode(null);
    setInspectorOpen(false);
  }, []);

  const handleLoginSuccess = useCallback((user: User) => {
    clearWorkspaceState();
    setIsAuthenticated(true);
    setCurrentUser(user);
    // Persist role so usePermissions() hook in child components sees isAdmin immediately
    if (user.role) {
      localStorage.setItem('chainbreak_role', user.role);
    }
    logger.audit('login', 'App', `User logged in: ${user.username}`, { role: user.role });
  }, [clearWorkspaceState]);

  const handleLogout = useCallback(async () => {
    try {
      logger.audit('logout', 'App', `User logged out: ${currentUser?.username}`, { role: currentUser?.role });
      try {
        await apiService.post('/api/auth/logout');
      } catch (e) {
        logger.warn('Logout API call failed, clearing local session anyway', e);
      }
    } catch (e) {
      logger.error('Error during logout', e);
    } finally {
      clearSession();
      clearWorkspaceState();
      setIsAuthenticated(false);
      setCurrentUser(null);
      toast.success('Logged out successfully');
    }
  }, [clearWorkspaceState, currentUser]);

  const checkBackendMode = useCallback(async () => {
    try {
      logger.info('Checking backend mode...');
      const response = await chainbreakAPI.getBackendMode();
      if (response.success) {
        setBackendMode(response.data as BackendMode);
        logger.info('Backend mode retrieved', response.data);
        return true;
      } else {
        throw new Error(response.error || 'Failed to get backend mode');
      }
    } catch (err) {
      logger.error('Backend mode check failed', err);
      const e = err as { response?: { status: number }; message?: string };
      const errorMsg = e.response?.status === 404 ?
        'Backend not found (404) - check if server is running on http://localhost:5000' :
        `Backend mode check failed: ${e.message}`;
      setError(errorMsg);
      toast.error(errorMsg);
      return false;
    }
  }, []);

  const checkSystemStatus = useCallback(async () => {
    try {
      logger.info('Checking system status...');
      const response = await chainbreakAPI.getSystemStatus();
      if (response.success) {
        setSystemStatus(response.data);
        return true;
      }
      throw new Error(response.error || 'Failed to get system status');
    } catch (err) {
      logger.error('System status check failed', err);
      const e = err as { message?: string };
      toast.error(`System status check failed: ${e.message}`);
      return false;
    }
  }, []);

  const loadAvailableGraphs = useCallback(async () => {
    try {
      logger.info('Loading available graphs...');
      const response = await chainbreakAPI.listGraphs();
      if (response.success) {
        setAvailableGraphs(response.files || []);
        return true;
      }
      throw new Error(response.error || 'Failed to load graphs');
    } catch (err) {
      logger.error('Failed to load available graphs', err);
      const e = err as { message?: string };
      toast.error(`Failed to load graphs: ${e.message}`);
      return false;
    }
  }, []);

  const initializeApp = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    logger.info('Starting app initialization...');
    try {
      const modeCheck = await checkBackendMode();
      if (!modeCheck) { setIsLoading(false); return; }
      await checkSystemStatus();
      await loadAvailableGraphs();
      logger.info('App initialization completed successfully');
      toast.success('ChainBreak initialized successfully');
    } catch (err) {
      logger.error('App initialization failed', err);
      const e = err as { message?: string };
      setError(`App initialization failed: ${e.message}`);
      toast.error(`App initialization failed: ${e.message}`);
    } finally {
      setIsLoading(false);
    }
  }, [checkBackendMode, checkSystemStatus, loadAvailableGraphs]);

  const handleAddressSubmit = useCallback(async (address: string, txLimit = 50) => {
    try {
      setIsLoading(true);
      setError(null);
      setClusterAddresses([address]);
      logger.info('Fetching graph for address', { address, txLimit });
      logger.audit('address_submit', 'App', `Submitted BTC address for analysis`, { address: address.slice(0, 12) + '...', txLimit });
      await fetchAddressGraph(address, txLimit);
      await loadAvailableGraphs();
    } catch (err) {
      logger.error('Address submission failed', err);
      const e = err as { message?: string };
      setError(`Failed to fetch graph: ${e.message}`);
    } finally {
      setIsLoading(false);
    }
  }, [fetchAddressGraph, loadAvailableGraphs]);

  const handleClusterSubmit = useCallback(async (addresses: string[], txLimit = 50) => {
    try {
      setIsLoading(true);
      setError(null);
      setClusterAddresses(addresses);
      toast.loading(`Analyzing cluster of ${addresses.length} addresses...`, { id: 'cluster-analysis' });
      await fetchClusterGraph(addresses, txLimit);
      toast.dismiss('cluster-analysis');
    } catch (err) {
      logger.error('Cluster submission failed', err);
      const e = err as { message?: string };
      setError(`Failed to fetch cluster graph: ${e.message}`);
      toast.dismiss('cluster-analysis');
    } finally {
      setIsLoading(false);
    }
  }, [fetchClusterGraph]);

  const handleNodeClick = useCallback((nodeData: unknown) => {
    if (!nodeData || typeof nodeData !== 'object') {
      setSelectedNode(null);
      setInspectorNode(null);
      setInspectorOpen(false);
      return;
    }
    const node = nodeData as { id?: string; label?: string; type?: string };
    if (!node.id && !node.label) {
      logger.warn('Invalid nodeData received:', nodeData);
      return;
    }
    try {
      if (node.type === 'address') {
        setInspectorNode(nodeData);
        setInspectorOpen(true);
      } else {
        setSelectedNode(nodeData);
      }
    } catch (e) {
      logger.error('Error handling node click:', e, nodeData);
    }
  }, []);

  const handleInspectorClose = useCallback(() => {
    setInspectorOpen(false);
    setInspectorNode(null);
  }, []);

  const handleGraphSelect = useCallback(async (graphName: string) => {
    try {
      setIsLoading(true);
      setError(null);
      const response = await chainbreakAPI.getGraph(graphName);
      setCurrentGraph(response);
      setSelectedNode(null);
      toast.success('Graph loaded successfully!');
    } catch (err) {
      logger.error('Failed to load selected graph', err);
      const e = err as { message?: string };
      setError(`Failed to load graph: ${e.message}`);
      toast.error(`Failed to load graph: ${e.message}`);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const handleRefresh = useCallback(async () => { await initializeApp(); }, [initializeApp]);
  const handleThreatIntelUpdate = useCallback((data: unknown) => { setThreatIntelData(data); }, []);
  const handleAlgorithmResult = useCallback((algorithmKey: keyof AlgorithmResults, result: unknown) => {
    setAlgorithmResults(prev => ({ ...prev, [algorithmKey]: result }));
  }, []);
  const handleUPIAnalysisComplete = useCallback((analysisResult: unknown) => {
    setUpiAnalysisData(analysisResult);
    setSelectedNode(null);
    const meta = analysisResult as Record<string, unknown>;
    logger.audit('upi_analysis_complete', 'App', 'UPI analysis completed', {
      nodes: (meta?.graph as Record<string, unknown>)?.nodes ? ((meta.graph as Record<string, unknown[]>).nodes as unknown[]).length : 0,
    });
  }, []);
  const handleUPIClear = useCallback(() => {
    setUpiAnalysisData(null);
    setSelectedNode(null);
    logger.audit('upi_analysis_cleared', 'App', 'UPI analysis data cleared');
  }, []);

  useEffect(() => {
    let inactivityTimer: ReturnType<typeof setTimeout>;
    const INACTIVITY_LIMIT = 30 * 60 * 1000;

    const resetTimer = () => {
      clearTimeout(inactivityTimer);
      if (isAuthenticated) {
        inactivityTimer = setTimeout(() => {
          handleLogout();
          toast.error('You have been logged out due to inactivity.');
        }, INACTIVITY_LIMIT);
      }
    };

    const handleUserActivity = () => resetTimer();

    if (isAuthenticated) {
      window.addEventListener('mousemove', handleUserActivity);
      window.addEventListener('keydown', handleUserActivity);
      window.addEventListener('scroll', handleUserActivity);
      window.addEventListener('click', handleUserActivity);
      resetTimer();
    }

    return () => {
      clearTimeout(inactivityTimer);
      window.removeEventListener('mousemove', handleUserActivity);
      window.removeEventListener('keydown', handleUserActivity);
      window.removeEventListener('scroll', handleUserActivity);
      window.removeEventListener('click', handleUserActivity);
    };
  }, [isAuthenticated, handleLogout]);

  useEffect(() => {
    const validateSession = async () => {
      const user = localStorage.getItem('chainbreak_user');
      if (user) {
        try {
          const data = await apiService.get('/api/auth/me');
          if (data.success && data.user) {
            setIsAuthenticated(true);
            setCurrentUser(data.user as User);
            localStorage.setItem('chainbreak_user', JSON.stringify(data.user));
            if (data.permissions) {
              localStorage.setItem('chainbreak_permissions', JSON.stringify(data.permissions));
            }
            if (data.role) {
              localStorage.setItem('chainbreak_role', data.role);
            }
          } else {
            localStorage.removeItem('chainbreak_user');
            localStorage.removeItem('chainbreak_permissions');
            localStorage.removeItem('chainbreak_role');
          }
        } catch (e) {
          logger.error('Session validation failed', e);
          localStorage.removeItem('chainbreak_user');
          localStorage.removeItem('chainbreak_permissions');
          localStorage.removeItem('chainbreak_role');
        }
      }
      setAuthLoading(false);
    };
    validateSession();
  }, []);

  useEffect(() => {
    if (isAuthenticated) initializeApp();
  }, [isAuthenticated, initializeApp]);

  if (authLoading) {
    return (
      <div style={{ minHeight: '100vh', background: COLORS.bg, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div style={{ width: '48px', height: '48px', border: `3px solid ${COLORS.accent}`, borderTopColor: 'transparent', borderRadius: '50%', animation: 'spin 0.8s linear infinite' }} />
        <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <LoginPage onLoginSuccess={handleLoginSuccess} />;
  }

  if (isLoading && !backendMode) {
    return (
      <div style={{ minHeight: '100vh', background: COLORS.bg, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div style={{ textAlign: 'center' }}>
          <div style={{ width: '56px', height: '56px', border: `3px solid ${COLORS.accent}`, borderTopColor: 'transparent', borderRadius: '50%', animation: 'spin 0.8s linear infinite', margin: '0 auto 16px' }} />
          <h2 style={{ fontSize: '18px', fontWeight: '600', color: COLORS.textPrimary, marginBottom: '8px' }}>Initializing ChainBreak</h2>
          <p style={{ color: COLORS.textMuted, fontSize: '14px' }}>Connecting to backend...</p>
        </div>
        <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
      </div>
    );
  }

  if (error && !backendMode) {
    return (
      <div style={{ minHeight: '100vh', background: COLORS.bg, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div style={{ maxWidth: '420px', textAlign: 'center', padding: '32px', background: 'rgba(239,68,68,0.06)', borderRadius: '12px', border: '1px solid rgba(239,68,68,0.2)' }}>
          <XCircle style={{ width: '48px', height: '48px', color: COLORS.danger, margin: '0 auto 16px' }} />
          <h2 style={{ fontSize: '18px', fontWeight: '600', color: '#fca5a5', marginBottom: '8px' }}>Connection Failed</h2>
          <p style={{ color: '#f87171', marginBottom: '16px', fontSize: '14px' }}>{error}</p>
          <div style={{ fontSize: '13px', color: '#fca5a5', textAlign: 'left', marginBottom: '20px', lineHeight: '1.8' }}>
            <p>• Ensure the backend server is running on http://localhost:5000</p>
            <p>• Check that all required dependencies are installed</p>
            <p>• Verify the backend configuration</p>
          </div>
          <button
            onClick={handleRefresh}
            style={{ padding: '10px 24px', background: COLORS.danger, color: '#fff', border: 'none', borderRadius: '8px', cursor: 'pointer', fontWeight: '600', fontSize: '14px' }}
          >
            Retry Connection
          </button>
        </div>
      </div>
    );
  }

  if (viewMode === 'investigation') {
    return (
      <div style={{ minHeight: '100vh', background: COLORS.bg }}>
        <Toaster position="top-right" toastOptions={{ duration: 4000, style: {
          background: isDark ? '#1f2937' : '#ffffff',
          color: isDark ? '#f9fafb' : '#0f172a',
          border: isDark ? '1px solid #374151' : '1px solid #e2e8f0',
          boxShadow: isDark ? 'none' : '0 4px 16px rgba(0,0,0,0.1)',
        }}} />
        {renderHeader()}
        <InvestigationDashboard />
        <InspectorErrorBoundary>
          <ForensicInspector node={inspectorNode} isOpen={inspectorOpen} onClose={handleInspectorClose} btcPrice={btcPrice} />
        </InspectorErrorBoundary>
        <SettingsPanel />
      </div>
    );
  }

  const upiGraphData = (() => {
    if (!upiAnalysisData) return null;
    const d = upiAnalysisData as Record<string, unknown>;
    const g = d.graph as Record<string, unknown> | undefined;
    if (g && Array.isArray(g.nodes) && (g.nodes as unknown[]).length > 0) return g;
    if (Array.isArray(d.nodes) && (d.nodes as unknown[]).length > 0) return d;
    const inner = d.data as Record<string, unknown> | undefined;
    if (inner) {
      const dg = (inner.graph || inner) as Record<string, unknown>;
      if (Array.isArray(dg.nodes) && (dg.nodes as unknown[]).length > 0) return dg;
    }
    console.warn('[App] upiAnalysisData present but no nodes found. Shape:', Object.keys(d));
    return null;
  })();

  const isUPIActive = !!(upiGraphData && Array.isArray((upiGraphData as Record<string, unknown>).nodes) && ((upiGraphData as Record<string, unknown>).nodes as unknown[]).length > 0);
  const activeGraphData = isUPIActive ? upiGraphData : (forensicGraphData || currentGraph);
  const hasGraph = isUPIActive || !!activeGraphData;
  const hasAlgorithmResults = Object.values(algorithmResults).some(r => r !== null);
  const showAlgorithmResults = !isUPIActive && hasAlgorithmResults;
  const upiMeta = upiAnalysisData as Record<string, unknown> | null;
  const upiNodes = upiGraphData ? ((upiGraphData as Record<string, unknown>).nodes as unknown[]) : [];
  const upiEdges = upiGraphData ? ((upiGraphData as Record<string, unknown>).edges as unknown[]) : [];
  const activeNodeCount = isUPIActive
    ? ((upiMeta?.metadata as Record<string, unknown>)?.totalNodes as number ?? upiNodes.length ?? 0)
    : ((activeGraphData as Record<string, unknown>)?.nodes as unknown[] | undefined)?.length || 0;
  const activeEdgeCount = isUPIActive
    ? ((upiMeta?.metadata as Record<string, unknown>)?.totalEdges as number ?? upiEdges.length ?? 0)
    : ((activeGraphData as Record<string, unknown>)?.edges as unknown[] | undefined)?.length || 0;

  function renderHeader() {
    return (
      <header style={{
        height: '52px',
        minHeight: '52px',
        background: 'var(--header-bg)',
        borderBottom: '1px solid var(--border)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 16px',
        zIndex: Z.HEADER,
        position: 'sticky',
        top: 0,
        flexShrink: 0,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          {/* Hamburger – only visible on tablet/mobile (≤1023px) via CSS class */}
          <button
            className="sidebar-toggle-btn"
            onClick={() => setSidebarOpen(prev => !prev)}
            style={{
              padding: '6px', borderRadius: '6px', border: 'none', cursor: 'pointer',
              background: 'transparent', color: 'var(--text-secondary)',
              display: 'flex', alignItems: 'center',
            }}
            title="Toggle sidebar"
          >
            <Menu size={18} />
          </button>
          <div style={{
            width: '30px', height: '30px', borderRadius: '8px',
            background: 'linear-gradient(135deg, #2563eb, #7c3aed)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            boxShadow: '0 2px 8px rgba(37, 99, 235, 0.3)'
          }}>
            <Shield size={16} color="#fff" />
          </div>
          <div>
            <h1 style={{ fontSize: '16px', fontWeight: '800', color: 'var(--text-primary)', margin: 0, letterSpacing: '-0.02em' }}>
              SurakshaNetra
            </h1>
          </div>
          {backendMode && (
            <div className="header-backend" style={{
              display: 'flex', alignItems: 'center', gap: '6px', marginLeft: '12px',
              padding: '4px 10px', borderRadius: '6px',
              background: backendMode.neo4j_available ? 'rgba(34,197,94,0.1)' : 'rgba(234,179,8,0.1)',
              border: `1px solid ${backendMode.neo4j_available ? 'rgba(34,197,94,0.2)' : 'rgba(234,179,8,0.2)'}`
            }}>
              <div style={{
                width: '6px', height: '6px', borderRadius: '50%',
                background: backendMode.neo4j_available ? COLORS.success : COLORS.warning,
                boxShadow: `0 0 6px ${backendMode.neo4j_available ? COLORS.success : COLORS.warning}`
              }} />
              <span style={{ fontSize: '11px', fontWeight: '600', color: backendMode.neo4j_available ? '#4ade80' : '#fbbf24' }}>
                {backendMode.backend_mode === 'neo4j' ? 'Neo4j' : 'JSON'}
              </span>
            </div>
          )}
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <button
            onClick={() => {
              const next = viewMode === 'graph' ? 'investigation' : 'graph';
              logger.audit('mode_switch', 'Header', `Switched to ${next} mode`);
              clearWorkspaceState();
              setViewMode(next);
            }}
            style={{
              display: 'flex', alignItems: 'center', gap: '6px',
              padding: '7px 10px', borderRadius: '6px', cursor: 'pointer',
              fontSize: '12px', fontWeight: '600', transition: 'all 0.2s',
              background: viewMode === 'investigation' ? COLORS.accent : COLORS.panel,
              color: viewMode === 'investigation' ? '#fff' : COLORS.textSecondary,
              border: viewMode === 'investigation' ? 'none' : `1px solid ${COLORS.panelBorder}`,
              whiteSpace: 'nowrap',
            }}
            title={viewMode === 'investigation' ? 'Switch to Blockchain Analysis' : 'Switch to Investigation Mode'}
          >
            <Search size={14} />
            <span className="header-mode-short">{viewMode === 'investigation' ? 'Blockchain' : 'Investigate'}</span>
            <span className="header-mode-full">{viewMode === 'investigation' ? 'Blockchain Mode' : 'Investigation Mode'}</span>
          </button>

          {/* Theme toggle */}
          <button
            onClick={toggleTheme}
            style={{
              padding: '7px 10px', borderRadius: '6px', border: 'none', cursor: 'pointer',
              background: isDark ? 'rgba(100,116,139,0.1)' : 'rgba(234,179,8,0.1)',
              color: isDark ? '#94a3b8' : '#fbbf24',
              display: 'flex', alignItems: 'center'
            }}
            title={isDark ? 'Switch to Light Mode' : 'Switch to Dark Mode'}
          >
            {isDark ? <Moon size={14} /> : <Sun size={14} />}
          </button>

          {currentUser && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginLeft: '4px' }}>
              <span className="header-role-badge" style={{
                fontSize: '10px', padding: '2px 8px', borderRadius: '4px', fontWeight: '600',
                background: currentUser.role === 'admin' ? 'rgba(124,58,237,0.2)' : 'rgba(37,99,235,0.15)',
                color: currentUser.role === 'admin' ? '#a78bfa' : '#60a5fa',
                border: `1px solid ${currentUser.role === 'admin' ? 'rgba(124,58,237,0.4)' : 'rgba(37,99,235,0.3)'}`,
                textTransform: 'uppercase',
                whiteSpace: 'nowrap',
              }}>
                {currentUser.role}
              </span>
              <button
                className="header-username"
                onClick={() => setProfileOpen(true)}
                style={{ fontSize: '12px', color: COLORS.textMuted, background: 'transparent', border: 'none', cursor: 'pointer', padding: '0 4px', whiteSpace: 'nowrap', maxWidth: '100px', overflow: 'hidden', textOverflow: 'ellipsis' }}
                title={`Profile: ${currentUser.username}`}
              >
                {currentUser.username}
              </button>
              <button
                className="header-home-btn"
                onClick={async () => { await handleLogout(); window.location.href = '/'; }}
                style={{
                  padding: '7px 10px', borderRadius: '6px', border: 'none', cursor: 'pointer',
                  background: 'rgba(100,116,139,0.1)', color: COLORS.textSecondary, display: 'flex', alignItems: 'center'
                }}
                title="Back to Home (logs you out)"
              >
                <Home size={14} />
              </button>
              <button
                onClick={handleLogout}
                style={{
                  padding: '7px 10px', borderRadius: '6px', border: 'none', cursor: 'pointer',
                  background: 'rgba(239,68,68,0.1)', color: '#f87171', display: 'flex', alignItems: 'center'
                }}
                title="Logout"
              >
                <LogOut size={14} />
              </button>
            </div>
          )}
        </div>
      </header>
    );
  }

  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column', background: 'var(--background)', color: 'var(--text-primary)', overflow: 'hidden' }}>
      <Toaster position="top-right" toastOptions={{ duration: 4000, style: {
        background: isDark ? '#1f2937' : '#ffffff',
        color: isDark ? '#f9fafb' : '#0f172a',
        border: isDark ? '1px solid #374151' : '1px solid #e2e8f0',
        boxShadow: isDark ? 'none' : '0 4px 16px rgba(0,0,0,0.1)',
      }}} />

      {renderHeader()}

      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>

        {/* Mobile overlay – closes sidebar when tapping outside */}
        <div
          className={`app-sidebar-overlay ${sidebarOpen ? 'sidebar-open' : ''}`}
          onClick={() => setSidebarOpen(false)}
        />

        <aside
          className={`app-sidebar ${sidebarOpen ? 'sidebar-open' : ''}`}
          style={{
            background: 'var(--sidebar-bg)',
            borderRight: '1px solid var(--border)',
            display: 'flex', flexDirection: 'column',
            overflowY: 'auto', overflowX: 'hidden',
          }}
        >
          <div style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '0' }}>

            <UPIMuleDetection
              onSubmit={handleAddressSubmit}
              onClusterSubmit={handleClusterSubmit}
              isLoading={isLoading || forensicLoading}
              onUPIAnalysisComplete={handleUPIAnalysisComplete}
              onUPIAnalysisClear={handleUPIClear}
            />

            {clusterAddresses.length > 0 && (
              <div style={{
                background: COLORS.panel, borderRadius: '10px',
                border: `1px solid ${COLORS.panelBorder}`, padding: '14px', marginTop: '12px'
              }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '10px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    {isMonitoring ? <Eye size={14} color="#4ade80" /> : <EyeOff size={14} color="#64748b" />}
                    <span style={{ fontSize: '12px', fontWeight: '600', color: COLORS.textPrimary }}>Mempool Monitor</span>
                  </div>
                  {isMonitoring && activeAddressCount > 0 && (
                    <span style={{
                      fontSize: '10px', padding: '2px 8px', borderRadius: '4px',
                      background: 'rgba(239,68,68,0.15)', color: '#f87171',
                      border: '1px solid rgba(239,68,68,0.3)', fontWeight: '600'
                    }}>
                      {activeAddressCount} Active
                    </span>
                  )}
                </div>
                <div style={{ display: 'flex', gap: '6px' }}>
                  {!isMonitoring ? (
                    <button onClick={startMonitoring} style={{
                      flex: 1, padding: '8px', background: 'rgba(34,197,94,0.15)',
                      color: '#4ade80', border: '1px solid rgba(34,197,94,0.3)',
                      borderRadius: '6px', cursor: 'pointer', fontSize: '11px', fontWeight: '600'
                    }}>
                      Start Monitoring
                    </button>
                  ) : (
                    <>
                      <button onClick={stopMonitoring} style={{
                        flex: 1, padding: '8px', background: 'rgba(239,68,68,0.15)',
                        color: '#f87171', border: '1px solid rgba(239,68,68,0.3)',
                        borderRadius: '6px', cursor: 'pointer', fontSize: '11px', fontWeight: '600'
                      }}>
                        Stop
                      </button>
                      <button onClick={refreshMempool} style={{
                        padding: '8px 12px', background: 'rgba(37,99,235,0.15)',
                        color: '#60a5fa', border: '1px solid rgba(37,99,235,0.3)',
                        borderRadius: '6px', cursor: 'pointer', fontSize: '11px', fontWeight: '600'
                      }}>
                        Refresh
                      </button>
                    </>
                  )}
                </div>
                <p style={{ fontSize: '10px', color: COLORS.textMuted, marginTop: '8px' }}>
                  {isMonitoring
                    ? `Monitoring ${clusterAddresses.length} addresses`
                    : 'Monitor addresses for unconfirmed txs'}
                </p>
              </div>
            )}

            {nodeStats && (
              <div style={{
                background: COLORS.panel, borderRadius: '10px',
                border: `1px solid ${COLORS.panelBorder}`, padding: '14px', marginTop: '12px'
              }}>
                <span style={{ fontSize: '11px', fontWeight: '700', color: COLORS.textMuted, textTransform: 'uppercase', letterSpacing: '0.08em', display: 'block', marginBottom: '10px' }}>
                  Graph Stats
                </span>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
                  {[
                    { label: 'Nodes', value: nodeStats.total, color: COLORS.textPrimary },
                    { label: 'Addresses', value: nodeStats.addresses, color: COLORS.textPrimary },
                    { label: 'Transactions', value: nodeStats.transactions, color: COLORS.textPrimary },
                    { label: 'Edges', value: nodeStats.totalEdges, color: COLORS.textPrimary },
                    ...(nodeStats.suspects > 0 ? [
                      { label: 'Suspects', value: nodeStats.suspects, color: '#f87171' },
                      { label: 'High-Prob', value: nodeStats.highProbabilityLinks, color: '#fb923c' },
                    ] : [])
                  ].map(({ label, value, color }) => (
                    <div key={label} style={{
                      background: COLORS.bg, padding: '8px 10px', borderRadius: '6px',
                      border: `1px solid ${COLORS.panelBorder}`,
                      boxShadow: isDark ? 'none' : '0 1px 3px rgba(0,0,0,0.06)',
                    }}>
                      <div style={{ fontSize: '14px', fontWeight: '700', color }}>{value}</div>
                      <div style={{ fontSize: '10px', color: COLORS.textMuted }}>{label}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}

          </div>
        </aside>

        <main style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', position: 'relative' }}>

          <div style={{
            height: '44px', minHeight: '44px',
            background: COLORS.headerBg,
            borderBottom: `1px solid ${COLORS.panelBorder}`,
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            padding: '0 20px'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <Activity size={15} color={COLORS.accent} />
              <span style={{ fontSize: '13px', fontWeight: '600', color: COLORS.textPrimary }}>
                {isUPIActive
                  ? 'UPI Transaction Network'
                  : (suspectAddresses.length > 0 ? 'Suspect Cluster Analysis' : 'Transaction Graph')}
              </span>
              {suspectAddresses.length > 0 && (
                <span style={{
                  fontSize: '10px', padding: '2px 8px', borderRadius: '4px',
                  background: 'rgba(239,68,68,0.15)', color: '#f87171',
                  border: '1px solid rgba(239,68,68,0.3)', fontWeight: '600'
                }}>
                  {suspectAddresses.length} Suspects
                </span>
              )}
              {hasGraph && (
                <span style={{ fontSize: '11px', color: COLORS.textMuted, marginLeft: '4px' }}>
                  {activeNodeCount} nodes · {activeEdgeCount} edges
                </span>
              )}
            </div>
          </div>

          <div style={{ flex: 1, position: 'relative', background: COLORS.graphBg, overflow: 'hidden' }}>
            {hasGraph ? (
              <GraphErrorBoundary onReset={() => {
                if (isUPIActive) {
                  handleUPIClear();
                } else {
                  setCurrentGraph(null);
                  setSelectedNode(null);
                }
              }}>
                {isUPIActive ? (
                  <UPIGraphRenderer
                    graphData={upiGraphData}
                    onNodeClick={handleNodeClick}
                    className="w-full h-full"
                  />
                ) : (
                  <GraphRenderer
                    graphData={activeGraphData}
                    onNodeClick={handleNodeClick}
                    className="w-full h-full"
                    illicitAddresses={((threatIntelData as Record<string, unknown>)?.illicitAddresses as never[]) || []}
                    onAlgorithmResult={handleAlgorithmResult}
                  />
                )}
              </GraphErrorBoundary>
            ) : (
              <div style={{
                display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
                height: '100%', position: 'relative'
              }}>
                <div style={{
                  position: 'absolute', inset: 0,
                  backgroundImage: isDark
                    ? 'radial-gradient(circle, rgba(255,255,255,0.06) 1px, transparent 1px)'
                    : 'radial-gradient(circle, rgba(0,0,0,0.07) 1px, transparent 1px)',
                  backgroundSize: '28px 28px',
                  opacity: 0.6,
                }} />

                <div style={{ position: 'relative', zIndex: 1, textAlign: 'center' }}>
                  <div style={{
                    width: '100px', height: '100px', borderRadius: '50%',
                    border: `2px dashed ${COLORS.textMuted}`,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    margin: '0 auto 24px',
                    animation: 'pulse-ring 3s ease-in-out infinite'
                  }}>
                    <div style={{
                      width: '60px', height: '60px', borderRadius: '50%',
                      background: isDark
                        ? `linear-gradient(135deg, ${COLORS.accentGlow}, transparent)`
                        : 'linear-gradient(135deg, rgba(37,99,235,0.08), transparent)',
                      display: 'flex', alignItems: 'center', justifyContent: 'center'
                    }}>
                      <Globe size={28} color={COLORS.textMuted} />
                    </div>
                  </div>

                  <h3 style={{ fontSize: '18px', fontWeight: '600', color: '#64748b', marginBottom: '8px' }}>
                    Ready to Analyze
                  </h3>
                  <p style={{ fontSize: '13px', color: COLORS.textMuted, maxWidth: '360px', lineHeight: '1.6' }}>
                    Upload a CSV file or enter a Bitcoin address in the sidebar to begin visualizing the transaction network graph.
                  </p>

                  <div style={{ display: 'flex', gap: '8px', justifyContent: 'center', marginTop: '20px', flexWrap: 'wrap' }}>
                    {[
                      { icon: '📄', label: 'Upload CSV' },
                      { icon: '🔗', label: 'Enter BTC Address' },
                      { icon: '🔍', label: 'Cluster Analysis' }
                    ].map(({ icon, label }) => (
                      <span key={label} style={{
                        fontSize: '11px', padding: '6px 12px', borderRadius: '6px',
                        background: COLORS.panel,
                        border: `1px solid ${COLORS.panelBorder}`,
                        boxShadow: isDark ? 'none' : '0 1px 3px rgba(0,0,0,0.08)',
                        color: COLORS.textSecondary, display: 'flex', alignItems: 'center', gap: '6px'
                      }}>
                        {icon} {label}
                      </span>
                    ))}
                  </div>
                </div>

                <style>{`
                  @keyframes pulse-ring {
                    0%, 100% { opacity: 0.5; transform: scale(1); }
                    50% { opacity: 1; transform: scale(1.05); }
                  }
                `}</style>
              </div>
            )}
          </div>

          {showAlgorithmResults && (
            <div style={{
              borderTop: `1px solid ${COLORS.panelBorder}`,
              maxHeight: '240px',
              overflowY: 'auto',
              background: COLORS.panel
            }}>
              <AlgorithmComparisonTable results={algorithmResults} />
            </div>
          )}
        </main>

      </div>

      <ProfileSettings isOpen={profileOpen} onClose={() => setProfileOpen(false)} user={currentUser} />
      <InspectorErrorBoundary>
        <ForensicInspector node={inspectorNode} isOpen={inspectorOpen} onClose={handleInspectorClose} btcPrice={btcPrice} />
      </InspectorErrorBoundary>
      <SettingsPanel />
    </div>
  );
};

const ConfigBridge = () => {
  const { config, toggleSettingsPanel } = useConfig();
  useEffect(() => { setConfigGetter(() => config); }, [config]);
  useEffect(() => {
    const handleOpenSettings = () => { toggleSettingsPanel(); };
    window.addEventListener('openSettings', handleOpenSettings);
    return () => window.removeEventListener('openSettings', handleOpenSettings);
  }, [toggleSettingsPanel]);
  return null;
};

const AppWithConfig = () => {
  return (
    <ThemeProvider>
      <ConfigProvider>
        <ConfigBridge />
        <App />
      </ConfigProvider>
    </ThemeProvider>
  );
};

export default AppWithConfig;
