// @ts-nocheck
"use client";
import React, { useEffect, useRef, useState, useMemo, useCallback } from 'react';
import * as d3 from 'd3';
import { ArrowUpRight, ArrowDownLeft, Info, Activity, ShieldAlert, CreditCard, Brain } from 'lucide-react';
import GraphLegendEnhanced from './GraphLegendEnhanced';
import DecisionPanel from './DecisionPanel';
import { useConfig } from '../context/ConfigContext';
import { useTheme } from '../context/ThemeContext';
import { Z } from '../styles/z-layers';


/* ─── colour / size helpers ──────────────────────────────────────── */
const riskColor = (score) => {
  if (score >= 80) return '#ef4444';
  if (score >= 60) return '#f97316';
  if (score >= 40) return '#eab308';
  if (score >= 20) return '#22c55e';
  return '#3b82f6';
};
const riskSize = (score) => Math.max(3, Math.min(14, 3 + score / 10));

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

const DARK_COLORS = {
  bg: '#030712',
  edge: 'rgba(107,114,128,0.18)',
  edgeFocus: 'rgba(255,255,255,0.55)',
  edgeDim: 'rgba(107,114,128,0.05)',
  nodeDim: 0.15,
  text: '#e2e8f0',
  nodeStroke: '#111827',
  panelBg: 'rgba(10,12,20,0.95)',
  panelBorder: 'rgba(255,255,255,0.08)',
  statsBg: 'rgba(0,0,0,0.65)',
  textMuted: '#94a3b8',
  textSecondary: '#cbd5e1',
  buttonBg: 'rgba(0,0,0,0.65)',
};

const LIGHT_COLORS = {
  bg: '#f1f5f9',
  edge: 'rgba(100,116,139,0.25)',
  edgeFocus: 'rgba(30,41,59,0.8)',
  edgeDim: 'rgba(100,116,139,0.07)',
  nodeDim: 0.2,
  text: '#0f172a',
  nodeStroke: '#e2e8f0',
  panelBg: 'rgba(255,255,255,0.96)',
  panelBorder: 'rgba(0,0,0,0.1)',
  statsBg: 'rgba(255,255,255,0.85)',
  textMuted: '#64748b',
  textSecondary: '#475569',
  buttonBg: 'rgba(255,255,255,0.85)',
};

