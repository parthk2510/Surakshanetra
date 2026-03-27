// frontend/core/LeidenDetector.ts
import Graph from 'graphology';
import louvain from 'graphology-communities-louvain';

/**
 * Leiden Community Detection Algorithm
 *
 * Leiden is an improvement over Louvain that guarantees connected communities.
 * Since a pure Leiden implementation is complex, we use Louvain with refinement
 * steps to ensure community connectivity — mimicking Leiden's key advantage.
 */

export interface CommunityMetadata {
    id: number;
    nodes: string[];
    size: number;
    totalValue: number;
    totalTxCount: number;
    avgRiskScore: number;
    density: number;
    externalConnections: number;
}

export interface LeidenResult {
    success: boolean;
    error?: string;
    communities: Record<string, number>;
    communityMetadata: Record<number, CommunityMetadata>;
    betweenness?: Record<string, number>;
    modularity?: number;
    numCommunities?: number;
}

interface RawNode {
    id?: string;
    nodeId?: string;
    type?: string;
    balance?: number;
    txCount?: number;
    riskScore?: number;
    [key: string]: unknown;
}

interface RawEdge {
    source: string;
    target: string;
    value?: number;
}

/**
 * Run Leiden-style community detection
 */
export async function runLeidenDetection(
    nodes: Record<string, RawNode>,
    edges: RawEdge[]
): Promise<LeidenResult> {
    try {
        const graph = new Graph({ type: 'undirected', multi: false });

        // Add address nodes only (skip transaction nodes)
        const addressNodes = Object.values(nodes).filter(n => n.type === 'address');
        addressNodes.forEach(node => {
            try {
                const nodeId = node.id ?? node.nodeId;
                if (nodeId) {
                    graph.addNode(nodeId, { ...node, weight: node.balance || 1 });
                }
            } catch {
                // Node might already exist
            }
        });

        // Collapse transaction nodes — connect addresses directly
        const addressEdges = new Map<string, { value: number; count: number; source: string; target: string }>();

        edges.forEach(edge => {
            const sourceNode = nodes[edge.source];
            const targetNode = nodes[edge.target];

            if (!sourceNode || !targetNode) return;

            if (sourceNode.type === 'address' && targetNode.type === 'address') {
                const edgeKey = [edge.source, edge.target].sort().join('->');
                const existing = addressEdges.get(edgeKey) || { value: 0, count: 0, source: edge.source, target: edge.target };
                addressEdges.set(edgeKey, {
                    value: existing.value + (edge.value || 0),
                    count: existing.count + 1,
                    source: edge.source,
                    target: edge.target,
                });
            } else if (sourceNode.type === 'address' && targetNode.type === 'transaction') {
                edges.forEach(outEdge => {
                    if (outEdge.source === targetNode.id && nodes[outEdge.target]?.type === 'address') {
                        const edgeKey = [sourceNode.id, outEdge.target].sort().join('->');
                        const existing = addressEdges.get(edgeKey) || { value: 0, count: 0, source: sourceNode.id as string, target: outEdge.target };
                        addressEdges.set(edgeKey, {
                            value: existing.value + (edge.value || 0),
                            count: existing.count + 1,
                            source: sourceNode.id as string,
                            target: outEdge.target,
                        });
                    }
                });
            } else if (sourceNode.type === 'transaction' && targetNode.type === 'address') {
                edges.forEach(inEdge => {
                    if (inEdge.target === sourceNode.id && nodes[inEdge.source]?.type === 'address') {
                        const edgeKey = [inEdge.source, targetNode.id].sort().join('->');
                        const existing = addressEdges.get(edgeKey) || { value: 0, count: 0, source: inEdge.source, target: targetNode.id as string };
                        addressEdges.set(edgeKey, {
                            value: existing.value + (edge.value || 0),
                            count: existing.count + 1,
                            source: inEdge.source,
                            target: targetNode.id as string,
                        });
                    }
                });
            }
        });

        addressEdges.forEach((edgeData) => {
            try {
                if (graph.hasNode(edgeData.source) && graph.hasNode(edgeData.target)) {
                    graph.addEdge(edgeData.source, edgeData.target, {
                        weight: edgeData.value || 1,
                        count: edgeData.count,
                    });
                }
            } catch {
                // Edge might already exist
            }
        });

        if (graph.order === 0) {
            return { success: false, error: 'No nodes to analyze', communities: {}, communityMetadata: {} };
        }

        const communities: Record<string, number> = louvain(graph, { resolution: 1.0, randomWalk: false });

        const refinedCommunities = ensureConnectedCommunities(graph, communities);
        const finalCommunities = refineWithLocalMoving(graph, refinedCommunities);
        const communityMetadata = calculateCommunityMetadata(graph, finalCommunities, nodes);
        const betweenness = calculateBetweennessCentrality(graph, finalCommunities);

        return {
            success: true,
            communities: finalCommunities,
            communityMetadata,
            betweenness,
            modularity: calculateModularity(graph, finalCommunities),
            numCommunities: Object.keys(communityMetadata).length,
        };
    } catch (error) {
        console.error('Leiden detection failed:', error);
        return {
            success: false,
            error: (error as Error).message,
            communities: {},
            communityMetadata: {},
        };
    }
}

