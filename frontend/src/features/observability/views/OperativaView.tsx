import { lazy, Suspense, useState } from 'react';
import { motion } from 'framer-motion';
import { Activity, AlertTriangle, FileSearch, RefreshCcw } from 'lucide-react';
import type {
    KpiAnalysisJob,
    KpiTransitions,
    KpiTenderSnapshot,
    Tender,
    TenderDetail,
} from '../../../api/client';
import { analysisJobColors, formatGeneratedAt } from '../shared';

const LifecycleControlPanel = lazy(() => import('../../../components/observability/LifecycleControlPanel'));
const TransitionTimelinePanel = lazy(() => import('../../../components/observability/TransitionTimelinePanel'));

interface OperativaViewProps {
    analysisJob: KpiAnalysisJob | null;
    transitions: KpiTransitions | null;
    snapshot: KpiTenderSnapshot | null;
    tender: Tender | null;
    tenderDetail: TenderDetail | null;
    onRefresh: () => void;
    onRecompute: () => void;
    onHistoryBackfill: () => void;
    isRecomputing: boolean;
    isBackfilling: boolean;
}

type TabId = 'workspace' | 'transitions' | 'lifecycle' | 'diagnostics';

const TABS: { id: TabId; label: string }[] = [
    { id: 'workspace', label: 'Workspace' },
    { id: 'transitions', label: 'Transitions' },
    { id: 'lifecycle', label: 'Lifecycle' },
    { id: 'diagnostics', label: 'Diagnostics' },
];

function jobStatusLabel(jobStatus: string | null | undefined): string {
    switch (jobStatus) {
        case 'queued':
            return 'In coda';
        case 'running':
            return 'In esecuzione';
        case 'succeeded':
            return 'Completato';
        case 'failed':
            return 'Fallito';
        case 'degraded':
            return 'Degradato';
        default:
            return 'Inattivo';
    }
}

