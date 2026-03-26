import { lazy, Suspense } from 'react';
import { motion } from 'framer-motion';
import {
    Gauge,
} from 'lucide-react';
import type {
    KpiTenderSnapshot,
    KpiForecast,
    KpiDiagnostics,
    KpiAnalysisJob,
    KpiTransitions,
    Tender,
    OperationalWorkspace,
    TenderDetail,
    KpiBottleneckItem,
    KpiPortfolioOverview,
} from '../../../api/client';
import { Link } from 'react-router-dom';
import {
    analysisJobColors,
    analysisJobLabel,
    chipStyle,
    formatGeneratedAt,
    formatScoreValue,
    healthColors,
    phaseLabel,
    semanticStatusLabel,
    semanticStatusTone,
    selectOperationalKpis,
    selectQualitativeKpis,
    signalTone,
} from '../shared';

const ComplianceDrilldownPanel = lazy(() => import('../../../components/observability/ComplianceDrilldownPanel'));
const LifecycleControlPanel = lazy(() => import('../../../components/observability/LifecycleControlPanel'));
const TransitionTimelinePanel = lazy(() => import('../../../components/observability/TransitionTimelinePanel'));

interface AmministrativaViewProps {
    snapshot: KpiTenderSnapshot | null;
    forecast: KpiForecast | null;
    diagnostics: KpiDiagnostics | null;
    transitions: KpiTransitions | null;
    analysisJob: KpiAnalysisJob | null;
    tender: Tender | null;
    tenderDetail: TenderDetail | null;
    workspace: OperationalWorkspace | null;
    selectedHealth: string;
    bottlenecks: KpiBottleneckItem[];
    overview: KpiPortfolioOverview | null;
    onRefresh: () => void;
    onRecompute: () => void;
}