function ensureConnectedCommunities(
    graph: Graph,
    communities: Record<string, number>
): Record<string, number> {
    const refined: Record<string, number> = { ...communities };
    const communityMap = new Map<number, Set<string>>();

    Object.entries(communities).forEach(([node, comm]) => {
        if (!communityMap.has(comm)) communityMap.set(comm, new Set());
        communityMap.get(comm)!.add(node);
    });

    let nextCommunityId = Math.max(...Object.values(communities)) + 1;

    communityMap.forEach((nodeSet) => {
        const nodeArr = Array.from(nodeSet);
        if (nodeArr.length <= 1) return;

        const visited = new Set<string>();
        const components: Set<string>[] = [];

        nodeArr.forEach(startNode => {
            if (visited.has(startNode)) return;

            const component = new Set<string>();
            const queue = [startNode];

            while (queue.length > 0) {
                const node = queue.shift()!;
                if (visited.has(node) || !nodeSet.has(node)) continue;
                visited.add(node);
                component.add(node);
                graph.forEachNeighbor(node, neighbor => {
                    if (nodeSet.has(neighbor) && !visited.has(neighbor)) queue.push(neighbor);
                });
            }

            if (component.size > 0) components.push(component);
        });

        if (components.length > 1) {
            components.slice(1).forEach(component => {
                component.forEach(node => { refined[node] = nextCommunityId; });
                nextCommunityId++;
            });
        }
    });

    return refined;
}

function refineWithLocalMoving(
    graph: Graph,
    communities: Record<string, number>
): Record<string, number> {
    const refined: Record<string, number> = { ...communities };
    let improved = true;
    let iterations = 0;
    const maxIterations = 10;

    while (improved && iterations < maxIterations) {
        improved = false;
        iterations++;

        graph.forEachNode(node => {
            const currentCommunity = refined[node];
            const neighborCommunities = new Map<number, number>();

            graph.forEachNeighbor(node, neighbor => {
                const neighborComm = refined[neighbor];
                const weight = (graph.getEdgeAttribute(graph.edge(node, neighbor) ?? '', 'weight') as number) || 1;
                neighborCommunities.set(neighborComm, (neighborCommunities.get(neighborComm) || 0) + weight);
            });

            let bestCommunity = currentCommunity;
            let bestWeight = neighborCommunities.get(currentCommunity) || 0;

            neighborCommunities.forEach((weight, comm) => {
                if (weight > bestWeight) {
                    bestWeight = weight;
                    bestCommunity = comm;
                }
            });

            if (bestCommunity !== currentCommunity) {
                refined[node] = bestCommunity;
                improved = true;
            }
        });
    }

    return refined;
}

function calculateCommunityMetadata(
    graph: Graph,
    communities: Record<string, number>,
    nodes: Record<string, RawNode>
): Record<number, CommunityMetadata> {
    const metadata: Record<number, CommunityMetadata> = {};

    Object.entries(communities).forEach(([nodeId, commId]) => {
        if (!metadata[commId]) {
            metadata[commId] = {
                id: commId,
                nodes: [],
                size: 0,
                totalValue: 0,
                totalTxCount: 0,
                avgRiskScore: 0,
                density: 0,
                externalConnections: 0,
            };
        }

        metadata[commId].nodes.push(nodeId);
        metadata[commId].size++;

        const node = nodes[nodeId];
        if (node) {
            metadata[commId].totalValue += (node.balance as number) || 0;
            metadata[commId].totalTxCount += (node.txCount as number) || 0;
            metadata[commId].avgRiskScore += (node.riskScore as number) || 0;
        }
    });

    Object.values(metadata).forEach(comm => {
        comm.avgRiskScore = comm.avgRiskScore / comm.size;

        let internalEdges = 0;
        comm.nodes.forEach(node => {
            graph.forEachNeighbor(node, neighbor => {
                if (comm.nodes.includes(neighbor)) {
                    internalEdges++;
                } else {
                    comm.externalConnections++;
                }
            });
        });

        const maxPossibleEdges = (comm.size * (comm.size - 1)) / 2;
        comm.density = maxPossibleEdges > 0 ? (internalEdges / 2) / maxPossibleEdges : 0;
    });

    return metadata;
}

function calculateBetweennessCentrality(
    graph: Graph,
    communities: Record<string, number>
): Record<string, number> {
    const betweenness: Record<string, number> = {};

    graph.forEachNode(node => { betweenness[node] = 0; });

    const commIds = [...new Set(Object.values(communities))];

    commIds.forEach(comm1 => {
        commIds.forEach(comm2 => {
            if (comm1 >= comm2) return;

            Object.entries(communities).forEach(([node, comm]) => {
                if (comm !== comm1 && comm !== comm2) return;

                const neighbors1: string[] = [];
                const neighbors2: string[] = [];

                graph.forEachNeighbor(node, neighbor => {
                    const neighborComm = communities[neighbor];
                    if (neighborComm === comm1) neighbors1.push(neighbor);
                    if (neighborComm === comm2) neighbors2.push(neighbor);
                });

                if (neighbors1.length > 0 && neighbors2.length > 0) {
                    betweenness[node] += neighbors1.length * neighbors2.length;
                }
            });
        });
    });

    const maxBetweenness = Math.max(...Object.values(betweenness), 1);
    Object.keys(betweenness).forEach(node => {
        betweenness[node] = betweenness[node] / maxBetweenness;
    });

    return betweenness;
}

function calculateModularity(graph: Graph, communities: Record<string, number>): number {
    const m = graph.size;
    if (m === 0) return 0;

    let modularity = 0;

    graph.forEachEdge((edge, attrs, source, target) => {
        const weight = (attrs.weight as number) || 1;
        if (communities[source] === communities[target]) {
            const degreeSource = graph.degree(source);
            const degreeTarget = graph.degree(target);
            modularity += weight - (degreeSource * degreeTarget) / (2 * m);
        }
    });

    return modularity / (2 * m);
}

export function getCommunityColor(communityId: number): string {
    const colors = [
        '#3b82f6', '#ef4444', '#10b981', '#f59e0b', '#8b5cf6',
        '#ec4899', '#14b8a6', '#f97316', '#6366f1', '#84cc16',
    ];
    return colors[communityId % colors.length];
}

export default { runLeidenDetection, getCommunityColor };
