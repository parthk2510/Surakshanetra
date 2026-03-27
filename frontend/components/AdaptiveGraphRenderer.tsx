// src/components/AdaptiveGraphRenderer.js
// ============================================================================
// ADAPTIVE GRAPH RENDERER - Automatically chooses between D3 and WebGL
// Based on graph size and user preferences from ConfigContext
// ============================================================================
import React, { useMemo } from 'react';
import { useConfig, GRAPH_RENDERER_MODES } from '../context/ConfigContext';
import GraphRenderer from './GraphRenderer';
import WebGLGraphRenderer from './WebGLGraphRenderer';
import logger from '../utils/logger';

/**
 * AdaptiveGraphRenderer - Smart wrapper that selects the best renderer
 * 
 * This component analyzes the graph data and user settings to automatically
 * choose between:
 * - D3.js (SVG): Best for smaller graphs (< 500 nodes), more interactive features
 * - Sigma.js (WebGL): Best for large graphs (500+ nodes), GPU-accelerated
 * 
 * The user can also manually override this in the Settings panel.
 */
const AdaptiveGraphRenderer = ({
    graphData,
    onNodeClick,
    className = '',
    illicitAddresses = [],
    onAlgorithmResult
}) => {
    const { config, shouldUseWebGL, getEffectiveRenderer } = useConfig();

    // Calculate node count from graph data
    const nodeCount = useMemo(() => {
        return graphData?.nodes?.length || 0;
    }, [graphData]);

    // Determine which renderer to use
    const rendererMode = useMemo(() => {
    // FORCE D3 RENDERER FOR ALL GRAPHS
    return GRAPH_RENDERER_MODES.D3_SVG;
    }, [nodeCount, getEffectiveRenderer, config.autoSelectRenderer, config.webglNodeThreshold, config.graphRenderer]);

    // Log performance recommendation
    useMemo(() => {
        if (nodeCount > 1000 && rendererMode === GRAPH_RENDERER_MODES.D3_SVG) {
            logger.warn(
                `Performance Warning: Rendering ${nodeCount} nodes with D3.js (SVG) may cause UI lag. ` +
                `Consider switching to WebGL renderer in Settings.`
            );
        }
    }, [nodeCount, rendererMode]);

    // Render the appropriate component
    if (rendererMode === GRAPH_RENDERER_MODES.WEBGL_SIGMA) {
        return (
            <WebGLGraphRenderer
                graphData={graphData}
                onNodeClick={onNodeClick}
                className={className}
                illicitAddresses={illicitAddresses}
                onAlgorithmResult={onAlgorithmResult}
            />
        );
    }

    // Default to D3 renderer
    return (
        <GraphRenderer
            graphData={graphData}
            onNodeClick={onNodeClick}
            className={className}
            illicitAddresses={illicitAddresses}
            onAlgorithmResult={onAlgorithmResult}
        />
    );
};

export default AdaptiveGraphRenderer;