export default function AmministrativaView({
    snapshot,
    forecast: _forecast,
    diagnostics: _diagnostics,
    transitions,
    analysisJob,
    tender,
    tenderDetail,
    workspace,
    selectedHealth,
    bottlenecks: _bottlenecks,
    overview: _overview,
    onRefresh,
    onRecompute: _onRecompute,
}: AmministrativaViewProps) {
    const palette = healthColors(selectedHealth);
    const analysisJobPalette = analysisJobColors(analysisJob?.job_status);
    const qualitativeKpis = selectQualitativeKpis(snapshot);
    const operationalKpis = selectOperationalKpis(snapshot);

    return (
        <div>
            <div
                className="card"
                style={{
                    background: `linear-gradient(135deg, ${palette.soft} 0%, rgba(15, 23, 42, 0.85) 100%)`,
                    border: `1px solid ${palette.accent}33`,
                }}
            >
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: '1rem', alignItems: 'flex-start' }}>
                    <div>
                        <div style={{ fontSize: '0.78rem', textTransform: 'uppercase', letterSpacing: '0.08em', color: palette.text }}>
                            Selected tender
                        </div>
                        <h2 style={{ margin: '0.4rem 0 0 0' }}>{tender?.title || 'Select a tender'}</h2>
                        <p style={{ margin: '0.45rem 0 0 0', color: 'var(--text-secondary)' }}>
                            {tender?.client || 'Client not available'}
                        </p>
                    </div>
                    <span
                        style={{
                            padding: '0.35rem 0.75rem',
                            borderRadius: '999px',
                            background: palette.soft,
                            color: palette.text,
                            border: `1px solid ${palette.accent}40`,
                            textTransform: 'capitalize',
                            fontSize: '0.8rem',
                        }}
                    >
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
                        <div style={{ fontWeight: 600 }}>{tender?.status.replace('_', ' ') || 'n/a'}</div>
                    </div>
                    <div>
                        <div style={{ fontSize: '0.76rem', color: 'var(--text-muted)', marginBottom: '0.2rem' }}>Generated at</div>
                        <div style={{ fontWeight: 600 }}>{formatGeneratedAt(snapshot?.generated_at || null)}</div>
                    </div>
                    <div>
                        <div style={{ fontSize: '0.76rem', color: 'var(--text-muted)', marginBottom: '0.2rem' }}>Analysis job</div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
                            <span
                                style={{
                                    padding: '0.25rem 0.6rem',
                                    borderRadius: '999px',
                                    background: analysisJobPalette.soft,
                                    color: analysisJobPalette.accent,
                                    border: `1px solid ${analysisJobPalette.accent}33`,
                                    fontSize: '0.76rem',
                                }}
                            >
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
                {analysisJob?.error_message && (
                    <p style={{ margin: '0.85rem 0 0 0', color: '#fecaca', fontSize: '0.82rem' }}>
                        {analysisJob.error_message}
                    </p>
                )}
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1rem', marginBottom: '1.5rem' }}>
                {qualitativeKpis.map((kpi) => {
                    const kpiPalette = healthColors(kpi.health);
                    const provenanceTone = signalTone(kpi.source_type || kpi.provenance);
                    const shadowTone = signalTone('shadow');
                    const semanticTone = kpi.semantic ? semanticStatusTone(kpi.semantic.status) : null;
                    return (
                        <motion.div
                            key={kpi.kpi_code}
                            className="card"
                            initial={{ opacity: 0, y: 8 }}
                            animate={{ opacity: 1, y: 0 }}
                            style={{ borderColor: `${kpiPalette.accent}33` }}
                        >
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '0.75rem' }}>
                                <div>
                                    <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>{kpi.kpi_code}</div>
                                    <div style={{ fontSize: '2rem', fontWeight: 700, marginTop: '0.25rem' }}>
                                        {formatScoreValue(kpi)}
                                    </div>
                                </div>
                                <div style={{ display: 'grid', gap: '0.35rem', justifyItems: 'end' }}>
                                    <div
                                        style={{
                                            padding: '0.3rem 0.65rem',
                                            borderRadius: '999px',
                                            background: kpiPalette.soft,
                                            color: kpiPalette.accent,
                                            textTransform: 'capitalize',
                                            fontSize: '0.75rem',
                                        }}
                                    >
                                        {kpi.health}
                                    </div>
                                    <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'capitalize' }}>
                                        Severity: {kpi.severity}
                                    </div>
                                </div>
                            </div>
                            <div style={{ display: 'flex', gap: '0.45rem', flexWrap: 'wrap', marginTop: '0.7rem' }}>
                                <span style={chipStyle(provenanceTone.accent, provenanceTone.soft)}>
                                    {kpi.source_type || kpi.provenance || 'unknown'}
                                </span>
                                {kpi.semantic && semanticTone && (
                                    <span style={chipStyle(semanticTone.accent, semanticTone.soft)}>
                                        {semanticStatusLabel(kpi.semantic.status)}
                                    </span>
                                )}
                                {kpi.shadow && <span style={chipStyle(shadowTone.accent, shadowTone.soft)}>shadow</span>}
                            </div>
                            <p style={{ margin: '0.75rem 0 0 0', fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
                                {kpi.label || 'No label available.'}
                            </p>
                            {kpi.recommendations.length > 0 && (
                                <p style={{ margin: '0.6rem 0 0 0', fontSize: '0.78rem', color: '#dbeafe' }}>
                                    Recommendation: {kpi.recommendations[0]}
                                </p>
                            )}
                            <p style={{ margin: '0.6rem 0 0 0', fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                                Confidence: {kpi.confidence?.toFixed(2) || '--'} | Formula: {kpi.formula_version || 'n/a'}
                            </p>
                            {kpi.semantic && semanticTone && (
                                <div
                                    style={{
                                        marginTop: '0.75rem',
                                        padding: '0.7rem 0.8rem',
                                        borderRadius: '12px',
                                        background: semanticTone.soft,
                                        border: `1px solid ${semanticTone.accent}33`,
                                    }}
                                >
                                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.5rem', alignItems: 'center' }}>
                                        <span style={{ fontWeight: 600, fontSize: '0.8rem', color: semanticTone.accent }}>
                                            {semanticStatusLabel(kpi.semantic.status)}
                                        </span>
                                        <span style={{ fontSize: '0.72rem', color: semanticTone.accent, textTransform: 'capitalize' }}>
                                            {kpi.semantic.health}
                                        </span>
                                    </div>
                                    <div style={{ marginTop: '0.45rem', fontSize: '0.76rem', color: 'var(--text-secondary)' }}>
                                        Semantic score {kpi.semantic.semantic_score ?? '--'} | Proxy {kpi.semantic.proxy_score ?? '--'}
                                    </div>
                                </div>
                            )}
                        </motion.div>
                    );
                })}
            </div>

            <div className="card">
                <h3 style={{ marginTop: 0, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <Gauge size={18} color="#38bdf8" /> Operational scorecards
                </h3>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '0.85rem' }}>
                    {operationalKpis.map((kpi) => {
                        const kpiPalette = healthColors(kpi.health);
                        return (
                            <div
                                key={kpi.kpi_code}
                                style={{
                                    padding: '0.85rem',
                                    borderRadius: '12px',
                                    border: `1px solid ${kpiPalette.accent}22`,
                                    background: 'rgba(15, 23, 42, 0.3)',
                                }}
                            >
                                <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.5rem', alignItems: 'center' }}>
                                    <span style={{ fontWeight: 600 }}>{kpi.kpi_code}</span>
                                    <span style={{ fontSize: '0.78rem', color: kpiPalette.accent, textTransform: 'capitalize' }}>
                                        {kpi.health}
                                    </span>
                                </div>
                                <div style={{ fontSize: '1.4rem', fontWeight: 700, marginTop: '0.45rem' }}>
                                    {formatScoreValue(kpi)}
                                </div>
                                <div style={{ marginTop: '0.35rem', fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                                    {kpi.recommendation || kpi.label || 'No recommendation available.'}
                                </div>
                            </div>
                        );
                    })}
                </div>
            </div>

            <Suspense fallback={<div className="card"><p style={{ margin: 0, color: 'var(--text-muted)' }}>Loading lifecycle control...</p></div>}>
                <LifecycleControlPanel
                    tender={tender}
                    tenderDetail={tenderDetail}
                    analyticalPhase={snapshot?.analytical_phase || null}
                    onDataChanged={onRefresh}
                />
            </Suspense>

            <Suspense fallback={<div className="card"><p style={{ margin: 0, color: 'var(--text-muted)' }}>Loading compliance drilldown...</p></div>}>
                <ComplianceDrilldownPanel
                    tenderDetail={tenderDetail}
                    workspace={workspace}
                    analyticalPhase={snapshot?.analytical_phase || null}
                />
            </Suspense>

            <Suspense fallback={<div className="card"><p style={{ margin: 0, color: 'var(--text-muted)' }}>Loading transition timeline...</p></div>}>
                <TransitionTimelinePanel transitions={transitions} />
            </Suspense>

            {tender ? (
                <div className="card" style={{ borderColor: 'rgba(56, 189, 248, 0.28)' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
                        <div>
                            <h3 style={{ margin: 0, fontSize: '1.05rem' }}>Operational Workspace</h3>
                            <p style={{ margin: '0.35rem 0 0 0', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                                Manage contributions, requests, open rework, gates and calls in a dedicated page.
                            </p>
                        </div>
                        <Link
                            to={`/observability-kpi/${tender.id}/operational-workspace`}
                            className="btn btn-primary"
                            style={{ whiteSpace: 'nowrap' }}
                        >
                            Apri Operational Workspace
                        </Link>
                    </div>
                </div>
            ) : null}
        </div>
    );
}