export default function OperativaView({
    analysisJob,
    transitions,
    snapshot,
    tender,
    tenderDetail,
    onRefresh,
    onRecompute,
    onHistoryBackfill,
    isRecomputing,
    isBackfilling,
}: OperativaViewProps) {
    const [activeTab, setActiveTab] = useState<TabId>('workspace');
    const jobPalette = analysisJobColors(analysisJob?.job_status);
    const jobLabel = jobStatusLabel(analysisJob?.job_status);

    return (
        <div>
            <nav
                style={{
                    display: 'flex',
                    gap: '0.25rem',
                    padding: '0 1.5rem',
                    background: 'var(--bg-card)',
                    borderBottom: '1px solid var(--border-default)',
                    marginBottom: '1.5rem',
                }}
            >
                {TABS.map((tab) => (
                    <button
                        key={tab.id}
                        onClick={() => setActiveTab(tab.id)}
                        style={{
                            padding: '0.75rem 1.125rem',
                            background: 'none',
                            border: 'none',
                            borderBottom: `2px solid ${activeTab === tab.id ? 'var(--color-primary)' : 'transparent'}`,
                            color: activeTab === tab.id ? 'var(--color-primary)' : 'var(--text-muted)',
                            fontSize: '0.875rem',
                            fontWeight: 500,
                            cursor: 'pointer',
                            transition: 'all 0.2s',
                        }}
                    >
                        {tab.label}
                    </button>
                ))}
            </nav>

            <motion.div
                key={activeTab}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.2 }}
            >
                {activeTab === 'workspace' && (
                    <div>
                        <div className="card">
                            <h3 style={{ margin: '0 0 1rem 0', fontSize: '0.95rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                <Activity size={16} color="#38bdf8" /> Job Queue
                            </h3>

                            <div
                                style={{
                                    padding: '1rem',
                                    borderRadius: '12px',
                                    background: jobPalette.soft,
                                    border: `1px solid ${jobPalette.accent}33`,
                                    marginBottom: '1rem',
                                }}
                            >
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                                    <div>
                                        <div style={{ fontWeight: 600, color: jobPalette.accent, marginBottom: '0.25rem' }}>
                                            {analysisJob?.job_type === 'history_backfill' ? 'History Backfill' : 'KPI Recompute'}
                                        </div>
                                        <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                                            Status: <span style={{ color: jobPalette.accent }}>{jobLabel}</span>
                                        </div>
                                        {analysisJob?.updated_at && (
                                            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
                                                Ultimo aggiornamento: {formatGeneratedAt(analysisJob.updated_at)}
                                            </div>
                                        )}
                                    </div>
                                    <span
                                        style={{
                                            padding: '0.25rem 0.6rem',
                                            borderRadius: '999px',
                                            background: jobPalette.soft,
                                            color: jobPalette.accent,
                                            border: `1px solid ${jobPalette.accent}33`,
                                            fontSize: '0.75rem',
                                        }}
                                    >
                                        {jobLabel}
                                    </span>
                                </div>
                                {analysisJob?.error_message && (
                                    <div
                                        style={{
                                            marginTop: '0.75rem',
                                            padding: '0.75rem',
                                            background: 'rgba(239, 68, 68, 0.1)',
                                            borderRadius: '8px',
                                            fontSize: '0.85rem',
                                            color: '#fecaca',
                                        }}
                                    >
                                        <AlertTriangle size={14} style={{ marginRight: '0.5rem', verticalAlign: 'middle' }} />
                                        {analysisJob.error_message}
                                    </div>
                                )}
                            </div>

                            <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
                                <button
                                    className={`btn btn-secondary btn-sm ${isRecomputing && analysisJob?.job_type !== 'history_backfill' ? 'animate-pulse' : ''}`}
                                    onClick={onRecompute}
                                    disabled={isRecomputing}
                                >
                                    <RefreshCcw size={14} />
                                    {isRecomputing && analysisJob?.job_type !== 'history_backfill' ? 'Recomputing...' : 'Recompute KPI'}
                                </button>
                                <button
                                    className={`btn btn-secondary btn-sm ${isBackfilling ? 'animate-pulse' : ''}`}
                                    onClick={onHistoryBackfill}
                                    disabled={isBackfilling}
                                >
                                    <FileSearch size={14} />
                                    {isBackfilling ? 'Replaying history...' : 'Replay History'}
                                </button>
                                <button className="btn btn-secondary btn-sm" onClick={onRefresh}>
                                    <RefreshCcw size={14} /> Refresh
                                </button>
                            </div>
                        </div>

                        {analysisJob && (
                            <div className="card">
                                <h3 style={{ margin: '0 0 1rem 0', fontSize: '0.95rem' }}>Job Details</h3>
                                <div style={{ display: 'grid', gap: '0.5rem', fontSize: '0.85rem' }}>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.5rem 0', borderBottom: '1px solid var(--border-default)' }}>
                                        <span style={{ color: 'var(--text-muted)' }}>Job ID</span>
                                        <span style={{ fontWeight: 500 }}>{analysisJob.job_id ?? 'N/A'}</span>
                                    </div>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.5rem 0', borderBottom: '1px solid var(--border-default)' }}>
                                        <span style={{ color: 'var(--text-muted)' }}>Job Type</span>
                                        <span style={{ fontWeight: 500, textTransform: 'capitalize' }}>{analysisJob.job_type?.replace('_', ' ')}</span>
                                    </div>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.5rem 0', borderBottom: '1px solid var(--border-default)' }}>
                                        <span style={{ color: 'var(--text-muted)' }}>Status</span>
                                        <span style={{ fontWeight: 500, color: jobPalette.accent }}>{jobLabel}</span>
                                    </div>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.5rem 0', borderBottom: '1px solid var(--border-default)' }}>
                                        <span style={{ color: 'var(--text-muted)' }}>Created</span>
                                        <span style={{ fontWeight: 500 }}>{formatGeneratedAt(analysisJob.created_at)}</span>
                                    </div>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.5rem 0' }}>
                                        <span style={{ color: 'var(--text-muted)' }}>Updated</span>
                                        <span style={{ fontWeight: 500 }}>{formatGeneratedAt(analysisJob.updated_at)}</span>
                                    </div>
                                </div>
                            </div>
                        )}
                    </div>
                )}

                {activeTab === 'transitions' && (
                    <Suspense fallback={<div className="card"><p style={{ margin: 0, color: 'var(--text-muted)' }}>Loading transitions...</p></div>}>
                        <TransitionTimelinePanel transitions={transitions} />
                    </Suspense>
                )}

                {activeTab === 'lifecycle' && (
                    <Suspense fallback={<div className="card"><p style={{ margin: 0, color: 'var(--text-muted)' }}>Loading lifecycle panel...</p></div>}>
                        <LifecycleControlPanel
                            tender={tender}
                            tenderDetail={tenderDetail}
                            analyticalPhase={snapshot?.analytical_phase || null}
                            onDataChanged={onRefresh}
                        />
                    </Suspense>
                )}

                {activeTab === 'diagnostics' && (
                    <div className="card">
                        <h3 style={{ margin: '0 0 1rem 0', fontSize: '0.95rem' }}>System Diagnostics</h3>
                        <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                            Detailed system diagnostics and engine status information.
                        </p>
                        <div style={{ marginTop: '1rem', padding: '1rem', background: 'rgba(15, 23, 42, 0.5)', borderRadius: '8px' }}>
                            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '0.5rem' }}>
                                Engine Status
                            </div>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                <span
                                    style={{
                                        width: '8px',
                                        height: '8px',
                                        borderRadius: '50%',
                                        background: analysisJob?.job_status === 'running' ? '#f59e0b' : '#10b981',
                                    }}
                                />
                                <span style={{ fontWeight: 500 }}>
                                    {analysisJob?.job_status === 'running' ? 'Processing' : 'Idle'}
                                </span>
                            </div>
                        </div>
                    </div>
                )}
            </motion.div>
        </div>
    );
}
