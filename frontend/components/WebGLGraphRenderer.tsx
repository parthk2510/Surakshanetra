// @ts-nocheck
"use client";
// src/components/WebGLGraphRenderer.js
// ============================================================================
// WEBGL GRAPH RENDERER - GPU-Accelerated Graph Visualization using Sigma.js
// Handles 10,000+ nodes efficiently by offloading to integrated GPU
// ============================================================================
import React, { useEffect, useRef, useState, useCallback, useMemo } from 'react';
import { motion } from 'framer-motion';
import {
    Loader2, AlertCircle, Play, Expand, Shrink, Image,
    Plus, Minus, Cpu, RotateCcw, ZoomIn, ZoomOut, Maximize2
} from 'lucide-react';
import Graph from 'graphology';
import Sigma from 'sigma';
import forceAtlas2 from 'graphology-layout-forceatlas2';
import FA2Layout from 'graphology-layout-forceatlas2/worker';
import circular from 'graphology-layout/circular';
import random from 'graphology-layout/random';
import logger from '../utils/logger';
import toast from 'react-hot-toast';

// Color schemes for communities
const COMMUNITY_COLORS = [
    '#6366f1', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6',
    '#06b6d4', '#ec4899', '#14b8a6', '#f97316', '#84cc16',
    '#a855f7', '#22c55e', '#eab308', '#3b82f6', '#d946ef'
];

// ============================================================================
// QUADTREE - O(log n) Spatial Index for Fast Hover Detection
// ============================================================================
class QuadTreeNode {
    constructor(bounds, capacity = 4) {
        this.bounds = bounds; // { x, y, width, height }
        this.capacity = capacity;
        this.points = [];
        this.divided = false;
        this.northeast = null;
        this.northwest = null;
        this.southeast = null;
        this.southwest = null;
    }

    contains(point) {
        return (
            point.x >= this.bounds.x &&
            point.x < this.bounds.x + this.bounds.width &&
            point.y >= this.bounds.y &&
            point.y < this.bounds.y + this.bounds.height
        );
    }

    intersects(range) {
        return !(
            range.x > this.bounds.x + this.bounds.width ||
            range.x + range.width < this.bounds.x ||
            range.y > this.bounds.y + this.bounds.height ||
            range.y + range.height < this.bounds.y
        );
    }

    subdivide() {
        const x = this.bounds.x;
        const y = this.bounds.y;
        const w = this.bounds.width / 2;
        const h = this.bounds.height / 2;

        this.northeast = new QuadTreeNode({ x: x + w, y: y, width: w, height: h }, this.capacity);
        this.northwest = new QuadTreeNode({ x: x, y: y, width: w, height: h }, this.capacity);
        this.southeast = new QuadTreeNode({ x: x + w, y: y + h, width: w, height: h }, this.capacity);
        this.southwest = new QuadTreeNode({ x: x, y: y + h, width: w, height: h }, this.capacity);
        this.divided = true;
    }

    insert(point) {
        if (!this.contains(point)) return false;

        if (this.points.length < this.capacity) {
            this.points.push(point);
            return true;
        }

        if (!this.divided) {
            this.subdivide();
        }

        return (
            this.northeast.insert(point) ||
            this.northwest.insert(point) ||
            this.southeast.insert(point) ||
            this.southwest.insert(point)
        );
    }

    query(range, found = []) {
        if (!this.intersects(range)) return found;

        for (const point of this.points) {
            if (
                point.x >= range.x &&
                point.x < range.x + range.width &&
                point.y >= range.y &&
                point.y < range.y + range.height
            ) {
                found.push(point);
            }
        }

        if (this.divided) {
            this.northwest.query(range, found);
            this.northeast.query(range, found);
            this.southwest.query(range, found);
            this.southeast.query(range, found);
        }

        return found;
    }

    // Find nearest point to a given coordinate
    findNearest(x, y, radius) {
        const range = {
            x: x - radius,
            y: y - radius,
            width: radius * 2,
            height: radius * 2
        };
        const candidates = this.query(range);

        let nearest = null;
        let minDist = Infinity;

        for (const point of candidates) {
            const dist = Math.sqrt((point.x - x) ** 2 + (point.y - y) ** 2);
            if (dist < minDist && dist <= radius) {
                minDist = dist;
                nearest = point;
            }
        }

        return nearest;
    }
}

