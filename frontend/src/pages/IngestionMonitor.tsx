import React, { useState, useEffect } from 'react';
import {
    Activity,
    FileText,
    CheckCircle,
    AlertCircle,
    Search,
    Loader2,
    RefreshCw,
    ChevronDown,
    ChevronUp
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { ingestionApi, IngestionMonitorRecord, IngestionStats } from '../api/client';

type IngestionStageSnapshot = {
    label?: string;
    status?: string;
    detail?: string;
    stats?: Record<string, unknown>;
};

type IngestionObservability = {
    current_stage?: string | null;
    current_stage_label?: string | null;
    current_stage_status?: string | null;
    current_stage_detail?: string | null;
    stages?: Record<string, IngestionStageSnapshot>;
};

const INGESTION_STAGE_ORDER = [
    'download',
    'parse',
    'requirement_extraction',
    'chunking',
    'index_qdrant',
    'sync_neo4j',
    'compliance',
    'completed',
] as const;

const STAGE_LABELS: Record<string, string> = {
    download: 'Download file',
    parse: 'Parse document',
    requirement_extraction: 'Requirement extraction',
    chunking: 'Chunking',
    index_qdrant: 'Index Qdrant',
    sync_neo4j: 'Sync Neo4j',
    compliance: 'Compliance sync',
    completed: 'Completed',
};

const humanizeToken = (value: string) =>
    value
        .replace(/_/g, ' ')
        .replace(/\b\w/g, (match) => match.toUpperCase());

const getObservability = (ingestion: IngestionMonitorRecord): IngestionObservability | null => {
    const raw = ingestion.metadata_json?.ingestion_observability;
    if (!raw || typeof raw !== 'object') {
        return null;
    }
    return raw as IngestionObservability;
};

const formatStageStats = (stats?: Record<string, unknown>) => {
    if (!stats || typeof stats !== 'object') {
        return null;
    }

    const entries = Object.entries(stats).filter(([, value]) =>
        ['string', 'number', 'boolean'].includes(typeof value)
    );
    if (entries.length === 0) {
        return null;
    }

    return entries
        .slice(0, 3)
        .map(([key, value]) => `${humanizeToken(key)}: ${String(value)}`)
        .join(' · ');
};

const getStageAccent = (status?: string, isCurrent = false) => {
    if (status === 'failed') return '#ef4444';
    if (status === 'completed' || status === 'skipped') return '#10b981';
    if (status === 'started' || isCurrent) return '#3b82f6';
    return '#64748b';
};

export default function IngestionMonitor() {
    const [ingestions, setIngestions] = useState<IngestionMonitorRecord[]>([]);
    const [stats, setStats] = useState<IngestionStats | null>(null);
    const [loading, setLoading] = useState(true);
    const [refreshing, setRefreshing] = useState(false);
    const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined);
    const [searchQuery, setSearchQuery] = useState('');
    const [selectedIngestion, setSelectedIngestion] = useState<IngestionMonitorRecord | null>(null);

    const loadData = async (isRefresh = false) => {
        try {
            if (isRefresh) setRefreshing(true);
            else setLoading(true);

            const [records, statistics] = await Promise.all([
                ingestionApi.list(statusFilter),
                ingestionApi.getStats()
            ]);

            setIngestions(records);
            setStats(statistics);
        } catch (err) {
            console.error('Failed to load ingestion data', err);
        } finally {
            setLoading(false);
            setRefreshing(false);
        }
    };

    useEffect(() => {
        loadData();
        const interval = setInterval(() => loadData(true), 10000); // Auto refresh every 10s
        return () => clearInterval(interval);
    }, [statusFilter]);

    const filteredIngestions = ingestions.filter(ing => 
        ing.filename.toLowerCase().includes(searchQuery.toLowerCase()) ||
        ing.tender_title?.toLowerCase().includes(searchQuery.toLowerCase())
    );

    const getStatusColor = (status: string) => {
        switch (status) {
            case 'completed': return '#10b981';
            case 'failed': return '#ef4444';
            case 'processing': return '#3b82f6';
            case 'pending': return '#64748b';
            default: return '#64748b';
        }
    };

    return (
        <div className="animate-in" style={{ paddingBottom: '2rem' }}>
            <div className="page-header">
                <div>
                    <h1 className="page-title">Ingestion Monitor</h1>
                    <p className="page-subtitle">Track and manage document processing lifecycle across the system</p>
                </div>
                <button 
                    className="btn btn-secondary" 
                    onClick={() => loadData(true)}
                    disabled={refreshing}
                >
                    <RefreshCw size={18} className={refreshing ? 'spin' : ''} />
                    Refresh
                </button>
            </div>

            {/* Stats Cards */}
            {stats && (
                <div className="stats-grid" style={{ marginBottom: '2rem' }}>
                    <div className="stat-card">
                        <div className="stat-label">Total Ingestions</div>
                        <div className="stat-value">{stats.total}</div>
                        <FileText size={20} className="stat-icon" style={{ opacity: 0.5 }} />
                    </div>
                    <div className="stat-card">
                        <div className="stat-label">Currently Processing</div>
                        <div className="stat-value" style={{ color: 'var(--accent-blue)' }}>{stats.processing}</div>
                        <Activity size={20} className="stat-icon" style={{ color: 'var(--accent-blue)' }} />
                    </div>
                    <div className="stat-card">
                        <div className="stat-label">Failed</div>
                        <div className="stat-value" style={{ color: '#ef4444' }}>{stats.failed}</div>
                        <AlertCircle size={20} className="stat-icon" style={{ color: '#ef4444' }} />
                    </div>
                    <div className="stat-card">
                        <div className="stat-label">Success Rate</div>
                        <div className="stat-value" style={{ color: '#10b981' }}>{stats.success_rate}%</div>
                        <CheckCircle size={20} className="stat-icon" style={{ color: '#10b981' }} />
                    </div>
                </div>
            )}

            {/* Filters */}
            <div className="card" style={{ marginBottom: '1.5rem', display: 'flex', gap: '1rem', alignItems: 'center', flexWrap: 'wrap' }}>
                <div style={{ position: 'relative', flex: 1, minWidth: '200px' }}>
                    <Search size={18} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
                    <input 
                        type="text" 
                        placeholder="Search by filename or tender..." 
                        className="input"
                        style={{ paddingLeft: '2.5rem', width: '100%' }}
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                    />
                </div>
                <div style={{ display: 'flex', gap: '0.5rem' }}>
                    {['all', 'processing', 'completed', 'failed'].map(s => (
                        <button
                            key={s}
                            className={`btn btn-sm ${statusFilter === (s === 'all' ? undefined : s) ? 'btn-primary' : 'btn-ghost'}`}
                            onClick={() => setStatusFilter(s === 'all' ? undefined : s)}
                        >
                            {s.charAt(0).toUpperCase() + s.slice(1)}
                        </button>
                    ))}
                </div>
            </div>

            {/* List */}
            <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                <table className="table" style={{ width: '100%' }}>
                    <thead>
                        <tr>
                            <th style={{ padding: '1rem' }}>Document</th>
                            <th>Tender</th>
                            <th>Status / Progress</th>
                            <th>Created At</th>
                            <th style={{ textAlign: 'right', paddingRight: '1rem' }}>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        {loading && ingestions.length === 0 ? (
                            <tr>
                                <td colSpan={5} style={{ padding: '4rem', textAlign: 'center' }}>
                                    <Loader2 className="spin" size={32} style={{ margin: '0 auto', opacity: 0.5 }} />
                                    <p style={{ marginTop: '1rem', color: 'var(--text-muted)' }}>Loading records...</p>
                                </td>
                            </tr>
                        ) : filteredIngestions.length === 0 ? (
                            <tr>
                                <td colSpan={5} style={{ padding: '4rem', textAlign: 'center', color: 'var(--text-muted)' }}>
                                    No records found matching filters.
                                </td>
                            </tr>
                        ) : (
                            filteredIngestions.map(ing => {
                                const observability = getObservability(ing);
                                const currentStage = ing.current_stage || observability?.current_stage || null;
                                const currentStageLabel = ing.current_stage_label || observability?.current_stage_label || null;
                                const currentStageDetail = ing.current_stage_detail || observability?.current_stage_detail || null;

                                return (
                                <React.Fragment key={ing.id}>
                                    <tr 
                                        style={{ 
                                            cursor: 'pointer', 
                                            background: selectedIngestion?.id === ing.id ? 'rgba(255,255,255,0.05)' : 'transparent' 
                                        }}
                                        onClick={() => setSelectedIngestion(selectedIngestion?.id === ing.id ? null : ing)}
                                    >
                                        <td style={{ padding: '1rem' }}>
                                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                                                <FileText size={18} color="var(--accent-blue)" />
                                                <div style={{ fontWeight: 500 }}>{ing.filename}</div>
                                            </div>
                                        </td>
                                        <td>
                                            <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                                                {ing.tender_title || 'No tender association'}
                                            </div>
                                        </td>
                                        <td>
                                            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', width: '150px' }}>
                                                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem' }}>
                                                    <span style={{ color: getStatusColor(ing.status), fontWeight: 600 }}>
                                                        {ing.status.toUpperCase()}
                                                    </span>
                                                    <span>{Math.round(ing.progress)}%</span>
                                                </div>
                                                <div style={{ width: '100%', height: '6px', background: 'rgba(255,255,255,0.05)', borderRadius: '3px', overflow: 'hidden' }}>
                                                    <div 
                                                        style={{ 
                                                            width: `${ing.progress}%`, 
                                                            height: '100%', 
                                                            background: getStatusColor(ing.status),
                                                            transition: 'width 0.4s ease'
                                                        }} 
                                                    />
                                                </div>
                                                {currentStageLabel && (
                                                    <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', lineHeight: 1.35 }}>
                                                        {currentStageLabel}
                                                    </div>
                                                )}
                                            </div>
                                        </td>
                                        <td style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                                            {new Date(ing.created_at).toLocaleString('it-IT', { 
                                                day: '2-digit', 
                                                month: 'short', 
                                                year: 'numeric', 
                                                hour: '2-digit', 
                                                minute: '2-digit' 
                                            })}
                                        </td>
                                        <td style={{ textAlign: 'right', paddingRight: '1rem' }}>
                                            <button className="btn btn-ghost btn-sm">
                                                {selectedIngestion?.id === ing.id ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                                            </button>
                                        </td>
                                    </tr>
                                    <AnimatePresence>
                                        {selectedIngestion?.id === ing.id && (
                                            <motion.tr
                                                initial={{ opacity: 0, height: 0 }}
                                                animate={{ opacity: 1, height: 'auto' }}
                                                exit={{ opacity: 0, height: 0 }}
                                            >
                                                <td colSpan={5} style={{ padding: '1.5rem', background: 'rgba(0,0,0,0.2)', borderLeft: `4px solid ${getStatusColor(ing.status)}` }}>
                                                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: '2rem' }}>
                                                        <div>
                                                            <h4 style={{ marginBottom: '1rem', fontSize: '0.9rem', color: 'var(--text-muted)' }}>Ingestion Details</h4>
                                                            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                                                                <div>
                                                                    <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Document ID</div>
                                                                    <div>#{ing.id}</div>
                                                                </div>
                                                                <div>
                                                                    <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Tender ID</div>
                                                                    <div>{ing.tender_id ? `#${ing.tender_id}` : 'N/A'}</div>
                                                                </div>
                                                                <div>
                                                                    <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Uploader ID</div>
                                                                    <div>{ing.uploaded_by || 'Unknown'}</div>
                                                                </div>
                                                                <div>
                                                                    <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Current Stage</div>
                                                                    <div>{currentStageLabel || 'N/A'}</div>
                                                                </div>
                                                            </div>
                                                        </div>
                                                        <div>
                                                            <h4 style={{ marginBottom: '1rem', fontSize: '0.9rem', color: 'var(--text-muted)' }}>Status & Logs</h4>
                                                            {ing.status === 'failed' ? (
                                                                <div style={{ background: 'rgba(239, 68, 68, 0.1)', padding: '1rem', borderRadius: '8px', border: '1px solid rgba(239, 68, 68, 0.2)', color: '#ef4444', fontSize: '0.85rem' }}>
                                                                    {currentStageLabel && (
                                                                        <div style={{ marginBottom: '0.75rem' }}>
                                                                            <strong>Failed Stage:</strong> {currentStageLabel}
                                                                        </div>
                                                                    )}
                                                                    <strong>Error Message:</strong>
                                                                    <pre style={{ marginTop: '0.5rem', whiteSpace: 'pre-wrap', fontSize: '0.8rem', opacity: 0.9 }}>
                                                                        {ing.error_message || 'No detailed error message provided by the worker.'}
                                                                    </pre>
                                                                </div>
                                                            ) : observability?.stages ? (
                                                                <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                                                                    {currentStageDetail && (
                                                                        <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                                                                            {currentStageDetail}
                                                                        </div>
                                                                    )}
                                                                    {INGESTION_STAGE_ORDER.map((stageKey) => {
                                                                        const stage = observability.stages?.[stageKey];
                                                                        const isCurrent = currentStage === stageKey;
                                                                        const stageLabel = stage?.label || STAGE_LABELS[stageKey] || humanizeToken(stageKey);
                                                                        const stageCaption =
                                                                            stage?.detail ||
                                                                            formatStageStats(stage?.stats) ||
                                                                            (stage?.status ? humanizeToken(stage.status) : 'Waiting');
                                                                        return (
                                                                            <div key={stageKey} style={{ display: 'flex', alignItems: 'flex-start', gap: '0.75rem' }}>
                                                                                <div
                                                                                    style={{
                                                                                        width: '10px',
                                                                                        height: '10px',
                                                                                        borderRadius: '999px',
                                                                                        marginTop: '0.35rem',
                                                                                        flexShrink: 0,
                                                                                        background: getStageAccent(stage?.status, isCurrent),
                                                                                    }}
                                                                                />
                                                                                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.2rem' }}>
                                                                                    <div style={{ fontWeight: isCurrent ? 600 : 500 }}>
                                                                                        {stageLabel}{isCurrent ? ' (current)' : ''}
                                                                                    </div>
                                                                                    <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                                                                                        {stageCaption}
                                                                                    </div>
                                                                                </div>
                                                                            </div>
                                                                        );
                                                                    })}
                                                                </div>
                                                            ) : (
                                                                <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                                                                    <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                                                                        <CheckCircle size={20} color={ing.progress >= 15 ? "#10b981" : "#64748b"} />
                                                                        <span>File Download & Validation</span>
                                                                    </div>
                                                                    <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                                                                        <CheckCircle size={20} color={ing.progress >= 40 ? "#10b981" : "#64748b"} />
                                                                        <span>Document Parsing & Text Extraction</span>
                                                                    </div>
                                                                    <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                                                                        <CheckCircle size={20} color={ing.progress >= 60 ? "#10b981" : "#64748b"} />
                                                                        <span>Requirement Extraction & Candidate Staging</span>
                                                                    </div>
                                                                    <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                                                                        <CheckCircle size={20} color={ing.progress >= 85 ? "#10b981" : "#64748b"} />
                                                                        <span>Graph Indexing & Compliance Calculation</span>
                                                                    </div>
                                                                </div>
                                                            )}
                                                        </div>
                                                    </div>
                                                </td>
                                            </motion.tr>
                                        )}
                                    </AnimatePresence>
                                </React.Fragment>
                            )})
                        )}
                    </tbody>
                </table>
            </div>
        </div>
    );
}
