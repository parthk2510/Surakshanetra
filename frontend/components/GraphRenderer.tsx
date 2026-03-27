// @ts-nocheck
"use client";
// src/components/GraphRenderer.js
import React, { useEffect, useRef, useState, useCallback } from 'react';
import * as d3 from 'd3';
import { motion, AnimatePresence } from 'framer-motion';
import { Loader2, AlertCircle, Play, Expand, Shrink, Image, ZoomIn, ZoomOut, Maximize2, Move } from 'lucide-react';
import logger from '../utils/logger';
import { Plus, Minus } from 'lucide-react';
import { saveSvgAsPng } from 'save-svg-as-png';
import toast from 'react-hot-toast';
import { useConfig } from '../context/ConfigContext';

// ── Risk-tier helpers ──────────────────────────────────────────────────────────
const LEGEND_TIERS = [
  { id: 'Critical',    label: 'Critical',    color: '#ef4444', textColor: '#fca5a5' },
  { id: 'High',        label: 'High Risk',   color: '#f97316', textColor: '#fdba74' },
  { id: 'Medium',      label: 'Medium Risk', color: '#eab308', textColor: '#fde047' },
  { id: 'Low',         label: 'Low Risk',    color: '#22c55e', textColor: '#86efac' },
  { id: 'Transaction', label: 'Transaction', color: '#3b82f6', textColor: '#93c5fd' },
];

function getNodeTier(d, illicitAddresses) {
  const isIllicit = illicitAddresses.some(i => i.address === d.id || i === d.id);
  if (isIllicit || d.riskScore >= 0.8) return 'Critical';
  if (d.riskScore >= 0.6 || d.isMalicious) return 'High';
  if (d.riskScore >= 0.35 || d.isAnomalous) return 'Medium';
  if (d.type === 'transaction') return 'Transaction';
  return 'Low';
}