const WebGLGraphRenderer = ({
    graphData,
    onNodeClick,
    className = '',
    illicitAddresses = [],
    onAlgorithmResult
}) => {
    // Refs
    const containerRef = useRef(null);
    const sigmaInstanceRef = useRef(null);
    const graphRef = useRef(null);
    const fa2LayoutRef = useRef(null);
    const quadtreeRef = useRef(null); // Quadtree for O(log n) hover detection
    const hoveredNodeRef = useRef(null); // Track hovered node WITHOUT causing re-renders

    // State
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState(null);
    const [layoutRunning, setLayoutRunning] = useState(false);
    const [communities, setCommunities] = useState(null);
    const [stats, setStats] = useState({ nodes: 0, edges: 0, fps: 0 });
    const [isFullscreen, setIsFullscreen] = useState(false);
    const [selectedNode, setSelectedNode] = useState(null);
    const [layoutProgress, setLayoutProgress] = useState(0);
    const [hoveredNode, setHoveredNode] = useState(null); // For tooltip display only
    const [tooltipPos, setTooltipPos] = useState({ x: 0, y: 0 }); // Tooltip position

    // Memoized illicit address set for O(1) lookup
    const illicitSet = useMemo(() => {
        return new Set(illicitAddresses.map(a => a.address));
    }, [illicitAddresses]);

    /**
     * Initialize Graphology graph from input data
     */
    const initializeGraph = useCallback(() => {
        if (!graphData) return null;

        try {
            logger.info('WebGL: Initializing graph with data', {
                nodes: graphData.nodes?.length || 0,
                edges: graphData.edges?.length || 0
            });

            const graph = new Graph({ multi: true, allowSelfLoops: false });

            // Add nodes
            const validNodes = (graphData.nodes || []).filter(n => n && n.id);
            const nodeIdSet = new Set();

            validNodes.forEach(node => {
                if (nodeIdSet.has(node.id)) return; // Skip duplicates
                nodeIdSet.add(node.id);

                const isIllicit = illicitSet.has(node.id);
                const isAddress = node.type === 'address';
                const isTransaction = node.type === 'transaction';

                // Determine node color
                let color = '#6366f1'; // default indigo
                if (isIllicit) {
                    color = '#ef4444'; // red for illicit
                } else if (isAddress && node.balance > 0) {
                    color = '#10b981'; // green for addresses with balance
                } else if (isAddress) {
                    color = '#6b7280'; // gray for empty addresses
                } else if (isTransaction) {
                    color = '#3b82f6'; // blue for transactions
                }

                // Calculate node size based on type and value
                let size = 5;
                if (isAddress) {
                    size = Math.max(4, Math.min(20, (node.balance || 0) / 1e9 + 4));
                } else if (isTransaction) {
                    size = Math.max(3, Math.min(15, (node.total_input_value || 0) / 1e9 + 3));
                }

                // NOTE: Sigma.js reserves 'type' for rendering program selection.
                // We store our custom type as 'nodeType' instead.
                graph.addNode(node.id, {
                    label: node.label || node.id.substring(0, 12) + '...',
                    x: node.x ?? Math.random() * 1000,
                    y: node.y ?? Math.random() * 1000,
                    size: size,
                    color: color,
                    // Store custom node type as 'nodeType' (NOT 'type' - reserved by Sigma)
                    nodeType: node.type || 'unknown',
                    originalColor: color,
                    // Store additional data for inspection
                    balance: node.balance || 0,
                    transaction_count: node.transaction_count || 0,
                    total_received: node.total_received || 0,
                    total_sent: node.total_sent || 0,
                    isIllicit: isIllicit
                });
            });

            // Add edges
            let edgeCount = 0;
            (graphData.edges || []).forEach((edge, index) => {
                const sourceId = typeof edge.source === 'object' ? edge.source?.id : edge.source;
                const targetId = typeof edge.target === 'object' ? edge.target?.id : edge.target;

                if (!sourceId || !targetId) return;
                if (sourceId === targetId) return; // No self-loops
                if (!graph.hasNode(sourceId) || !graph.hasNode(targetId)) return;

                try {
                    // NOTE: Sigma.js edge 'type' should be 'line' or 'arrow' only
                    graph.addEdge(sourceId, targetId, {
                        size: Math.max(0.5, Math.min(3, (edge.value || 0) / 1e8)),
                        color: edge.direction === 'incoming' ? '#10b98180' :
                            edge.direction === 'outgoing' ? '#ef444480' : '#94a3b880',
                        value: edge.value || 0
                        // Removed 'type' - let Sigma use default 'line'
                    });
                    edgeCount++;
                } catch (e) {
                    // Edge might already exist in multi-graph
                }
            });

            logger.info('WebGL: Graph initialized', {
                nodes: graph.order,
                edges: graph.size
            });

            graphRef.current = graph;
            setStats({ nodes: graph.order, edges: graph.size, fps: 60 });

            return graph;
        } catch (err) {
            logger.error('WebGL: Failed to initialize graph', err);
            setError(`Graph initialization failed: ${err.message}`);
            return null;
        }
    }, [graphData, illicitSet]);

    /**
     * Build Quadtree from graph nodes for fast spatial lookup
     */
    const buildQuadtree = useCallback((graph) => {
        if (!graph || graph.order === 0) return null;

        // Find bounds of all nodes
        let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
        graph.forEachNode((node, attrs) => {
            minX = Math.min(minX, attrs.x);
            minY = Math.min(minY, attrs.y);
            maxX = Math.max(maxX, attrs.x);
            maxY = Math.max(maxY, attrs.y);
        });

        // Add padding
        const padding = 100;
        const bounds = {
            x: minX - padding,
            y: minY - padding,
            width: (maxX - minX) + padding * 2,
            height: (maxY - minY) + padding * 2
        };

        const quadtree = new QuadTreeNode(bounds, 8);

        // Insert all nodes
        graph.forEachNode((node, attrs) => {
            quadtree.insert({
                id: node,
                x: attrs.x,
                y: attrs.y,
                size: attrs.size || 5,
                ...attrs
            });
        });

        logger.info(`WebGL: Built Quadtree with ${graph.order} nodes`);
        return quadtree;
    }, []);

    /**
     * Initialize Sigma.js WebGL renderer
     */
    const initializeSigma = useCallback((graph) => {
        if (!graph || !containerRef.current) return;

        try {
            // Cleanup existing instance
            if (sigmaInstanceRef.current) {
                sigmaInstanceRef.current.kill();
                sigmaInstanceRef.current = null;
            }

            // Apply initial layout
            if (graph.order > 0) {
                circular(graph, { scale: 500 });
            }

            // Build Quadtree for O(log n) hover detection
            quadtreeRef.current = buildQuadtree(graph);

            // Log performance info for large graphs
            if (graph.order > 10000) {
                logger.info(`WebGL: Initializing renderer for LARGE graph (${graph.order.toLocaleString()} nodes, ${graph.size.toLocaleString()} edges)`);
            }

            // Create Sigma instance with WebGL renderer - OPTIMIZED for 100K+ nodes
            const isLargeGraph = graph.order > 10000;
            const isHugeGraph = graph.order > 50000;
            const isMassiveGraph = graph.order > 100000;

            const sigma = new Sigma(graph, containerRef.current, {
                // Rendering settings - show labels for your 1998 nodes
                renderLabels: graph.order < 5000, // Increased from 500 to 5000
                labelSize: 10, // Slightly smaller for better fit
                labelWeight: 'normal',
                labelColor: { color: '#e2e8f0' }, // Softer white

                // Node settings
                defaultNodeColor: '#6366f1',
                defaultNodeType: 'circle',
                defaultNodeSize: 6, // ADD THIS - base size for nodes

                // Performance-optimized node reducer - MODIFY to preserve node attributes
                nodeReducer: (node, data) => ({
                    ...data,
                    highlighted: data.highlighted || false,
                    // Preserve original size and color from your data
                    size: data.size || 6,
                    color: data.color || data.originalColor || '#6366f1',
                    // Keep label for rendering
                    label: data.label || node.substring(0, 12) + '...'
                }),

                // Edge settings - make them more visible
                defaultEdgeColor: '#94a3b8', // Less transparent (remove the '70' alpha)
                defaultEdgeType: 'line',
                defaultEdgeSize: 1.2, // ADD THIS - thicker edges
                renderEdgeLabels: false,

                // Performance optimizations - adjusted thresholds
                hideEdgesOnMove: graph.size > 10000, // Increased threshold
                hideLabelsOnMove: graph.order > 5000, // Only hide labels when moving on very large graphs

                // Hover events - keep your custom quadtree
                enableEdgeHoverEvents: false,
                enableEdgeClickEvents: graph.size < 10000, // Enable for your graph size

                // Zoom settings - better defaults for 1998 nodes
                minCameraRatio: 0.05, // Less aggressive min zoom
                maxCameraRatio: 20, // Slightly reduced max zoom

                // Anti-aliasing - enable for better visuals
                antialiasing: true,

                // Z-index for better layering
                zIndex: true,

                // WebGL-specific optimizations
                allowInvalidContainer: true,
            });

            // Event handlers for clicks - FIXED: Prevent re-layout on click
            sigma.on('clickNode', ({ node, event }) => {
                // Prevent any default behavior that might trigger layout
                if (event && event.original) {
                    event.original.stopPropagation();
                }

                const nodeData = graph.getNodeAttributes(node);
                const clickedNodeData = { id: node, ...nodeData };

                // Store selected node in ref to avoid re-renders affecting layout
                setSelectedNode(clickedNodeData);

                if (onNodeClick) {
                    onNodeClick(clickedNodeData);
                }

                // Refresh only the rendering, not the layout
                sigma.refresh({ skipIndexation: true });
            });

            sigma.on('clickStage', ({ event }) => {
                // Prevent any default behavior
                if (event && event.original) {
                    event.original.stopPropagation();
                }

                setSelectedNode(null);
                setHoveredNode(null);
                if (onNodeClick) {
                    onNodeClick(null);
                }
            });

            // QUADTREE-BASED HOVER DETECTION - O(log n) instead of O(n)
            // This prevents lag with 10,000+ nodes
            let lastHoverCheck = 0;
            const HOVER_THROTTLE_MS = 16; // ~60fps max

            const handleMouseMove = (e) => {
                const now = Date.now();
                if (now - lastHoverCheck < HOVER_THROTTLE_MS) return;
                lastHoverCheck = now;

                if (!quadtreeRef.current || !sigma) return;

                const rect = containerRef.current.getBoundingClientRect();
                const mouseX = e.clientX - rect.left;
                const mouseY = e.clientY - rect.top;

                // Convert screen coordinates to graph coordinates
                const camera = sigma.getCamera();
                const graphCoords = sigma.viewportToGraph({ x: mouseX, y: mouseY });

                // Use quadtree for O(log n) nearest neighbor search
                const hoverRadius = 30 / camera.ratio; // Adjust radius based on zoom
                const nearestNode = quadtreeRef.current.findNearest(
                    graphCoords.x,
                    graphCoords.y,
                    hoverRadius
                );

                if (nearestNode) {
                    // Check if within node's visual radius
                    const nodeScreenPos = sigma.graphToViewport({ x: nearestNode.x, y: nearestNode.y });
                    const dist = Math.sqrt(
                        (mouseX - nodeScreenPos.x) ** 2 +
                        (mouseY - nodeScreenPos.y) ** 2
                    );
                    const nodeRadius = (nearestNode.size || 5) * camera.ratio * 2;

                    if (dist <= nodeRadius + 5) {
                        // Only update if different node
                        if (hoveredNodeRef.current?.id !== nearestNode.id) {
                            // Clear previous highlight
                            if (hoveredNodeRef.current) {
                                try {
                                    graph.setNodeAttribute(hoveredNodeRef.current.id, 'highlighted', false);
                                } catch (e) { /* Node may not exist */ }
                            }
                            // Set new highlight
                            hoveredNodeRef.current = nearestNode;
                            graph.setNodeAttribute(nearestNode.id, 'highlighted', true);
                            setHoveredNode(nearestNode);
                            sigma.refresh();
                        }
                        // Always update tooltip position
                        setTooltipPos({ x: e.clientX, y: e.clientY });
                    } else {
                        // Mouse moved outside node radius
                        if (hoveredNodeRef.current) {
                            try {
                                graph.setNodeAttribute(hoveredNodeRef.current.id, 'highlighted', false);
                                sigma.refresh();
                            } catch (e) { /* Node may not exist */ }
                            hoveredNodeRef.current = null;
                            setHoveredNode(null);
                        }
                    }
                } else {
                    // No node found nearby
                    if (hoveredNodeRef.current) {
                        try {
                            graph.setNodeAttribute(hoveredNodeRef.current.id, 'highlighted', false);
                            sigma.refresh();
                        } catch (e) { /* Node may not exist */ }
                        hoveredNodeRef.current = null;
                        setHoveredNode(null);
                    }
                }
            };

            // Attach optimized mouse handler
            containerRef.current.addEventListener('mousemove', handleMouseMove);

            // Store cleanup function
            sigma._quadtreeCleanup = () => {
                containerRef.current?.removeEventListener('mousemove', handleMouseMove);
            };

            sigmaInstanceRef.current = sigma;
            logger.info('WebGL: Sigma renderer initialized with Quadtree hover detection');

            return sigma;
        } catch (err) {
            logger.error('WebGL: Failed to initialize Sigma', err);
            setError(`WebGL renderer initialization failed: ${err.message}`);
            return null;
        }
    }, [onNodeClick, buildQuadtree]); // REMOVED hoveredNode - using ref instead

    /**
     * Run ForceAtlas2 layout algorithm (GPU-accelerated via Web Workers)
     */
    const runLayout = useCallback(() => {
        const graph = graphRef.current;
        if (!graph || graph.order === 0) return;

        setLayoutRunning(true);
        setLayoutProgress(0);

        try {
            // Stop existing layout if running
            if (fa2LayoutRef.current) {
                fa2LayoutRef.current.stop();
                fa2LayoutRef.current = null;
            }

            logger.info('WebGL: Starting ForceAtlas2 layout...');

            // Calculate optimal settings based on graph size
            const nodeCount = graph.order;
            const iterations = Math.min(500, Math.max(100, 1000 - nodeCount / 20));

            // Use Web Worker for large graphs (non-blocking)
            if (nodeCount > 1000) {
                const fa2Layout = new FA2Layout(graph, {
                    settings: {
                        barnesHutOptimize: true,
                        barnesHutTheta: 0.5,
                        scalingRatio: 10,
                        gravity: 1,
                        adjustSizes: true,
                        strongGravityMode: false,
                        slowDown: 1 + Math.log10(nodeCount)
                    }
                });

                fa2LayoutRef.current = fa2Layout;
                fa2Layout.start();

                // Auto-stop after calculated iterations
                const progressInterval = setInterval(() => {
                    setLayoutProgress(prev => {
                        const newProgress = Math.min(prev + 2, 100);
                        if (newProgress >= 100) {
                            clearInterval(progressInterval);
                            fa2Layout.stop();
                            setLayoutRunning(false);
                            // Rebuild quadtree after layout (node positions changed)
                            quadtreeRef.current = buildQuadtree(graph);
                            sigmaInstanceRef.current?.refresh();
                            toast.success('Layout complete!');
                            logger.info('WebGL: Layout complete, quadtree rebuilt');
                        }
                        return newProgress;
                    });
                }, iterations * 10 / 50);

            } else {
                // Synchronous layout for smaller graphs
                forceAtlas2.assign(graph, {
                    iterations: iterations,
                    settings: {
                        barnesHutOptimize: nodeCount > 500,
                        scalingRatio: 10,
                        gravity: 1,
                        adjustSizes: true
                    }
                });

                // Rebuild quadtree after layout (node positions changed)
                quadtreeRef.current = buildQuadtree(graph);

                setLayoutProgress(100);
                setLayoutRunning(false);
                sigmaInstanceRef.current?.refresh();
                toast.success('Layout complete!');
                logger.info('WebGL: Sync layout complete, quadtree rebuilt');
            }

            logger.info('WebGL: ForceAtlas2 layout applied');
        } catch (err) {
            logger.error('WebGL: Layout failed', err);
            setError(`Layout failed: ${err.message}`);
            setLayoutRunning(false);
        }
    }, [buildQuadtree]);

    /**
     * Stop running layout
     */
    const stopLayout = useCallback(() => {
        if (fa2LayoutRef.current) {
            fa2LayoutRef.current.stop();
            fa2LayoutRef.current = null;
        }
        setLayoutRunning(false);
        setLayoutProgress(0);
    }, []);

    /**
     * Apply community colors to nodes
     */
    const applyCommunityColors = useCallback((partition, numCommunities) => {
        const graph = graphRef.current;
        const sigma = sigmaInstanceRef.current;
        if (!graph || !sigma) {
            logger.warn('WebGL: Cannot apply community colors - graph or sigma not ready');
            return;
        }

        let coloredNodes = 0;
        let missingNodes = 0;

        // Apply colors to all nodes in partition
        Object.entries(partition).forEach(([nodeId, communityId]) => {
            try {
                if (graph.hasNode(nodeId)) {
                    const color = COMMUNITY_COLORS[communityId % COMMUNITY_COLORS.length];
                    graph.setNodeAttribute(nodeId, 'color', color);
                    coloredNodes++;
                } else {
                    missingNodes++;
                }
            } catch (e) {
                logger.warn(`WebGL: Could not color node ${nodeId}:`, e);
            }
        });

        // Force full refresh to ensure colors are applied
        try {
            sigma.refresh({ skipIndexation: false });
        } catch (e) {
            logger.warn('WebGL: Error during sigma refresh after coloring:', e);
        }

        logger.info(`WebGL: Applied ${numCommunities} community colors to ${coloredNodes} nodes (${missingNodes} missing)`);
    }, []);

    /**
     * Run Louvain community detection
     */
    const runLouvainAlgorithm = useCallback(async () => {
        try {
            setIsLoading(true);
            const graph = graphRef.current;
            if (!graph) throw new Error('No graph loaded');

            logger.info('WebGL: Running Louvain community detection...');

            // Prepare data for backend
            const graphData = {
                nodes: [],
                edges: []
            };

            graph.forEachNode((node, attrs) => {
                graphData.nodes.push({ id: node, label: attrs.label, type: attrs.type });
            });

            graph.forEachEdge((edge, attrs, source, target) => {
                graphData.edges.push({ source, target, value: attrs.value || 1 });
            });

            const response = await fetch('/api/louvain', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ...graphData, resolution: 1.0 })
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || `API error: ${response.status}`);
            }

            const result = await response.json();
            if (!result.success) throw new Error(result.error || 'Unknown API error');

            const data = result.data;
            setCommunities(data);
            applyCommunityColors(data.partition, data.num_communities);

            toast.success(
                `Found ${data.num_communities} communities! Modularity: ${data.modularity.toFixed(3)}`,
                { duration: 5000 }
            );

            if (onAlgorithmResult) {
                onAlgorithmResult('louvain', data);
            }

        } catch (err) {
            logger.error('WebGL: Louvain failed', err);
            toast.error(`Community detection failed: ${err.message}`);
        } finally {
            setIsLoading(false);
        }
    }, [applyCommunityColors, onAlgorithmResult]);

    /**
     * Run Leiden community detection
     */
    const runLeidenAlgorithm = useCallback(async () => {
        try {
            setIsLoading(true);
            const graph = graphRef.current;
            if (!graph) throw new Error('No graph loaded');

            logger.info('WebGL: Running Leiden community detection...');

            const graphData = {
                nodes: [],
                edges: []
            };

            graph.forEachNode((node, attrs) => {
                graphData.nodes.push({ id: node, label: attrs.label, type: attrs.type });
            });

            graph.forEachEdge((edge, attrs, source, target) => {
                graphData.edges.push({ source, target, value: attrs.value || 1 });
            });

            const response = await fetch('/api/leiden', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ...graphData, resolution: 1.0 })
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || `API error: ${response.status}`);
            }

            const result = await response.json();
            if (!result.success) throw new Error(result.error || 'Unknown API error');

            const data = result.data;
            setCommunities(data);
            applyCommunityColors(data.partition, data.num_communities);

            toast.success(
                `Leiden found ${data.num_communities} communities! Modularity: ${data.modularity.toFixed(3)}`,
                { duration: 5000 }
            );

            if (onAlgorithmResult) {
                onAlgorithmResult('leiden', data);
            }

        } catch (err) {
            logger.error('WebGL: Leiden failed', err);
            toast.error(`Leiden detection failed: ${err.message}`);
        } finally {
            setIsLoading(false);
        }
    }, [applyCommunityColors, onAlgorithmResult]);

    /**
     * Run Label Propagation
     */
    const runLabelPropagation = useCallback(async () => {
        try {
            setIsLoading(true);
            const graph = graphRef.current;
            if (!graph) throw new Error('No graph loaded');

            logger.info('WebGL: Running Label Propagation...');

            const graphData = {
                nodes: [],
                edges: []
            };

            graph.forEachNode((node, attrs) => {
                graphData.nodes.push({ id: node, label: attrs.label, type: attrs.type });
            });

            graph.forEachEdge((edge, attrs, source, target) => {
                graphData.edges.push({ source, target });
            });

            const response = await fetch('/api/label-propagation', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(graphData)
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || `API error: ${response.status}`);
            }

            const result = await response.json();
            if (!result.success) throw new Error(result.error || 'Unknown API error');

            const data = result.data;
            // Use modularity from backend (now calculated properly)
            const modularity = data.modularity ?? 0;
            setCommunities({ ...data, modularity });
            applyCommunityColors(data.partition, data.num_communities);

            toast.success(
                `Label Propagation found ${data.num_communities} communities! Modularity: ${modularity.toFixed(3)}`,
                { duration: 5000 }
            );

            if (onAlgorithmResult) {
                // Include modularity in the result
                onAlgorithmResult('labelPropagation', { ...data, modularity });
            }

        } catch (err) {
            logger.error('WebGL: Label Propagation failed', err);
            toast.error(`Label Propagation failed: ${err.message}`);
        } finally {
            setIsLoading(false);
        }
    }, [applyCommunityColors, onAlgorithmResult]);

    /**
     * Run Infomap community detection (flow-based)
     */
    const runInfomapAlgorithm = useCallback(async () => {
        try {
            setIsLoading(true);
            const graph = graphRef.current;
            if (!graph) throw new Error('No graph loaded');

            logger.info('WebGL: Running Infomap community detection (flow-based)...');

            const graphData = {
                nodes: [],
                edges: []
            };

            graph.forEachNode((node, attrs) => {
                graphData.nodes.push({ id: node, label: attrs.label, type: attrs.type });
            });

            graph.forEachEdge((edge, attrs, source, target) => {
                graphData.edges.push({ source, target, value: attrs.value || 1 });
            });

            const response = await fetch('/api/infomap', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    ...graphData,
                    num_trials: 10,
                    directed: true  // Bitcoin transactions are directed
                })
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || `API error: ${response.status}`);
            }

            const result = await response.json();
            if (!result.success) throw new Error(result.error || 'Unknown API error');

            const data = result.data;
            setCommunities(data);
            applyCommunityColors(data.partition, data.num_communities);

            toast.success(
                `Infomap found ${data.num_communities} communities! Codelength: ${data.codelength.toFixed(3)}, Modularity: ${data.modularity.toFixed(3)}`,
                { duration: 5000 }
            );

            if (onAlgorithmResult) {
                onAlgorithmResult('infomap', data);
            }

        } catch (err) {
            logger.error('WebGL: Infomap failed', err);
            toast.error(`Infomap detection failed: ${err.message}`);
        } finally {
            setIsLoading(false);
        }
    }, [applyCommunityColors, onAlgorithmResult]);

    /**
     * Camera controls
     */
    const zoomIn = useCallback(() => {
        const sigma = sigmaInstanceRef.current;
        if (!sigma) return;
        const camera = sigma.getCamera();
        camera.animatedZoom({ duration: 300, factor: 1.5 });
    }, []);

    const zoomOut = useCallback(() => {
        const sigma = sigmaInstanceRef.current;
        if (!sigma) return;
        const camera = sigma.getCamera();
        camera.animatedUnzoom({ duration: 300, factor: 1.5 });
    }, []);

    const resetCamera = useCallback(() => {
        const sigma = sigmaInstanceRef.current;
        if (!sigma) return;
        const camera = sigma.getCamera();
        camera.animatedReset({ duration: 300 });
    }, []);

    /**
     * Toggle fullscreen
     */
    const toggleFullscreen = useCallback(async () => {
        if (!containerRef.current) return;

        try {
            if (!document.fullscreenElement) {
                await containerRef.current.requestFullscreen();
                setIsFullscreen(true);
            } else {
                await document.exitFullscreen();
                setIsFullscreen(false);
            }
        } catch (err) {
            logger.error('Fullscreen toggle failed', err);
            toast.error('Failed to toggle fullscreen mode');
        }
    }, []);

    /**
     * Export graph as PNG
     */
    const exportAsImage = useCallback(() => {
        const sigma = sigmaInstanceRef.current;
        if (!sigma) return;

        try {
            // Get the canvas element
            const canvas = containerRef.current.querySelector('canvas');
            if (!canvas) throw new Error('Canvas not found');

            // Create download link
            const link = document.createElement('a');
            link.download = 'chainbreak_graph.png';
            link.href = canvas.toDataURL('image/png');
            link.click();

            toast.success('Graph exported as PNG');
            logger.info('WebGL: Graph exported as image');
        } catch (err) {
            logger.error('WebGL: Export failed', err);
            toast.error(`Export failed: ${err.message}`);
        }
    }, []);

    // Initialize on mount/data change
    useEffect(() => {
        if (!graphData) return;

        setError(null);
        setIsLoading(true);

        const graph = initializeGraph();
        if (graph) {
            initializeSigma(graph);
            setIsLoading(false);
        } else {
            setIsLoading(false);
        }

        return () => {
            if (fa2LayoutRef.current) {
                fa2LayoutRef.current.stop();
            }
            if (sigmaInstanceRef.current) {
                // Cleanup quadtree mouse handler
                if (sigmaInstanceRef.current._quadtreeCleanup) {
                    sigmaInstanceRef.current._quadtreeCleanup();
                }
                sigmaInstanceRef.current.kill();
            }
        };
    }, [graphData, initializeGraph, initializeSigma]);

    // Handle container resize
    useEffect(() => {
        const handleResize = () => {
            if (sigmaInstanceRef.current) {
                sigmaInstanceRef.current.refresh();
            }
        };

        window.addEventListener('resize', handleResize);
        return () => window.removeEventListener('resize', handleResize);
    }, []);

    return (
        <div className={`relative w-full h-full ${className}`}>
            {/* Graph Container */}
            <div
                ref={containerRef}
                className="w-full h-full bg-gray-900 rounded-lg overflow-hidden"
                style={{ 
                    minHeight: '400px',
                    minWidth: '400px',
                    position: 'absolute',
                    top: 0,
                    left: 0,
                    right: 0,
                    bottom: 0
                }}
            />

            {/* Loading Overlay */}
            {isLoading && (
                <div className="absolute inset-0 bg-gray-900/80 flex items-center justify-center z-10">
                    <div className="flex flex-col items-center space-y-4">
                        <Loader2 className="w-8 h-8 text-blue-500 animate-spin" />
                        <span className="text-white">Initializing WebGL Renderer...</span>
                    </div>
                </div>
            )}

            {/* Error Display */}
            {error && (
                <div className="absolute inset-0 bg-gray-900/80 flex items-center justify-center z-10">
                    <div className="flex flex-col items-center space-y-4 text-red-400">
                        <AlertCircle className="w-8 h-8" />
                        <span>{error}</span>
                    </div>
                </div>
            )}

            {/* Stats Bar */}
            <div className="absolute top-3 right-3 flex items-center space-x-2 bg-gray-800/90 px-3 py-1.5 rounded-lg border border-gray-700">
                <Cpu className="w-4 h-4 text-green-400" />
                <span className="text-xs text-gray-300">
                    {stats.nodes.toLocaleString()} nodes • {stats.edges.toLocaleString()} edges
                </span>
                <span className="text-xs text-green-400 font-mono">WebGL</span>
            </div>

            {/* Quadtree-optimized Hover Tooltip - FIXED: Better positioning */}
            {hoveredNode && containerRef.current && (
                <div
                    className="absolute z-50 pointer-events-none"
                    style={{
                        left: Math.min(
                            tooltipPos.x - containerRef.current.getBoundingClientRect().left + 15,
                            containerRef.current.offsetWidth - 320 // Keep tooltip within container
                        ),
                        top: Math.max(
                            10,
                            tooltipPos.y - containerRef.current.getBoundingClientRect().top + 15
                        ),
                        maxWidth: '300px'
                    }}
                >
                    <div className="bg-gray-900/95 backdrop-blur-sm border border-gray-600 rounded-lg p-3 shadow-xl">
                        <div className="flex items-center space-x-2 mb-2">
                            <div
                                className="w-3 h-3 rounded-full"
                                style={{ backgroundColor: hoveredNode.color || '#6366f1' }}
                            />
                            <span className="text-white font-medium text-sm truncate">
                                {hoveredNode.label || hoveredNode.id}
                            </span>
                            {hoveredNode.isIllicit && (
                                <span className="px-1.5 py-0.5 bg-red-500/20 text-red-400 text-xs rounded">
                                    ILLICIT
                                </span>
                            )}
                        </div>
                        <div className="text-xs text-gray-400 space-y-1">
                            <div className="flex justify-between">
                                <span>Type:</span>
                                <span className="text-gray-200 capitalize">{hoveredNode.nodeType || 'unknown'}</span>
                            </div>
                            {hoveredNode.nodeType === 'address' && (
                                <>
                                    <div className="flex justify-between">
                                        <span>Balance:</span>
                                        <span className="text-green-400 font-mono">
                                            {((hoveredNode.balance || 0) / 1e8).toFixed(8)} BTC
                                        </span>
                                    </div>
                                    <div className="flex justify-between">
                                        <span>Transactions:</span>
                                        <span className="text-gray-200">
                                            {(hoveredNode.transaction_count || 0).toLocaleString()}
                                        </span>
                                    </div>
                                </>
                            )}
                            {hoveredNode.nodeType === 'transaction' && (
                                <div className="flex justify-between">
                                    <span>Value:</span>
                                    <span className="text-blue-400 font-mono">
                                        {((hoveredNode.value || hoveredNode.total_received || 0) / 1e8).toFixed(8)} BTC
                                    </span>
                                </div>
                            )}
                        </div>
                        <div className="mt-2 pt-2 border-t border-gray-700 text-xs text-gray-500">
                            Click for details
                        </div>
                    </div>
                </div>
            )}

            {/* Control Buttons */}
            <div className="absolute left-3 top-3 flex flex-col space-y-2">
                {/* Algorithm Buttons */}
                <motion.button
                    whileHover={{ scale: 1.05 }}
                    whileTap={{ scale: 0.95 }}
                    onClick={runLabelPropagation}
                    disabled={isLoading}
                    className="flex items-center space-x-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium text-sm disabled:opacity-50 shadow-lg"
                >
                    <Play className="w-4 h-4" />
                    <span>Run Label Propagation</span>
                </motion.button>

                <motion.button
                    whileHover={{ scale: 1.05 }}
                    whileTap={{ scale: 0.95 }}
                    onClick={runLouvainAlgorithm}
                    disabled={isLoading}
                    className="flex items-center space-x-2 px-4 py-2 bg-orange-600 hover:bg-orange-700 text-white rounded-lg font-medium text-sm disabled:opacity-50 shadow-lg"
                >
                    <Play className="w-4 h-4" />
                    <span>Run Louvain</span>
                </motion.button>

                <motion.button
                    whileHover={{ scale: 1.05 }}
                    whileTap={{ scale: 0.95 }}
                    onClick={runLeidenAlgorithm}
                    disabled={isLoading}
                    className="flex items-center space-x-2 px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg font-medium text-sm disabled:opacity-50 shadow-lg"
                >
                    <Play className="w-4 h-4" />
                    <span>Run Leiden</span>
                </motion.button>

                <motion.button
                    whileHover={{ scale: 1.05 }}
                    whileTap={{ scale: 0.95 }}
                    onClick={runInfomapAlgorithm}
                    disabled={isLoading}
                    className="flex items-center space-x-2 px-4 py-2 bg-amber-600 hover:bg-amber-700 text-white rounded-lg font-medium text-sm disabled:opacity-50 shadow-lg"
                >
                    <Play className="w-4 h-4" />
                    <span>Run Infomap</span>
                </motion.button>

                <motion.button
                    whileHover={{ scale: 1.05 }}
                    whileTap={{ scale: 0.95 }}
                    onClick={exportAsImage}
                    className="flex items-center space-x-2 px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-lg font-medium text-sm shadow-lg"
                >
                    <Image className="w-4 h-4" />
                    <span>Export PNG</span>
                </motion.button>
            </div>

            {/* Zoom & Layout Controls */}
            <div className="absolute left-3 bottom-3 flex flex-col space-y-2">
                <motion.button
                    whileHover={{ scale: 1.1 }}
                    whileTap={{ scale: 0.9 }}
                    onClick={zoomIn}
                    className="p-2 bg-gray-800/90 hover:bg-gray-700 rounded-lg border border-gray-700"
                >
                    <Plus className="w-4 h-4 text-white" />
                </motion.button>

                <motion.button
                    whileHover={{ scale: 1.1 }}
                    whileTap={{ scale: 0.9 }}
                    onClick={resetCamera}
                    className="p-2 bg-gray-800/90 hover:bg-gray-700 rounded-lg border border-gray-700"
                >
                    <span className="text-xs text-white font-mono">100%</span>
                </motion.button>

                <motion.button
                    whileHover={{ scale: 1.1 }}
                    whileTap={{ scale: 0.9 }}
                    onClick={zoomOut}
                    className="p-2 bg-gray-800/90 hover:bg-gray-700 rounded-lg border border-gray-700"
                >
                    <Minus className="w-4 h-4 text-white" />
                </motion.button>

                <motion.button
                    whileHover={{ scale: 1.1 }}
                    whileTap={{ scale: 0.9 }}
                    onClick={toggleFullscreen}
                    className="p-2 bg-gray-800/90 hover:bg-gray-700 rounded-lg border border-gray-700"
                >
                    {isFullscreen ? (
                        <Shrink className="w-4 h-4 text-white" />
                    ) : (
                        <Expand className="w-4 h-4 text-white" />
                    )}
                </motion.button>
            </div>

            {/* Layout Controls */}
            <div className="absolute right-3 bottom-3 flex flex-col space-y-2">
                <motion.button
                    whileHover={{ scale: 1.05 }}
                    whileTap={{ scale: 0.95 }}
                    onClick={layoutRunning ? stopLayout : runLayout}
                    className={`flex items-center space-x-2 px-4 py-2 rounded-lg font-medium text-sm shadow-lg ${layoutRunning
                        ? 'bg-red-600 hover:bg-red-700 text-white'
                        : 'bg-purple-600 hover:bg-purple-700 text-white'
                        }`}
                >
                    {layoutRunning ? (
                        <>
                            <RotateCcw className="w-4 h-4 animate-spin" />
                            <span>Stop Layout ({layoutProgress}%)</span>
                        </>
                    ) : (
                        <>
                            <Play className="w-4 h-4" />
                            <span>Run ForceAtlas2</span>
                        </>
                    )}
                </motion.button>
            </div>

            {/* Layout Progress Bar */}
            {layoutRunning && (
                <div className="absolute bottom-0 left-0 right-0 h-1 bg-gray-700">
                    <motion.div
                        className="h-full bg-purple-500"
                        initial={{ width: 0 }}
                        animate={{ width: `${layoutProgress}%` }}
                        transition={{ duration: 0.3 }}
                    />
                </div>
            )}
        </div>
    );
};

export default WebGLGraphRenderer;
