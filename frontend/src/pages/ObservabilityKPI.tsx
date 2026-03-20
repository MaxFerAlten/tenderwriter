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
    type KpiAnalysisMetadata,
    type KpiBottleneckItem,
    type KpiDiagnostics,
    type KpiForecast,
    type KpiPortfolioIntelligence,
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
import LifecycleControlPanel from '../components/observability/LifecycleControlPanel';
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

function formatProbability(value: number | null | undefined): string {
    if (value === null || value === undefined) {
        return '--';
    }
    return `${Math.round(value * 100)}%`;
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

function signalTone(signal: string | null | undefined): { accent: string; soft: string } {
    switch (signal) {
        case 'observed':
            return { accent: '#10b981', soft: 'rgba(16, 185, 129, 0.12)' };
        case 'inferred':
            return { accent: '#f59e0b', soft: 'rgba(245, 158, 11, 0.14)' };
        case 'reconstructed':
        case 'predicted':
            return { accent: '#38bdf8', soft: 'rgba(56, 189, 248, 0.14)' };
        case 'shadow':
            return { accent: '#14b8a6', soft: 'rgba(20, 184, 166, 0.14)' };
        case 'calibrated':
            return { accent: '#22c55e', soft: 'rgba(34, 197, 94, 0.14)' };
        case 'locked':
            return { accent: '#64748b', soft: 'rgba(100, 116, 139, 0.14)' };
        default:
            return { accent: '#64748b', soft: 'rgba(100, 116, 139, 0.14)' };
    }
}

function chipStyle(accent: string, soft: string) {
    return {
        padding: '0.24rem 0.62rem',
        borderRadius: '999px',
        fontSize: '0.72rem',
        background: soft,
        color: accent,
        border: `1px solid ${accent}33`,
        textTransform: 'capitalize' as const,
    };
}

function formatConfidenceValue(value: number | null | undefined): string {
    if (value === null || value === undefined) {
        return '--';
    }
    return value.toFixed(2);
}

function scoreEvidenceItems(score: KpiScore): string[] {
    return score.evidences.length > 0 ? score.evidences : score.evidence;
}

function scoreRecommendations(score: KpiScore): string[] {
    return score.recommendations.length > 0
        ? score.recommendations
        : (score.recommendation ? [score.recommendation] : []);
}

function semanticStatusTone(status: string | null | undefined): { accent: string; soft: string } {
    switch (status) {
        case 'official':
            return { accent: '#22c55e', soft: 'rgba(34, 197, 94, 0.14)' };
        case 'fallback':
            return { accent: '#f59e0b', soft: 'rgba(245, 158, 11, 0.14)' };
        case 'shadow':
            return { accent: '#14b8a6', soft: 'rgba(20, 184, 166, 0.14)' };
        default:
            return { accent: '#64748b', soft: 'rgba(100, 116, 139, 0.14)' };
    }
}

function semanticStatusLabel(status: string | null | undefined): string {
    switch (status) {
        case 'official':
            return 'semantic official';
        case 'fallback':
            return 'semantic fallback';
        case 'shadow':
            return 'semantic shadow';
        default:
            return status || 'semantic';
    }
}

function actionPriorityTone(priority: string | null | undefined): { accent: string; soft: string } {
    switch (priority) {
        case 'now':
            return { accent: '#ef4444', soft: 'rgba(239, 68, 68, 0.14)' };
        case 'next':
            return { accent: '#f59e0b', soft: 'rgba(245, 158, 11, 0.14)' };
        default:
            return { accent: '#38bdf8', soft: 'rgba(56, 189, 248, 0.14)' };
    }
}

function mergeAnalysisMetadata(...items: Array<KpiAnalysisMetadata | null | undefined>): KpiAnalysisMetadata | null {
    const present = items.filter(Boolean) as KpiAnalysisMetadata[];
    if (present.length === 0) {
        return null;
    }

    return present.reduce<KpiAnalysisMetadata>((accumulator, current) => ({
        ...accumulator,
        ...current,
        markov_phase_scope: current.markov_phase_scope.length > 0 ? current.markov_phase_scope : accumulator.markov_phase_scope,
        markov_reliable_phase_scope: current.markov_reliable_phase_scope.length > 0 ? current.markov_reliable_phase_scope : accumulator.markov_reliable_phase_scope,
        semantic_priority: current.semantic_priority.length > 0 ? current.semantic_priority : accumulator.semantic_priority,
        canonical_source_types: current.canonical_source_types.length > 0 ? current.canonical_source_types : accumulator.canonical_source_types,
        semantic_kpis: current.semantic_kpis.length > 0 ? current.semantic_kpis : accumulator.semantic_kpis,
        semantic_fallback_kpis: current.semantic_fallback_kpis.length > 0 ? current.semantic_fallback_kpis : accumulator.semantic_fallback_kpis,
        shadow_kpis: current.shadow_kpis.length > 0 ? current.shadow_kpis : accumulator.shadow_kpis,
        forecast_engine_candidates: current.forecast_engine_candidates.length > 0 ? current.forecast_engine_candidates : accumulator.forecast_engine_candidates,
        markov_state_scope: current.markov_state_scope.length > 0 ? current.markov_state_scope : accumulator.markov_state_scope,
        markov_absorbing_states: current.markov_absorbing_states.length > 0 ? current.markov_absorbing_states : accumulator.markov_absorbing_states,
        markov_projected_path: current.markov_projected_path.length > 0 ? current.markov_projected_path : accumulator.markov_projected_path,
        forecast_driver_kpis: current.forecast_driver_kpis.length > 0 ? current.forecast_driver_kpis : accumulator.forecast_driver_kpis,
        scored_kpis: current.scored_kpis.length > 0 ? current.scored_kpis : accumulator.scored_kpis,
        markov_source_mix: Object.keys(current.markov_source_mix).length > 0 ? current.markov_source_mix : accumulator.markov_source_mix,
        forecast_driver_scores: Object.keys(current.forecast_driver_scores).length > 0 ? current.forecast_driver_scores : accumulator.forecast_driver_scores,
    }), present[0]);
}

function forecastSignalLabel(signalType: string | null | undefined): string {
    switch (signalType) {
        case 'predicted':
            return 'predicted forecast';
        case 'calibrated':
            return 'calibrated forecast';
        case 'locked':
            return 'locked outcome';
        case 'not_ready':
            return 'forecast pending';
        default:
            return signalType || 'forecast signal';
    }
}

export default function ObservabilityKPI() {
    const [overview, setOverview] = useState<KpiPortfolioOverview | null>(null);
    const [bottlenecks, setBottlenecks] = useState<KpiBottleneckItem[]>([]);
    const [portfolioIntelligence, setPortfolioIntelligence] = useState<KpiPortfolioIntelligence | null>(null);
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
    const [isPortfolioResyncing, setIsPortfolioResyncing] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [actionNotice, setActionNotice] = useState<string | null>(null);

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
            const [overviewResponse, bottlenecksResponse, intelligenceResponse, tendersResponse] = await Promise.all([
                kpiAdminApi.getPortfolioOverview(),
                kpiAdminApi.getPortfolioBottlenecks(),
                kpiAdminApi.getPortfolioIntelligence(),
                tenderApi.list({ limit: '100' }),
            ]);
            setOverview(overviewResponse);
            setBottlenecks(bottlenecksResponse.items);
            setPortfolioIntelligence(intelligenceResponse);
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
    const qualitativeKpis = (snapshot?.kpis || []).filter((score) => ['A1', 'A2', 'A3', 'A4', 'Q'].includes(score.kpi_code));
    const operationalKpis = (snapshot?.kpis || []).filter((score) => ['B1', 'B2', 'B3', 'B4', 'E'].includes(score.kpi_code));
    const scoredKpis = (snapshot?.kpis || []).filter((score) => score.value !== null || scoreEvidenceItems(score).length > 0 || scoreRecommendations(score).length > 0 || Boolean(score.semantic) || Boolean(score.shadow));
    const analysisMetadata = mergeAnalysisMetadata(snapshot?.analysis_metadata ?? null, diagnostics?.analysis_metadata ?? null, forecast?.analysis_metadata ?? null);
    const forecastMetadata = forecast?.analysis_metadata ? mergeAnalysisMetadata(snapshot?.analysis_metadata ?? null, diagnostics?.analysis_metadata ?? null, forecast.analysis_metadata) : analysisMetadata;
    const redCount = riskCount(bottlenecks, 'red');
    const amberCount = riskCount(bottlenecks, 'amber');
    const watchlistCount = portfolioIntelligence?.watchlist.length ?? 0;
    const analysisJobPalette = analysisJobColors(analysisJob?.job_status);
    const recomputeDisabled = !selectedTenderId || isDetailLoading || isAnalysisJobActive(analysisJob);
    const backfillDisabled = recomputeDisabled;
    const portfolioResyncDisabled = isPortfolioResyncing || isRefreshing || isLoading;
    const activeJobType = analysisJob?.job_type || null;

    const handlePortfolioResync = async () => {
        setError(null);
        setActionNotice(null);
        setIsPortfolioResyncing(true);
        try {
            const response = await kpiAdminApi.resyncPortfolio();
            const total = response.total_tenders ?? 0;
            const synced = response.synced_tenders ?? 0;
            const failed = response.failed_tenders ?? 0;
            setActionNotice(
                failed > 0
                    ? `Portfolio resync completed: ${synced}/${total} synced, ${failed} failed.`
                    : `Portfolio resync completed: ${synced}/${total} tenders synced into the KPI engine.`
            );
            await loadPortfolio(true);
        } catch (resyncError) {
            setError(resyncError instanceof Error ? resyncError.message : 'Failed to resync the KPI portfolio.');
        } finally {
            setIsPortfolioResyncing(false);
        }
    };

    const handleRecompute = async () => {
        if (selectedTenderId === null) {
            return;
        }
        setError(null);
        setIsRecomputing(true);
        try {
            const response = await kpiAdminApi.recomputeTender(selectedTenderId);
            setAnalysisJob(response);
            setIsRecomputing(isAnalysisJobActive(response));
        } catch (recomputeError) {
            setIsRecomputing(false);
            setError(recomputeError instanceof Error ? recomputeError.message : 'Failed to trigger KPI recompute.');
        }
    };

    const handleHistoryBackfill = async () => {
        if (selectedTenderId === null) {
            return;
        }
        setError(null);
        setIsRecomputing(true);
        try {
            const response = await kpiAdminApi.backfillTenderHistory(selectedTenderId);
            setAnalysisJob(response);
            setIsRecomputing(isAnalysisJobActive(response));
        } catch (backfillError) {
            setIsRecomputing(false);
            setError(backfillError instanceof Error ? backfillError.message : 'Failed to trigger KPI history backfill.');
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
                        className={`btn btn-secondary btn-sm ${isPortfolioResyncing ? 'animate-pulse' : ''}`}
                        onClick={() => void handlePortfolioResync()}
                        disabled={portfolioResyncDisabled}
                    >
                        <RefreshCcw size={14} /> {isPortfolioResyncing ? 'Resyncing portfolio...' : 'Resync Portfolio'}
                    </button>
                    <button
                        className={`btn btn-secondary btn-sm ${isRecomputing && activeJobType === 'history_backfill' ? 'animate-pulse' : ''}`}
                        onClick={() => void handleHistoryBackfill()}
                        disabled={backfillDisabled}
                    >
                        <FileSearch size={14} /> {isRecomputing && activeJobType === 'history_backfill' ? 'Replaying history…' : 'Replay History'}
                    </button>
                    <button
                        className={`btn btn-primary btn-sm ${isRecomputing && activeJobType !== 'history_backfill' ? 'animate-pulse' : ''}`}
                        onClick={() => void handleRecompute()}
                        disabled={recomputeDisabled}
                    >
                        <RefreshCcw size={14} /> {isRecomputing && activeJobType !== 'history_backfill' ? 'Recomputing…' : 'Recompute KPI'}
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

            {actionNotice && (
                <div className="card" style={{ borderColor: 'rgba(16, 185, 129, 0.28)', background: 'rgba(6, 78, 59, 0.18)', marginBottom: '1.5rem' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', color: '#bbf7d0' }}>
                        <Activity size={18} />
                        <span>{actionNotice}</span>
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
                            <div style={{ fontSize: '2rem', fontWeight: 700 }}>{Math.max(amberCount, watchlistCount)}</div>
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


                    <div className="card">
                        <h3 style={{ marginTop: 0, marginBottom: '0.6rem', fontSize: '0.95rem' }}>Portfolio intelligence</h3>
                        {!portfolioIntelligence ? (
                            <p style={{ margin: 0, color: 'var(--text-muted)', fontSize: '0.85rem' }}>Portfolio intelligence not available yet.</p>
                        ) : (
                            <div style={{ display: 'grid', gap: '0.9rem' }}>
                                <div>
                                    <div style={{ fontSize: '0.76rem', color: 'var(--text-muted)', marginBottom: '0.45rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Phase hotspots</div>
                                    <div style={{ display: 'grid', gap: '0.55rem' }}>
                                        {portfolioIntelligence.phase_hotspots.slice(0, 3).map((item) => (
                                            <div key={`phase-${item.phase}`} style={{ padding: '0.7rem 0.8rem', borderRadius: '12px', background: 'rgba(15, 23, 42, 0.28)', border: '1px solid var(--border-color)' }}>
                                                <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.5rem', alignItems: 'center' }}>
                                                    <span style={{ fontWeight: 600 }}>{phaseLabel(item.phase)}</span>
                                                    <span style={{ fontSize: '0.74rem', color: '#38bdf8' }}>{item.count}</span>
                                                </div>
                                                <div style={{ marginTop: '0.35rem', fontSize: '0.76rem', color: 'var(--text-muted)' }}>{item.summary}</div>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                                <div>
                                    <div style={{ fontSize: '0.76rem', color: 'var(--text-muted)', marginBottom: '0.45rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Risk hotspots</div>
                                    <div style={{ display: 'grid', gap: '0.55rem' }}>
                                        {portfolioIntelligence.risk_hotspots.slice(0, 3).map((item) => {
                                            const tone = healthColors(item.severity === 'critical' || item.severity === 'high' ? 'red' : item.severity === 'medium' ? 'amber' : 'green');
                                            return (
                                                <div key={`risk-${item.code}`} style={{ padding: '0.7rem 0.8rem', borderRadius: '12px', background: tone.soft, border: `1px solid ${tone.accent}33` }}>
                                                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.5rem', alignItems: 'center' }}>
                                                        <span style={{ fontWeight: 600 }}>{item.code}</span>
                                                        <span style={{ fontSize: '0.74rem', color: tone.accent }}>{item.count}</span>
                                                    </div>
                                                    <div style={{ marginTop: '0.35rem', fontSize: '0.76rem', color: 'var(--text-secondary)' }}>{item.summary}</div>
                                                </div>
                                            );
                                        })}
                                    </div>
                                </div>
                                <div>
                                    <div style={{ fontSize: '0.76rem', color: 'var(--text-muted)', marginBottom: '0.45rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Admin watchlist</div>
                                    <div style={{ display: 'grid', gap: '0.55rem' }}>
                                        {portfolioIntelligence.watchlist.slice(0, 3).map((item) => {
                                            const tone = healthColors(item.health);
                                            return (
                                                <div key={`watch-${item.external_tender_id}`} style={{ padding: '0.7rem 0.8rem', borderRadius: '12px', background: 'rgba(15, 23, 42, 0.28)', border: `1px solid ${tone.accent}33` }}>
                                                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.5rem', alignItems: 'center' }}>
                                                        <span style={{ fontWeight: 600 }}>{item.title}</span>
                                                        <span style={{ fontSize: '0.74rem', color: tone.accent, textTransform: 'capitalize' }}>{item.health}</span>
                                                    </div>
                                                    <div style={{ marginTop: '0.35rem', fontSize: '0.74rem', color: 'var(--text-muted)' }}>{phaseLabel(item.analytical_phase)}</div>
                                                    <div style={{ marginTop: '0.35rem', fontSize: '0.76rem', color: 'var(--text-secondary)' }}>{item.summary}</div>
                                                </div>
                                            );
                                        })}
                                    </div>
                                </div>
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
                                {qualitativeKpis.map((score) => {
                                    const scorePalette = healthColors(score.health);
                                    const provenanceTone = signalTone(score.source_type || score.provenance);
                                    const shadowTone = signalTone('shadow');
                                    const semanticTone = score.semantic ? semanticStatusTone(score.semantic.status) : null;
                                    const recommendations = scoreRecommendations(score);
                                    return (
                                        <div key={score.kpi_code} className="card" style={{ borderColor: `${scorePalette.accent}33` }}>
                                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '0.75rem' }}>
                                                <div>
                                                    <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>{score.kpi_code}</div>
                                                    <div style={{ fontSize: '2rem', fontWeight: 700, marginTop: '0.25rem' }}>{formatScoreValue(score)}</div>
                                                </div>
                                                <div style={{ display: 'grid', gap: '0.35rem', justifyItems: 'end' }}>
                                                    <div style={{ padding: '0.3rem 0.65rem', borderRadius: '999px', background: scorePalette.soft, color: scorePalette.accent, textTransform: 'capitalize', fontSize: '0.75rem' }}>
                                                        {score.health}
                                                    </div>
                                                    <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'capitalize' }}>
                                                        Severity: {score.severity}
                                                    </div>
                                                </div>
                                            </div>
                                            <div style={{ display: 'flex', gap: '0.45rem', flexWrap: 'wrap', marginTop: '0.7rem' }}>
                                                <span style={chipStyle(provenanceTone.accent, provenanceTone.soft)}>{score.source_type || score.provenance || 'unknown'}</span>
                                                {score.semantic && semanticTone && <span style={chipStyle(semanticTone.accent, semanticTone.soft)}>{semanticStatusLabel(score.semantic.status)}</span>}
                                                {score.shadow && <span style={chipStyle(shadowTone.accent, shadowTone.soft)}>shadow</span>}
                                            </div>
                                            <p style={{ margin: '0.75rem 0 0 0', fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
                                                {score.label || 'No label available.'}
                                            </p>
                                            {recommendations.length > 0 && (
                                                <p style={{ margin: '0.6rem 0 0 0', fontSize: '0.78rem', color: '#dbeafe' }}>
                                                    Recommendation: {recommendations[0]}
                                                </p>
                                            )}
                                            <p style={{ margin: '0.6rem 0 0 0', fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                                                Confidence: {formatConfidenceValue(score.confidence)} | Formula: {score.formula_version || 'n/a'}
                                            </p>
                                            {score.semantic && semanticTone && (
                                                <div style={{ marginTop: '0.75rem', padding: '0.7rem 0.8rem', borderRadius: '12px', background: semanticTone.soft, border: `1px solid ${semanticTone.accent}33` }}>
                                                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.5rem', alignItems: 'center' }}>
                                                        <span style={{ fontWeight: 600, fontSize: '0.8rem', color: semanticTone.accent }}>{semanticStatusLabel(score.semantic.status)}</span>
                                                        <span style={{ fontSize: '0.72rem', color: semanticTone.accent, textTransform: 'capitalize' }}>{score.semantic.health}</span>
                                                    </div>
                                                    <div style={{ marginTop: '0.45rem', fontSize: '0.76rem', color: 'var(--text-secondary)' }}>
                                                        Semantic score {score.semantic.semantic_score ?? '--'} | Proxy {score.semantic.proxy_score ?? '--'} | Delta {score.semantic.delta_vs_proxy ?? '--'}
                                                    </div>
                                                    <div style={{ marginTop: '0.35rem', fontSize: '0.74rem', color: 'var(--text-muted)' }}>
                                                        Source {score.semantic.source_type} | Confidence {formatConfidenceValue(score.semantic.confidence)}{score.semantic.fallback_reason ? ` | Fallback ${score.semantic.fallback_reason}` : ''}
                                                    </div>
                                                    {score.semantic.criticalities.length > 0 && (
                                                        <ul style={{ margin: '0.45rem 0 0 0', paddingLeft: '1rem', color: 'var(--text-secondary)' }}>
                                                            {score.semantic.criticalities.slice(0, 2).map((item) => (
                                                                <li key={`${score.kpi_code}-semantic-${item}`} style={{ fontSize: '0.76rem', marginBottom: '0.3rem' }}>{item}</li>
                                                            ))}
                                                        </ul>
                                                    )}
                                                    {(score.semantic.coverage_gaps.length > 0 || score.semantic.risk_items.length > 0 || score.semantic.dimension_items.length > 0) && (
                                                        <div style={{ marginTop: '0.45rem', fontSize: '0.74rem', color: 'var(--text-muted)' }}>
                                                            {score.semantic.coverage_gaps.length > 0 ? `Coverage gaps ${score.semantic.coverage_gaps.length}. ` : ''}
                                                            {score.semantic.risk_items.length > 0 ? `Risk items ${score.semantic.risk_items.length}. ` : ''}
                                                            {score.semantic.dimension_items.length > 0 ? `Rubric dimensions ${score.semantic.dimension_items.length}.` : ''}
                                                        </div>
                                                    )}
                                                </div>
                                            )}
                                            {score.shadow && (
                                                <div style={{ marginTop: '0.75rem', padding: '0.7rem 0.8rem', borderRadius: '12px', background: 'rgba(20, 184, 166, 0.08)', border: '1px solid rgba(20, 184, 166, 0.2)' }}>
                                                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.5rem', alignItems: 'center' }}>
                                                        <span style={{ fontWeight: 600, fontSize: '0.8rem', color: '#99f6e4' }}>Semantic shadow</span>
                                                        <span style={{ fontSize: '0.72rem', color: '#99f6e4', textTransform: 'capitalize' }}>{score.shadow.health}</span>
                                                    </div>
                                                    <div style={{ marginTop: '0.45rem', fontSize: '0.76rem', color: '#ccfbf1' }}>
                                                        Shadow score {score.shadow.shadow_score ?? '--'} | Delta vs proxy {score.shadow.delta_vs_proxy ?? '--'}
                                                    </div>
                                                    <div style={{ marginTop: '0.35rem', fontSize: '0.74rem', color: 'rgba(204, 251, 241, 0.8)' }}>
                                                        Source {score.shadow.source_type} | Confidence {formatConfidenceValue(score.shadow.confidence)}
                                                    </div>
                                                </div>
                                            )}
                                        </div>
                                    );
                                })}
                            </div>

                            <div className="card">
                                <h3 style={{ marginTop: 0, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                    <Gauge size={18} color="#38bdf8" /> Operational scorecards
                                </h3>
                                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '0.85rem' }}>
                                    {operationalKpis.map((score) => {
                                        const scorePalette = healthColors(score.health);
                                        return (
                                            <div key={score.kpi_code} style={{ padding: '0.85rem', borderRadius: '12px', border: `1px solid ${scorePalette.accent}22`, background: 'rgba(15, 23, 42, 0.3)' }}>
                                                <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.5rem', alignItems: 'center' }}>
                                                    <span style={{ fontWeight: 600 }}>{score.kpi_code}</span>
                                                    <span style={{ fontSize: '0.78rem', color: scorePalette.accent, textTransform: 'capitalize' }}>{score.health}</span>
                                                </div>
                                                <div style={{ fontSize: '1.4rem', fontWeight: 700, marginTop: '0.45rem' }}>{formatScoreValue(score)}</div>
                                                <div style={{ marginTop: '0.35rem', fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                                                    {score.recommendation || score.label || 'No recommendation available.'}
                                                </div>
                                            </div>
                                        );
                                    })}
                                </div>
                            </div>

                            <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1.2fr) minmax(320px, 0.8fr)', gap: '1rem' }}>
                                <div className="card">
                                    <h3 style={{ marginTop: 0, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                        <FileSearch size={18} color="#38bdf8" /> KPI evidence
                                    </h3>
                                    <div style={{ display: 'grid', gap: '0.9rem' }}>
                                        {scoredKpis.map((score) => {
                                            const evidenceItems = scoreEvidenceItems(score);
                                            const recommendations = scoreRecommendations(score);
                                            const provenanceTone = signalTone(score.source_type || score.provenance);
                                            const shadowTone = signalTone('shadow');
                                            const semanticTone = score.semantic ? semanticStatusTone(score.semantic.status) : null;
                                            return (
                                                <div key={`${score.kpi_code}-evidence`} style={{ padding: '0.85rem', borderRadius: '12px', background: 'rgba(15, 23, 42, 0.35)', border: '1px solid var(--border-color)' }}>
                                                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.75rem', marginBottom: '0.5rem' }}>
                                                        <div style={{ fontWeight: 600 }}>{score.kpi_code} evidence</div>
                                                        <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                                                            <span style={chipStyle(provenanceTone.accent, provenanceTone.soft)}>{score.source_type || score.provenance || 'unknown'}</span>
                                                            {score.semantic && semanticTone && <span style={chipStyle(semanticTone.accent, semanticTone.soft)}>{semanticStatusLabel(score.semantic.status)}</span>}
                                                            {score.shadow && <span style={chipStyle(shadowTone.accent, shadowTone.soft)}>shadow</span>}
                                                        </div>
                                                    </div>
                                                    <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginBottom: '0.5rem' }}>
                                                        {score.formula_version || 'n/a'} | Confidence {formatConfidenceValue(score.confidence)}
                                                    </div>
                                                    {recommendations.length > 0 && (
                                                        <p style={{ margin: '0 0 0.55rem 0', fontSize: '0.8rem', color: '#dbeafe' }}>
                                                            {recommendations[0]}
                                                        </p>
                                                    )}
                                                    {evidenceItems.length === 0 ? (
                                                        <div style={{ fontSize: '0.82rem', color: 'var(--text-muted)' }}>No evidence available.</div>
                                                    ) : (
                                                        <ul style={{ margin: 0, paddingLeft: '1rem', color: 'var(--text-secondary)' }}>
                                                            {evidenceItems.slice(0, 4).map((item) => (
                                                                <li key={item} style={{ marginBottom: '0.4rem', fontSize: '0.82rem' }}>{item}</li>
                                                            ))}
                                                        </ul>
                                                    )}
                                                    {score.semantic && semanticTone && (
                                                        <div style={{ marginTop: '0.75rem', padding: '0.7rem 0.8rem', borderRadius: '12px', background: semanticTone.soft, border: `1px solid ${semanticTone.accent}33` }}>
                                                            <div style={{ fontWeight: 600, fontSize: '0.78rem', color: semanticTone.accent }}>{semanticStatusLabel(score.semantic.status)}</div>
                                                            <div style={{ marginTop: '0.35rem', fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                                                                Score {score.semantic.semantic_score ?? '--'} | Proxy {score.semantic.proxy_score ?? '--'} | Delta {score.semantic.delta_vs_proxy ?? '--'} | Source {score.semantic.source_type}
                                                            </div>
                                                            {score.semantic.dimension_items.length > 0 && (
                                                                <ul style={{ margin: '0.45rem 0 0 0', paddingLeft: '1rem', color: 'var(--text-secondary)' }}>
                                                                    {score.semantic.dimension_items.slice(0, 2).map((item) => (
                                                                        <li key={`${score.kpi_code}-dimension-${item.code}`} style={{ fontSize: '0.76rem', marginBottom: '0.3rem' }}>{item.summary}</li>
                                                                    ))}
                                                                </ul>
                                                            )}
                                                            {score.semantic.risk_items.length > 0 && (
                                                                <ul style={{ margin: '0.45rem 0 0 0', paddingLeft: '1rem', color: 'var(--text-secondary)' }}>
                                                                    {score.semantic.risk_items.slice(0, 2).map((item) => (
                                                                        <li key={`${score.kpi_code}-risk-${item.code}-${item.summary}`} style={{ fontSize: '0.76rem', marginBottom: '0.3rem' }}>{item.summary}</li>
                                                                    ))}
                                                                </ul>
                                                            )}
                                                            {score.semantic.coverage_gaps.length > 0 && (
                                                                <div style={{ marginTop: '0.45rem', fontSize: '0.74rem', color: 'var(--text-muted)' }}>
                                                                    Coverage gaps surfaced: {score.semantic.coverage_gaps.length}
                                                                </div>
                                                            )}
                                                        </div>
                                                    )}
                                                    {score.shadow && (
                                                        <div style={{ marginTop: '0.75rem', padding: '0.7rem 0.8rem', borderRadius: '12px', background: 'rgba(20, 184, 166, 0.08)', border: '1px solid rgba(20, 184, 166, 0.2)' }}>
                                                            <div style={{ fontWeight: 600, fontSize: '0.78rem', color: '#99f6e4' }}>Shadow semantic view</div>
                                                            <div style={{ marginTop: '0.35rem', fontSize: '0.75rem', color: '#ccfbf1' }}>
                                                                Score {score.shadow.shadow_score ?? '--'} | Delta {score.shadow.delta_vs_proxy ?? '--'} | Source {score.shadow.source_type}
                                                            </div>
                                                            {score.shadow.criticalities.length > 0 && (
                                                                <ul style={{ margin: '0.45rem 0 0 0', paddingLeft: '1rem', color: 'rgba(204, 251, 241, 0.85)' }}>
                                                                    {score.shadow.criticalities.slice(0, 2).map((item) => (
                                                                        <li key={`${score.kpi_code}-${item}`} style={{ fontSize: '0.76rem', marginBottom: '0.3rem' }}>{item}</li>
                                                                    ))}
                                                                </ul>
                                                            )}
                                                        </div>
                                                    )}
                                                </div>
                                            );
                                        })}
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
                                        {analysisMetadata && (
                                            <>
                                                <div style={{ display: 'flex', gap: '0.45rem', flexWrap: 'wrap', marginTop: '0.75rem' }}>
                                                    {analysisMetadata.rollout_policy && (
                                                        <span style={chipStyle('#38bdf8', 'rgba(56, 189, 248, 0.14)')}>rollout {analysisMetadata.rollout_policy}</span>
                                                    )}
                                                    <span style={chipStyle(analysisMetadata.semantic_official_enabled ? '#22c55e' : '#64748b', analysisMetadata.semantic_official_enabled ? 'rgba(34, 197, 94, 0.14)' : 'rgba(100, 116, 139, 0.14)')}>
                                                        {analysisMetadata.qualitative_engine_mode || 'proxy_only'}
                                                    </span>
                                                    {analysisMetadata.shadow_mode_enabled && (
                                                        <span style={chipStyle('#14b8a6', 'rgba(20, 184, 166, 0.14)')}>
                                                            shadow control
                                                        </span>
                                                    )}
                                                    {analysisMetadata.forecast_signal_type && (
                                                        <span style={chipStyle(signalTone(analysisMetadata.forecast_signal_type).accent, signalTone(analysisMetadata.forecast_signal_type).soft)}>
                                                            {forecastSignalLabel(analysisMetadata.forecast_signal_type)}
                                                        </span>
                                                    )}
                                                    {analysisMetadata.reconstructed && (
                                                        <span style={chipStyle('#f59e0b', 'rgba(245, 158, 11, 0.14)')}>reconstructed history</span>
                                                    )}
                                                </div>
                                                <div style={{ display: 'grid', gap: '0.45rem', marginTop: '0.75rem', fontSize: '0.76rem', color: 'var(--text-muted)' }}>
                                                    <div>Contract: {analysisMetadata.contract_version || 'n/a'}</div>
                                                    <div>Formula bundle: {analysisMetadata.formula_bundle_version || 'n/a'}</div>
                                                    <div>Model bundle: {analysisMetadata.model_bundle_version || 'n/a'}</div>
                                                    <div>Prompt bundle: {analysisMetadata.prompt_bundle_version || 'n/a'}</div>
                                                    <div>Qualitative engine: {analysisMetadata.qualitative_engine_kind || 'n/a'}</div>
                                                    <div>Semantic bundle: {analysisMetadata.semantic_bundle_version || 'n/a'}</div>
                                                    <div>Semantic KPI: {analysisMetadata.semantic_kpis.join(', ') || 'n/a'}</div>
                                                    <div>Semantic fallback KPI: {analysisMetadata.semantic_fallback_kpis.join(', ') || 'n/a'}</div>
                                                    <div>Forecast engine: {analysisMetadata.forecast_engine_active || 'n/a'}</div>
                                                    <div>Fallback: {analysisMetadata.forecast_fallback_reason || 'n/a'}</div>
                                                    <div>Markov samples: {analysisMetadata.markov_transition_samples ?? 'n/a'}</div>
                                                    <div>Scored KPI: {analysisMetadata.scored_kpis.join(', ') || 'n/a'}</div>
                                                </div>
                                            </>
                                        )}
                                        <div style={{ display: 'grid', gap: '0.55rem', marginTop: '0.75rem' }}>
                                            {(diagnostics?.findings || snapshot.notes).slice(0, 8).map((item) => (
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
                                        {forecast?.summary && (
                                            <p style={{ marginTop: 0, marginBottom: '0.65rem', fontSize: '0.84rem', color: 'var(--text-secondary)' }}>
                                                {forecast.summary}
                                            </p>
                                        )}
                                        <div style={{ display: 'flex', gap: '0.55rem', flexWrap: 'wrap', marginBottom: '0.85rem' }}>
                                            <span style={chipStyle('#38bdf8', 'rgba(56, 189, 248, 0.14)')}>
                                                Overall confidence: {formatProbability(forecast?.overall_confidence)}
                                            </span>
                                            {forecastMetadata?.forecast_signal_type && (
                                                <span style={chipStyle(signalTone(forecastMetadata.forecast_signal_type).accent, signalTone(forecastMetadata.forecast_signal_type).soft)}>
                                                    {forecastSignalLabel(forecastMetadata.forecast_signal_type)}
                                                </span>
                                            )}
                                            {forecastMetadata?.forecast_engine_active && (
                                                <span style={chipStyle('#22c55e', 'rgba(34, 197, 94, 0.14)')}>
                                                    {forecastMetadata.forecast_engine_active}
                                                </span>
                                            )}
                                            {forecastMetadata?.forecast_fallback_reason && (
                                                <span style={chipStyle('#f59e0b', 'rgba(245, 158, 11, 0.14)')}>
                                                    fallback {forecastMetadata.forecast_fallback_reason}
                                                </span>
                                            )}
                                            {forecastMetadata?.markov_transition_samples ? (
                                                <span style={chipStyle('#38bdf8', 'rgba(56, 189, 248, 0.14)')}>
                                                    samples {forecastMetadata.markov_transition_samples}
                                                </span>
                                            ) : null}
                                            {forecastMetadata?.markov_full_journey_enabled && (
                                                <span style={chipStyle('#22c55e', 'rgba(34, 197, 94, 0.14)')}>
                                                    full journey markov
                                                </span>
                                            )}
                                            {forecastMetadata?.markov_coverage_ratio !== null && forecastMetadata?.markov_coverage_ratio !== undefined ? (
                                                <span style={chipStyle('#14b8a6', 'rgba(20, 184, 166, 0.14)')}>
                                                    coverage {formatProbability(forecastMetadata.markov_coverage_ratio)}
                                                </span>
                                            ) : null}
                                            {forecastMetadata?.markov_backtest_submission_accuracy !== null && forecastMetadata?.markov_backtest_submission_accuracy !== undefined ? (
                                                <span style={chipStyle('#a78bfa', 'rgba(167, 139, 250, 0.14)')}>
                                                    backtest {formatProbability(forecastMetadata.markov_backtest_submission_accuracy)}
                                                </span>
                                            ) : null}
                                            {forecastMetadata?.reconstructed && (
                                                <span style={chipStyle('#f59e0b', 'rgba(245, 158, 11, 0.14)')}>
                                                    Snapshot includes reconstructed history
                                                </span>
                                            )}
                                        </div>
                                        {forecastMetadata?.markov_projected_path?.length ? (
                                            <div style={{ marginBottom: '0.85rem', padding: '0.75rem 0.85rem', borderRadius: '12px', background: 'rgba(15, 23, 42, 0.28)', border: '1px solid var(--border-color)' }}>
                                                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '0.4rem' }}>Projected path</div>
                                                <div style={{ fontSize: '0.84rem', color: '#dbeafe' }}>
                                                    {forecastMetadata.markov_projected_path.map((item) => phaseLabel(item)).join(' -> ')}
                                                </div>
                                                {forecastMetadata.forecast_driver_kpis.length > 0 && (
                                                    <div style={{ marginTop: '0.45rem', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                                                        Drivers: {forecastMetadata.forecast_driver_kpis.join(', ')}
                                                    </div>
                                                )}
                                            </div>
                                        ) : null}
                                        {(forecast?.next_best_actions || []).length > 0 && (
                                            <div style={{ display: 'grid', gap: '0.75rem', marginBottom: '0.9rem' }}>
                                                {forecast?.next_best_actions?.map((action) => {
                                                    const tone = actionPriorityTone(action.priority);
                                                    return (
                                                        <div key={action.code} style={{ padding: '0.8rem', borderRadius: '12px', background: tone.soft, border: `1px solid ${tone.accent}33` }}>
                                                            <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.75rem', alignItems: 'center' }}>
                                                                <div style={{ fontWeight: 600 }}>{action.title}</div>
                                                                <span style={chipStyle(tone.accent, tone.soft)}>{action.priority}</span>
                                                            </div>
                                                            <div style={{ marginTop: '0.45rem', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>{action.rationale}</div>
                                                            {action.expected_impact && (
                                                                <div style={{ marginTop: '0.45rem', fontSize: '0.76rem', color: '#bae6fd' }}>Expected impact: {action.expected_impact}</div>
                                                            )}
                                                            <div style={{ marginTop: '0.45rem', fontSize: '0.74rem', color: 'var(--text-muted)' }}>
                                                                Confidence {formatProbability(action.confidence)}
                                                            </div>
                                                            {action.drivers.length > 0 && (
                                                                <div style={{ display: 'grid', gap: '0.3rem', marginTop: '0.5rem' }}>
                                                                    {action.drivers.slice(0, 3).map((driver) => (
                                                                        <div key={`${action.code}-${driver}`} style={{ fontSize: '0.74rem', color: 'var(--text-muted)' }}>- {driver}</div>
                                                                    ))}
                                                                </div>
                                                            )}
                                                        </div>
                                                    );
                                                })}
                                            </div>
                                        )}
                                        {(forecast?.scenarios || []).length === 0 ? (
                                            <p style={{ margin: 0, color: 'var(--text-muted)', fontSize: '0.85rem' }}>Forecast not available.</p>
                                        ) : (
                                            <div style={{ display: 'grid', gap: '0.75rem' }}>
                                                {forecast?.scenarios.map((scenario) => (
                                                    <div key={scenario.name} style={{ padding: '0.8rem', borderRadius: '12px', background: 'rgba(15, 23, 42, 0.35)', border: '1px solid var(--border-color)' }}>
                                                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '0.75rem' }}>
                                                            <span style={{ fontWeight: 600 }}>{scenario.name.replace(/_/g, ' ')}</span>
                                                            <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                                                                <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                                                                    {formatProbability(scenario.probability)}
                                                                </span>
                                                                <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                                                                    Confidence {formatProbability(scenario.confidence)}
                                                                </span>
                                                            </div>
                                                        </div>
                                                        <p style={{ margin: '0.45rem 0 0 0', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                                                            {scenario.description || 'No description available.'}
                                                        </p>
                                                        {scenario.drivers.length > 0 && (
                                                            <div style={{ display: 'grid', gap: '0.35rem', marginTop: '0.65rem' }}>
                                                                {scenario.drivers.slice(0, 4).map((driver) => (
                                                                    <div key={`${scenario.name}-${driver}`} style={{ fontSize: '0.76rem', color: 'var(--text-muted)' }}>
                                                                        - {driver}
                                                                    </div>
                                                                ))}
                                                            </div>
                                                        )}
                                                        {scenario.recommended_action && (
                                                            <div style={{ marginTop: '0.65rem', fontSize: '0.78rem', color: '#bae6fd' }}>
                                                                Recommended action: {scenario.recommended_action}
                                                            </div>
                                                        )}
                                                    </div>
                                                ))}
                                            </div>
                                        )}
                                    </div>
                                </div>
                            </div>

                            <LifecycleControlPanel
                                tender={selectedTender}
                                tenderDetail={tenderDetail}
                                analyticalPhase={snapshot?.analytical_phase || null}
                                onDataChanged={() => {
                                    void loadPortfolio(true);
                                }}
                            />

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
