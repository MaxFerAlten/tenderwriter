import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import {
    Activity,
    AlertTriangle,
    FileSearch,
    Gauge,
    RefreshCcw,
    ShieldAlert,
    Sparkles,
    TrendingUp,
} from 'lucide-react';
import {
    kpiAdminApi,
    observabilityApi,
    tenderApi,
    type KpiAnalysisJob,
    type KpiBottleneckItem,
    type KpiDiagnostics,
    type KpiForecast,
    type KpiPortfolioOverview,
    type KpiScore,
    type KpiTenderSnapshot,
    type KpiTransitions,
    type OperationalWorkspace,
    type Tender,
    type TenderDetail,
} from '../api/client';
import ComplianceDrilldownPanel from '../components/observability/ComplianceDrilldownPanel';
import OperationalWorkspacePanel from '../components/observability/OperationalWorkspacePanel';
import TransitionTimelinePanel from '../components/observability/TransitionTimelinePanel';

function healthColors(health: string): { accent: string; soft: string; text: string } {
    switch (health) {
        case 'green':
            return { accent: '#10b981', soft: 'rgba(16, 185, 129, 0.12)', text: '#d1fae5' };
        case 'amber':
            return { accent: '#f59e0b', soft: 'rgba(245, 158, 11, 0.14)', text: '#fef3c7' };
        case 'red':
            return { accent: '#ef4444', soft: 'rgba(239, 68, 68, 0.14)', text: '#fee2e2' };
        default:
            return { accent: '#64748b', soft: 'rgba(100, 116, 139, 0.14)', text: '#e2e8f0' };
    }
}

function phaseLabel(phase: string | null): string {
    const labels: Record<string, string> = {
        S0: 'Intake Opportunity',
        S1: 'Go / No-Go',
        S2: 'Bid Planning',
        S3: 'Request Contributions',
        S4: 'Coordination & Collection',
        S5: 'Quality / Technical Review',
        S6: 'Rework / Clarifications',
        S7: 'Integrated Draft',
        S8: 'Compliance Gate',
        S9: 'Submission',
        S10: 'Post-Submission Clarifications',
        S11: 'Win',
        S12: 'Loss',
        S13: 'Excluded / Withdrawn / No-Bid',
    };

    if (!phase) return 'Phase unavailable';
    return labels[phase] || phase;
}

function formatScoreValue(score: KpiScore): string {
    if (score.value === null || score.value === undefined) {
        return '--';
    }
    return `${score.value.toFixed(1)}`;
}

function formatGeneratedAt(value: string | null): string {
    if (!value) return 'Not generated yet';
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return value;
    return parsed.toLocaleString('it-IT');
}

function riskCount(items: KpiBottleneckItem[], health: string): number {
    return items.filter((item) => item.health === health).length;
}

function isAnalysisJobActive(job: KpiAnalysisJob | null): boolean {
    return job?.job_status === 'queued' || job?.job_status === 'running';
}

function analysisJobLabel(jobStatus: string | null | undefined): string {
    switch (jobStatus) {
        case 'queued':
            return 'Queued';
        case 'running':
            return 'Running';
        case 'succeeded':
            return 'Completed';
        case 'failed':
            return 'Failed';
        case 'degraded':
            return 'Service degraded';
        default:
            return 'Idle';
    }
}

function analysisJobColors(jobStatus: string | null | undefined): { accent: string; soft: string } {
    switch (jobStatus) {
        case 'queued':
            return { accent: '#38bdf8', soft: 'rgba(56, 189, 248, 0.14)' };
        case 'running':
            return { accent: '#f59e0b', soft: 'rgba(245, 158, 11, 0.14)' };
        case 'succeeded':
            return { accent: '#10b981', soft: 'rgba(16, 185, 129, 0.14)' };
        case 'failed':
        case 'degraded':
            return { accent: '#ef4444', soft: 'rgba(239, 68, 68, 0.14)' };
        default:
            return { accent: '#64748b', soft: 'rgba(100, 116, 139, 0.14)' };
    }
}