/* ─── main component ─────────────────────────────────────────────── */
const UPIGraphRenderer = ({ graphData, onNodeClick, className = '' }) => {
  const canvasRef = useRef(null);
  const containerRef = useRef(null);
  const simulationRef = useRef(null);
  const transformRef = useRef(d3.zoomIdentity);
  const drawRef = useRef(null);
  const animationRef = useRef(null);

  const [layoutRunning, setLayoutRunning] = useState(false);
  const initializedRef = useRef(false);
  const [selectedNode, setSelectedNode] = useState(null);
  const selectedNodeRef = useRef(null);
  const [animationDirection, setAnimationDirection] = useState('all');
  const [showLegend, setShowLegend] = useState(true);
  const [isIntelligencePanelOpen, setIsIntelligencePanelOpen] = useState(true);
  const [showRGCN, setShowRGCN] = useState(false);
  const [rgcnNodeData, setRgcnNodeData] = useState<any>(null);
  const [rgcnLoading, setRgcnLoading] = useState(false);
  const [rgcnUnavailable, setRgcnUnavailable] = useState(false);
  const { config, isSettingsPanelOpen } = useConfig();
  const { isDark } = useTheme();
  const COLORS = isDark ? DARK_COLORS : LIGHT_COLORS;
  const colorsRef = useRef(COLORS);
  colorsRef.current = COLORS;

  useEffect(() => {
    return () => {
      if (animationRef.current) cancelAnimationFrame(animationRef.current);
    };
  }, []);

  useEffect(() => {
    if (!selectedNode) {
      setRgcnNodeData(null);
      setRgcnUnavailable(false);
      return;
    }
    // Guard: skip RGCN fetch when disabled in settings
    if (!config.enableRGCN) {
      setRgcnNodeData(null);
      setRgcnUnavailable(true);
      setRgcnLoading(false);
      return;
    }
    const nodeId = selectedNode.upiId || selectedNode.id;
    if (!nodeId) return;
    let cancelled = false;
    setRgcnLoading(true);
    setRgcnUnavailable(false);
    const traditionalRiskScore = (selectedNode.riskScore || 0) / 100;
    fetch(`/api/rgcn/account/${encodeURIComponent(nodeId)}?traditional_risk_score=${traditionalRiskScore}`)
      .then(r => {
        if (r.ok) return r.json();
        // 503 = pipeline not loaded; 404 = account not in lookup
        return null;
      })
      .then(data => {
        if (!cancelled) {
          setRgcnNodeData(data);
          setRgcnUnavailable(data === null);
          setRgcnLoading(false);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setRgcnNodeData(null);
          setRgcnUnavailable(true);
          setRgcnLoading(false);
        }
      });
    return () => { cancelled = true; };
  }, [selectedNode, config.enableRGCN]);

  /* ── build graph objects once ─────────────────────────────────── */
  const MAX_RENDER_NODES = 50000;
  const MAX_RENDER_EDGES = 80000;

  const formattedData = useMemo(() => {
    if (!graphData || !Array.isArray(graphData.nodes)) return { nodes: [], edges: [], adjSet: new Set(), totalNodes: 0, totalEdges: 0 };

    let rawNodes = graphData.nodes;
    let rawEdges = graphData.edges || [];

    if (!config.showUPIDevices) {
      rawNodes = rawNodes.filter(n => !n.isDevice);
      rawEdges = rawEdges.filter(e => e.edgeType !== 'USED_DEVICE');
    }

    const totalNodes = rawNodes.length;
    const totalEdges = rawEdges.length;

    // For very large graphs, keep only top N nodes by risk score + degree
    if (totalNodes > MAX_RENDER_NODES) {
      rawNodes = [...rawNodes]
        .sort((a, b) => (b.riskScore || 0) - (a.riskScore || 0))
        .slice(0, MAX_RENDER_NODES);
    }

    const n = rawNodes.length;
    const spread = n > 3000 ? Math.sqrt(n) * 60 : 800;
    const cols = Math.ceil(Math.sqrt(n));
    const rows = Math.ceil(n / cols);

    const nodes = rawNodes.map((nd, i) => {
      let x = nd.x, y = nd.y;
      if (x == null || y == null) {
        if (n > 1000) {
          const col = i % cols;
          const row = Math.floor(i / cols);
          x = ((col / Math.max(cols - 1, 1)) - 0.5) * spread * 2 + jitterFromSeed(nd.id ?? nd.nodeId, 1, spread * 0.25);
          y = ((row / Math.max(rows - 1, 1)) - 0.5) * spread * 2 + jitterFromSeed(nd.id ?? nd.nodeId, 2, spread * 0.25);
        } else {
          x = jitterFromSeed(nd.id ?? nd.nodeId, 1, spread);
          y = jitterFromSeed(nd.id ?? nd.nodeId, 2, spread);
        }
      }
      return {
        ...nd,
        x,
        y,
        radius: n > 5000 ? Math.max(1.5, riskSize(nd.riskScore || 0) * 0.6) : riskSize(nd.riskScore || 0),
        color: riskColor(nd.riskScore || 0),
      };
    });

    const nodeMap = new Map(nodes.map((nd) => [nd.id, nd]));

    // de-duplicate edges; for huge graphs sort by weight and keep top N
    const edgeMap = new Map();
    rawEdges.forEach((e) => {
      const sid = typeof e.source === 'object' ? e.source.id : e.source;
      const tid = typeof e.target === 'object' ? e.target.id : e.target;
      if (sid === tid || !nodeMap.has(sid) || !nodeMap.has(tid)) return;
      const key = sid < tid ? `${sid}||${tid}` : `${tid}||${sid}`;
      if (!edgeMap.has(key)) {
        edgeMap.set(key, { source: nodeMap.get(sid), target: nodeMap.get(tid), weight: e.amount || 1, sid, tid });
      } else {
        edgeMap.get(key).weight += e.amount || 1;
      }
    });

    let edges = Array.from(edgeMap.values());
    if (edges.length > MAX_RENDER_EDGES) {
      edges.sort((a, b) => b.weight - a.weight);
      edges = edges.slice(0, MAX_RENDER_EDGES);
    }

    const adjSet = new Set();
    edges.forEach(({ sid, tid }) => {
      adjSet.add(`${sid}:${tid}`);
      adjSet.add(`${tid}:${sid}`);
    });

    return { nodes, edges, adjSet, totalNodes, totalEdges };
  }, [graphData, config]);

  /* ── draw ─────────────────────────────────────────────────────── */
  useEffect(() => {
    drawRef.current = () => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const ctx = canvas.getContext('2d');
      const C = colorsRef.current;
      const dpr = window.devicePixelRatio || 1;
      const cssW = canvas.width / dpr;
      const cssH = canvas.height / dpr;
      const t = transformRef.current;

      ctx.save();
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.fillStyle = C.bg;
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.scale(dpr, dpr);
      ctx.translate(t.x, t.y);
      ctx.scale(t.k, t.k);

      const vl = -t.x / t.k, vt = -t.y / t.k;
      const vr = (cssW - t.x) / t.k, vb = (cssH - t.y) / t.k;
      const mg = 20 / t.k, minPx = 0.5 / t.k;

      const sel = selectedNodeRef.current;
      const selId = sel?.id ?? null;
      const adjSet = formattedData.adjSet;

      const isNeighbour = (nid) => selId && adjSet.has(`${selId}:${nid}`);

      /* ── edges ── */
      // 1) dim batch (all, single path)
      ctx.beginPath();
      ctx.strokeStyle = selId ? C.edgeDim : C.edge;
      ctx.lineWidth = 0.5 / t.k;
      for (const e of formattedData.edges) {
        const sx = e.source.x, sy = e.source.y;
        const tx = e.target.x, ty = e.target.y;
        if ((sx < vl - mg && tx < vl - mg) || (sx > vr + mg && tx > vr + mg)) continue;
        if ((sy < vt - mg && ty < vt - mg) || (sy > vb + mg && ty > vb + mg)) continue;
        if (selId && (e.sid === selId || e.tid === selId)) continue; // drawn separately

        ctx.beginPath();
        if (e.edgeType === 'USED_DEVICE') {
          ctx.setLineDash([4 / t.k, 4 / t.k]);
          ctx.strokeStyle = selId ? 'rgba(156, 163, 175, 0.1)' : 'rgba(156, 163, 175, 0.4)'; // Gray dashed for device links
        } else {
          ctx.setLineDash([]);
          ctx.strokeStyle = selId ? C.edgeDim : C.edge;
        }

        ctx.moveTo(sx, sy);
        ctx.lineTo(tx, ty);
        ctx.stroke();
      }
      ctx.setLineDash([]);

      // 2) highlighted edges (neighbour or self)
      if (selId) {
        const timeOffset = (Date.now() % 2000) / 2000; // 0 to 1 loop every 2s

        for (const e of formattedData.edges) {
          if (e.sid !== selId && e.tid !== selId) continue;
          const sx = e.source.x, sy = e.source.y;
          const ex2 = e.target.x, ey2 = e.target.y;

          ctx.beginPath();
          ctx.strokeStyle = C.edgeFocus;
          ctx.lineWidth = Math.max(1, Math.min(3, e.weight / 500)) / t.k;
          // glow
          ctx.shadowColor = 'rgba(255,255,255,0.4)';
          ctx.shadowBlur = 6 / t.k;
          ctx.moveTo(sx, sy);
          ctx.lineTo(ex2, ey2);
          ctx.stroke();
          ctx.shadowBlur = 0;

          // Draw an animated flowing dot along the edge
          // Direction: source -> target (default in dataset usually means flow direction)
          
          // Determine if we should draw this dot based on animationDirection
          const isOutgoing = e.sid === selId;
          const isIncoming = e.tid === selId;
          
          let shouldAnimate = false;
          if (animationDirection === 'all') shouldAnimate = true;
          else if (animationDirection === 'sending' && isOutgoing) shouldAnimate = true;
          else if (animationDirection === 'receiving' && isIncoming) shouldAnimate = true;

          if (shouldAnimate) {
            const flowX = sx + (ex2 - sx) * timeOffset;
            const flowY = sy + (ey2 - sy) * timeOffset;

            ctx.beginPath();
            ctx.fillStyle = '#60a5fa'; // bright blue dot
            ctx.arc(flowX, flowY, Math.max(2, 4 / t.k), 0, 2 * Math.PI);
            ctx.fill();
          }
        }

        // Keep animating while a node is selected
        if (!layoutRunning) {
          animationRef.current = requestAnimationFrame(() => drawRef.current?.());
        }
      }

      /* ── nodes (by colour batch for performance) ── */
      // dim layer
      if (selId) {
        ctx.globalAlpha = C.nodeDim;
        for (const n of formattedData.nodes) {
          if (n.id === selId || isNeighbour(n.id)) continue;
          if (n.x < vl - mg || n.x > vr + mg || n.y < vt - mg || n.y > vb + mg) continue;
          ctx.fillStyle = n.color;
          ctx.beginPath();
          ctx.arc(n.x, n.y, n.radius, 0, 2 * Math.PI);
          ctx.fill();
        }
        ctx.globalAlpha = 1;
      }

      // active nodes (neighbours + selected) - grouped by colour
      const toRender = selId
        ? formattedData.nodes.filter(n => n.id === selId || isNeighbour(n.id))
        : formattedData.nodes;

      const byColor = new Map();
      for (const n of toRender) {
        if (n.x < vl - mg || n.x > vr + mg || n.y < vt - mg || n.y > vb + mg) continue;
        if (n.radius < minPx) continue;
        if (n.id === selId) continue; // drawn last with glow
        if (!byColor.has(n.color)) byColor.set(n.color, []);
        byColor.get(n.color).push(n);
      }
      for (const [color, ns] of byColor) {
        ctx.fillStyle = color;
        ctx.beginPath();
        for (const n of ns) {
          if (n.isDevice) {
            ctx.rect(n.x - n.radius, n.y - n.radius, n.radius * 2, n.radius * 2);
          } else {
            ctx.moveTo(n.x + n.radius, n.y);
            ctx.arc(n.x, n.y, n.radius, 0, 2 * Math.PI);
          }
        }
        ctx.fill();
      }

      /* ── selected node with glow ── */
      if (selId) {
        const sn = formattedData.nodes.find(n => n.id === selId);
        if (sn) {
          // glow ring
          ctx.shadowColor = sn.color;
          ctx.shadowBlur = 20 / t.k;
          ctx.fillStyle = sn.color;
          ctx.beginPath();
          ctx.arc(sn.x, sn.y, sn.radius * 1.4, 0, 2 * Math.PI);
          ctx.fill();
          ctx.shadowBlur = 0;

          // white ring
          ctx.strokeStyle = '#ffffff';
          ctx.lineWidth = 2 / t.k;
          ctx.beginPath();
          ctx.arc(sn.x, sn.y, sn.radius * 1.4 + 3 / t.k, 0, 2 * Math.PI);
          ctx.stroke();
        }
      }

      /* ── labels (high zoom) ── */
      if (t.k > 1.5) {
        ctx.fillStyle = C.text;
        ctx.font = `${Math.max(8, 10 / t.k)}px "Inter",sans-serif`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'top';
        for (const [, ns] of byColor) {
          for (const n of ns) {
            const lbl = n.upiId || n.label || n.id || '';
            if (lbl) ctx.fillText(lbl.length > 16 ? lbl.slice(0, 14) + '…' : lbl, n.x, n.y + n.radius + 2);
          }
        }
      }

      ctx.restore();
    };
  }, [formattedData]);

  /* keep ref in sync and redraw on selection change */
  useEffect(() => {
    selectedNodeRef.current = selectedNode;
    drawRef.current?.();
  }, [selectedNode]);

  /* redraw when theme changes */
  useEffect(() => {
    drawRef.current?.();
  }, [isDark]);

  /* ── force simulation ─────────────────────────────────────────── */
  useEffect(() => {
    if (formattedData.nodes.length === 0) return;
    if (simulationRef.current) simulationRef.current.stop();

    const n = formattedData.nodes.length;
    const isLarge = n > 2000;
    const isHuge  = n > 8000;
    const isGiant = n > 20000;

    if (isGiant) {
      drawRef.current?.();
      initializedRef.current = true;
      setTimeout(() => setLayoutRunning(false), 0);
      return;
    }

    const chargeStrength  = isHuge ? -40  : isLarge ? -60   : -80;
    const chargeRange     = isHuge ? 200  : isLarge ? 250   : 500;
    const linkDist        = isHuge ? 60   : isLarge ? 70    : 60;
    const collideRadius   = isHuge ? 3    : isLarge ? 4     : 5;
    const useXYForce = isHuge;

    const sim = d3.forceSimulation(formattedData.nodes)
      .alphaDecay(isHuge ? 0.15 : isLarge ? 0.08 : 0.0228)
      .force('link', d3.forceLink(formattedData.edges).id(d => d.id)
        .distance(linkDist).strength(isHuge ? 0.02 : 0.04))
      .force('charge', d3.forceManyBody().strength(chargeStrength).distanceMax(chargeRange))
      .force('center', useXYForce ? null : d3.forceCenter(0, 0))
      .force('x', useXYForce ? d3.forceX(0).strength(0.02) : null)
      .force('y', useXYForce ? d3.forceY(0).strength(0.02) : null)
      .force('collision', d3.forceCollide().radius(d => d.radius + collideRadius))
      .stop(); // Don't auto-tick — we control the schedule

    // Pre-warm: run ticks synchronously for a stable initial layout
    const warmup = isHuge ? 80 : isLarge ? 60 : Math.min(80, Math.ceil(Math.sqrt(n)));
    for (let i = 0; i < warmup; i++) sim.tick();

    // Auto-fit: compute bounding box of nodes and set zoom to fit all nodes in view
    if (canvasRef.current && containerRef.current && formattedData.nodes.length > 0) {
      const nodes = formattedData.nodes;
      let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
      for (const node of nodes) {
        if (node.x < minX) minX = node.x;
        if (node.x > maxX) maxX = node.x;
        if (node.y < minY) minY = node.y;
        if (node.y > maxY) maxY = node.y;
      }
      const { clientWidth: w, clientHeight: h } = containerRef.current;
      const graphW = maxX - minX || 1;
      const graphH = maxY - minY || 1;
      const padding = 60;
      const scale = Math.min((w - padding * 2) / graphW, (h - padding * 2) / graphH, 4);
      const tx = w / 2 - scale * (minX + maxX) / 2;
      const ty = h / 2 - scale * (minY + maxY) / 2;
      transformRef.current = d3.zoomIdentity.translate(tx, ty).scale(scale);
    }

    drawRef.current?.(); // Draw once with pre-warmed positions
    initializedRef.current = true;
    simulationRef.current = sim;

    if (isLarge) {
      // Large graphs: pre-warmed layout is good enough; no ongoing animation
      setTimeout(() => setLayoutRunning(false), 0);
      return () => sim.stop();
    }

    // Small graphs: animate to a polished layout
    const dur = n < 50 ? 3000 : n < 300 ? 5000 : 8000;
    sim.on('tick', () => drawRef.current?.()).restart();
    setTimeout(() => setLayoutRunning(true), 0);

    const t = setTimeout(() => { sim.stop(); setLayoutRunning(false); }, dur);
    return () => { clearTimeout(t); sim.stop(); };
  }, [formattedData]);

  /* ── canvas resize + zoom + click ────────────────────────────── */
  useEffect(() => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!canvas || !container) return;

    const resize = () => {
      const { clientWidth: w, clientHeight: h } = container;
      const dpr = window.devicePixelRatio || 1;
      const nw = Math.max(1, Math.floor(w * dpr));
      const nh = Math.max(1, Math.floor(h * dpr));
      if (canvas.width !== nw || canvas.height !== nh) {
        canvas.width = nw;
        canvas.height = nh;
        if (!initializedRef.current) transformRef.current = d3.zoomIdentity.translate(w / 2, h / 2);
        drawRef.current?.();
      }
    };

    const ro = new ResizeObserver(() => requestAnimationFrame(resize));
    ro.observe(container);
    resize();

    const zoom = d3.zoom()
      .scaleExtent([0.05, 12])
      .on('zoom', (ev) => { transformRef.current = ev.transform; drawRef.current?.(); });
    d3.select(canvas).call(zoom);

    if (!initializedRef.current) {
      const { width, height } = container.getBoundingClientRect();
      d3.select(canvas).call(zoom.transform, d3.zoomIdentity.translate(width / 2, height / 2));
    }

    /* click = find nearest node via d3.quadtree for O(log n) lookup */
    const handleClick = (e) => {
      const rect = canvas.getBoundingClientRect();
      const tr = transformRef.current;
      const wx = (e.clientX - rect.left - tr.x) / tr.k;
      const wy = (e.clientY - rect.top - tr.y) / tr.k;
      const threshold = Math.max(20, 20 / tr.k);

      // Build quadtree and find nearest node within threshold
      const qt = d3.quadtree()
        .x(d => d.x).y(d => d.y)
        .addAll(formattedData.nodes);
      const nearest = qt.find(wx, wy, threshold);

      if (nearest) {
        if (selectedNodeRef.current?.id === nearest.id) {
          setSelectedNode(null);
          onNodeClick?.(null);
        } else {
          setSelectedNode(nearest);
          setIsIntelligencePanelOpen(true);
          onNodeClick?.(nearest);
        }
      } else {
        setSelectedNode(null);
        onNodeClick?.(null);
      }
    };

    canvas.addEventListener('click', handleClick);
    return () => {
      ro.disconnect();
      d3.select(canvas).on('.zoom', null);
      canvas.removeEventListener('click', handleClick);
    };
  }, [formattedData, onNodeClick]);

  /* ── derive neighbour count for selected node ─────────────────── */
  const neighbourCount = useMemo(() => {
    if (!selectedNode) return 0;
    return formattedData.edges.filter(
      e => e.sid === selectedNode.id || e.tid === selectedNode.id
    ).length;
  }, [selectedNode, formattedData.edges]);

  /* ─── render ─────────────────────────────────────────────────── */
  return (
    <div
      ref={containerRef}
      className={className}
      style={{ width: '100%', height: '100%', position: 'relative', background: COLORS.bg, overflow: 'hidden', transition: 'background 0.2s' }}
    >
      <canvas
        ref={canvasRef}
        style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', display: 'block', cursor: 'grab' }}
      />

      {/* top-left stats badge */}
      <div style={{
        position: 'absolute', top: 12, left: 12,
        pointerEvents: 'none',
        padding: '8px 12px',
        borderRadius: 8,
        background: COLORS.statsBg,
        backdropFilter: 'blur(6px)',
        border: `1px solid ${COLORS.panelBorder}`,
        color: COLORS.textMuted,
        fontSize: 11,
        fontWeight: 500,
        display: 'flex',
        flexDirection: 'column',
        gap: 2,
      }}>
        <span>D3 + Canvas Renderer ({formattedData.nodes.length.toLocaleString()} nodes · {formattedData.edges.length.toLocaleString()} edges)</span>
        {formattedData.totalNodes > formattedData.nodes.length && (
          <span style={{ color: '#fbbf24', fontSize: 10 }}>
            Showing top {formattedData.nodes.length.toLocaleString()} of {formattedData.totalNodes.toLocaleString()} (by risk)
          </span>
        )}
        {selectedNode && (
          <span style={{ color: '#a5b4fc', fontSize: 10 }}>
            Click same node to deselect · {neighbourCount} connection{neighbourCount !== 1 ? 's' : ''}
          </span>
        )}
      </div>

      {/* top-right physics toggle and options */}
      <div style={{ position: 'absolute', top: 12, right: 12, display: 'flex', flexDirection: 'column', gap: 8, alignItems: 'flex-end', pointerEvents: 'none' }}>
        <button
          onClick={() => {
            if (layoutRunning) { simulationRef.current?.stop(); setLayoutRunning(false); }
            else { simulationRef.current?.alpha(0.3).restart(); setLayoutRunning(true); }
          }}
          style={{
            pointerEvents: 'auto',
            padding: '6px 14px',
            borderRadius: 8,
            background: layoutRunning ? 'rgba(239,68,68,0.2)' : 'rgba(34,197,94,0.2)',
            border: `1px solid ${layoutRunning ? 'rgba(239,68,68,0.4)' : 'rgba(34,197,94,0.4)'}`,
            color: layoutRunning ? '#f87171' : '#4ade80',
            fontSize: 11, fontWeight: 600, cursor: 'pointer',
            backdropFilter: 'blur(4px)',
            display: 'flex', alignItems: 'center', gap: 8,
          }}
        >
          <div style={{
            width: 6, height: 6, borderRadius: '50%',
            background: 'currentColor', boxShadow: '0 0 6px currentColor',
            animation: layoutRunning ? 'pulse 1s ease-in-out infinite' : 'none',
          }} />
          {layoutRunning ? 'Freeze Layout' : 'Resume Physics'}
        </button>

        {/* Fit View button */}
        <button
          onClick={() => {
            if (!canvasRef.current || !containerRef.current || formattedData.nodes.length === 0) return;
            const nodes = formattedData.nodes;
            let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
            for (const node of nodes) {
              if (node.x < minX) minX = node.x;
              if (node.x > maxX) maxX = node.x;
              if (node.y < minY) minY = node.y;
              if (node.y > maxY) maxY = node.y;
            }
            const { clientWidth: w, clientHeight: h } = containerRef.current;
            const graphW = maxX - minX || 1;
            const graphH = maxY - minY || 1;
            const padding = 60;
            const scale = Math.min((w - padding * 2) / graphW, (h - padding * 2) / graphH, 4);
            const tx = w / 2 - scale * (minX + maxX) / 2;
            const ty = h / 2 - scale * (minY + maxY) / 2;
            const newTransform = d3.zoomIdentity.translate(tx, ty).scale(scale);
            d3.select(canvasRef.current).call(
              d3.zoom().transform as any,
              newTransform
            );
            transformRef.current = newTransform;
            drawRef.current?.();
          }}
          style={{
            pointerEvents: 'auto',
            padding: '6px 14px',
            borderRadius: 8,
            background: 'rgba(59,130,246,0.2)',
            border: '1px solid rgba(59,130,246,0.4)',
            color: '#60a5fa',
            fontSize: 11, fontWeight: 600, cursor: 'pointer',
            backdropFilter: 'blur(4px)',
          }}
        >
          ⊞ Fit View
        </button>

      </div>

      {showLegend && !isSettingsPanelOpen && (
        <GraphLegendEnhanced position="bottom-left" />
      )}

      {selectedNode && isIntelligencePanelOpen && (
        <NodeDetailPanel
          node={selectedNode}
          edges={formattedData.edges.filter(e => e.sid === selectedNode.id || e.tid === selectedNode.id)}
          animationDirection={animationDirection}
          setAnimationDirection={setAnimationDirection}
          onClose={() => setIsIntelligencePanelOpen(false)}
          showRGCN={showRGCN}
          onToggleRGCN={() => setShowRGCN(v => !v)}
          enableDecisionEngine={!!config.enableDecisionEngine}
          enableRGCN={!!config.enableRGCN}
          rgcnData={rgcnNodeData}
          rgcnLoading={rgcnLoading}
          rgcnUnavailable={rgcnUnavailable}
        />
      )}

      {/* RGCN Decision Panel – positioned to the right of NodeDetailPanel on wide
          screens; falls below it on narrow containers (CSS handles the breakpoint
          via .decision-panel-overlay in globals.css).                           */}
      {selectedNode && isIntelligencePanelOpen && showRGCN && config.enableDecisionEngine && (
        <div
          className="graph-overlay-panel decision-panel-overlay"
          style={{
            position: 'absolute', top: 70, left: 374,
            width: 360,
            zIndex: Z.DECISION_PANEL,
          }}
        >
          <DecisionPanel
            identifier={selectedNode.upiId || selectedNode.id}
            traditionalRiskScore={(selectedNode.riskScore || 0) / 100}
          />
        </div>
      )}

      {/* Re-open Intelligence Button */}
      {selectedNode && !isIntelligencePanelOpen && !isSettingsPanelOpen && (
        <button
          onClick={() => setIsIntelligencePanelOpen(true)}
          style={{
            position: 'absolute', top: 70, left: 12,
            background: COLORS.accent || '#2563eb', color: '#fff',
            border: 'none', borderRadius: 8, padding: '8px 12px',
            fontSize: 11, fontWeight: 600, cursor: 'pointer',
            boxShadow: '0 4px 12px rgba(0,0,0,0.3)',
            display: 'flex', alignItems: 'center', gap: 6,
            zIndex: Z.NODE_DETAIL,
          }}
        >
          <Info size={14} /> Open Intelligence
        </button>
      )}
    </div>
  );
};

