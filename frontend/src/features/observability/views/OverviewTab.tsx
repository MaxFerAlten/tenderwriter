import { FileSearch, Gauge, TrendingUp } from 'lucide-react';
import type {
    KpiTenderSnapshot,
    KpiForecast,
    KpiDiagnostics,
    KpiAnalysisJob,
    Tender,
} from '../../../api/client';
import {
    analysisJobLabel,
    formatScoreValue,
    healthColor,
    healthColors,
    phaseLabel,
    selectOperationalKpis,
    selectQualitativeKpis,
} from '../shared';

interface OverviewTabProps {
    snapshot: KpiTenderSnapshot | null;
    forecast: KpiForecast | null;
    diagnostics: KpiDiagnostics | null;
    analysisJob: KpiAnalysisJob | null;
    tender: Tender | null;
    selectedHealth: string;
}

export default function OverviewTab({
    snapshot,
    forecast,
    diagnostics,
    analysisJob,
    tender,
    selectedHealth,
}: OverviewTabProps) {
    const palette = healthColors(selectedHealth);

    const qualitativeKpis = selectQualitativeKpis(snapshot);
    const operationalKpis = selectOperationalKpis(snapshot);

    const forecastSignal = forecast?.analysis_metadata?.forecast_signal_type || 'not_ready';
    const analysisJobStatus = analysisJobLabel(analysisJob?.job_status);

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
                        <div style={{ fontSize: '0.78rem', textTransform: 'uppercase', letterSpacing: '0.08em', color: palette.accent }}>
                            Selected Tender
                        </div>
                        <h2 style={{ margin: '0.4rem 0 0 0' }}>{tender?.title || 'Select a tender'}</h2>
                        <p style={{ margin: '0.45rem 0 0 0', color: 'var(--text-secondary)', fontSize: '0.875rem' }}>
                            {tender?.client || 'Client not available'}
                        </p>
                    </div>
                    <span
                        style={{
                            padding: '0.35rem 0.75rem',
                            borderRadius: '999px',
                            background: palette.soft,
                            color: palette.accent,
                            border: `1px solid ${palette.accent}40`,
                            textTransform: 'capitalize',
                            fontSize: '0.8rem',
                        }}
                    >
                        {selectedHealth}
                    </span>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '0.9rem', marginTop: '1rem' }}>
                    <div>
                        <div style={{ fontSize: '0.76rem', color: 'var(--text-muted)', marginBottom: '0.2rem' }}>Analytical Phase</div>
                        <div style={{ fontWeight: 600, fontSize: '0.875rem' }}>{phaseLabel(snapshot?.analytical_phase || null)}</div>
                    </div>
                    <div>
                        <div style={{ fontSize: '0.76rem', color: 'var(--text-muted)', marginBottom: '0.2rem' }}>Workflow Status</div>
                        <div style={{ fontWeight: 600, fontSize: '0.875rem' }}>{tender?.status.replace('_', ' ') || 'n/a'}</div>
                    </div>
                    <div>
                        <div style={{ fontSize: '0.76rem', color: 'var(--text-muted)', marginBottom: '0.2rem' }}>Generated</div>
                        <div style={{ fontWeight: 600, fontSize: '0.875rem' }}>
                            {snapshot?.generated_at
                                ? new Date(snapshot.generated_at).toLocaleString('it-IT')
                                : 'Not generated'}
                        </div>
                    </div>
                    <div>
                        <div style={{ fontSize: '0.76rem', color: 'var(--text-muted)', marginBottom: '0.2rem' }}>Job Status</div>
                        <div style={{ fontWeight: 600, fontSize: '0.875rem', color: analysisJobStatus === 'Completed' ? '#10b981' : analysisJobStatus === 'Running' ? '#f59e0b' : 'inherit' }}>
                            {analysisJobStatus}
                        </div>
                    </div>
                </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1rem', marginBottom: '1.5rem' }}>
                <div className="card" style={{ textAlign: 'center' }}>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '0.5rem' }}>
                        Qualitative Score
                    </div>
                    <div style={{ fontSize: '2rem', fontWeight: 700, color: '#10b981' }}>
                        {formatScoreValue(qualitativeKpis[0]?.value)}
                    </div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
                        Overall quality index
                    </div>
                </div>
                <div className="card" style={{ textAlign: 'center' }}>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '0.5rem' }}>
                        Operational Score
                    </div>
                    <div style={{ fontSize: '2rem', fontWeight: 700, color: '#f59e0b' }}>
                        {formatScoreValue(operationalKpis[0]?.value)}
                    </div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
                        Process efficiency
                    </div>
                </div>
                <div className="card" style={{ textAlign: 'center' }}>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '0.5rem' }}>
                        Compliance Status
                    </div>
                    <div style={{ fontSize: '2rem', fontWeight: 700, color: '#38bdf8' }}>
                        {qualitativeKpis.find((k) => k.kpi_code === 'A1')?.value
                            ? `${Math.round(qualitativeKpis.find((k) => k.kpi_code === 'A1')?.value || 0)}`
                            : '--'}
                        /24
                    </div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
                        Documents verified
                    </div>
                </div>
                <div className="card" style={{ textAlign: 'center' }}>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '0.5rem' }}>
                        Forecast Signal
                    </div>
                    <div style={{ fontSize: '1.5rem', fontWeight: 700, color: '#38bdf8', textTransform: 'capitalize' }}>
                        {forecastSignal}
                    </div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
                        Markov-based prediction
                    </div>
                </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '1rem' }}>
                <div>
                    <div style={{ marginBottom: '1rem' }}>
                        <h3 style={{ margin: '0 0 0.75rem 0', fontSize: '0.95rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                            <Gauge size={16} color="#38bdf8" /> Top KPI Cards
                        </h3>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1rem' }}>
                            {qualitativeKpis.slice(0, 3).map((kpi) => {
                                const kpiPalette = healthColor(kpi.health || 'unknown');
                                return (
                                    <div
                                        key={kpi.kpi_code}
                                        className="card"
                                        style={{ borderColor: `${kpiPalette}33`, padding: '0' }}
                                    >
                                        <div
                                            style={{
                                                padding: '0.75rem 1rem',
                                                background: `${kpiPalette}15`,
                                                borderBottom: `1px solid ${kpiPalette}33`,
                                                display: 'flex',
                                                justifyContent: 'space-between',
                                                alignItems: 'center',
                                            }}
                                        >
                                            <span style={{ fontWeight: 700, fontSize: '1rem' }}>{kpi.kpi_code}</span>
                                            <span style={{ fontWeight: 700, fontSize: '1.25rem', color: kpiPalette }}>
                                                {formatScoreValue(kpi.value)}
                                            </span>
                                        </div>
                                        <div style={{ padding: '1rem' }}>
                                            <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '0.5rem' }}>
                                                {kpi.label || kpi.kpi_code}
                                            </div>
                                            <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                                                Confidence: {kpi.confidence?.toFixed(2) || '--'}
                                            </div>
                                            <div style={{ marginTop: '0.5rem' }}>
                                                <span
                                                    style={{
                                                        padding: '0.15rem 0.5rem',
                                                        borderRadius: '999px',
                                                        fontSize: '0.65rem',
                                                        background: `${kpiPalette}20`,
                                                        color: kpiPalette,
                                                    }}
                                                >
                                                    {kpi.source_type || 'unknown'}
                                                </span>
                                            </div>
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    </div>

                    <div>
                        <h3 style={{ margin: '0 0 0.75rem 0', fontSize: '0.95rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                            <TrendingUp size={16} color="#38bdf8" /> Next Best Actions
                        </h3>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1rem' }}>
                            {(forecast?.next_best_actions || []).slice(0, 3).map((action) => {
                                return (
                                    <div
                                        key={action.code}
                                        style={{
                                            background: 'rgba(56, 139, 253, 0.08)',
                                            border: '1px solid rgba(56, 139, 253, 0.2)',
                                            borderRadius: '8px',
                                            padding: '1rem',
                                        }}
                                    >
                                        <div style={{ fontWeight: 600, fontSize: '0.875rem', marginBottom: '0.5rem', color: '#58a6ff' }}>
                                            {action.title}
                                        </div>
                                        <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', lineHeight: 1.4 }}>
                                            {action.rationale}
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    </div>
                </div>

                <div>
                    <div className="card">
                        <h3 style={{ margin: '0 0 1rem 0', fontSize: '0.95rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                            <FileSearch size={16} color="#38bdf8" /> Diagnostics & Drivers
                        </h3>
                        {(diagnostics?.findings || []).slice(0, 3).map((finding, idx) => (
                            <div
                                key={idx}
                                style={{
                                    padding: '0.75rem',
                                    borderBottom: '1px solid var(--border-default)',
                                }}
                            >
                                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.25rem' }}>
                                    <span style={{ fontWeight: 500, fontSize: '0.8rem' }}>Driver {idx + 1}</span>
                                    <span
                                        style={{
                                            fontSize: '0.65rem',
                                            fontWeight: 600,
                                            textTransform: 'uppercase',
                                            color: idx === 0 ? '#ef4444' : idx === 1 ? '#f59e0b' : '#10b981',
                                        }}
                                    >
                                        {idx === 0 ? 'Critical' : idx === 1 ? 'Watch' : 'Stable'}
                                    </span>
                                </div>
                                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{finding}</div>
                            </div>
                        ))}
                        {(!diagnostics?.findings || diagnostics.findings.length === 0) && (
                            <div style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                                No diagnostics available yet.
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}