const GraphRenderer = ({ graphData, onNodeClick, className = '', illicitAddresses = [], onAlgorithmResult }) => {
  const { config } = useConfig();
  const containerRef = useRef(null);
  const svgRef = useRef(null);
  const simulationRef = useRef(null);
  const graphRef = useRef({ nodes: [], edges: [] });
  const roRef = useRef(null);
  const resizeObserverRef = useRef(null);
  const zoomBehaviorRef = useRef(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [layoutRunning, setLayoutRunning] = useState(false);
  const [communities, setCommunities] = useState(null);
  const [containerReady, setContainerReady] = useState(false);
  const [zoomLevel, setZoomLevel] = useState(1);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [activeLegendFilter, setActiveLegendFilter] = useState(null);
  const communitiesRef = useRef(null);


  useEffect(() => {
    communitiesRef.current = communities;
  }, [communities]);

  // Interactive legend – fade non-selected tiers
  useEffect(() => {
    if (!svgRef.current) return;
    const allNodeGroups = svgRef.current.selectAll('.node-group');
    const allLinks = svgRef.current.selectAll('path, line').filter(function() {
      return !d3.select(this.parentNode).classed('node-group');
    });
    if (!activeLegendFilter) {
      allNodeGroups.style('opacity', 1);
      allLinks.style('opacity', 0.55);
      return;
    }
    allNodeGroups.style('opacity', d => {
      const tier = getNodeTier(d, illicitAddresses);
      return tier === activeLegendFilter ? 1 : 0.08;
    });
    allLinks.style('opacity', d => {
      const srcTier = getNodeTier(
        typeof d.source === 'object' ? d.source : { id: d.source, riskScore: 0, type: 'address' },
        illicitAddresses
      );
      const tgtTier = getNodeTier(
        typeof d.target === 'object' ? d.target : { id: d.target, riskScore: 0, type: 'address' },
        illicitAddresses
      );
      return srcTier === activeLegendFilter || tgtTier === activeLegendFilter ? 0.6 : 0.04;
    });
  }, [activeLegendFilter, illicitAddresses]);

  const initializeGraph = useCallback(() => {
    if (!graphData || !containerRef.current) return null;
    try {
      logger.debug('Initializing graph with data', {
        nodes: graphData.nodes?.length || 0,
        edges: graphData.edges?.length || 0
      });
      const nodes = (graphData.nodes || [])
        .filter(n => n && typeof n.id === 'string')
        .map(n => ({
          id: n.id,
          label: n.label || n.id,
          size: 8,
          color: n.color || '#6366f1',
          x: n.x ?? Math.random() * 1000,
          y: n.y ?? Math.random() * 1000,
          type: 'circle',
          ...Object.fromEntries(
            Object.entries(n).filter(([key, value]) => {
              const exclude = ['type', 'id', 'label', 'size', 'color', 'x', 'y'];
              return !exclude.includes(key) && value !== undefined && value !== null && typeof value !== 'function';
            })
          )
        }));

      // Create a Set of valid node IDs for edge validation
      // Validate nodes have required properties
      const validNodes = nodes.filter(n => n && typeof n === 'object' && n.id);
      const validNodeIds = new Set(validNodes.map(n => n.id));

      // Helper function to extract node ID from source/target (handles both string and object)
      const getNodeId = (nodeRef) => {
        if (typeof nodeRef === 'string') return nodeRef;
        if (typeof nodeRef === 'object' && nodeRef !== null) return nodeRef.id;
        return null;
      };

      const initialEdgeCount = (graphData.edges || []).length;
      const edges = (graphData.edges || [])
        .filter(e => {
          if (!e) return false;
          const sourceId = getNodeId(e.source);
          const targetId = getNodeId(e.target);

          // Validate that source and target exist and are different
          if (!sourceId || !targetId || sourceId === targetId) return false;

          // Validate that both nodes exist in the nodes array
          const sourceExists = validNodeIds.has(sourceId);
          const targetExists = validNodeIds.has(targetId);

          if (!sourceExists || !targetExists) {
            logger.warn('Filtering edge with missing node', {
              source: sourceId,
              target: targetId,
              sourceExists,
              targetExists
            });
            return false;
          }

          return true;
        })
        .map(e => {
          const sourceId = getNodeId(e.source);
          const targetId = getNodeId(e.target);
          return {
            source: sourceId,
            target: targetId,
            weight: e.weight || 1,
            color: e.color || '#94a3b8',
            size: e.size || 1,
            type: 'line',
            ...Object.fromEntries(
              Object.entries(e).filter(([key, value]) => {
                const exclude = ['source', 'target', 'weight', 'color', 'size', 'type', 'id'];
                return !exclude.includes(key) && value !== undefined && value !== null && typeof value !== 'function';
              })
            )
          };
        });

      const filteredEdgeCount = initialEdgeCount - edges.length;
      if (filteredEdgeCount > 0) {
        logger.warn(`Filtered ${filteredEdgeCount} edge(s) with missing nodes`, {
          initialEdges: initialEdgeCount,
          validEdges: edges.length,
          filteredEdges: filteredEdgeCount
        });
      }

      graphRef.current = { nodes, edges };
      logger.info('Graph initialized successfully', {
        nodeCount: nodes.length,
        edgeCount: edges.length
      });
      return graphRef.current;
    } catch (err) {
      logger.error('Failed to initialize graph', err);
      setError(`Renderer initialization failed: ${err.message}`);
      return null;
    }
  }, [graphData]);
  const applyLouvainColors = (nodesSelection, communitiesArg) => {
    const communities = communitiesArg || communitiesRef.current;
    if (!communities || !communities.partition) {
      logger.warn('No communities data available for coloring');
      return;
    }

    const { partition, num_communities } = communities;

    if (!partition || Object.keys(partition).length === 0) {
      logger.warn('Partition is empty, cannot apply colors');
      return;
    }

    const colorScale = num_communities <= 10
      ? d3.scaleOrdinal(d3.schemeCategory10)
      : d3.scaleOrdinal(d3.schemePaired);

    const selectionSize = nodesSelection.size();
    if (selectionSize === 0) {
      logger.error('No nodes found to color (selection size 0)');
      return;
    }
    logger.info(`Applying colors to ${selectionSize} nodes across ${num_communities} communities`);

    nodesSelection
      .each(function (d) {
        const communityId = partition[d.id];
        const node = d3.select(this);

        const communityDefined = communityId !== undefined;
        const fillColor = communityDefined ? colorScale(communityId) : (d.color || '#6366f1');
        const strokeColor = communityDefined ? d3.color(fillColor).darker(1) : '#111827';

        // Preserve illicit address indication with stroke
        const isIllicit = illicitAddresses.some(illicit => illicit.address === d.id);

        node.attr('fill', fillColor)
          .style('fill', fillColor)
          .attr('stroke', isIllicit ? '#dc2626' : strokeColor)
          .style('stroke', isIllicit ? '#dc2626' : strokeColor)
          .attr('stroke-width', isIllicit ? 3 : 2.5)
          .style('stroke-width', isIllicit ? 3 : 2.5);

        // Persist color on backing data for consistency
        if (graphRef.current?.nodes) {
          const targetNode = graphRef.current.nodes.find(n => n.id === d.id);
          if (targetNode) {
            targetNode.color = fillColor;
          }
        }
      });

    logger.info('Community colors applied successfully');
  };

  const applyColorsToGraphNodes = (communityData) => {
    if (!svgRef.current) return;
    let nodesSelection = svgRef.current.selectAll('.graph-node');
    if (nodesSelection.size() === 0) {
      logger.warn('No .graph-node elements found, falling back to all circles');
      nodesSelection = svgRef.current.selectAll('circle');
    }
    if (nodesSelection.size() === 0 && containerRef.current) {
      logger.warn('No circles found in svgRef, trying container fallback');
      nodesSelection = d3.select(containerRef.current).selectAll('circle');
    }
    if (nodesSelection.size() === 0) {
      logger.error('No nodes found to color (post-selection)');
      return;
    }
    applyLouvainColors(nodesSelection, communityData);
    requestAnimationFrame(() => applyLouvainColors(nodesSelection, communityData));
  };




  const initializeD3 = useCallback((graph) => {
    if (!graph || !containerRef.current) return null;

    // Validate graph structure
    if (!graph.nodes || !Array.isArray(graph.nodes)) {
      logger.error('Invalid graph: nodes array is missing or not an array', graph);
      return null;
    }

    // Filter out invalid nodes
    const validNodes = graph.nodes.filter(n => n && typeof n === 'object' && n.id);
    if (validNodes.length === 0) {
      logger.warn('No valid nodes in graph', graph);
      return null;
    }

    // Create a sanitized graph with only valid nodes
    const sanitizedGraph = {
      ...graph,
      nodes: validNodes,
      edges: (graph.edges || []).filter(e => e && typeof e === 'object')
    };

    try {
      const container = containerRef.current;
      const width = container.clientWidth;
      const height = container.clientHeight;
      if (width === 0 || height === 0) {
        logger.warn('Container has zero dimensions, postponing D3 initialization');
        return null;
      }
      d3.select(container).selectAll('svg').remove();
      const svg = d3.select(container)
        .append('svg')
        .attr('width', '100%')
        .attr('height', '100%')
        .attr('viewBox', `0 0 ${width} ${height}`)
        .style('background', '#111827');
      svgRef.current = svg;
      const g = svg.append('g');

      // Add arrow markers for edges
      const defs = svg.append('defs');
      const arrowMarker = defs.append('marker')
        .attr('id', 'arrowhead')
        .attr('viewBox', '0 -5 10 10')
        .attr('refX', 8)
        .attr('refY', 0)
        .attr('markerWidth', 6)
        .attr('markerHeight', 6)
        .attr('orient', 'auto');

      arrowMarker.append('path')
        .attr('d', 'M0,-5L10,0L0,5')
        .attr('fill', '#94a3b8');

      const linkGroup = g.append('g');
      const nodeGroup = g.append('g');
      const zoom = d3.zoom()
        .scaleExtent([0.05, 15])
        .on('zoom', (event) => {
          g.attr('transform', event.transform);
          setZoomLevel(event.transform.k);
        });
      svg.call(zoom);
      zoomBehaviorRef.current = zoom;
      const useBundling = config?.enableEdgeBundling !== false;
      const links = linkGroup.selectAll(useBundling ? 'path' : 'line')
        .data(sanitizedGraph.edges)
        .join(useBundling ? 'path' : 'line')
        .attr('fill', 'none')
        .attr('stroke-width', d => Math.max(1, Math.min(4, (d.value || 0) / 100000000)) || 1)
        .attr('stroke', d => {
          if (d.direction === 'incoming') return '#10b981';
          if (d.direction === 'outgoing') return '#ef4444';
          return d.color || '#94a3b8';
        })
        .attr('stroke-opacity', 0.55);
      // Use sanitized graph nodes
      const nodes = nodeGroup.selectAll('g.node-group')
        .data(sanitizedGraph.nodes)
        .join('g')
        .classed('node-group', true)
        .style('cursor', 'pointer');

      // Aggressive node-radius helper
      const nodeRadius = (d) => {
        const useRisk = config?.nodeSizeMetric === 'risk';
        if (d.type === 'address') {
          if (useRisk) {
            const rs = d.riskScore || 0;
            return Math.max(5, Math.min(50, 5 + rs * 45));
          }
          const balance = d.balance || 0;
          const isIllicit = illicitAddresses.some(i => i.address === d.id || i === d.id);
          const boost = isIllicit || d.riskScore > 0.7 ? 1.5 : 1;
          return Math.max(5, Math.min(50, Math.log10(balance + 2) * 10)) * boost;
        }
        if (d.type === 'transaction') {
          const value = d.total_input_value || d.result || 0;
          return Math.max(4, Math.min(36, Math.log10(value + 2) * 8));
        }
        return Math.max(5, Math.min(30, (d.size || 8) * 1.8));
      };

      // Add pulse effect ring for anomalous/flagged nodes
      nodes.append('circle')
        .classed('pulse-ring', true)
        .attr('r', d => {
          const isIllicit = illicitAddresses.some(illicit => illicit.address === d.id || illicit === d.id);
          const isAnomalous = d.isAnomalous || d.isMalicious || d.riskScore > 0.7;
          if (!isIllicit && !isAnomalous) return 0;
          return nodeRadius(d) + 7;
        })
        .attr('fill', 'none')
        .attr('stroke', d => {
          const isIllicit = illicitAddresses.some(illicit => illicit.address === d.id || illicit === d.id);
          if (isIllicit) return '#ef4444';
          return '#f59e0b';
        })
        .attr('stroke-width', 2)
        .attr('stroke-opacity', d => {
          const isIllicit = illicitAddresses.some(illicit => illicit.address === d.id || illicit === d.id);
          const isAnomalous = d.isAnomalous || d.isMalicious || d.riskScore > 0.7;
          return (isIllicit || isAnomalous) ? 0.5 : 0;
        })
        .style('animation', d => {
          const isIllicit = illicitAddresses.some(illicit => illicit.address === d.id || illicit === d.id);
          const isAnomalous = d.isAnomalous || d.isMalicious || d.riskScore > 0.7;
          return (isIllicit || isAnomalous) ? 'pulse 2s ease-in-out infinite' : 'none';
        });

      // Main node circle with aggressive size scaling
      nodes.append('circle')
        .classed('graph-node', true)
        .attr('r', d => nodeRadius(d))
        .attr('fill', d => {
          // Check if address is illicit
          const isIllicit = illicitAddresses.some(illicit => illicit.address === d.id || illicit === d.id);
          if (isIllicit) {
            return '#ef4444'; // red for illicit addresses
          }

          // Check for anomalous nodes
          if (d.isAnomalous || d.riskScore > 0.7) {
            return '#f59e0b'; // amber for anomalous
          }

          if (d.type === 'address') {
            if (d.balance > 0) return '#10b981'; // green for addresses with balance
            return '#6b7280'; // gray for addresses without balance
          }
          if (d.type === 'transaction') return '#3b82f6'; // blue for transactions
          return d.color || '#6366f1';
        })
        .attr('stroke', d => {
          // Check if address is illicit
          const isIllicit = illicitAddresses.some(illicit => illicit.address === d.id || illicit === d.id);
          if (isIllicit) {
            return '#dc2626'; // darker red stroke for illicit addresses
          }

          if (d.isAnomalous || d.riskScore > 0.7) {
            return '#d97706'; // darker amber for anomalous
          }

          if (d.type === 'address' && d.balance > 0) return '#059669';
          if (d.type === 'transaction') return '#1d4ed8';
          return '#111827';
        })
        .attr('stroke-width', d => {
          const isIllicit = illicitAddresses.some(illicit => illicit.address === d.id || illicit === d.id);
          return isIllicit ? 3 : 2;
        });

      // Add drag behavior to node groups
      nodes.call(d3.drag()
        .on('start', (event, d) => {
          if (!event.active && simulationRef.current) simulationRef.current.alphaTarget(0.3).restart();
          d.fx = d.x;
          d.fy = d.y;
        })
        .on('drag', (event, d) => {
          d.fx = event.x;
          d.fy = event.y;
        })
        .on('end', (event, d) => {
          if (!event.active && simulationRef.current) simulationRef.current.alphaTarget(0);
          d.fx = null;
          d.fy = null;
        })
      );


      // Add tooltips with rich information
      nodes.append('title').text(d => {
        const isIllicit = illicitAddresses.some(illicit => illicit.address === d.id);
        let tooltip = `${d.label || d.id}\n`;

        if (isIllicit) {
          const illicitData = illicitAddresses.find(illicit => illicit.address === d.id);
          tooltip += `🚨 ILLICIT ADDRESS 🚨\n`;
          tooltip += `Risk Level: ${illicitData.risk_level?.toUpperCase()}\n`;
          tooltip += `Confidence: ${(illicitData.confidence * 100).toFixed(1)}%\n`;
          tooltip += `Sources: ${illicitData.sources.join(', ')}\n`;

          if (illicitData.illicit_activity_analysis) {
            tooltip += `Primary Activity: ${illicitData.illicit_activity_analysis.primary_activity_type?.replace(/_/g, ' ').toUpperCase()}\n`;
            if (illicitData.illicit_activity_analysis.secondary_activities?.length > 0) {
              tooltip += `Secondary: ${illicitData.illicit_activity_analysis.secondary_activities.map(sa => sa.type.replace(/_/g, ' ')).join(', ')}\n`;
            }
            if (illicitData.illicit_activity_analysis.risk_indicators?.length > 0) {
              tooltip += `Evidence: ${illicitData.illicit_activity_analysis.risk_indicators.slice(0, 2).join(', ')}\n`;
            }
          }
        }

        if (d.type === 'address') {
          tooltip += `Type: Address\nBalance: ${(d.balance || 0) / 100000000} BTC\nTransactions: ${d.transaction_count || 0}`;
        } else if (d.type === 'transaction') {
          tooltip += `Type: Transaction\nValue: ${(d.total_input_value || 0) / 100000000} BTC\nFee: ${(d.fee || 0) / 100000000} BTC`;
        }

        return tooltip;
      });

      nodes.on('click', (event, d) => {
        event.stopPropagation();
        event.preventDefault();
        // Prevent simulation restart on click
        if (simulationRef.current) {
          simulationRef.current.alphaTarget(0);
        }
        if (onNodeClick && d && typeof d === 'object') {
          try {
            // Create a clean copy to prevent mutation issues
            const nodeData = {
              id: d.id,
              label: d.label,
              type: d.type || (d.id?.length === 64 ? 'transaction' : 'address'),
              balance: d.balance,
              txCount: d.txCount || d.transaction_count,
              total_input_value: d.total_input_value,
              fee: d.fee,
              communityId: d.communityId,
              ...d
            };
            onNodeClick(nodeData);
          } catch (error) {
            logger.error('Error in node click handler:', error, d);
          }
        }
      });
      svg.on('click', (event) => {
        if ((event.target.tagName === 'svg' || event.target.tagName === 'rect') && onNodeClick) {
          event.stopPropagation();
          event.preventDefault();
          try {
            onNodeClick(null);
          } catch (error) {
            logger.error('Error in background click handler:', error);
          }
        }
      });

      // Final validation: ensure all edges reference existing nodes
      const nodeIdSet = new Set(sanitizedGraph.nodes.map(n => n.id));
      const validEdges = sanitizedGraph.edges.filter(e => {
        const sourceId = typeof e.source === 'string' ? e.source : e.source?.id;
        const targetId = typeof e.target === 'string' ? e.target : e.target?.id;
        const isValid = sourceId && targetId && nodeIdSet.has(sourceId) && nodeIdSet.has(targetId);
        if (!isValid) {
          logger.warn('Removing invalid edge before force simulation', { source: sourceId, target: targetId });
        }
        return isValid;
      });

      if (validEdges.length !== sanitizedGraph.edges.length) {
        logger.warn(`Filtered ${sanitizedGraph.edges.length - validEdges.length} invalid edge(s) before force simulation`);
        sanitizedGraph.edges = validEdges;
      }

      const simulation = d3.forceSimulation(sanitizedGraph.nodes)
        .force('link', d3.forceLink(validEdges).id(d => d && d.id ? d.id : null).distance(80).strength(0.08))
        .force('charge', d3.forceManyBody().strength(-150))
        .force('center', d3.forceCenter(width / 2, height / 2))
        .force('collision', d3.forceCollide().radius(d => nodeRadius(d) + 4));
      simulation.on('tick', () => {
        if (useBundling) {
          links.attr('d', d => {
            const sx = d.source.x, sy = d.source.y;
            const tx = d.target.x, ty = d.target.y;
            const dx = tx - sx, dy = ty - sy;
            const dr = Math.sqrt(dx * dx + dy * dy) * 0.40;
            return `M${sx},${sy}A${dr},${dr} 0 0,1 ${tx},${ty}`;
          });
        } else {
          links
            .attr('x1', d => d.source.x)
            .attr('y1', d => d.source.y)
            .attr('x2', d => d.target.x)
            .attr('y2', d => d.target.y);
        }
        nodes.attr('transform', d => `translate(${d.x}, ${d.y})`);
      });
      simulationRef.current = simulation;
      setContainerReady(true);
      logger.info('D3 renderer initialized successfully');
      return svg;
    } catch (err) {
      logger.error('Failed to initialize D3 renderer', err);
      setError(`Renderer initialization failed: ${err.message}`);
      return null;
    }
  }, [onNodeClick]);

  const setupResizeObserver = useCallback(() => {
    if (!containerRef.current) return;
    if (resizeObserverRef.current) resizeObserverRef.current.disconnect();
    const observer = new ResizeObserver(() => {
      if (graphRef.current) initializeD3(graphRef.current);
    });
    observer.observe(containerRef.current);
    resizeObserverRef.current = observer;
  }, [initializeD3]);

  const runLabelPropagationAlgorithm = useCallback(async () => {
    try {
      setIsLoading(true);
      setLayoutRunning(true);
      setError(null);
      logger.info('Running Label Propagation community detection (backend)...');

      const graphData = {
        nodes: graphRef.current?.nodes?.map(n => ({
          id: n.id,
          label: n.label || n.id,
          type: n.type || 'unknown'
        })) || [],
        edges: graphRef.current?.edges?.map(e => ({
          source: typeof e.source === 'object' ? e.source?.id : e.source,
          target: typeof e.target === 'object' ? e.target?.id : e.target
        })) || []
      };

      if (graphData.nodes.length === 0 || graphData.edges.length === 0) {
        toast.error('Graph must have nodes and edges to run Label Propagation');
        setIsLoading(false);
        setLayoutRunning(false);
        return;
      }

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

      if (!result.success) {
        throw new Error(result.error || 'Unknown error from API');
      }

      const data = result.data;
      logger.info('Label Propagation results received:', {
        num_communities: data.num_communities
      });

      if (svgRef.current && data.partition) {
        // Adapt to applyLouvainColors expected shape
        const lpaData = {
          partition: data.partition,
          num_communities: data.num_communities,
          modularity: 0
        };
        setCommunities(lpaData);

        // Robust coloring
        applyColorsToGraphNodes(lpaData);

        logger.info('Applied Label Propagation community colors to nodes');
      }

      toast.success(
        `Label Propagation found ${data.num_communities} ${data.num_communities === 1 ? 'community' : 'communities'}`,
        { duration: 5000 }
      );

      // Report result to parent
      if (onAlgorithmResult) {
        onAlgorithmResult('labelPropagation', {
          num_communities: data.num_communities,
          modularity: 0, // Label Propagation doesn't provide modularity
          partition: data.partition
        });
      }

      setIsLoading(false);
      setLayoutRunning(false);
    } catch (err) {
      logger.error('Label Propagation algorithm failed:', err);
      setError(`Label Propagation detection failed: ${err.message}`);
      toast.error(`Failed to detect communities: ${err.message}`);
      setIsLoading(false);
      setLayoutRunning(false);
    }
  }, []);

  const runLouvainAlgorithm = useCallback(async () => {
    try {
      setIsLoading(true);
      logger.info('Running Louvain community detection...');

      // Prepare graph data from current graph
      const graphData = {
        nodes: graphRef.current.nodes.map(n => ({
          id: n.id,
          label: n.label || n.id,
          type: n.type || 'unknown'
        })),
        edges: graphRef.current.edges.map(e => ({
          source: typeof e.source === 'object' ? e.source.id : e.source,
          target: typeof e.target === 'object' ? e.target.id : e.target,
          value: e.weight || e.value || 1
        })),
        resolution: 1.0
      };

      // Validate graph has data
      if (graphData.nodes.length === 0 || graphData.edges.length === 0) {
        toast.error('Graph must have nodes and edges to run community detection');
        setIsLoading(false);
        return;
      }

      logger.info(`Sending graph data: ${graphData.nodes.length} nodes, ${graphData.edges.length} edges`);

      // Call backend API
      const response = await fetch('/api/louvain', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(graphData)
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || `API error: ${response.status}`);
      }

      const result = await response.json();

      if (!result.success) {
        throw new Error(result.error || 'Unknown error from API');
      }

      const data = result.data;
      logger.info('Louvain results received:', {
        num_communities: data.num_communities,
        modularity: data.modularity
      });

      // Apply community colors to nodes
      if (svgRef.current && data.partition) {
        // store result in state (updates communitiesRef via useEffect)
        setCommunities(data);

        // Robust coloring
        applyColorsToGraphNodes(data);

        logger.info('Applied Louvain community colors to nodes');
      }


      // Show success notification with modularity and community count
      const modularityText = data.modularity.toFixed(3);
      const qualityText = data.modularity > 0.3 ? '(Good structure)' : '(Weak structure)';

      toast.success(
        `Found ${data.num_communities} ${data.num_communities === 1 ? 'community' : 'communities'}! ` +
        `Modularity: ${modularityText} ${qualityText}`,
        { duration: 5000 }
      );

      // Report result to parent
      if (onAlgorithmResult) {
        onAlgorithmResult('louvain', {
          num_communities: data.num_communities,
          modularity: data.modularity,
          partition: data.partition
        });
      }

      setIsLoading(false);

    } catch (err) {
      logger.error('Louvain algorithm failed:', err);
      setError(`Community detection failed: ${err.message}`);
      toast.error(`Failed to detect communities: ${err.message}`);
      setIsLoading(false);
    }
  }, []);

  const runLeidenAlgorithm = useCallback(async () => {
    try {
      setIsLoading(true);
      setError(null);
      logger.info('Running Leiden community detection (backend)...');

      const graphData = {
        nodes: graphRef.current?.nodes?.map(n => ({
          id: n.id,
          label: n.label || n.id,
          type: n.type || 'unknown'
        })) || [],
        edges: graphRef.current?.edges?.map(e => ({
          source: typeof e.source === 'object' ? e.source?.id : e.source,
          target: typeof e.target === 'object' ? e.target?.id : e.target,
          value: e.weight || e.value || 1
        })) || [],
        resolution: 1.0
      };

      if (graphData.nodes.length === 0 || graphData.edges.length === 0) {
        toast.error('Graph must have nodes and edges to run Leiden');
        setIsLoading(false);
        return;
      }

      const response = await fetch('/api/leiden', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(graphData)
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || `API error: ${response.status}`);
      }

      const result = await response.json();

      if (!result.success) {
        throw new Error(result.error || 'Unknown error from API');
      }

      const data = result.data;
      logger.info('Leiden results received:', {
        num_communities: data.num_communities,
        modularity: data.modularity
      });

      if (svgRef.current && data.partition) {
        setCommunities(data);

        // Robust coloring
        applyColorsToGraphNodes(data);

        logger.info('Applied Leiden community colors to nodes');
      }

      const modularityText = data.modularity.toFixed(3);
      const qualityText = data.modularity > 0.3 ? '(Good structure)' : '(Weak structure)';

      toast.success(
        `Leiden found ${data.num_communities} ${data.num_communities === 1 ? 'community' : 'communities'}! ` +
        `Modularity: ${modularityText} ${qualityText}`,
        { duration: 5000 }
      );

      // Report result to parent
      if (onAlgorithmResult) {
        onAlgorithmResult('leiden', {
          num_communities: data.num_communities,
          modularity: data.modularity,
          partition: data.partition
        });
      }

      setIsLoading(false);
    } catch (err) {
      logger.error('Leiden algorithm failed:', err);
      setError(`Leiden detection failed: ${err.message}`);
      toast.error(`Failed to detect communities: ${err.message}`);
      setIsLoading(false);
    }
  }, []);

  const runInfomapAlgorithm = useCallback(async () => {
    try {
      setIsLoading(true);
      setLayoutRunning(true);
      setError(null);
      logger.info('Running Infomap community detection (flow-based)...');

      const graphData = {
        nodes: graphRef.current?.nodes?.map(n => ({
          id: n.id,
          label: n.label || n.id,
          type: n.type || 'unknown'
        })) || [],
        edges: graphRef.current?.edges?.map(e => ({
          source: typeof e.source === 'object' ? e.source?.id : e.source,
          target: typeof e.target === 'object' ? e.target?.id : e.target,
          value: e.weight || e.value || 1
        })) || [],
        num_trials: 10,
        directed: true  // Bitcoin transactions are directed
      };

      if (graphData.nodes.length === 0 || graphData.edges.length === 0) {
        toast.error('Graph must have nodes and edges to run Infomap');
        setIsLoading(false);
        setLayoutRunning(false);
        return;
      }

      const response = await fetch('/api/infomap', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(graphData)
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || `API error: ${response.status}`);
      }

      const result = await response.json();

      if (!result.success) {
        throw new Error(result.error || 'Unknown error from API');
      }

      const data = result.data;
      logger.info('Infomap results received:', {
        num_communities: data.num_communities,
        codelength: data.codelength,
        modularity: data.modularity
      });

      if (svgRef.current && data.partition) {
        setCommunities(data);

        // Apply community colors
        applyColorsToGraphNodes(data);

        logger.info('Applied Infomap community colors to nodes');
      }

      const modularityText = data.modularity.toFixed(3);
      const codelengthText = data.codelength.toFixed(3);
      const qualityText = data.modularity > 0.3 ? '(Good structure)' : '(Weak structure)';

      toast.success(
        `Infomap found ${data.num_communities} ${data.num_communities === 1 ? 'community' : 'communities'}! ` +
        `Codelength: ${codelengthText}, Modularity: ${modularityText} ${qualityText}`,
        { duration: 5000 }
      );

      // Report result to parent
      if (onAlgorithmResult) {
        onAlgorithmResult('infomap', {
          num_communities: data.num_communities,
          modularity: data.modularity,
          codelength: data.codelength,
          partition: data.partition,
          flow_distribution: data.flow_distribution
        });
      }

      setIsLoading(false);
      setLayoutRunning(false);
    } catch (err) {
      logger.error('Infomap algorithm failed:', err);
      setError(`Infomap detection failed: ${err.message}`);
      toast.error(`Failed to detect communities: ${err.message}`);
      setIsLoading(false);
      setLayoutRunning(false);
    }
  }, []);

  const exportAsImage = useCallback(() => {
    if (!svgRef.current) return;
    try {
      const svgElement = svgRef.current.node();
      if (!svgElement) {
        logger.warn('No SVG element found for export');
        return;
      }

      // Get the SVG element and save using saveSvgAsPng.js
      saveSvgAsPng(svgElement, "chainbreak_graph.png", {
        backgroundColor: '#111827', // Match the dark background
        scale: 2, // Higher resolution
        width: svgElement.clientWidth,
        height: svgElement.clientHeight
      });

      logger.info('Graph exported as PNG image successfully');
    } catch (err) {
      logger.error('Failed to export graph as image', err);
      setError(`Image export failed: ${err.message}`);
    }
  }, []);

  const zoomIn = useCallback(() => {
    if (!svgRef.current || !zoomBehaviorRef.current) return;
    try {
      const svg = svgRef.current;
      svg.transition().duration(300).call(zoomBehaviorRef.current.scaleBy, 1.2);
    } catch (err) {
      logger.warn('Zoom in failed', err);
    }
  }, []);

  const zoomOut = useCallback(() => {
    if (!svgRef.current || !zoomBehaviorRef.current) return;
    try {
      const svg = svgRef.current;
      svg.transition().duration(300).call(zoomBehaviorRef.current.scaleBy, 1 / 1.2);
    } catch (err) {
      logger.warn('Zoom out failed', err);
    }
  }, []);

  const resetZoom = useCallback(() => {
    if (!svgRef.current || !zoomBehaviorRef.current) return;
    try {
      const svg = svgRef.current;
      svg.transition().duration(300).call(zoomBehaviorRef.current.transform, d3.zoomIdentity);
    } catch (err) {
      logger.warn('Reset zoom failed', err);
    }
  }, []);

  const fitView = useCallback(() => {
    if (!svgRef.current || !zoomBehaviorRef.current || !containerRef.current) return;
    try {
      const nodes = graphRef.current?.nodes;
      if (!nodes || nodes.length === 0) return;
      const xs = nodes.map(n => n.x).filter(Boolean);
      const ys = nodes.map(n => n.y).filter(Boolean);
      if (!xs.length) return;
      const minX = Math.min(...xs), maxX = Math.max(...xs);
      const minY = Math.min(...ys), maxY = Math.max(...ys);
      const w = containerRef.current.clientWidth;
      const h = containerRef.current.clientHeight;
      const gw = maxX - minX + 80, gh = maxY - minY + 80;
      const scale = Math.min(0.9, Math.min(w / gw, h / gh));
      const tx = (w - scale * (minX + maxX)) / 2;
      const ty = (h - scale * (minY + maxY)) / 2;
      const t = d3.zoomIdentity.translate(tx, ty).scale(scale);
      svgRef.current.transition().duration(500).call(zoomBehaviorRef.current.transform, t);
    } catch (err) {
      logger.warn('Fit view failed', err);
    }
  }, []);

  const toggleFullscreen = useCallback(async () => {
    if (!containerRef.current) return;

    try {
      if (!document.fullscreenElement) {
        await containerRef.current.requestFullscreen();
        setIsFullscreen(true);
        logger.info('Entered fullscreen mode');
      } else {
        await document.exitFullscreen();
        setIsFullscreen(false);
        logger.info('Exited fullscreen mode');
      }

    } catch (err) {
      logger.error('Fullscreen toggle failed', err);
      toast.error('Failed to toggle fullscreen mode');
    }
  }, []);


  useEffect(() => {
    if (!graphData) return;
    setError(null);
    setContainerReady(false);
    const graph = initializeGraph();
    if (graph) {
      const svg = initializeD3(graph);
      if (svg) {
        setupResizeObserver();
      }
    }
    return () => {
      if (roRef.current) {
        try { roRef.current.disconnect(); } catch (e) { /* ignore */ }
        roRef.current = null;
      }
      if (resizeObserverRef.current) {
        try { resizeObserverRef.current.disconnect(); } catch (e) { /* ignore */ }
        resizeObserverRef.current = null;
      }
      try { d3.select(containerRef.current).selectAll('svg').remove(); } catch (e) { /* ignore */ }
      if (simulationRef.current) {
        try { simulationRef.current.stop(); } catch (e) { /* ignore */ }
        simulationRef.current = null;
      }
      graphRef.current = { nodes: [], edges: [] };
    };
  }, [graphData, initializeGraph, initializeD3, setupResizeObserver]);

  useEffect(() => {
    const handleFullscreenChange = () => {
      setIsFullscreen(!!document.fullscreenElement);

      if (svgRef.current) {
        setTimeout(() => {
          try {
            if (graphRef.current) initializeD3(graphRef.current);
          } catch (err) {
            logger.warn('D3 re-render failed after fullscreen change', err);
          }
        }, 300);
      }
    };

    const handleKeyDown = (event) => {
      if (event.key === 'Escape' && document.fullscreenElement) {
        document.exitFullscreen().then(() => {
          setIsFullscreen(false);
          logger.info('Exited fullscreen via ESC key');
        }).catch(err => {
          logger.error('Failed to exit fullscreen via ESC', err);
        });
      }
    };

    document.addEventListener('fullscreenchange', handleFullscreenChange);
    document.addEventListener('keydown', handleKeyDown);

    return () => {
      document.removeEventListener('fullscreenchange', handleFullscreenChange);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, []);

  if (!graphData) {
    return (
      <div className={`flex items-center justify-center h-96 bg-gray-50 rounded-lg border-2 border-dashed border-gray-300 ${className}`}>
        <div className="text-center">
          <AlertCircle className="w-12 h-12 text-gray-400 mx-auto mb-4" />
          <p className="text-gray-500 text-lg">No graph data available</p>
          <p className="text-gray-400 text-sm">Fetch a Bitcoin address to visualize the transaction graph</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className={`flex items-center justify-center h-96 bg-red-50 rounded-lg border-2 border-red-200 ${className}`}>
        <div className="text-center">
          <AlertCircle className="w-12 h-12 text-red-400 mx-auto mb-4" />
          <p className="text-red-600 text-lg font-medium">Graph Rendering Error</p>
          <p className="text-red-500 text-sm">{error}</p>
          <div className="mt-4 flex gap-2 justify-center">
            <button
              onClick={() => {
                setError(null);
                const graph = initializeGraph();
                if (graph) initializeD3(graph);
              }}
              className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors"
            >
              Retry
            </button>
            <button
              onClick={() => {
                setError(null);
                if (graphRef.current) {
                  try {
                    graphRef.current.nodes = graphRef.current.nodes.map(n => ({ ...n, x: Math.random() * 1000, y: Math.random() * 1000 }));
                    initializeD3(graphRef.current);
                  } catch (e) {
                    logger.error('Fallback layout failed', e);
                    setError(`Fallback layout failed: ${e.message}`);
                  }
                }
              }}
              className="px-4 py-2 bg-gray-600 text-white rounded-lg hover:bg-gray-700 transition-colors"
            >
              Use Simple Layout
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={`relative ${className}`}>
      <div className="absolute top-4 left-4 z-10 flex flex-col gap-2">
        <motion.button
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          onClick={runLabelPropagationAlgorithm}
          disabled={isLoading || layoutRunning || !containerReady}
          className="flex items-center gap-2 px-3 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {isLoading && layoutRunning ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Play className="w-4 h-4" />
          )}
          {layoutRunning ? 'Running...' : 'Run Label Propagation'}
        </motion.button>
        <motion.button
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          onClick={runLouvainAlgorithm}
          disabled={isLoading || !containerReady}
          className="flex items-center gap-2 px-3 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {isLoading ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Play className="w-4 h-4" />
          )}
          Run Louvain
        </motion.button>
        <motion.button
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          onClick={runLeidenAlgorithm}
          disabled={isLoading || !containerReady}
          className="flex items-center gap-2 px-3 py-2 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {isLoading ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Play className="w-4 h-4" />
          )}
          Run Leiden
        </motion.button>
        <motion.button
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          onClick={runInfomapAlgorithm}
          disabled={isLoading || layoutRunning || !containerReady}
          className="flex items-center gap-2 px-3 py-2 bg-amber-600 text-white rounded-lg hover:bg-amber-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {isLoading && layoutRunning ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Play className="w-4 h-4" />
          )}
          {layoutRunning ? 'Running...' : 'Run Infomap'}
        </motion.button>
        <motion.button
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          onClick={exportAsImage}
          disabled={isLoading || !containerReady}
          className="flex items-center gap-2 px-3 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          <Image className="w-4 h-4" />
          Export PNG
        </motion.button>
      </div>

      {/* ── Viewport controls – bottom-right corner ──────────────────────────── */}
      <div className="absolute bottom-4 right-4 z-10 flex flex-col gap-1.5">
        {/* Zoom in */}
        <motion.button
          whileHover={{ scale: 1.08 }} whileTap={{ scale: 0.92 }}
          onClick={zoomIn} disabled={!containerReady}
          title="Zoom In"
          className="w-9 h-9 flex items-center justify-center bg-gray-800/90 text-white rounded-lg border border-gray-600 hover:bg-gray-700 disabled:opacity-40 transition-colors shadow"
        >
          <Plus className="w-4 h-4" />
        </motion.button>
        {/* Zoom level / reset */}
        <motion.button
          whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}
          onClick={resetZoom} disabled={!containerReady}
          title="Reset zoom to 100%"
          className="h-9 px-1.5 flex items-center justify-center bg-gray-800/90 text-white text-xs rounded-lg border border-gray-600 hover:bg-gray-700 disabled:opacity-40 transition-colors shadow font-mono"
        >
          {Math.round(zoomLevel * 100)}%
        </motion.button>
        {/* Zoom out */}
        <motion.button
          whileHover={{ scale: 1.08 }} whileTap={{ scale: 0.92 }}
          onClick={zoomOut} disabled={!containerReady}
          title="Zoom Out"
          className="w-9 h-9 flex items-center justify-center bg-gray-800/90 text-white rounded-lg border border-gray-600 hover:bg-gray-700 disabled:opacity-40 transition-colors shadow"
        >
          <Minus className="w-4 h-4" />
        </motion.button>
        {/* Fit view */}
        <motion.button
          whileHover={{ scale: 1.08 }} whileTap={{ scale: 0.92 }}
          onClick={fitView} disabled={!containerReady}
          title="Fit graph to viewport"
          className="w-9 h-9 flex items-center justify-center bg-indigo-700/90 text-white rounded-lg border border-indigo-500 hover:bg-indigo-600 disabled:opacity-40 transition-colors shadow"
        >
          <Maximize2 className="w-4 h-4" />
        </motion.button>
        {/* Fullscreen */}
        <motion.button
          whileHover={{ scale: 1.08 }} whileTap={{ scale: 0.92 }}
          onClick={toggleFullscreen} disabled={!containerReady}
          title={isFullscreen ? 'Exit Fullscreen' : 'Fullscreen'}
          className={`w-9 h-9 flex items-center justify-center rounded-lg border disabled:opacity-40 transition-colors shadow ${
            isFullscreen
              ? 'bg-red-700/90 border-red-500 hover:bg-red-600 text-white'
              : 'bg-gray-800/90 border-gray-600 hover:bg-gray-700 text-white'
          }`}
        >
          {isFullscreen ? <Shrink className="w-4 h-4" /> : <Expand className="w-4 h-4" />}
        </motion.button>
        {/* Pan hint */}
        <div className="flex items-center justify-center gap-1 mt-1 text-gray-500" title="Click + drag to pan">
          <Move className="w-3 h-3" />
          <span className="text-xs">Pan</span>
        </div>
      </div>

      {/* ── Interactive Legend – bottom-left ─────────────────────────────────── */}
      <div className="absolute bottom-4 left-4 z-10 bg-gray-900/90 border border-gray-700 rounded-xl p-3 shadow-xl backdrop-blur-sm">
        <p className="text-xs font-semibold text-gray-400 mb-2 tracking-wide uppercase">Legend</p>
        <div className="flex flex-col gap-1">
          {LEGEND_TIERS.map(tier => {
            const isActive = activeLegendFilter === tier.id;
            const isFiltering = activeLegendFilter !== null;
            return (
              <button
                key={tier.id}
                onClick={() => setActiveLegendFilter(prev => prev === tier.id ? null : tier.id)}
                className={`flex items-center gap-2 px-2 py-1 rounded-lg text-xs transition-all ${
                  isActive
                    ? 'ring-2 ring-white/30 scale-105'
                    : isFiltering
                    ? 'opacity-40 hover:opacity-70'
                    : 'hover:bg-gray-700/50'
                }`}
                title={isActive ? 'Click to clear filter' : `Filter to ${tier.label}`}
              >
                <span
                  className="w-3 h-3 rounded-full flex-shrink-0"
                  style={{ backgroundColor: tier.color, boxShadow: isActive ? `0 0 8px ${tier.color}` : 'none' }}
                />
                <span style={{ color: isActive ? tier.textColor : '#9ca3af' }}>{tier.label}</span>
                {isActive && <span className="ml-auto text-gray-500 text-xs">✕</span>}
              </button>
            );
          })}
        </div>
        {activeLegendFilter && (
          <button
            onClick={() => setActiveLegendFilter(null)}
            className="mt-2 w-full text-xs text-gray-500 hover:text-white border border-gray-700 rounded-lg py-1 transition-colors"
          >
            Clear filter
          </button>
        )}
      </div>




      <div
        ref={containerRef}
        className="w-full h-full bg-gray-900 rounded-lg overflow-hidden"
        style={{ minHeight: '400px' }}
      />

      {!containerReady && (
        <div className="absolute inset-0 flex items-center justify-center bg-gray-900/80 rounded-lg z-20">
          <div className="text-center">
            <Loader2 className="w-8 h-8 text-white animate-spin mx-auto mb-2" />
            <p className="text-white text-sm">Initializing graph renderer...</p>
          </div>
        </div>
      )}
    </div>
  );
};

// Only re-render (and thus re-run D3 initialization effect) when actual graph
// inputs change, not on unrelated parent state updates.
const arePropsEqual = (prevProps, nextProps) => {
  return (
    prevProps.graphData === nextProps.graphData &&
    prevProps.onNodeClick === nextProps.onNodeClick &&
    prevProps.className === nextProps.className &&
    prevProps.illicitAddresses === nextProps.illicitAddresses
  );
};

export default React.memo(GraphRenderer, arePropsEqual);
