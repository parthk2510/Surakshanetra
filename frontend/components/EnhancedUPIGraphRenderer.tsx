// @ts-nocheck
"use client";
/**
 * Enhanced UPI Graph Renderer with Fullscreen Support
 * ==================================================
 * 
 * Features:
 * - Fullscreen mode
 * - Edge weighting by transaction volume/frequency
 * - Time-based filtering
 * - Legend integration  
 * - Optimized D3 + Canvas rendering
 */

import React, { useEffect, useRef, useState, useMemo, useCallback } from 'react';
import * as d3 from 'd3';
import { Maximize2, Minimize2, Play, Pause, SkipBack, SkipForward } from 'lucide-react';
import GraphLegendEnhanced from './GraphLegendEnhanced';

const COLORS = {
    bg: '#030712',
    edge: 'rgba(107, 114, 128, 0.25)',
    edgeActive: 'rgba(255, 255, 255, 0.4)',
    text: '#e2e8f0',
    nodeStroke: '#111827',
};

/** 5-tier risk color scale */
const riskColor = (score) => {
    if (score >= 80) return '#ef4444'; // Red - Critical
    if (score >= 60) return '#f97316'; // Orange - High
    if (score >= 40) return '#eab308'; // Yellow - Medium
    if (score >= 20) return '#22c55e'; // Green - Low
    return '#3b82f6';                  // Blue - Minimal
};

/** Node size scaled by risk */
const riskSize = (score) => Math.max(3, Math.min(12, 3 + (score / 12)));

/** Edge thickness based on weight (volume + frequency) */
const edgeThickness = (weight) => {
    if (weight > 10000) return 3;
    if (weight > 1000) return 2;
    return 0.5;
};

const stableUnit = (seed: string) => {
    let h = 2166136261;
    for (let i = 0; i < seed.length; i++) {
        h ^= seed.charCodeAt(i);
        h = Math.imul(h, 16777619);
    }
    return (h >>> 0) / 4294967295;
};

const jitterFromSeed = (seed: unknown, salt: number, spread: number) => {
    const s = `${String(seed ?? '')}:${salt}`;
    const u = stableUnit(s);
    return (u - 0.5) * spread;
};

