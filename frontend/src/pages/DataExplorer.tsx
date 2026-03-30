import { motion } from 'framer-motion';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
    Activity,
    ChevronDown,
    ChevronRight,
    CircleDot,
    Database,
    GitFork,
    Hash,
    HardDrive,
    Layers,
    Network,
    RefreshCcw,
    Tag,
    Zap,
} from 'lucide-react';
import {
    dataExplorerApi,
    type DataExplorerStatus,
    type Neo4jGraphEdge,
    type Neo4jGraphNode,
    type Neo4jOverview,
    type Neo4jNodeDetail,
    type Neo4jRelationshipDetail,
    type QdrantCollectionInfo,
    type QdrantSamplePoint,
} from '../api/client';
import { useAuth } from '../contexts/AuthContext';

// ── Styles ──

const cardStyle = {
    background: 'rgba(15, 23, 42, 0.78)',
    border: '1px solid rgba(148, 163, 184, 0.16)',
    borderRadius: '1rem',
    backdropFilter: 'blur(24px)',
};

const accentBlue = '#60a5fa';
const accentPurple = '#a78bfa';
const accentAmber = '#fbbf24';
const accentGreen = '#34d399';
const accentRose = '#fb7185';

const labelColors: Record<string, string> = {
    Tender: '#22c55e',
    Project: accentBlue,
    TeamMember: accentPurple,
    Client: accentAmber,
    Certification: accentGreen,
    Category: accentRose,
    Requirement: '#f472b6',
};

function getLabelColor(label: string): string {
    return labelColors[label] || '#94a3b8';
}

const relColors: Record<string, string> = {
    HAS_REQUIREMENT: '#22c55e',
    FOR_CLIENT: accentAmber,
    HAS_CATEGORY: accentRose,
    DELIVERED: accentPurple,
    HOLDS: accentGreen,
    REQUIRES_CERT: accentBlue,
};

// ── Subcomponents ──

function StatCard({ label, value, icon: Icon, color }: { label: string; value: string | number; icon: typeof Database; color: string }) {
    return (
        <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            style={{
                ...cardStyle,
                padding: '1.25rem',
                display: 'flex',
                alignItems: 'center',
                gap: '1rem',
                flex: '1 1 200px',
                minWidth: 180,
            }}
        >
            <div style={{
                width: 44, height: 44, borderRadius: '0.75rem',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                background: `${color}18`, border: `1px solid ${color}30`,
            }}>
                <Icon size={22} color={color} />
            </div>
            <div>
                <div style={{ fontSize: '1.5rem', fontWeight: 700, color: '#f1f5f9' }}>{value}</div>
                <div style={{ fontSize: '0.78rem', color: '#94a3b8', marginTop: 2 }}>{label}</div>
            </div>
        </motion.div>
    );
}

function SectionHeader({ title, icon: Icon, color, badge }: { title: string; icon: typeof Database; color: string; badge?: string }) {
    return (
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1rem' }}>
            <div style={{
                width: 36, height: 36, borderRadius: '0.625rem',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                background: `${color}18`, border: `1px solid ${color}30`,
            }}>
                <Icon size={18} color={color} />
            </div>
            <h2 style={{ margin: 0, fontSize: '1.15rem', fontWeight: 600, color: '#f1f5f9' }}>{title}</h2>
            {badge && (
                <span style={{
                    fontSize: '0.7rem', padding: '2px 8px', borderRadius: '999px',
                    background: `${color}20`, color, border: `1px solid ${color}40`,
                }}>{badge}</span>
            )}
        </div>
    );
}

function Badge({ text, color }: { text: string; color: string }) {
    return (
        <span style={{
            display: 'inline-block', fontSize: '0.68rem', fontWeight: 600,
            padding: '2px 8px', borderRadius: '999px',
            background: `${color}20`, color, border: `1px solid ${color}40`,
            whiteSpace: 'nowrap',
        }}>{text}</span>
    );
}