export default function ObservabilityKPI() {
    const [overview, setOverview] = useState<KpiPortfolioOverview | null>(null);
    const [bottlenecks, setBottlenecks] = useState<KpiBottleneckItem[]>([]);
    const [tenders, setTenders] = useState<Tender[]>([]);
    const [selectedTenderId, setSelectedTenderId] = useState<number | null>(null);
    const [tenderDetail, setTenderDetail] = useState<TenderDetail | null>(null);
    const [workspace, setWorkspace] = useState<OperationalWorkspace | null>(null);
    const [snapshot, setSnapshot] = useState<KpiTenderSnapshot | null>(null);
    const [diagnostics, setDiagnostics] = useState<KpiDiagnostics | null>(null);
    const [transitions, setTransitions] = useState<KpiTransitions | null>(null);
    const [forecast, setForecast] = useState<KpiForecast | null>(null);
    const [analysisJob, setAnalysisJob] = useState<KpiAnalysisJob | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [isRefreshing, setIsRefreshing] = useState(false);
    const [isDetailLoading, setIsDetailLoading] = useState(false);
    const [isRecomputing, setIsRecomputing] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const loadTenderDetail = async (tenderId: number) => {
        setIsDetailLoading(true);
        try {
            const [snapshotResponse, diagnosticsResponse, transitionsResponse, forecastResponse, tenderResponse, workspaceResponse, analysisJobResponse] = await Promise.all([
                kpiAdminApi.getTenderSnapshot(tenderId),
                kpiAdminApi.getTenderDiagnostics(tenderId),
                kpiAdminApi.getTenderTransitions(tenderId),
                kpiAdminApi.getTenderForecast(tenderId),
                tenderApi.get(tenderId),
                observabilityApi.getWorkspace(tenderId),
                kpiAdminApi.getLatestAnalysisJob(tenderId),
            ]);
            setSnapshot(snapshotResponse);
            setDiagnostics(diagnosticsResponse);
            setTransitions(transitionsResponse);
            setForecast(forecastResponse);
            setTenderDetail(tenderResponse);
            setWorkspace(workspaceResponse);
            setAnalysisJob(analysisJobResponse);
            setIsRecomputing(isAnalysisJobActive(analysisJobResponse));
        } catch (detailError) {
            setError(detailError instanceof Error ? detailError.message : 'Failed to load KPI tender detail.');
        } finally {
            setIsDetailLoading(false);
        }
    };

    const loadPortfolio = async (refresh = false) => {
        if (refresh) {
            setIsRefreshing(true);
        } else {
            setIsLoading(true);
        }
        setError(null);

        try {
            const [overviewResponse, bottlenecksResponse, tendersResponse] = await Promise.all([
                kpiAdminApi.getPortfolioOverview(),
                kpiAdminApi.getPortfolioBottlenecks(),
                tenderApi.list({ limit: '100' }),
            ]);
            setOverview(overviewResponse);
            setBottlenecks(bottlenecksResponse.items);
            setTenders(tendersResponse.items);

            if (tendersResponse.items.length > 0 && selectedTenderId === null) {
                const bottleneckTenderId = bottlenecksResponse.items[0]?.external_tender_id;
                const preferred = bottleneckTenderId ? Number.parseInt(bottleneckTenderId, 10) : tendersResponse.items[0].id;
                setSelectedTenderId(Number.isNaN(preferred) ? tendersResponse.items[0].id : preferred);
            } else if (refresh && selectedTenderId !== null && tendersResponse.items.some((item) => item.id === selectedTenderId)) {
                await loadTenderDetail(selectedTenderId);
            }
        } catch (loadError) {
            setError(loadError instanceof Error ? loadError.message : 'Failed to load KPI observability.');
        } finally {
            setIsLoading(false);
            setIsRefreshing(false);
        }
    };

    useEffect(() => {
        void loadPortfolio();
    }, []);

    useEffect(() => {
        if (selectedTenderId === null) {
            return;
        }

        void loadTenderDetail(selectedTenderId);
    }, [selectedTenderId]);

    useEffect(() => {
        if (selectedTenderId === null || !isAnalysisJobActive(analysisJob)) {
            return;
        }

        let cancelled = false;
        const intervalId = window.setInterval(() => {
            void (async () => {
                try {
                    const latestJob = await kpiAdminApi.getLatestAnalysisJob(selectedTenderId);
                    if (cancelled) {
                        return;
                    }
                    setAnalysisJob(latestJob);
                    if (!isAnalysisJobActive(latestJob)) {
                        setIsRecomputing(false);
                        window.clearInterval(intervalId);
                        if (latestJob.job_status === 'succeeded') {
                            await loadPortfolio(true);
                        } else if (latestJob.error_message) {
                            setError(latestJob.error_message);
                        }
                    }
                } catch (jobError) {
                    if (!cancelled) {
                        setIsRecomputing(false);
                        setError(jobError instanceof Error ? jobError.message : 'Failed to refresh KPI recompute status.');
                        window.clearInterval(intervalId);
                    }
                }
            })();
        }, 1200);

        return () => {
            cancelled = true;
            window.clearInterval(intervalId);
        };
    }, [analysisJob?.job_status, selectedTenderId]);

    const selectedTender = tenders.find((item) => item.id === selectedTenderId) || null;
    const selectedBottleneck = bottlenecks.find((item) => item.external_tender_id === String(selectedTenderId)) || null;
    const selectedHealth = snapshot?.health || selectedBottleneck?.health || 'unknown';
    const palette = healthColors(selectedHealth);
    const leadingKpis = (snapshot?.kpis || []).filter((score) => ['A1', 'A4'].includes(score.kpi_code));
    const redCount = riskCount(bottlenecks, 'red');
    const amberCount = riskCount(bottlenecks, 'amber');
    const analysisJobPalette = analysisJobColors(analysisJob?.job_status);
    const recomputeDisabled = !selectedTenderId || isDetailLoading || isAnalysisJobActive(analysisJob);

    const handleRecompute = async () => {
        if (selectedTenderId === null) {
            return;
        }
        setError(null);
        setIsRecomputing(true);
        try {
            const response = await kpiAdminApi.recomputeTender(selectedTenderId);
            setAnalysisJob(response);
        } catch (recomputeError) {
            setIsRecomputing(false);
            setError(recomputeError instanceof Error ? recomputeError.message : 'Failed to trigger KPI recompute.');
        }
    };

    if (isLoading) {
        return <div className="loading-spinner"><div className="spinner" /></div>;
    }

    return (
        <div className="animate-in">
            <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '1rem' }}>
                <div>
                    <h1 className="page-title" style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                        <Sparkles size={28} color="#38bdf8" />
                        Observability KPI
                    </h1>
                    <p className="page-subtitle">
                        Portfolio observability for the KPI reason engine, exposed through the TenderWriter admin BFF.
                    </p>
                </div>
                <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                    <button
                        className={`btn btn-secondary btn-sm ${isRefreshing ? 'animate-pulse' : ''}`}
                        onClick={() => void loadPortfolio(true)}
                    >
                        <RefreshCcw size={14} /> Refresh
                    </button>
                    <button
                        className={`btn btn-primary btn-sm ${isRecomputing ? 'animate-pulse' : ''}`}
                        onClick={() => void handleRecompute()}
                        disabled={recomputeDisabled}
                    >
                        <RefreshCcw size={14} /> {isRecomputing ? 'Recomputing…' : 'Recompute KPI'}
                    </button>
                </div>
            </div>

            {error && (
                <div className="card" style={{ borderColor: 'rgba(239, 68, 68, 0.35)', background: 'rgba(127, 29, 29, 0.18)', marginBottom: '1.5rem' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', color: '#fecaca' }}>
                        <AlertTriangle size={18} />
                        <span>{error}</span>
                    </div>
                </div>
            )}

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1rem', marginBottom: '1.5rem' }}>
                <motion.div className="card" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div>
                            <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '0.35rem' }}>Tracked tenders</div>
                            <div style={{ fontSize: '2rem', fontWeight: 700 }}>{overview?.total_tenders ?? 0}</div>
                        </div>
                        <Activity size={22} color="#38bdf8" />
                    </div>
                </motion.div>
                <motion.div className="card" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.04 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div>
                            <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '0.35rem' }}>Portfolio health</div>
                            <div style={{ fontSize: '2rem', fontWeight: 700, textTransform: 'capitalize' }}>{overview?.portfolio_health || 'unknown'}</div>
                        </div>
                        <Gauge size={22} color={healthColors(overview?.portfolio_health || 'unknown').accent} />
                    </div>
                </motion.div>
                <motion.div className="card" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.08 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div>
                            <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '0.35rem' }}>Red bottlenecks</div>
                            <div style={{ fontSize: '2rem', fontWeight: 700 }}>{redCount}</div>
                        </div>
                        <ShieldAlert size={22} color="#ef4444" />
                    </div>
                </motion.div>
                <motion.div className="card" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.12 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div>
                            <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '0.35rem' }}>Amber watchlist</div>
                            <div style={{ fontSize: '2rem', fontWeight: 700 }}>{amberCount}</div>
                        </div>
                        <TrendingUp size={22} color="#f59e0b" />
                    </div>
                </motion.div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'minmax(280px, 360px) minmax(0, 1fr)', gap: '1.5rem', alignItems: 'start' }}>
                <div style={{ display: 'grid', gap: '1rem' }}>
                    <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                        <div style={{ padding: '1rem 1rem 0.5rem 1rem' }}>
                            <h3 style={{ margin: 0, fontSize: '0.95rem' }}>Tender focus list</h3>
                            <p style={{ margin: '0.35rem 0 0 0', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                                Admin drilldown on the tenders already mirrored by the KPI engine.
                            </p>
                        </div>
                        <div style={{ maxHeight: '620px', overflowY: 'auto', padding: '0.75rem' }}>
                            {tenders.length === 0 ? (
                                <div style={{ padding: '1rem', color: 'var(--text-muted)', fontSize: '0.9rem' }}>No tenders available yet.</div>
                            ) : (
                                tenders.map((tender) => {
                                    const itemBottleneck = bottlenecks.find((item) => item.external_tender_id === String(tender.id));
                                    const itemPalette = healthColors(itemBottleneck?.health || 'unknown');
                                    const isSelected = tender.id === selectedTenderId;
                                    return (
                                        <button
                                            key={tender.id}
                                            onClick={() => setSelectedTenderId(tender.id)}
                                            style={{
                                                width: '100%',
                                                textAlign: 'left',
                                                border: `1px solid ${isSelected ? itemPalette.accent : 'var(--border-color)'}`,
                                                background: isSelected ? itemPalette.soft : 'rgba(255,255,255,0.02)',
                                                borderRadius: '14px',
                                                padding: '0.9rem',
                                                marginBottom: '0.75rem',
                                                cursor: 'pointer',
                                                color: 'inherit',
                                            }}
                                        >
                                            <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.75rem', alignItems: 'flex-start' }}>
                                                <div>
                                                    <div style={{ fontWeight: 600, marginBottom: '0.25rem' }}>{tender.title}</div>
                                                    <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>{tender.client || 'Client not set'}</div>
                                                </div>
                                                <span style={{
                                                    padding: '0.2rem 0.55rem',
                                                    borderRadius: '999px',
                                                    fontSize: '0.72rem',
                                                    textTransform: 'capitalize',
                                                    background: itemPalette.soft,
                                                    color: itemPalette.accent,
                                                    border: `1px solid ${itemPalette.accent}33`,
                                                }}>
                                                    {itemBottleneck?.health || 'unknown'}
                                                </span>
                                            </div>
                                            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '0.75rem', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                                                <span>Status: {tender.status.replace('_', ' ')}</span>
                                                <span>Deadline: {tender.deadline ? new Date(tender.deadline).toLocaleDateString('it-IT') : 'n/a'}</span>
                                            </div>
                                            {itemBottleneck && (
                                                <div style={{ marginTop: '0.6rem', fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                                                    {itemBottleneck.summary}
                                                </div>
                                            )}
                                        </button>
                                    );
                                })
                            )}
                        </div>
                    </div>

                    <div className="card">
                        <h3 style={{ marginTop: 0, marginBottom: '0.6rem', fontSize: '0.95rem' }}>Current bottlenecks</h3>
                        {bottlenecks.length === 0 ? (
                            <p style={{ margin: 0, color: 'var(--text-muted)', fontSize: '0.85rem' }}>No bottlenecks surfaced yet.</p>
                        ) : (
                            <div style={{ display: 'grid', gap: '0.75rem' }}>
                                {bottlenecks.slice(0, 5).map((item) => {
                                    const itemPalette = healthColors(item.health);
                                    return (
                                        <div key={`${item.external_tender_id}-${item.bottleneck_type}`} style={{ borderLeft: `3px solid ${itemPalette.accent}`, paddingLeft: '0.75rem' }}>
                                            <div style={{ fontSize: '0.78rem', color: itemPalette.accent, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                                                {item.bottleneck_type}
                                            </div>
                                            <div style={{ fontSize: '0.85rem', marginTop: '0.2rem' }}>{item.summary}</div>
                                        </div>
                                    );
                                })}
                            </div>
                        )}
                    </div>
                </div>

                <div style={{ display: 'grid', gap: '1rem' }}>
                    <div className="card" style={{
                        background: `linear-gradient(135deg, ${palette.soft} 0%, rgba(15, 23, 42, 0.85) 100%)`,
                        border: `1px solid ${palette.accent}33`,
                    }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', gap: '1rem', alignItems: 'flex-start' }}>
                            <div>
                                <div style={{ fontSize: '0.78rem', textTransform: 'uppercase', letterSpacing: '0.08em', color: palette.text }}>Selected tender</div>
                                <h2 style={{ margin: '0.4rem 0 0 0' }}>{selectedTender?.title || 'Select a tender'}</h2>
                                <p style={{ margin: '0.45rem 0 0 0', color: 'var(--text-secondary)' }}>{selectedTender?.client || 'Client not available'}</p>
                            </div>
                            <span style={{
                                padding: '0.35rem 0.75rem',
                                borderRadius: '999px',
                                background: palette.soft,
                                color: palette.text,
                                border: `1px solid ${palette.accent}40`,
                                textTransform: 'capitalize',
                                fontSize: '0.8rem',
                            }}>
                                {selectedHealth}
                            </span>
                        </div>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '0.9rem', marginTop: '1rem' }}>
                            <div>
                                <div style={{ fontSize: '0.76rem', color: 'var(--text-muted)', marginBottom: '0.2rem' }}>Analytical phase</div>
                                <div style={{ fontWeight: 600 }}>{phaseLabel(snapshot?.analytical_phase || null)}</div>
                            </div>
                            <div>
                                <div style={{ fontSize: '0.76rem', color: 'var(--text-muted)', marginBottom: '0.2rem' }}>Workflow status</div>
                                <div style={{ fontWeight: 600 }}>{selectedTender?.status.replace('_', ' ') || 'n/a'}</div>
                            </div>
                            <div>
                                <div style={{ fontSize: '0.76rem', color: 'var(--text-muted)', marginBottom: '0.2rem' }}>Generated at</div>
                                <div style={{ fontWeight: 600 }}>{formatGeneratedAt(snapshot?.generated_at || null)}</div>
                            </div>
                            <div>
                                <div style={{ fontSize: '0.76rem', color: 'var(--text-muted)', marginBottom: '0.2rem' }}>Analysis job</div>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
                                    <span style={{
                                        padding: '0.25rem 0.6rem',
                                        borderRadius: '999px',
                                        background: analysisJobPalette.soft,
                                        color: analysisJobPalette.accent,
                                        border: `1px solid ${analysisJobPalette.accent}33`,
                                        fontSize: '0.76rem',
                                    }}>
                                        {analysisJobLabel(analysisJob?.job_status)}
                                    </span>
                                    {analysisJob?.updated_at && (
                                        <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                                            {formatGeneratedAt(analysisJob.updated_at)}
                                        </span>
                                    )}
                                </div>
                            </div>
                        </div>
                        {analysisJob?.error_message && !isAnalysisJobActive(analysisJob) && (
                            <p style={{ margin: '0.85rem 0 0 0', color: '#fecaca', fontSize: '0.82rem' }}>
                                {analysisJob.error_message}
                            </p>
                        )}
                    </div>

                    {isDetailLoading ? (
                        <div className="card"><p style={{ margin: 0, color: 'var(--text-muted)' }}>Loading KPI detail...</p></div>
                    ) : !selectedTenderId || !snapshot ? (
                        <div className="card"><p style={{ margin: 0, color: 'var(--text-muted)' }}>Select a tender to inspect observability detail.</p></div>
                    ) : (
                        <>
                            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1rem' }}>
                                {leadingKpis.map((score) => {
                                    const scorePalette = healthColors(score.health);
                                    return (
                                        <div key={score.kpi_code} className="card" style={{ borderColor: `${scorePalette.accent}33` }}>
                                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                                <div>
                                                    <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>{score.kpi_code}</div>
                                                    <div style={{ fontSize: '2rem', fontWeight: 700, marginTop: '0.25rem' }}>{formatScoreValue(score)}</div>
                                                </div>
                                                <div style={{
                                                    padding: '0.3rem 0.65rem',
                                                    borderRadius: '999px',
                                                    background: scorePalette.soft,
                                                    color: scorePalette.accent,
                                                    textTransform: 'capitalize',
                                                    fontSize: '0.75rem',
                                                }}>
                                                    {score.health}
                                                </div>
                                            </div>
                                            <p style={{ margin: '0.75rem 0 0 0', fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
                                                {score.label || 'No label available.'}
                                            </p>
                                            <p style={{ margin: '0.6rem 0 0 0', fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                                                Provenance: {score.provenance} | Confidence: {score.confidence ?? 0}
                                            </p>
                                        </div>
                                    );
                                })}
                            </div>

                            <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1.2fr) minmax(320px, 0.8fr)', gap: '1rem' }}>
                                <div className="card">
                                    <h3 style={{ marginTop: 0, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                        <FileSearch size={18} color="#38bdf8" /> KPI evidence
                                    </h3>
                                    <div style={{ display: 'grid', gap: '0.9rem' }}>
                                        {leadingKpis.map((score) => (
                                            <div key={`${score.kpi_code}-evidence`} style={{ padding: '0.85rem', borderRadius: '12px', background: 'rgba(15, 23, 42, 0.35)', border: '1px solid var(--border-color)' }}>
                                                <div style={{ fontWeight: 600, marginBottom: '0.5rem' }}>{score.kpi_code} evidence</div>
                                                {score.evidence.length === 0 ? (
                                                    <div style={{ fontSize: '0.82rem', color: 'var(--text-muted)' }}>No evidence available.</div>
                                                ) : (
                                                    <ul style={{ margin: 0, paddingLeft: '1rem', color: 'var(--text-secondary)' }}>
                                                        {score.evidence.slice(0, 4).map((item) => (
                                                            <li key={item} style={{ marginBottom: '0.4rem', fontSize: '0.82rem' }}>{item}</li>
                                                        ))}
                                                    </ul>
                                                )}
                                            </div>
                                        ))}
                                    </div>
                                </div>

                                <div style={{ display: 'grid', gap: '1rem' }}>
                                    <div className="card">
                                        <h3 style={{ marginTop: 0, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                            <Activity size={18} color="#38bdf8" /> Diagnostics
                                        </h3>
                                        <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                                            {diagnostics?.summary || 'Diagnostics not available.'}
                                        </p>
                                        <div style={{ display: 'grid', gap: '0.55rem', marginTop: '0.75rem' }}>
                                            {(diagnostics?.findings || snapshot.notes).slice(0, 6).map((item) => (
                                                <div key={item} style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', padding: '0.65rem 0.75rem', background: 'rgba(255,255,255,0.02)', borderRadius: '10px' }}>
                                                    {item}
                                                </div>
                                            ))}
                                        </div>
                                    </div>

                                    <div className="card">
                                        <h3 style={{ marginTop: 0, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                            <TrendingUp size={18} color="#38bdf8" /> Forecast
                                        </h3>
                                        {(forecast?.scenarios || []).length === 0 ? (
                                            <p style={{ margin: 0, color: 'var(--text-muted)', fontSize: '0.85rem' }}>Forecast not available.</p>
                                        ) : (
                                            <div style={{ display: 'grid', gap: '0.75rem' }}>
                                                {forecast?.scenarios.map((scenario) => (
                                                    <div key={scenario.name} style={{ padding: '0.8rem', borderRadius: '12px', background: 'rgba(15, 23, 42, 0.35)', border: '1px solid var(--border-color)' }}>
                                                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '0.75rem' }}>
                                                            <span style={{ fontWeight: 600 }}>{scenario.name}</span>
                                                            <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                                                                {scenario.probability === null || scenario.probability === undefined ? '--' : `${Math.round(scenario.probability * 100)}%`}
                                                            </span>
                                                        </div>
                                                        <p style={{ margin: '0.45rem 0 0 0', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                                                            {scenario.description || 'No description available.'}
                                                        </p>
                                                    </div>
                                                ))}
                                            </div>
                                        )}
                                    </div>
                                </div>
                            </div>

                            <ComplianceDrilldownPanel
                                tenderDetail={tenderDetail}
                                workspace={workspace}
                                analyticalPhase={snapshot?.analytical_phase || null}
                            />

                            <TransitionTimelinePanel transitions={transitions} />
                        </>
                    )}

                    <OperationalWorkspacePanel
                        tender={selectedTender}
                        onDataChanged={() => {
                            void loadPortfolio(true);
                        }}
                    />
                </div>
            </div>
        </div>
    );
}
