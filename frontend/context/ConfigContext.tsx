'use client';
import React, { createContext, useContext, useState, useCallback, useEffect } from 'react';

export const ANALYSIS_MODES = {
    LITE_EXPLORER: 'LITE_EXPLORER',
    FORENSIC_DEEP_DIVE: 'FORENSIC_DEEP_DIVE'
};

export const GRAPH_RENDERER_MODES = {
    D3_SVG: 'D3_SVG',
    WEBGL_SIGMA: 'WEBGL_SIGMA'
};

const DEFAULT_CONFIG = {
    fetchLimit: 100,
    searchDepth: 1,
    analysisMode: ANALYSIS_MODES.LITE_EXPLORER,
    graphRenderer: GRAPH_RENDERER_MODES.D3_SVG,
    webglNodeThreshold: 500,
    autoSelectRenderer: true,
    showDust: true,
    dustThreshold: 1000,
    enableParallelFetch: true,
    rateLimitDelay: 250,
    maxConcurrentRequests: 5,
    autoRefreshInterval: 0,
    showRawData: false,
    graphLayout: 'force',
    enableDebugLogs: false,
    // ── RGCN / Decision Engine ──────────────────────────────────────────────
    enableRGCN: true,
    rgcnWeight: 0.55,
    communityWeight: 0.20,
    traditionalWeight: 0.25,
    enableDecisionEngine: true,
    showConfidenceScore: true,
    nodeSizeMetric: 'volume' as 'volume' | 'risk',
    enableEdgeBundling: true,
    showUPIDevices: false,
};

type Config = typeof DEFAULT_CONFIG;

interface ConfigContextValue {
    config: Config;
    isSettingsPanelOpen: boolean;
    setConfig: (key: keyof Config, value: unknown) => void;
    updateConfig: (updates: Partial<Config>) => void;
    resetConfig: () => void;
    toggleSettingsPanel: () => void;
    openSettingsPanel: () => void;
    closeSettingsPanel: () => void;
    getEffectiveFetchLimit: () => number;
    getAPIParams: () => Record<string, unknown>;
    isForensicMode: () => boolean;
    getEffectiveRenderer: (nodeCount?: number) => string;
    shouldUseWebGL: (nodeCount?: number) => boolean;
    ANALYSIS_MODES: typeof ANALYSIS_MODES;
    GRAPH_RENDERER_MODES: typeof GRAPH_RENDERER_MODES;
    DEFAULT_CONFIG: Config;
}

const ConfigContext = createContext<ConfigContextValue | null>(null);

const STORAGE_KEY = 'chainbreak_config';

export function ConfigProvider({ children }: { children: React.ReactNode }) {
    const [config, setConfigState] = useState<Config>(() => {
        try {
            const stored = localStorage.getItem(STORAGE_KEY);
            if (stored) {
                const parsed = JSON.parse(stored);
                return { ...DEFAULT_CONFIG, ...parsed };
            }
        } catch {
        }
        return DEFAULT_CONFIG;
    });

    const [isSettingsPanelOpen, setIsSettingsPanelOpen] = useState(false);

    useEffect(() => {
        try {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(config));
        } catch {
        }
    }, [config]);

    const setConfig = useCallback((key: keyof Config, value: unknown) => {
        setConfigState(prev => ({ ...prev, [key]: value }));
    }, []);

    const updateConfig = useCallback((updates: Partial<Config>) => {
        setConfigState(prev => ({ ...prev, ...updates }));
    }, []);

    const resetConfig = useCallback(() => {
        setConfigState(DEFAULT_CONFIG);
        localStorage.removeItem(STORAGE_KEY);
    }, []);

    const getEffectiveFetchLimit = useCallback(() => {
        if (config.analysisMode === ANALYSIS_MODES.LITE_EXPLORER) {
            return Math.min(config.fetchLimit, 50);
        }
        return Math.min(config.fetchLimit, 10000);
    }, [config.analysisMode, config.fetchLimit]);

    const getAPIParams = useCallback(() => {
        return {
            limit: getEffectiveFetchLimit(),
            mode: config.analysisMode,
            depth: config.searchDepth,
            show_dust: config.showDust,
            dust_threshold: config.dustThreshold,
            parallel: config.enableParallelFetch,
            max_concurrent: config.maxConcurrentRequests
        };
    }, [config, getEffectiveFetchLimit]);

    const isForensicMode = useCallback(() => {
        return config.analysisMode === ANALYSIS_MODES.FORENSIC_DEEP_DIVE;
    }, [config.analysisMode]);

    const getEffectiveRenderer = useCallback((nodeCount = 0) => {
        if (config.autoSelectRenderer && nodeCount > 0) {
            if (nodeCount > config.webglNodeThreshold) {
                return GRAPH_RENDERER_MODES.WEBGL_SIGMA;
            }
            return GRAPH_RENDERER_MODES.D3_SVG;
        }
        return config.graphRenderer;
    }, [config.autoSelectRenderer, config.graphRenderer, config.webglNodeThreshold]);

    const shouldUseWebGL = useCallback((nodeCount = 0) => {
        return getEffectiveRenderer(nodeCount) === GRAPH_RENDERER_MODES.WEBGL_SIGMA;
    }, [getEffectiveRenderer]);

    const toggleSettingsPanel = useCallback(() => {
        setIsSettingsPanelOpen(prev => !prev);
    }, []);

    const openSettingsPanel = useCallback(() => {
        setIsSettingsPanelOpen(true);
    }, []);

    const closeSettingsPanel = useCallback(() => {
        setIsSettingsPanelOpen(false);
    }, []);

    const contextValue: ConfigContextValue = {
        config,
        isSettingsPanelOpen,
        setConfig,
        updateConfig,
        resetConfig,
        toggleSettingsPanel,
        openSettingsPanel,
        closeSettingsPanel,
        getEffectiveFetchLimit,
        getAPIParams,
        isForensicMode,
        getEffectiveRenderer,
        shouldUseWebGL,
        ANALYSIS_MODES,
        GRAPH_RENDERER_MODES,
        DEFAULT_CONFIG
    };

    return (
        <ConfigContext.Provider value={contextValue}>
            {children}
        </ConfigContext.Provider>
    );
}

export function useConfig() {
    const context = useContext(ConfigContext);
    if (!context) {
        throw new Error('useConfig must be used within a ConfigProvider');
    }
    return context;
}

export function withConfig(Component: React.ComponentType<Record<string, unknown>>) {
    return function ConfiguredComponent(props: Record<string, unknown>) {
        const config = useConfig();
        return <Component {...props} config={config} />;
    };
}

export default ConfigContext;