function BarChart({ items, maxValue }: { items: { label: string; value: number; color: string }[]; maxValue: number }) {
    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            {items.map((item) => (
                <div key={item.label} style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                    <div style={{ width: 110, fontSize: '0.78rem', color: '#cbd5e1', textAlign: 'right', flexShrink: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {item.label}
                    </div>
                    <div style={{ flex: 1, height: 22, borderRadius: '0.375rem', background: 'rgba(30,41,59,0.7)', overflow: 'hidden', position: 'relative' }}>
                        <motion.div
                            initial={{ width: 0 }}
                            animate={{ width: `${maxValue > 0 ? (item.value / maxValue) * 100 : 0}%` }}
                            transition={{ duration: 0.6, ease: 'easeOut' }}
                            style={{
                                height: '100%', borderRadius: '0.375rem',
                                background: `linear-gradient(90deg, ${item.color}60, ${item.color})`,
                            }}
                        />
                        <span style={{
                            position: 'absolute', right: 8, top: '50%', transform: 'translateY(-50%)',
                            fontSize: '0.7rem', fontWeight: 600, color: '#f1f5f9',
                        }}>{item.value.toLocaleString()}</span>
                    </div>
                </div>
            ))}
        </div>
    );
}

// ── Graph Visualization (Canvas-based) ──

function GraphCanvas({ nodes, edges }: { nodes: Neo4jGraphNode[]; edges: Neo4jGraphEdge[] }) {
    const canvasWidth = 900;
    const canvasHeight = 500;

    const layout = useMemo(() => {
        // Group nodes by label
        const groups: Record<string, Neo4jGraphNode[]> = {};
        nodes.forEach((n) => {
            if (!groups[n.label]) groups[n.label] = [];
            groups[n.label].push(n);
        });

        const labels = Object.keys(groups);
        const positions: Record<string, { x: number; y: number }> = {};
        const cx = canvasWidth / 2;
        const cy = canvasHeight / 2;

        // Place groups in a radial layout
        labels.forEach((label, li) => {
            const angle = (li / labels.length) * 2 * Math.PI - Math.PI / 2;
            const groupRadius = 160;
            const gcx = cx + Math.cos(angle) * groupRadius;
            const gcy = cy + Math.sin(angle) * groupRadius;

            const groupNodes = groups[label];
            groupNodes.forEach((node, ni) => {
                const subAngle = (ni / Math.max(groupNodes.length, 1)) * 2 * Math.PI;
                const subRadius = Math.min(50 + groupNodes.length * 8, 120);
                positions[node.id] = {
                    x: gcx + Math.cos(subAngle) * subRadius,
                    y: gcy + Math.sin(subAngle) * subRadius,
                };
            });
        });

        return positions;
    }, [nodes]);

    const [hoveredNode, setHoveredNode] = useState<string | null>(null);
    const [tooltip, setTooltip] = useState<{ x: number; y: number; node: Neo4jGraphNode } | null>(null);

    const handleMouseMove = useCallback((e: React.MouseEvent<SVGSVGElement>) => {
        const rect = e.currentTarget.getBoundingClientRect();
        const mx = e.clientX - rect.left;
        const my = e.clientY - rect.top;

        let found: Neo4jGraphNode | null = null;
        for (const node of nodes) {
            const pos = layout[node.id];
            if (!pos) continue;
            const dx = mx - pos.x;
            const dy = my - pos.y;
            if (dx * dx + dy * dy < 225) {
                found = node;
                break;
            }
        }

        if (found) {
            setHoveredNode(found.id);
            setTooltip({ x: mx, y: my, node: found });
        } else {
            setHoveredNode(null);
            setTooltip(null);
        }
    }, [nodes, layout]);

    if (nodes.length === 0) {
        return (
            <div style={{ padding: '2rem', textAlign: 'center', color: '#94a3b8' }}>
                No graph data available. Ingest documents to populate the knowledge graph.
            </div>
        );
    }

    return (
        <div style={{ position: 'relative', overflow: 'hidden', borderRadius: '0.75rem', background: 'rgba(10,15,30,0.6)' }}>
            <svg
                width="100%"
                height={canvasHeight}
                viewBox={`0 0 ${canvasWidth} ${canvasHeight}`}
                onMouseMove={handleMouseMove}
                onMouseLeave={() => { setHoveredNode(null); setTooltip(null); }}
                style={{ display: 'block' }}
            >
                {/* Edges */}
                {edges.map((edge, i) => {
                    const src = layout[edge.source];
                    const tgt = layout[edge.target];
                    if (!src || !tgt) return null;
                    const isHighlighted = hoveredNode === edge.source || hoveredNode === edge.target;
                    return (
                        <line
                            key={i}
                            x1={src.x} y1={src.y}
                            x2={tgt.x} y2={tgt.y}
                            stroke={relColors[edge.type] || '#475569'}
                            strokeWidth={isHighlighted ? 2 : 1}
                            strokeOpacity={hoveredNode ? (isHighlighted ? 0.8 : 0.15) : 0.35}
                        />
                    );
                })}

                {/* Nodes */}
                {nodes.map((node) => {
                    const pos = layout[node.id];
                    if (!pos) return null;
                    const color = getLabelColor(node.label);
                    const isHovered = hoveredNode === node.id;
                    const isConnected = hoveredNode ? edges.some(
                        (e) => (e.source === hoveredNode && e.target === node.id) || (e.target === hoveredNode && e.source === node.id)
                    ) : false;
                    const opacity = hoveredNode ? (isHovered || isConnected ? 1 : 0.25) : 1;

                    return (
                        <g key={node.id} opacity={opacity}>
                            <circle
                                cx={pos.x} cy={pos.y}
                                r={isHovered ? 14 : 10}
                                fill={`${color}30`}
                                stroke={color}
                                strokeWidth={isHovered ? 2.5 : 1.5}
                            />
                            <text
                                x={pos.x} y={pos.y + 22}
                                textAnchor="middle"
                                fontSize="8"
                                fill="#cbd5e1"
                                fontFamily="inherit"
                            >
                                {node.name.length > 15 ? node.name.slice(0, 14) + '...' : node.name}
                            </text>
                        </g>
                    );
                })}
            </svg>

            {/* Tooltip */}
            {tooltip && (
                <div style={{
                    position: 'absolute',
                    left: tooltip.x + 16,
                    top: tooltip.y - 10,
                    background: 'rgba(15, 23, 42, 0.95)',
                    border: `1px solid ${getLabelColor(tooltip.node.label)}50`,
                    borderRadius: '0.5rem',
                    padding: '0.5rem 0.75rem',
                    pointerEvents: 'none',
                    zIndex: 10,
                    maxWidth: 250,
                }}>
                    <div style={{ fontSize: '0.75rem', fontWeight: 600, color: getLabelColor(tooltip.node.label) }}>{tooltip.node.label}</div>
                    <div style={{ fontSize: '0.82rem', color: '#f1f5f9', marginTop: 2 }}>{tooltip.node.name}</div>
                </div>
            )}

            {/* Legend */}
            <div style={{
                position: 'absolute', bottom: 12, left: 12,
                display: 'flex', gap: '0.75rem', flexWrap: 'wrap',
            }}>
                {Object.entries(labelColors).map(([label, color]) => (
                    <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                        <div style={{ width: 10, height: 10, borderRadius: '50%', background: color }} />
                        <span style={{ fontSize: '0.68rem', color: '#94a3b8' }}>{label}</span>
                    </div>
                ))}
            </div>
        </div>
    );
}

// ── Collection Detail Panel ──

function QdrantCollectionDetail({ collection }: { collection: QdrantCollectionInfo }) {
    const [expanded, setExpanded] = useState(false);
    const [points, setPoints] = useState<QdrantSamplePoint[]>([]);
    const [payloadKeys, setPayloadKeys] = useState<Record<string, { count: number; type: string; sample_values: (string | null)[] }> | null>(null);
    const [loading, setLoading] = useState(false);

    const loadDetails = async () => {
        if (points.length > 0) {
            setExpanded(!expanded);
            return;
        }
        setExpanded(true);
        setLoading(true);
        try {
            const [sampleRes, keysRes] = await Promise.all([
                dataExplorerApi.qdrantSample(collection.name, 8),
                dataExplorerApi.qdrantPayloadKeys(collection.name),
            ]);
            setPoints(sampleRes.items);
            setPayloadKeys(keysRes.keys);
        } catch { /* ignore */ }
        setLoading(false);
    };

    return (
        <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            style={{ ...cardStyle, padding: '1rem', marginBottom: '0.75rem' }}
        >
            <div
                style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', cursor: 'pointer' }}
                onClick={loadDetails}
            >
                {expanded ? <ChevronDown size={16} color="#94a3b8" /> : <ChevronRight size={16} color="#94a3b8" />}
                <HardDrive size={18} color={accentBlue} />
                <div style={{ flex: 1 }}>
                    <span style={{ fontWeight: 600, color: '#f1f5f9', fontSize: '0.92rem' }}>{collection.name}</span>
                </div>
                <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                    <Badge text={`${collection.points_count.toLocaleString()} points`} color={accentBlue} />
                    <Badge text={`${collection.dimension ?? '?'}d`} color={accentPurple} />
                    <Badge text={collection.distance} color={accentAmber} />
                    <Badge text={collection.status} color={collection.status === 'green' ? accentGreen : accentAmber} />
                </div>
            </div>

            {expanded && (
                <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: 'auto', opacity: 1 }}
                    style={{ marginTop: '1rem', overflow: 'hidden' }}
                >
                    {loading ? (
                        <div style={{ padding: '1rem', color: '#94a3b8', textAlign: 'center' }}>Loading...</div>
                    ) : (
                        <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
                            {/* Payload schema */}
                            {payloadKeys && (
                                <div style={{ flex: '1 1 280px', minWidth: 280 }}>
                                    <div style={{ fontSize: '0.78rem', fontWeight: 600, color: accentPurple, marginBottom: '0.5rem' }}>
                                        Payload Schema (sampled)
                                    </div>
                                    <div style={{
                                        background: 'rgba(10,15,30,0.5)', borderRadius: '0.5rem', padding: '0.75rem',
                                        fontSize: '0.75rem', fontFamily: 'monospace',
                                    }}>
                                        {Object.entries(payloadKeys).map(([key, info]) => (
                                            <div key={key} style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.35rem', alignItems: 'baseline' }}>
                                                <span style={{ color: accentBlue, fontWeight: 600, minWidth: 100 }}>{key}</span>
                                                <span style={{ color: '#94a3b8' }}>{info.type}</span>
                                                <span style={{ color: '#64748b' }}>({info.count}x)</span>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}

                            {/* Sample points */}
                            <div style={{ flex: '2 1 400px', minWidth: 300 }}>
                                <div style={{ fontSize: '0.78rem', fontWeight: 600, color: accentAmber, marginBottom: '0.5rem' }}>
                                    Sample Points ({points.length})
                                </div>
                                <div style={{
                                    maxHeight: 360, overflowY: 'auto',
                                    display: 'flex', flexDirection: 'column', gap: '0.4rem',
                                }}>
                                    {points.map((pt) => (
                                        <div key={pt.id} style={{
                                            background: 'rgba(10,15,30,0.5)', borderRadius: '0.4rem', padding: '0.6rem',
                                            border: '1px solid rgba(148,163,184,0.08)',
                                        }}>
                                            <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.3rem', flexWrap: 'wrap' }}>
                                                <span style={{ fontSize: '0.65rem', color: '#64748b', fontFamily: 'monospace' }}>
                                                    {pt.id.slice(0, 12)}...
                                                </span>
                                                {pt.metadata.doc_type != null && <Badge text={String(pt.metadata.doc_type)} color={accentPurple} />}
                                                {pt.metadata.document_id != null && <Badge text={`doc:${String(pt.metadata.document_id)}`} color={accentBlue} />}
                                            </div>
                                            <div style={{ fontSize: '0.76rem', color: '#cbd5e1', lineHeight: 1.45 }}>
                                                {pt.text_preview || '(empty)'}
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        </div>
                    )}
                </motion.div>
            )}
        </motion.div>
    );
}

// ── Neo4j Node Explorer ──

function Neo4jNodeExplorer({ nodeLabels }: { nodeLabels: { label: string; count: number }[] }) {
    const [selectedLabel, setSelectedLabel] = useState<string | null>(null);
    const [nodes, setNodes] = useState<Neo4jNodeDetail[]>([]);
    const [relationships, setRelationships] = useState<Neo4jRelationshipDetail[]>([]);
    const [loading, setLoading] = useState(false);

    const loadSample = async (label: string) => {
        if (selectedLabel === label) {
            setSelectedLabel(null);
            return;
        }
        setSelectedLabel(label);
        setLoading(true);
        try {
            const res = await dataExplorerApi.neo4jSample(label, 15);
            setNodes(res.nodes);
            setRelationships(res.relationships);
        } catch {
            setNodes([]);
            setRelationships([]);
        }
        setLoading(false);
    };

    return (
        <div>
            <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '1rem' }}>
                {nodeLabels.map(({ label, count }) => (
                    <button
                        key={label}
                        onClick={() => loadSample(label)}
                        style={{
                            background: selectedLabel === label ? `${getLabelColor(label)}30` : 'rgba(30,41,59,0.5)',
                            border: `1px solid ${selectedLabel === label ? getLabelColor(label) : 'rgba(148,163,184,0.16)'}`,
                            borderRadius: '0.5rem',
                            padding: '0.5rem 0.9rem',
                            color: selectedLabel === label ? getLabelColor(label) : '#cbd5e1',
                            cursor: 'pointer',
                            display: 'flex', alignItems: 'center', gap: '0.4rem',
                            fontFamily: 'inherit', fontSize: '0.82rem', fontWeight: 500,
                            transition: 'all 0.2s',
                        }}
                    >
                        <CircleDot size={12} color={getLabelColor(label)} />
                        {label}
                        <span style={{ fontSize: '0.68rem', opacity: 0.7 }}>({count})</span>
                    </button>
                ))}
            </div>

            {selectedLabel && (
                <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    style={{
                        background: 'rgba(10,15,30,0.5)', borderRadius: '0.75rem',
                        padding: '1rem', maxHeight: 420, overflowY: 'auto',
                    }}
                >
                    {loading ? (
                        <div style={{ padding: '1rem', color: '#94a3b8', textAlign: 'center' }}>Loading...</div>
                    ) : (
                        <>
                            <div style={{ fontSize: '0.78rem', fontWeight: 600, color: getLabelColor(selectedLabel), marginBottom: '0.75rem' }}>
                                {selectedLabel} Nodes ({nodes.length})
                            </div>
                            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '0.5rem' }}>
                                {nodes.map((node) => {
                                    const nodeRels = relationships.filter((r) => r.source_id === node.id);
                                    return (
                                        <div key={node.id} style={{
                                            background: 'rgba(15,23,42,0.6)',
                                            border: `1px solid ${getLabelColor(selectedLabel)}25`,
                                            borderRadius: '0.5rem', padding: '0.75rem',
                                        }}>
                                            <div style={{ fontSize: '0.85rem', fontWeight: 600, color: '#f1f5f9', marginBottom: '0.35rem' }}>
                                                {String(node.properties.name || node.properties.id || node.id).slice(0, 60)}
                                            </div>
                                            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.2rem' }}>
                                                {Object.entries(node.properties)
                                                    .filter(([k]) => k !== 'name')
                                                    .slice(0, 6)
                                                    .map(([key, val]) => (
                                                        <div key={key} style={{ fontSize: '0.72rem', display: 'flex', gap: '0.4rem' }}>
                                                            <span style={{ color: '#64748b', minWidth: 80 }}>{key}:</span>
                                                            <span style={{ color: '#94a3b8' }}>
                                                                {Array.isArray(val) ? val.join(', ') : String(val).slice(0, 80)}
                                                            </span>
                                                        </div>
                                                    ))}
                                            </div>
                                            {nodeRels.length > 0 && (
                                                <div style={{ marginTop: '0.4rem', display: 'flex', gap: '0.3rem', flexWrap: 'wrap' }}>
                                                    {nodeRels.slice(0, 5).map((rel, i) => (
                                                        <Badge
                                                            key={i}
                                                            text={`${rel.rel_type} -> ${rel.target_name || rel.target_labels[0]}`}
                                                            color={relColors[rel.rel_type] || '#94a3b8'}
                                                        />
                                                    ))}
                                                </div>
                                            )}
                                        </div>
                                    );
                                })}
                            </div>
                        </>
                    )}
                </motion.div>
            )}
        </div>
    );
}

// ── Main Page ──

export default function DataExplorerPage() {
    const { user } = useAuth();
    const navigate = useNavigate();

    const [activeTab, setActiveTab] = useState<'overview' | 'qdrant' | 'neo4j' | 'graph'>('overview');
    const [isLoading, setIsLoading] = useState(true);
    const [isRefreshing, setIsRefreshing] = useState(false);
    const [isInitializing, setIsInitializing] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // Status
    const [engineStatus, setEngineStatus] = useState<DataExplorerStatus | null>(null);

    // Qdrant state
    const [qdrantCollections, setQdrantCollections] = useState<QdrantCollectionInfo[]>([]);

    // Neo4j state
    const [neo4jOverview, setNeo4jOverview] = useState<Neo4jOverview | null>(null);

    // Graph state
    const [graphNodes, setGraphNodes] = useState<Neo4jGraphNode[]>([]);
    const [graphEdges, setGraphEdges] = useState<Neo4jGraphEdge[]>([]);

    useEffect(() => {
        if (user && user.role !== 'admin') navigate('/');
    }, [navigate, user]);

    const loadData = useCallback(async (refresh = false) => {
        if (user?.role !== 'admin') return;
        refresh ? setIsRefreshing(true) : setIsLoading(true);
        setError(null);

        const results = await Promise.allSettled([
            dataExplorerApi.status(),
            dataExplorerApi.qdrantOverview(),
            dataExplorerApi.neo4jOverview(),
            dataExplorerApi.neo4jGraphSnapshot(150),
        ]);

        if (results[0].status === 'fulfilled') {
            setEngineStatus(results[0].value);
        }
        if (results[1].status === 'fulfilled') {
            setQdrantCollections(results[1].value.collections);
        }
        if (results[2].status === 'fulfilled') {
            setNeo4jOverview(results[2].value);
        }
        if (results[3].status === 'fulfilled') {
            setGraphNodes(results[3].value.nodes);
            setGraphEdges(results[3].value.edges);
        }

        const allFailed = results.slice(1).every((r) => r.status === 'rejected');
        if (allFailed) {
            setError('Unable to connect to Qdrant or Neo4j. Check that services are running.');
        }

        setIsLoading(false);
        setIsRefreshing(false);
    }, [user]);

    const handleInitialize = async () => {
        setIsInitializing(true);
        setError(null);
        try {
            await dataExplorerApi.initialize();
            await loadData(true);
        } catch (e: any) {
            setError(`Initialization failed: ${e.message || e}`);
        }
        setIsInitializing(false);
    };

    useEffect(() => {
        loadData();
    }, [loadData]);

    // Compute totals
    const totalVectors = qdrantCollections.reduce((sum, c) => sum + c.points_count, 0);
    const totalNodes = neo4jOverview?.total_nodes ?? 0;
    const totalRels = neo4jOverview?.total_relationships ?? 0;
    const totalLabels = neo4jOverview?.node_labels?.length ?? 0;

    const tabs = [
        { key: 'overview' as const, label: 'Overview', icon: Activity },
        { key: 'qdrant' as const, label: 'Qdrant Vectors', icon: Zap },
        { key: 'neo4j' as const, label: 'Neo4j Nodes', icon: Database },
        { key: 'graph' as const, label: 'Graph View', icon: Network },
    ];

    if (isLoading) {
        return (
            <div style={{ minHeight: '60vh', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#94a3b8' }}>
                Loading data explorer...
            </div>
        );
    }

    return (
        <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            style={{ padding: '0.5rem 0' }}
        >
            {/* Header */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.5rem', flexWrap: 'wrap', gap: '0.75rem' }}>
                <div>
                    <h1 style={{ margin: 0, fontSize: '1.5rem', fontWeight: 700, color: '#f1f5f9', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                        <Layers size={24} color={accentBlue} />
                        Data Explorer
                    </h1>
                    <p style={{ margin: '0.25rem 0 0', fontSize: '0.82rem', color: '#94a3b8' }}>
                        Introspect Qdrant vector store & Neo4j knowledge graph
                    </p>
                </div>
                <button
                    onClick={() => loadData(true)}
                    disabled={isRefreshing}
                    style={{
                        background: 'rgba(30,41,59,0.8)',
                        border: '1px solid rgba(148,163,184,0.2)',
                        borderRadius: '0.5rem',
                        padding: '0.5rem 1rem',
                        color: '#cbd5e1',
                        cursor: 'pointer',
                        display: 'flex', alignItems: 'center', gap: '0.4rem',
                        fontFamily: 'inherit', fontSize: '0.82rem',
                        transition: 'all 0.2s',
                    }}
                >
                    <RefreshCcw size={14} className={isRefreshing ? 'spin' : ''} />
                    {isRefreshing ? 'Refreshing...' : 'Refresh'}
                </button>
            </div>

            {error && (
                <div style={{
                    ...cardStyle, padding: '1rem', marginBottom: '1rem',
                    borderColor: 'rgba(239,68,68,0.3)', color: '#fca5a5', fontSize: '0.85rem',
                }}>
                    {error}
                </div>
            )}

            {/* Engine status banner */}
            {engineStatus && (
                <>
                    {/* Case 1: DB not reachable */}
                    {(!engineStatus.qdrant_connected || !engineStatus.neo4j_connected) && (
                        <motion.div
                            initial={{ opacity: 0, y: -8 }}
                            animate={{ opacity: 1, y: 0 }}
                            style={{
                                ...cardStyle, padding: '1.25rem', marginBottom: '1rem',
                                borderColor: 'rgba(239,68,68,0.3)',
                                display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap',
                            }}
                        >
                            <div style={{
                                width: 44, height: 44, borderRadius: '0.75rem',
                                display: 'flex', alignItems: 'center', justifyContent: 'center',
                                background: 'rgba(239,68,68,0.15)', border: '1px solid rgba(239,68,68,0.3)',
                                flexShrink: 0,
                            }}>
                                <Database size={22} color={accentRose} />
                            </div>
                            <div style={{ flex: 1 }}>
                                <div style={{ fontWeight: 600, color: accentRose, fontSize: '0.92rem' }}>
                                    Connessione ai database fallita
                                </div>
                                <div style={{ display: 'flex', gap: '0.75rem', marginTop: '0.5rem', fontSize: '0.78rem' }}>
                                    <span style={{ color: engineStatus.qdrant_connected ? accentGreen : accentRose }}>
                                        Qdrant: {engineStatus.qdrant_connected ? 'Connesso' : 'Non raggiungibile'}
                                    </span>
                                    <span style={{ color: engineStatus.neo4j_connected ? accentGreen : accentRose }}>
                                        Neo4j: {engineStatus.neo4j_connected ? 'Connesso' : 'Non raggiungibile'}
                                    </span>
                                </div>
                            </div>
                        </motion.div>
                    )}

                    {/* Case 2: DB reachable but no schema/collections yet */}
                    {engineStatus.qdrant_connected && engineStatus.neo4j_connected && !engineStatus.data_ready && (
                        <motion.div
                            initial={{ opacity: 0, y: -8 }}
                            animate={{ opacity: 1, y: 0 }}
                            style={{
                                ...cardStyle, padding: '1.25rem', marginBottom: '1rem',
                                borderColor: 'rgba(245,158,11,0.3)',
                                display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap',
                            }}
                        >
                            <div style={{
                                width: 44, height: 44, borderRadius: '0.75rem',
                                display: 'flex', alignItems: 'center', justifyContent: 'center',
                                background: 'rgba(245,158,11,0.15)', border: '1px solid rgba(245,158,11,0.3)',
                                flexShrink: 0,
                            }}>
                                <Zap size={22} color={accentAmber} />
                            </div>
                            <div style={{ flex: 1 }}>
                                <div style={{ fontWeight: 600, color: accentAmber, fontSize: '0.92rem' }}>
                                    Schema non presente
                                </div>
                                <div style={{ color: '#94a3b8', fontSize: '0.78rem', marginTop: 2 }}>
                                    Le collections Qdrant e lo schema Neo4j non sono ancora stati creati.
                                    Inizializza il RAG Engine oppure carica un documento per crearli automaticamente.
                                </div>
                            </div>
                            <button
                                onClick={handleInitialize}
                                disabled={isInitializing}
                                style={{
                                    background: `linear-gradient(135deg, ${accentAmber}20, ${accentAmber}35)`,
                                    border: `1px solid ${accentAmber}60`,
                                    borderRadius: '0.5rem',
                                    padding: '0.6rem 1.2rem',
                                    color: accentAmber,
                                    cursor: isInitializing ? 'wait' : 'pointer',
                                    fontFamily: 'inherit', fontSize: '0.82rem', fontWeight: 600,
                                    display: 'flex', alignItems: 'center', gap: '0.4rem',
                                    transition: 'all 0.2s',
                                    opacity: isInitializing ? 0.7 : 1,
                                    whiteSpace: 'nowrap',
                                }}
                            >
                                <Zap size={14} />
                                {isInitializing ? 'Inizializzazione...' : 'Inizializza Schema'}
                            </button>
                        </motion.div>
                    )}

                    {/* Case 3: Schema ready but no data ingested */}
                    {engineStatus.data_ready && totalVectors === 0 && totalNodes === 0 && (
                        <motion.div
                            initial={{ opacity: 0, y: -8 }}
                            animate={{ opacity: 1, y: 0 }}
                            style={{
                                ...cardStyle, padding: '1rem', marginBottom: '1rem',
                                borderColor: 'rgba(96,165,250,0.2)',
                                display: 'flex', alignItems: 'center', gap: '0.75rem',
                            }}
                        >
                            <Layers size={18} color={accentBlue} />
                            <div style={{ color: '#94a3b8', fontSize: '0.82rem' }}>
                                <span style={{ color: accentGreen, fontWeight: 600 }}>Schema pronto.</span>{' '}
                                I database sono vuoti. Carica un documento in un tender per popolare Qdrant e Neo4j con i dati.
                            </div>
                        </motion.div>
                    )}
                </>
            )}

            {/* Stat cards */}
            <div style={{ display: 'flex', gap: '0.75rem', marginBottom: '1.5rem', flexWrap: 'wrap' }}>
                <StatCard label="Vector Points" value={totalVectors.toLocaleString()} icon={Zap} color={accentBlue} />
                <StatCard label="Collections" value={qdrantCollections.length} icon={HardDrive} color={accentPurple} />
                <StatCard label="Graph Nodes" value={totalNodes.toLocaleString()} icon={Database} color={accentGreen} />
                <StatCard label="Relationships" value={totalRels.toLocaleString()} icon={GitFork} color={accentAmber} />
                <StatCard label="Node Labels" value={totalLabels} icon={Tag} color={accentRose} />
            </div>

            {/* Tabs */}
            <div style={{ display: 'flex', gap: '0.25rem', marginBottom: '1.25rem', borderBottom: '1px solid rgba(148,163,184,0.12)', paddingBottom: '0.5rem' }}>
                {tabs.map((tab) => (
                    <button
                        key={tab.key}
                        onClick={() => setActiveTab(tab.key)}
                        style={{
                            background: activeTab === tab.key ? 'rgba(96,165,250,0.15)' : 'transparent',
                            border: activeTab === tab.key ? '1px solid rgba(96,165,250,0.3)' : '1px solid transparent',
                            borderRadius: '0.5rem',
                            padding: '0.5rem 1rem',
                            color: activeTab === tab.key ? accentBlue : '#94a3b8',
                            cursor: 'pointer',
                            fontFamily: 'inherit', fontSize: '0.82rem', fontWeight: 500,
                            display: 'flex', alignItems: 'center', gap: '0.4rem',
                            transition: 'all 0.2s',
                        }}
                    >
                        <tab.icon size={15} />
                        {tab.label}
                    </button>
                ))}
            </div>

            {/* Tab content */}
            {activeTab === 'overview' && (
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                    {/* Qdrant overview */}
                    <div style={{ ...cardStyle, padding: '1.25rem' }}>
                        <SectionHeader title="Qdrant Vector Store" icon={Zap} color={accentBlue} badge="Dense Retrieval" />
                        {qdrantCollections.length === 0 ? (
                            <div style={{ color: '#64748b', fontSize: '0.82rem' }}>No collections found</div>
                        ) : (
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                                {qdrantCollections.map((col) => (
                                    <div key={col.name} style={{
                                        background: 'rgba(10,15,30,0.5)', borderRadius: '0.5rem', padding: '0.75rem',
                                        border: '1px solid rgba(148,163,184,0.08)',
                                    }}>
                                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.4rem' }}>
                                            <span style={{ fontWeight: 600, color: '#f1f5f9', fontSize: '0.85rem' }}>{col.name}</span>
                                            <Badge text={col.status} color={col.status === 'green' ? accentGreen : accentAmber} />
                                        </div>
                                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '0.3rem', fontSize: '0.72rem' }}>
                                            <div><span style={{ color: '#64748b' }}>Points:</span> <span style={{ color: '#cbd5e1' }}>{col.points_count.toLocaleString()}</span></div>
                                            <div><span style={{ color: '#64748b' }}>Dimension:</span> <span style={{ color: '#cbd5e1' }}>{col.dimension ?? 'N/A'}</span></div>
                                            <div><span style={{ color: '#64748b' }}>Distance:</span> <span style={{ color: '#cbd5e1' }}>{col.distance}</span></div>
                                            <div><span style={{ color: '#64748b' }}>Indexed:</span> <span style={{ color: '#cbd5e1' }}>{col.indexed_vectors_count.toLocaleString()}</span></div>
                                            <div><span style={{ color: '#64748b' }}>Segments:</span> <span style={{ color: '#cbd5e1' }}>{col.segments_count}</span></div>
                                            <div><span style={{ color: '#64748b' }}>On-disk:</span> <span style={{ color: '#cbd5e1' }}>{col.on_disk_payload ? 'Yes' : 'No'}</span></div>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>

                    {/* Neo4j overview */}
                    <div style={{ ...cardStyle, padding: '1.25rem' }}>
                        <SectionHeader title="Neo4j Knowledge Graph" icon={Database} color={accentGreen} badge="Graph Retrieval" />
                        {neo4jOverview ? (
                            <div>
                                <div style={{ marginBottom: '1rem' }}>
                                    <div style={{ fontSize: '0.78rem', fontWeight: 600, color: '#94a3b8', marginBottom: '0.5rem' }}>Node Labels</div>
                                    <BarChart
                                        items={neo4jOverview.node_labels.map((nl) => ({
                                            label: nl.label,
                                            value: nl.count,
                                            color: getLabelColor(nl.label),
                                        }))}
                                        maxValue={Math.max(...neo4jOverview.node_labels.map((n) => n.count), 1)}
                                    />
                                </div>
                                <div>
                                    <div style={{ fontSize: '0.78rem', fontWeight: 600, color: '#94a3b8', marginBottom: '0.5rem' }}>Relationship Types</div>
                                    <BarChart
                                        items={neo4jOverview.relationship_types.map((rt) => ({
                                            label: rt.type,
                                            value: rt.count,
                                            color: relColors[rt.type] || '#94a3b8',
                                        }))}
                                        maxValue={Math.max(...neo4jOverview.relationship_types.map((r) => r.count), 1)}
                                    />
                                </div>

                                {neo4jOverview.constraints.length > 0 && (
                                    <div style={{ marginTop: '1rem' }}>
                                        <div style={{ fontSize: '0.78rem', fontWeight: 600, color: '#94a3b8', marginBottom: '0.5rem' }}>Constraints</div>
                                        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.3rem' }}>
                                            {neo4jOverview.constraints.map((c, i) => (
                                                <div key={i} style={{ fontSize: '0.72rem', color: '#64748b', display: 'flex', gap: '0.4rem', alignItems: 'center' }}>
                                                    <Hash size={10} color={accentGreen} />
                                                    <span style={{ color: '#94a3b8' }}>{c.labels_or_types?.join(', ')}</span>
                                                    <span>.</span>
                                                    <span style={{ color: accentPurple }}>{c.properties?.join(', ')}</span>
                                                    <span style={{ color: '#475569' }}>({c.type})</span>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                )}
                            </div>
                        ) : (
                            <div style={{ color: '#64748b', fontSize: '0.82rem' }}>Unable to connect to Neo4j</div>
                        )}
                    </div>
                </div>
            )}

            {activeTab === 'qdrant' && (
                <div>
                    <SectionHeader title="Qdrant Collections" icon={Zap} color={accentBlue} badge={`${qdrantCollections.length} collections`} />
                    {qdrantCollections.length === 0 ? (
                        <div style={{ ...cardStyle, padding: '2rem', textAlign: 'center', color: '#94a3b8' }}>
                            No Qdrant collections found. Ingest documents to create collections.
                        </div>
                    ) : (
                        qdrantCollections.map((col) => (
                            <QdrantCollectionDetail key={col.name} collection={col} />
                        ))
                    )}
                </div>
            )}

            {activeTab === 'neo4j' && (
                <div>
                    <SectionHeader title="Neo4j Node Explorer" icon={Database} color={accentGreen} badge={`${totalNodes} nodes`} />
                    <div style={{ ...cardStyle, padding: '1.25rem' }}>
                        {neo4jOverview && neo4jOverview.node_labels.length > 0 ? (
                            <Neo4jNodeExplorer nodeLabels={neo4jOverview.node_labels} />
                        ) : (
                            <div style={{ color: '#94a3b8', textAlign: 'center', padding: '2rem' }}>
                                No nodes in Neo4j. Populate the knowledge graph by ingesting documents.
                            </div>
                        )}
                    </div>
                </div>
            )}

            {activeTab === 'graph' && (
                <div>
                    <SectionHeader
                        title="Knowledge Graph Visualization"
                        icon={Network}
                        color={accentPurple}
                        badge={`${graphNodes.length} nodes, ${graphEdges.length} edges`}
                    />
                    <div style={{ ...cardStyle, padding: '0.75rem' }}>
                        <GraphCanvas nodes={graphNodes} edges={graphEdges} />
                    </div>

                    {/* Relationship legend */}
                    {graphEdges.length > 0 && (
                        <div style={{ ...cardStyle, padding: '1rem', marginTop: '0.75rem' }}>
                            <div style={{ fontSize: '0.78rem', fontWeight: 600, color: '#94a3b8', marginBottom: '0.5rem' }}>
                                Relationship Types in View
                            </div>
                            <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
                                {[...new Set(graphEdges.map((e) => e.type))].map((type) => (
                                    <div key={type} style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                                        <div style={{ width: 20, height: 3, borderRadius: 2, background: relColors[type] || '#94a3b8' }} />
                                        <span style={{ fontSize: '0.72rem', color: '#cbd5e1' }}>{type}</span>
                                        <span style={{ fontSize: '0.65rem', color: '#64748b' }}>
                                            ({graphEdges.filter((e) => e.type === type).length})
                                        </span>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            )}
        </motion.div>
    );
}