/* ─── Node Detail Panel ──────────────────────────────────────────── */
const NodeDetailPanel = ({ node, edges, animationDirection, setAnimationDirection, onClose, showRGCN, onToggleRGCN, enableDecisionEngine, enableRGCN, rgcnData, rgcnLoading, rgcnUnavailable }) => {
  const { isDark } = useTheme();
  const PC = isDark ? DARK_COLORS : LIGHT_COLORS;
  const riskLabel = node.riskScore >= 80 ? 'CRITICAL'
    : node.riskScore >= 60 ? 'HIGH'
      : node.riskScore >= 40 ? 'MEDIUM'
        : node.riskScore >= 20 ? 'LOW' : 'SAFE';

  const riskBg = node.riskScore >= 80 ? 'rgba(239,68,68,0.15)'
    : node.riskScore >= 60 ? 'rgba(249,115,22,0.15)'
      : node.riskScore >= 40 ? 'rgba(234,179,8,0.15)'
        : 'rgba(34,197,94,0.15)';

  const riskBorder = node.riskScore >= 80 ? 'rgba(239,68,68,0.4)'
    : node.riskScore >= 60 ? 'rgba(249,115,22,0.4)'
      : node.riskScore >= 40 ? 'rgba(234,179,8,0.4)'
        : 'rgba(34,197,94,0.4)';

  const color = riskColor(node.riskScore || 0);

  // Filter edges for history table based on animationDirection
  const filteredHistoryEdges = edges.filter(e => {
    if (animationDirection === 'all') return true;
    if (animationDirection === 'sending') return e.sid === node.id;
    if (animationDirection === 'receiving') return e.tid === node.id;
    return true;
  });

  return (
    <div className="graph-overlay-panel" style={{
      position: 'absolute', top: 70, left: 16,
      width: 340,
      background: PC.panelBg,
      backdropFilter: 'blur(16px)',
      border: `1px solid ${color}66`,
      borderRadius: 16,
      boxShadow: isDark ? `0 0 32px ${color}33, 0 12px 48px rgba(0,0,0,0.7)` : `0 4px 24px rgba(0,0,0,0.12)`,
      color: PC.textSecondary,
      fontSize: 12,
      fontFamily: '"Inter", system-ui, sans-serif',
      display: 'flex', flexDirection: 'column',
      overflow: 'hidden',
      animation: 'fadeSlideIn 0.2s cubic-bezier(0.16, 1, 0.3, 1)',
      zIndex: Z.NODE_DETAIL,
    }}>
      {/* header */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '12px 16px',
        borderBottom: `1px solid ${PC.panelBorder}`,
        background: `linear-gradient(135deg, ${color}22, transparent)`,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{
            width: 12, height: 12, borderRadius: '50%',
            background: color, boxShadow: `0 0 12px ${color}`,
          }} />
          <div>
            <div style={{ fontSize: 13, fontWeight: 700, color: isDark ? '#f8fafc' : '#0f172a', letterSpacing: '0.02em' }}>
               {node.isDevice ? 'DEVICE INFRASTRUCTURE' : (node.upiId || 'UPI ACCOUNT')}
            </div>
            <div style={{ fontSize: 10, color: PC.textMuted, marginTop: 1, display: 'flex', alignItems: 'center', gap: 4 }}>
              {node.isDevice ? <Info size={10} /> : <CreditCard size={10} />}
              {node.isDevice ? `ID: ${node.id.slice(0, 16)}...` : (node.accountType || 'Standard Account')}
            </div>
          </div>
        </div>
        <button
          onClick={onClose}
          style={{
            background: 'rgba(255,255,255,0.08)', border: 'none',
            color: '#94a3b8', cursor: 'pointer',
            width: 24, height: 24, borderRadius: '50%',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 16, transition: 'all 0.2s',
          }}
          onMouseOver={(e) => e.currentTarget.style.background = 'rgba(255,255,255,0.12)'}
          onMouseOut={(e) => e.currentTarget.style.background = 'rgba(255,255,255,0.08)'}
        >×</button>
      </div>

      {/* scrollable body */}
      <div style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: 12, overflowY: 'auto', flex: 1 }}>
        
        {/* UPI ID */}
        <div style={{
          background: 'rgba(255,255,255,0.03)',
          borderRadius: 8, padding: '10px 12px',
          border: '1px solid rgba(255,255,255,0.06)',
        }}>
          <div style={{ color: '#64748b', fontSize: 10, marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.1em', fontWeight: 600 }}>UPI Identification</div>
          <div style={{ color: '#f1f5f9', fontWeight: 600, fontSize: 13, wordBreak: 'break-all', fontFamily: 'monospace' }}>
            {node.upiId || node.label || node.id}
          </div>
        </div>

        {/* Connection Mode Toggle - Only for Accounts */}
        {!node.isDevice && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <div style={{ color: '#64748b', fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.1em', fontWeight: 600 }}>Visual Flow Control</div>
            <div style={{ display: 'flex', background: 'rgba(255,255,255,0.05)', borderRadius: 8, padding: 3 }}>
                {['all', 'sending', 'receiving'].map(dir => (
                  <button
                    key={dir}
                    onClick={() => setAnimationDirection(dir)}
                    style={{
                      flex: 1, padding: '6px 0', border: 'none', borderRadius: 6,
                      fontSize: 11, fontWeight: 600, cursor: 'pointer',
                      background: animationDirection === dir ? color : 'transparent',
                      color: animationDirection === dir ? '#fff' : '#94a3b8',
                      transition: 'all 0.2s ease',
                      display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 4
                    }}
                  >
                    {dir === 'sending' && <ArrowUpRight size={12} />}
                    {dir === 'receiving' && <ArrowDownLeft size={12} />}
                    {dir.charAt(0).toUpperCase() + dir.slice(1)}
                  </button>
                ))}
            </div>
          </div>
        )}

        {/* risk score + connections row */}
        <div style={{ display: 'flex', gap: 10 }}>
          <div style={{
            flex: 1,
            background: riskBg,
            border: `1px solid ${riskBorder}`,
            borderRadius: 10, padding: '10px 12px',
            display: 'flex', flexDirection: 'column', justifyContent: 'center'
          }}>
            <div style={{ color: '#64748b', fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 4, fontWeight: 600 }}>Risk Index</div>
            <div style={{ color, fontWeight: 800, fontSize: 22, lineHeight: 1 }}>
              {(node.riskScore || 0).toFixed(0)}
              <span style={{ fontSize: 12, fontWeight: 400, color: '#94a3b8', marginLeft: 4 }}>/100</span>
            </div>
            <div style={{
              marginTop: 6, fontSize: 10, fontWeight: 700,
              color,
              background: `${color}22`, borderRadius: 4, padding: '2px 8px', display: 'inline-block', alignSelf: 'flex-start'
            }}>{riskLabel}</div>
          </div>

          <div style={{
            flex: 1,
            background: 'rgba(99,102,241,0.08)',
            border: '1px solid rgba(99,102,241,0.25)',
            borderRadius: 10, padding: '10px 12px',
          }}>
            <div style={{ color: '#64748b', fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 4, fontWeight: 600 }}>
               {node.isDevice ? 'Associated Users' : 'Network Links'}
            </div>
            <div style={{ color: '#a5b4fc', fontWeight: 800, fontSize: 22, lineHeight: 1 }}>
              {node.isDevice ? node.deviceUsers : edges.length}
              <span style={{ fontSize: 12, fontWeight: 400, color: '#94a3b8', marginLeft: 4 }}>
                {node.isDevice ? 'users' : 'peers'}
              </span>
            </div>
            <div style={{ fontSize: 10, color: '#6366f1', marginTop: 6, fontWeight: 600 }}>
              {node.isDevice ? (node.deviceUsers > 1 ? 'Shared Node' : 'Dedicated') : 'Connected Hub'}
            </div>
          </div>
        </div>

        {!node.isDevice && (
          <div style={{
            background: 'rgba(99,102,241,0.07)',
            borderRadius: 8, padding: '10px 12px',
            border: '1px solid rgba(99,102,241,0.2)',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
              <Brain size={12} color="#818cf8" />
              <span style={{ color: '#818cf8', fontSize: 10, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em' }}>RGCN Model Score</span>
              {rgcnLoading && (
                <span style={{ marginLeft: 'auto', fontSize: 9, color: '#64748b' }}>loading…</span>
              )}
              {rgcnData && !rgcnLoading && (
                <span style={{
                  marginLeft: 'auto', fontSize: 9, padding: '1px 6px', borderRadius: 4, fontWeight: 700,
                  background: rgcnData.risk_tier === 'Critical' ? 'rgba(239,68,68,0.15)'
                    : rgcnData.risk_tier === 'High' ? 'rgba(249,115,22,0.15)'
                    : rgcnData.risk_tier === 'Medium' ? 'rgba(234,179,8,0.15)'
                    : 'rgba(34,197,94,0.15)',
                  color: rgcnData.risk_tier === 'Critical' ? '#ef4444'
                    : rgcnData.risk_tier === 'High' ? '#f97316'
                    : rgcnData.risk_tier === 'Medium' ? '#eab308'
                    : '#22c55e',
                }}>{rgcnData.risk_tier || 'Unknown'}</span>
              )}
              {rgcnUnavailable && !rgcnLoading && (
                <span style={{ marginLeft: 'auto', fontSize: 9, padding: '1px 6px', borderRadius: 4, fontWeight: 600, color: '#64748b', background: 'rgba(100,116,139,0.1)' }}>
                  {enableRGCN === false ? 'Disabled' : 'Heuristic'}
                </span>
              )}
            </div>
            {rgcnLoading && (
              <div style={{ color: '#64748b', fontSize: 10, textAlign: 'center', padding: '4px 0' }}>Querying RGCN model…</div>
            )}
            {rgcnData && !rgcnLoading && (
              <>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 8 }}>
                  <div>
                    <div style={{ color: '#64748b', fontSize: 9, marginBottom: 2 }}>Fraud Probability</div>
                    <div style={{ color: '#a5b4fc', fontWeight: 700, fontSize: 14 }}>
                      {((rgcnData.fraud_probability || 0) * 100).toFixed(1)}%
                    </div>
                  </div>
                  <div>
                    <div style={{ color: '#64748b', fontSize: 9, marginBottom: 2 }}>Anomaly Score</div>
                    <div style={{ color: '#a5b4fc', fontWeight: 700, fontSize: 14 }}>
                      {((rgcnData.anomaly_score || 0) * 100).toFixed(1)}%
                    </div>
                  </div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <div style={{ flex: 1, height: 3, borderRadius: 2, background: 'rgba(255,255,255,0.08)', overflow: 'hidden' }}>
                    <div style={{
                      height: '100%', borderRadius: 2, background: '#818cf8',
                      width: `${Math.round((rgcnData.final_risk_score || 0) * 100)}%`,
                      transition: 'width 0.6s ease',
                    }} />
                  </div>
                  <span style={{ color: '#64748b', fontSize: 9, whiteSpace: 'nowrap' }}>
                    {rgcnData.flag_source && rgcnData.flag_source !== 'none'
                      ? `Flagged · ${rgcnData.flag_source}`
                      : 'No flag'}
                  </span>
                </div>
              </>
            )}
            {rgcnUnavailable && !rgcnLoading && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 0', color: '#64748b', fontSize: 10 }}>
                <Brain size={12} color="#64748b" />
                {enableRGCN === false
                  ? <span>RGCN scoring is <strong style={{ color: '#94a3b8' }}>disabled</strong> in settings. Enable it to see AI-driven risk scores.</span>
                  : <span>RGCN model not trained — run <code style={{ fontSize: 9 }}>run_pipeline.py</code> to enable AI scoring. Heuristic score shown above.</span>
                }
              </div>
            )}
          </div>
        )}

        {/* Mule Logic Reasoning - WHY IS THIS A MULE? */}
        <div style={{
          background: 'rgba(244, 63, 94, 0.05)',
          borderRadius: 8, padding: '12px',
          border: '1px solid rgba(244, 63, 94, 0.15)',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
            <ShieldAlert size={14} color="#f43f5e" />
            <span style={{ color: '#f43f5e', fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              {node.isDevice ? 'Infrastructure Risk' : 'Mule Detection Reasoning'}
            </span>
          </div>
          <div style={{ fontSize: 11, color: '#e2e8f0', lineHeight: 1.5 }}>
            {node.riskScore >= 80 ? (
                <span>
                   {node.isDevice ? (
                     'Mule infrastructure detected: This device is shared between multiple high-risk accounts, suggesting centralized control.'
                   ) : (
                     `Critical risk profile detected (Score: ${node.riskScore.toFixed(0)}/100). Activity matches high-certainty mule signatures including: ${node.reasonCodes?.map(rc => rc.replace(/_/g, ' ')).join(', ') || 'behavioral anomalies'}.`
                   )}
                </span>
            ) : node.riskScore >= 40 ? (
                <span>
                   {node.isDevice ? (
                     'Suspicious device sharing: Multiple accounts have accessed the system from this single hardware identifier.'
                   ) : (
                     `Elevated risk markers identified. Patterns suggest potential mule activity linked to ${node.reasonCodes?.map(rc => rc.replace(/_/g, ' ')).join(', ') || 'atypical transaction velocity'}.`
                   )}
                </span>
            ) : (
                <span>Standard activity profile. No significant behavioral anomalies or infrastructure risk markers identified.</span>
            )}
          </div>
          
          {/* Risk Factors List */}
          <div style={{ marginTop: 10, display: 'flex', flexWrap: 'wrap', gap: 6 }}>
             {(node.reasonCodes || []).map((code, idx) => {
               const labels = {
                 high_fan_in: "Fan-in Burst",
                 high_fan_out: "Fan-out Burst",
                 rapid_burst: "Velocity Spike",
                 circular_flow: "Money Loop",
                 structuring: "Threshold Structuring",
                 pass_through: "Pass-through",
                 dormant_spike: "Dormant Spike",
                 shared_device: "Shared Device",
                 multiple_devices: "Device Proliferation",
                 multiple_ips: "IP Subnet Hopping",
                 FAST_LOCATION_CHANGE: "Impossible Travel",
                 MULTIPLE_LOCATIONS: "Geo-Anomaly",
                 MULTIPLE_DEVICES: "Multi-Device"
               };
               return (
                 <span key={idx} title={code} style={{ 
                   fontSize: 9, background: 'rgba(244, 63, 94, 0.1)', padding: '2px 6px', borderRadius: 4, 
                   color: '#f43f5e', border: '1px solid rgba(244, 63, 94, 0.2)',
                   fontWeight: 600
                 }}>
                   {labels[code] || code.replace(/_/g, ' ').toUpperCase()}
                 </span>
               );
             })}
             {(!node.reasonCodes || node.reasonCodes.length === 0) && node.riskScore > 0 && (
               <span style={{ fontSize: 9, color: '#64748b' }}>No specific pattern flags</span>
             )}
          </div>
        </div>

        {/* Transaction Table - Only for Accounts */}
        {!node.isDevice && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <Activity size={12} color="#94a3b8" />
              <span style={{ color: '#64748b', fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.1em', fontWeight: 600 }}>Transaction History</span>
            </div>
            <div style={{ 
              background: 'rgba(0,0,0,0.3)', 
              borderRadius: 8, 
              border: '1px solid rgba(255,255,255,0.05)',
              overflow: 'hidden'
            }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr 0.8fr', padding: '8px 10px', background: 'rgba(255,255,255,0.03)', fontSize: 9, color: '#64748b', fontWeight: 700 }}>
                 <div>PEER UPI</div>
                 <div style={{ textAlign: 'right' }}>AMOUNT</div>
                 <div style={{ textAlign: 'right' }}>FLOW</div>
              </div>
              <div style={{ maxHeight: 180, overflowY: 'auto' }}>
                {filteredHistoryEdges.slice(0, 50).map((e, i) => {
                  const peerId = e.sid === node.id ? e.tid : e.sid;
                  const isOut = e.sid === node.id;
                  return (
                    <div key={i} style={{ 
                      display: 'grid', gridTemplateColumns: '1.2fr 1fr 0.8fr', 
                      padding: '8px 10px', borderTop: '1px solid rgba(255,255,255,0.03)',
                      fontSize: 10, transition: 'background 0.2s'
                    }} onMouseOver={ev => ev.currentTarget.style.background = 'rgba(255,255,255,0.02)'}
                       onMouseOut={ev => ev.currentTarget.style.background = 'transparent'}>
                      <div style={{ color: '#94a3b8', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{peerId}</div>
                      <div style={{ textAlign: 'right', fontWeight: 600, color: '#f1f5f9' }}>₹{(e.weight || 0).toLocaleString()}</div>
                      <div style={{ textAlign: 'right', fontWeight: 700, color: isOut ? '#ef4444' : '#22c55e', fontSize: 9 }}>
                        {isOut ? 'SENT' : 'RECV'}
                      </div>
                    </div>
                  );
                })}
                {edges.length === 0 && (
                  <div style={{ padding: '20px', textAlign: 'center', color: '#475569', fontSize: 11 }}>No transactions recorded</div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Footprint Anomaly Flags */}
        {(node.riskFactors?.includes('MULTIPLE_LOCATIONS') || node.riskFactors?.includes('MULTIPLE_DEVICES') || node.riskFactors?.includes('FAST_LOCATION_CHANGE')) && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {node.riskFactors.includes('FAST_LOCATION_CHANGE') && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, background: 'rgba(239, 68, 68, 0.1)', border: '1px solid rgba(239, 68, 68, 0.2)', padding: '8px 12px', borderRadius: 8 }}>
                <span style={{ fontSize: 14 }}>⏱️</span>
                <div style={{ flex: 1 }}>
                  <div style={{ color: '#ef4444', fontSize: 11, fontWeight: 700 }}>Impossible Travel Velocity</div>
                  <div style={{ color: '#fca5a5', fontSize: 10, marginTop: 1 }}>Account shifted IP locations rapidly</div>
                </div>
              </div>
            )}
            {/* ... other factors could be added here if needed, keeping it concise as requested ... */}
          </div>
        )}

      </div>
      
      {/* footer sticky */}
      <div style={{ padding: '10px 16px', background: 'rgba(0,0,0,0.5)', borderTop: '1px solid rgba(255,255,255,0.05)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span style={{ fontSize: 10, color: '#475569' }}>AI-Powered Mule Detection</span>
        {enableDecisionEngine && (
          <button
            onClick={onToggleRGCN}
            style={{
              display: 'flex', alignItems: 'center', gap: 5,
              padding: '4px 10px', borderRadius: 6, border: 'none', cursor: 'pointer',
              fontSize: 10, fontWeight: 600,
              background: showRGCN ? 'rgba(99,102,241,0.25)' : 'rgba(99,102,241,0.1)',
              color: showRGCN ? '#a5b4fc' : '#6366f1',
              transition: 'all 0.2s',
            }}
          >
            <Brain size={11} />
            {showRGCN ? 'Hide RGCN' : 'RGCN Analysis'}
          </button>
        )}
      </div>

      <style>{`
        @keyframes fadeSlideIn {
          from { opacity: 0; transform: translateX(20px) scale(0.98); }
          to   { opacity: 1; transform: translateX(0) scale(1); }
        }
        @keyframes pulse {
          0%, 100% { opacity: 1; } 50% { opacity: 0.4; }
        }
      `}</style>
    </div>
  );
};

export default UPIGraphRenderer;