const EnhancedUPIGraphRenderer = ({ graphData, onNodeClick, className = '' }) => {
    const canvasRef = useRef(null);
    const containerRef = useRef(null);
    const simulationRef = useRef(null);

    const [layoutRunning, setLayoutRunning] = useState(false);
    const initializedRef = useRef(false);
    const [isFullscreen, setIsFullscreen] = useState(false);
    const [selectedNodeId, setSelectedNodeId] = useState(null);
    const [showLegend, setShowLegend] = useState(true);

    // Time slider state
    const [currentTimeIndex, setCurrentTimeIndex] = useState(0);
    const [isAnimating, setIsAnimating] = useState(false);

    const transformRef = useRef(d3.zoomIdentity);

    // Extract time range from graph data
    const computedTimeRange = useMemo(() => {
        if (!graphData?.edges || graphData.edges.length === 0) {
            return { min: 0, max: 0, bins: [] };
        }

        const timestamps = graphData.edges
            .map(e => e.timestamp || e.time || 0)
            .filter(t => t > 0);

        if (timestamps.length === 0) {
            return { min: 0, max: 0, bins: [] };
        }

        const min = Math.min(...timestamps);
        const max = Math.max(...timestamps);

        // Create 24-hour time bins for velocity analysis
        const binCount = 24;
        const binSize = (max - min) / binCount;
        const bins = Array.from({ length: binCount }, (_, i) => ({
            start: min + (i * binSize),
            end: min + ((i + 1) * binSize),
            index: i
        }));

        return { min, max, bins };
    }, [graphData]);

    const timeRange = computedTimeRange;

    // Filter graph data by time
    const timeFilteredData = useMemo(() => {
        if (!graphData || !timeRange.bins || timeRange.bins.length === 0) {
            return { nodes: [], edges: [] };
        }

        const safeIndex = Math.min(Math.max(currentTimeIndex, 0), timeRange.bins.length - 1);
        const currentBin = timeRange.bins[safeIndex];
        if (!currentBin) {
            return { nodes: [], edges: [] };
        }

        // Filter edges by time
        const filteredEdges = (graphData.edges || []).filter(e => {
            const t = e.timestamp || e.time || 0;
            return t >= timeRange.min && t <= currentBin.end;
        });

        // Get nodes that are connected by filtered edges
        const activeNodeIds = new Set();
        filteredEdges.forEach(e => {
            const sourceId = typeof e.source === 'object' ? e.source.id : e.source;
            const targetId = typeof e.target === 'object' ? e.target.id : e.target;
            activeNodeIds.add(sourceId);
            activeNodeIds.add(targetId);
        });

        const filteredNodes = (graphData.nodes || []).filter(n => activeNodeIds.has(n.id));

        return { nodes: filteredNodes, edges: filteredEdges };
    }, [graphData, currentTimeIndex, timeRange]);

    // Format data for D3
    const formattedData = useMemo(() => {
        const { nodes: filteredNodes, edges: filteredEdges } = timeFilteredData;

        if (!filteredNodes || filteredNodes.length === 0) {
            return { nodes: [], edges: [] };
        }

        const totalN = filteredNodes.length;
        const spread = totalN > 3000 ? Math.sqrt(totalN) * 40 : 800;

        // Prepare nodes with visual properties
        const nodes = filteredNodes.map(n => ({
            ...n,
            x: n.x ?? jitterFromSeed(n.id ?? n.nodeId, 1, spread),
            y: n.y ?? jitterFromSeed(n.id ?? n.nodeId, 2, spread),
            radius: totalN > 5000 ? Math.max(2, riskSize(n.riskScore || 0) * 0.7) : riskSize(n.riskScore || 0),
            color: riskColor(n.riskScore || 0)
        }));

        const nodeMap = new Map(nodes.map(n => [n.id, n]));

        // Aggregate and weight edges
        const edgeMap = new Map();
        (filteredEdges || []).forEach(e => {
            const sourceId = typeof e.source === 'object' ? e.source.id : e.source;
            const targetId = typeof e.target === 'object' ? e.target.id : e.target;

            if (sourceId === targetId || !nodeMap.has(sourceId) || !nodeMap.has(targetId)) return;

            const key = sourceId < targetId ? `${sourceId}-${targetId}` : `${targetId}-${sourceId}`;
            const existing = edgeMap.get(key);

            const amount = e.amount || e.value || 1;
            const frequency = 1; // Each edge represents a transaction

            if (existing) {
                existing.weight += amount;
                existing.frequency += frequency;
            } else {
                edgeMap.set(key, {
                    source: nodeMap.get(sourceId),
                    target: nodeMap.get(targetId),
                    weight: amount,
                    frequency: frequency,
                    timestamp: e.timestamp || e.time
                });
            }
        });

        return { nodes, edges: Array.from(edgeMap.values()) };
    }, [timeFilteredData]);

    // Rendering loop
    const draw = useCallback(() => {
        const canvas = canvasRef.current;
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        const { width, height } = canvas;
        const transform = transformRef.current;

        ctx.save();
        ctx.clearRect(0, 0, width, height);

        // Apply zoom/pan transform
        ctx.translate(transform.x, transform.y);
        ctx.scale(transform.k, transform.k);

        // Draw Edges with varying thickness based on weight
        for (const e of formattedData.edges) {
            const thickness = edgeThickness(e.weight);
            const alpha = Math.min(0.8, 0.2 + (e.frequency / 10));

            ctx.beginPath();
            ctx.strokeStyle = `rgba(107, 114, 128, ${alpha})`;
            ctx.lineWidth = thickness / transform.k;
            ctx.moveTo(e.source.x, e.source.y);
            ctx.lineTo(e.target.x, e.target.y);
            ctx.stroke();
        }

        // Draw Nodes (batched by color)
        const nodesByColor = new Map();
        for (const n of formattedData.nodes) {
            if (!nodesByColor.has(n.color)) nodesByColor.set(n.color, []);
            nodesByColor.get(n.color).push(n);
        }

        for (const [color, nodes] of nodesByColor) {
            ctx.fillStyle = color;
            ctx.beginPath();
            for (const n of nodes) {
                ctx.moveTo(n.x + n.radius, n.y);
                ctx.arc(n.x, n.y, n.radius, 0, 2 * Math.PI);
            }
            ctx.fill();
        }

        // Highlight Selected Node
        if (selectedNodeId) {
            const sn = formattedData.nodes.find(n => n.id === selectedNodeId);
            if (sn) {
                ctx.beginPath();
                ctx.arc(sn.x, sn.y, sn.radius + 4, 0, 2 * Math.PI);
                ctx.strokeStyle = '#6366f1';
                ctx.lineWidth = 3 / transform.k;
                ctx.stroke();

                ctx.beginPath();
                ctx.arc(sn.x, sn.y, sn.radius + 6, 0, 2 * Math.PI);
                ctx.strokeStyle = 'rgba(99, 102, 241, 0.3)';
                ctx.lineWidth = 1 / transform.k;
                ctx.stroke();
            }
        }

        ctx.restore();
    }, [formattedData, selectedNodeId]);

    // Simulation Logic — pre-warm for large graphs to avoid slow animation
    useEffect(() => {
        if (formattedData.nodes.length === 0) return;
        if (simulationRef.current) simulationRef.current.stop();

        const n = formattedData.nodes.length;
        const isLarge = n > 2000;
        const isHuge  = n > 8000;

        const chargeStrength = isHuge ? -8  : isLarge ? -20  : -80;
        const chargeRange    = isHuge ? 40  : isLarge ? 80   : 500;
        const linkDist       = isHuge ? 20  : isLarge ? 30   : 60;

        const simulation = d3.forceSimulation(formattedData.nodes)
            .alphaDecay(isHuge ? 0.3 : isLarge ? 0.15 : 0.0228)
            .force('link', d3.forceLink(formattedData.edges).id(d => d.id)
                .distance(linkDist).strength(0.04))
            .force('charge', d3.forceManyBody().strength(chargeStrength).distanceMax(chargeRange))
            .force('center', d3.forceCenter(0, 0))
            .force('collision', d3.forceCollide().radius(d => d.radius + (isHuge ? 1 : 2)))
            .stop();

        // Synchronous pre-warm: stable positions without per-tick draws
        const warmup = isHuge ? 20 : isLarge ? 40 : 60;
        for (let i = 0; i < warmup; i++) simulation.tick();

        draw(); // Single draw with pre-warmed positions
        simulationRef.current = simulation;
        initializedRef.current = true;

        if (isLarge) {
            setTimeout(() => setLayoutRunning(false), 0);
            return () => simulation.stop();
        }

        simulation.on('tick', draw).restart();
        setTimeout(() => setLayoutRunning(true), 0);

        const timer = setTimeout(() => {
            simulation.stop();
            setLayoutRunning(false);
        }, n < 300 ? 5000 : 8000);

        return () => {
            clearTimeout(timer);
            simulation.stop();
        };
    }, [formattedData, draw]);

    // Interaction Setup
    useEffect(() => {
        const canvas = canvasRef.current;
        const container = containerRef.current;
        if (!canvas || !container) return;

        const resize = () => {
            const { width, height } = container.getBoundingClientRect();
            const dpr = window.devicePixelRatio || 1;
            canvas.width = width * dpr;
            canvas.height = height * dpr;
            canvas.style.width = `${width}px`;
            canvas.style.height = `${height}px`;
            canvas.getContext('2d').scale(dpr, dpr);

            if (!initializedRef.current) {
                transformRef.current = d3.zoomIdentity.translate(width / 2, height / 2);
            }
            draw();
        };

        window.addEventListener('resize', resize);
        resize();

        const zoom = d3.zoom()
            .scaleExtent([0.05, 10])
            .on('zoom', (event) => {
                transformRef.current = event.transform;
                draw();
            });

        d3.select(canvas).call(zoom);

        if (!initializedRef.current) {
            const { width, height } = container.getBoundingClientRect();
            d3.select(canvas).call(zoom.transform, d3.zoomIdentity.translate(width / 2, height / 2));
        }

        const handleClick = (e) => {
            const rect = canvas.getBoundingClientRect();
            const transform = transformRef.current;
            const x = (e.clientX - rect.left - transform.x) / transform.k;
            const y = (e.clientY - rect.top  - transform.y) / transform.k;
            const threshold = Math.max(20, 20 / transform.k);

            // O(log n) quadtree lookup
            const qt = d3.quadtree()
                .x(d => d.x).y(d => d.y)
                .addAll(formattedData.nodes);
            const nearest = qt.find(x, y, threshold);

            if (nearest) {
                setSelectedNodeId(nearest.id);
                onNodeClick?.(nearest);
            } else {
                setSelectedNodeId(null);
                onNodeClick?.(null);
            }
        };

        canvas.addEventListener('click', handleClick);

        return () => {
            window.removeEventListener('resize', resize);
            canvas.removeEventListener('click', handleClick);
        };
    }, [formattedData, onNodeClick, draw]);

    // Fullscreen handling
    const toggleFullscreen = useCallback(() => {
        const elem = containerRef.current;
        if (!document.fullscreenElement) {
            elem.requestFullscreen().then(() => setIsFullscreen(true));
        } else {
            document.exitFullscreen().then(() => setIsFullscreen(false));
        }
    }, []);

    // Time animation
    useEffect(() => {
        if (!isAnimating) return;

        const interval = setInterval(() => {
            setCurrentTimeIndex(prev => {
                if (prev >= timeRange.bins.length - 1) {
                    setIsAnimating(false);
                    return prev;
                }
                return prev + 1;
            });
        }, 500); // 500ms per frame

        return () => clearInterval(interval);
    }, [isAnimating, timeRange.bins.length]);

    return (
        <div
            ref={containerRef}
            className={className}
            style={{
                width: '100%',
                height: '100%',
                position: 'relative',
                background: COLORS.bg,
                overflow: 'hidden'
            }}
        >
            <canvas
                ref={canvasRef}
                style={{ cursor: 'grab', display: 'block' }}
            />

            {/* Legend */}
            {showLegend && <GraphLegendEnhanced position="bottom-left" />}

            {/* Top Controls */}
            <div style={{
                position: 'absolute',
                top: 12,
                left: 12,
                right: 12,
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'flex-start',
                pointerEvents: 'none',
                gap: '12px'
            }}>
                {/* Info Badge */}
                <div style={{
                    padding: '8px 14px',
                    borderRadius: '8px',
                    background: 'rgba(0,0,0,0.7)',
                    backdropFilter: 'blur(8px)',
                    border: '1px solid rgba(255,255,255,0.1)',
                    color: '#94a3b8',
                    fontSize: '11px',
                    fontWeight: '600',
                    pointerEvents: 'auto'
                }}>
                    D3 + Canvas • {formattedData.nodes.length} nodes • {formattedData.edges.length} edges
                </div>

                {/* Control Buttons */}
                <div style={{ display: 'flex', gap: '8px', pointerEvents: 'auto' }}>
                    <button
                        onClick={() => setShowLegend(!showLegend)}
                        style={{
                            padding: '8px 14px',
                            borderRadius: '8px',
                            background: 'rgba(0,0,0,0.7)',
                            border: `1px solid ${showLegend ? 'rgba(59, 130, 246, 0.5)' : 'rgba(255,255,255,0.1)'}`,
                            color: showLegend ? '#3b82f6' : '#94a3b8',
                            fontSize: '11px',
                            fontWeight: '600',
                            cursor: 'pointer',
                            backdropFilter: 'blur(8px)'
                        }}
                    >
                        {showLegend ? 'Hide' : 'Show'} Legend
                    </button>

                    <button
                        onClick={() => {
                            if (layoutRunning) {
                                simulationRef.current?.stop();
                                setLayoutRunning(false);
                            } else {
                                simulationRef.current?.alpha(0.3).restart();
                                setLayoutRunning(true);
                            }
                        }}
                        style={{
                            padding: '8px 14px',
                            borderRadius: '8px',
                            background: layoutRunning ? 'rgba(239, 68, 68, 0.2)' : 'rgba(34, 197, 94, 0.2)',
                            border: `1px solid ${layoutRunning ? 'rgba(239, 68, 68, 0.4)' : 'rgba(34, 197, 94, 0.4)'}`,
                            color: layoutRunning ? '#f87171' : '#4ade80',
                            fontSize: '11px',
                            fontWeight: '600',
                            cursor: 'pointer',
                            backdropFilter: 'blur(8px)'
                        }}
                    >
                        {layoutRunning ? 'Pause Physics' : 'Resume Physics'}
                    </button>

                    <button
                        onClick={toggleFullscreen}
                        style={{
                            padding: '8px 12px',
                            borderRadius: '8px',
                            background: 'rgba(0,0,0,0.7)',
                            border: '1px solid rgba(255,255,255,0.1)',
                            color: '#e2e8f0',
                            cursor: 'pointer',
                            backdropFilter: 'blur(8px)',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '6px'
                        }}
                        title={isFullscreen ? 'Exit Fullscreen' : 'Enter Fullscreen'}
                    >
                        {isFullscreen ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
                    </button>
                </div>
            </div>

            {/* Time Slider */}
            {timeRange.bins.length > 0 && (
                <div style={{
                    position: 'absolute',
                    bottom: showLegend ? '220px' : '20px',
                    left: '20px',
                    right: '20px',
                    background: 'rgba(0,0,0,0.7)',
                    backdropFilter: 'blur(8px)',
                    borderRadius: '12px',
                    padding: '16px',
                    border: '1px solid rgba(255,255,255,0.1)',
                    pointerEvents: 'auto'
                }}>
                    <div style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        marginBottom: '12px'
                    }}>
                        <span style={{ fontSize: '12px', fontWeight: '600', color: '#e2e8f0' }}>
                            Transaction Velocity Timeline
                        </span>
                        <div style={{ display: 'flex', gap: '6px' }}>
                            <button
                                onClick={() => setCurrentTimeIndex(0)}
                                style={{
                                    padding: '6px',
                                    borderRadius: '6px',
                                    background: 'rgba(59, 130, 246, 0.2)',
                                    border: '1px solid rgba(59, 130, 246, 0.4)',
                                    color: '#60a5fa',
                                    cursor: 'pointer',
                                    display: 'flex',
                                    alignItems: 'center'
                                }}
                                title="Reset to start"
                            >
                                <SkipBack size={12} />
                            </button>
                            <button
                                onClick={() => setIsAnimating(!isAnimating)}
                                style={{
                                    padding: '6px 12px',
                                    borderRadius: '6px',
                                    background: isAnimating ? 'rgba(239, 68, 68, 0.2)' : 'rgba(34, 197, 94, 0.2)',
                                    border: `1px solid ${isAnimating ? 'rgba(239, 68, 68, 0.4)' : 'rgba(34, 197, 94, 0.4)'}`,
                                    color: isAnimating ? '#f87171' : '#4ade80',
                                    cursor: 'pointer',
                                    display: 'flex',
                                    alignItems: 'center',
                                    gap: '4px',
                                    fontSize: '11px',
                                    fontWeight: '600'
                                }}
                            >
                                {isAnimating ? <><Pause size={12} /> Pause</> : <><Play size={12} /> Play</>}
                            </button>
                            <button
                                onClick={() => setCurrentTimeIndex(timeRange.bins.length - 1)}
                                style={{
                                    padding: '6px',
                                    borderRadius: '6px',
                                    background: 'rgba(59, 130, 246, 0.2)',
                                    border: '1px solid rgba(59, 130, 246, 0.4)',
                                    color: '#60a5fa',
                                    cursor: 'pointer',
                                    display: 'flex',
                                    alignItems: 'center'
                                }}
                                title="Skip to end"
                            >
                                <SkipForward size={12} />
                            </button>
                        </div>
                    </div>
                    <input
                        type="range"
                        min="0"
                        max={timeRange.bins.length - 1}
                        value={currentTimeIndex}
                        onChange={(e) => {
                            setCurrentTimeIndex(parseInt(e.target.value));
                            setIsAnimating(false);
                        }}
                        style={{
                            width: '100%',
                            height: '6px',
                            borderRadius: '3px',
                            outline: 'none',
                            background: `linear-gradient(to right, #3b82f6 0%, #3b82f6 ${(currentTimeIndex / (timeRange.bins.length - 1)) * 100}%, #1e293b ${(currentTimeIndex / (timeRange.bins.length - 1)) * 100}%, #1e293b 100%)`,
                            cursor: 'pointer'
                        }}
                    />
                    <div style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        marginTop: '8px',
                        fontSize: '10px',
                        color: '#64748b'
                    }}>
                        <span>{new Date(timeRange.min).toLocaleString()}</span>
                        <span style={{ color: '#3b82f6', fontWeight: '600' }}>
                            Period {currentTimeIndex + 1} / {timeRange.bins.length}
                        </span>
                        <span>{new Date(timeRange.bins[currentTimeIndex]?.end || timeRange.max).toLocaleString()}</span>
                    </div>
                </div>
            )}
        </div>
    );
};

export default EnhancedUPIGraphRenderer;
