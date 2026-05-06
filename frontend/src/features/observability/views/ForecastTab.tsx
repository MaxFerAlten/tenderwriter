import { TrendingUp, Users } from 'lucide-react';
import type {
    KpiForecast,
    KpiDiagnostics,
    KpiAnalysisJob,
    RehearsalHealthProjection,
    RehearsalSummary,
    Tender,
} from '../../../api/client';
import {
    chipStyle,
    forecastSignalLabel,
    formatProbability,
    phaseLabel,
    signalTone,
} from '../shared';

interface ForecastTabProps {
    forecast: KpiForecast | null;
    diagnostics: KpiDiagnostics | null;
    analysisJob: KpiAnalysisJob | null;
    tender: Tender | null;
}

const HEALTH_TONE: Record<RehearsalHealthProjection, { accent: string; soft: string; label: string }> = {
    green: { accent: '#22c55e', soft: 'rgba(34, 197, 94, 0.12)', label: 'Green' },
    amber: { accent: '#f59e0b', soft: 'rgba(245, 158, 11, 0.12)', label: 'Amber' },
    red: { accent: '#ef4444', soft: 'rgba(239, 68, 68, 0.12)', label: 'Red' },
};

function formatRehearsalDate(iso: string | null): string {
    if (!iso) return '—';
    try {
        const d = new Date(iso);
        if (Number.isNaN(d.getTime())) return iso;
        return d.toLocaleString();
    } catch {
        return iso;
    }
}

function formatScore(score: number | null): string {
    return score === null || score === undefined ? '—' : score.toFixed(1);
}

function formatDivergence(value: number | null): string {
    return value === null || value === undefined ? '—' : value.toFixed(2);
}

function RehearsalSummaryCard({ summary }: { summary: RehearsalSummary }) {
    const health = summary.health_projection ? HEALTH_TONE[summary.health_projection] : null;
    const hasRun = summary.run_id !== null && summary.run_id !== undefined;

    return (
        <div className="card" data-testid="rehearsal-summary-card">
            <h3 style={{ margin: '0 0 1rem 0', fontSize: '0.95rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <Users size={16} color="#a78bfa" /> Rehearsal Summary
            </h3>
            {!hasRun ? (
                <p style={{ margin: 0, fontSize: '0.85rem', color: 'var(--text-muted)' }} data-testid="rehearsal-summary-empty">
                    No rehearsal has completed yet for this tender.
                </p>
            ) : (
                <>
                    <div style={{ display: 'flex', gap: '0.45rem', flexWrap: 'wrap', marginBottom: '0.85rem' }}>
                        {health && (
                            <span
                                style={chipStyle(health.accent, health.soft)}
                                data-testid="rehearsal-health-chip"
                            >
                                Health: {health.label}
                            </span>
                        )}
                        <span style={chipStyle('#a78bfa', 'rgba(167, 139, 250, 0.12)')}>
                            Score: {formatScore(summary.overall_score)}
                        </span>
                        <span style={chipStyle('#38bdf8', 'rgba(56, 189, 248, 0.12)')}>
                            Divergence: {formatDivergence(summary.persona_divergence)}
                        </span>
                        {summary.blocking_findings > 0 && (
                            <span style={chipStyle('#ef4444', 'rgba(239, 68, 68, 0.12)')}>
                                Blocking: {summary.blocking_findings}
                            </span>
                        )}
                        {summary.high_severity_rework_suggestions > 0 && (
                            <span style={chipStyle('#f59e0b', 'rgba(245, 158, 11, 0.12)')}>
                                High-severity rework: {summary.high_severity_rework_suggestions}
                            </span>
                        )}
                    </div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                        Last rehearsal: {formatRehearsalDate(summary.last_rehearsal_at)}
                        {summary.run_id !== null && summary.run_id !== undefined && (
                            <span style={{ marginLeft: '0.75rem' }}>Run #{summary.run_id}</span>
                        )}
                    </div>
                </>
            )}
        </div>
    );
}

export default function ForecastTab({ forecast, diagnostics, analysisJob: _analysisJob, tender: _tender }: ForecastTabProps) {
    const analysisMetadata = diagnostics?.analysis_metadata;
    const forecastSignal = forecast?.analysis_metadata?.forecast_signal_type || analysisMetadata?.forecast_signal_type;

    return (
        <div>
            <div className="card">
                <h3 style={{ margin: '0 0 1rem 0', fontSize: '0.95rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <TrendingUp size={16} color="#38bdf8" /> Forecast Summary
                </h3>
                {forecast?.summary ? (
                    <p style={{ margin: '0 0 1rem 0', fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                        {forecast.summary}
                    </p>
                ) : (
                    <p style={{ margin: '0 0 1rem 0', fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                        Forecast not available yet.
                    </p>
                )}

                <div style={{ display: 'flex', gap: '0.45rem', flexWrap: 'wrap', marginBottom: '0.85rem' }}>
                    <span style={chipStyle('#38bdf8', 'rgba(56, 189, 248, 0.12)')}>
                        Overall confidence: {formatProbability(forecast?.overall_confidence)}
                    </span>
                    {forecastSignal && (
                        <span style={chipStyle(signalTone(forecastSignal).accent, signalTone(forecastSignal).soft)}>
                            {forecastSignalLabel(forecastSignal)}
                        </span>
                    )}
                    {analysisMetadata?.forecast_engine_active && (
                        <span
                            style={{
                                padding: '0.25rem 0.6rem',
                                borderRadius: '999px',
                                fontSize: '0.72rem',
                                background: 'rgba(34, 197, 94, 0.12)',
                                color: '#22c55e',
                            }}
                        >
                            {analysisMetadata.forecast_engine_active}
                        </span>
                    )}
                </div>
            </div>

            {analysisMetadata?.markov_projected_path && analysisMetadata.markov_projected_path.length > 0 && (
                <div className="card">
                    <h3 style={{ margin: '0 0 1rem 0', fontSize: '0.95rem' }}>Projected Path</h3>
                    <div
                        style={{
                            padding: '0.75rem 0.85rem',
                            borderRadius: '12px',
                            background: 'rgba(15, 23, 42, 0.28)',
                            border: '1px solid var(--border-default)',
                        }}
                    >
                        <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '0.4rem' }}>
                            Markov Projected Journey
                        </div>
                        <div style={{ fontSize: '0.875rem', color: '#dbeafe' }}>
                            {analysisMetadata.markov_projected_path.map((phase) => phaseLabel(phase)).join(' → ')}
                        </div>
                        {analysisMetadata.forecast_driver_kpis.length > 0 && (
                            <div style={{ marginTop: '0.45rem', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                                Primary drivers: {analysisMetadata.forecast_driver_kpis.join(', ')}
                            </div>
                        )}
                    </div>
                </div>
            )}

            {(forecast?.next_best_actions || []).length > 0 && (
                <div className="card">
                    <h3 style={{ margin: '0 0 1rem 0', fontSize: '0.95rem' }}>Next Best Actions</h3>
                    <div style={{ display: 'grid', gap: '0.75rem' }}>
                        {forecast?.next_best_actions?.map((action) => {
                            const priorityColor =
                                action.priority === 'now' ? '#ef4444' : action.priority === 'next' ? '#f59e0b' : '#38bdf8';
                            return (
                                <div
                                    key={action.code}
                                    style={{
                                        padding: '0.8rem',
                                        borderRadius: '12px',
                                        background: `${priorityColor}15`,
                                        border: `1px solid ${priorityColor}33`,
                                    }}
                                >
                                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                        <div style={{ fontWeight: 600 }}>{action.title}</div>
                                        <span
                                            style={{
                                                padding: '0.2rem 0.5rem',
                                                borderRadius: '999px',
                                                fontSize: '0.7rem',
                                                background: `${priorityColor}20`,
                                                color: priorityColor,
                                                textTransform: 'uppercase',
                                            }}
                                        >
                                            {action.priority}
                                        </span>
                                    </div>
                                    <div style={{ marginTop: '0.45rem', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                                        {action.rationale}
                                    </div>
                                    {action.expected_impact && (
                                        <div style={{ marginTop: '0.45rem', fontSize: '0.76rem', color: '#bae6fd' }}>
                                            Expected impact: {action.expected_impact}
                                        </div>
                                    )}
                                    <div style={{ marginTop: '0.45rem', fontSize: '0.74rem', color: 'var(--text-muted)' }}>
                                        Confidence {formatProbability(action.confidence)}
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                </div>
            )}

            {forecast?.rehearsal_summary && (
                <RehearsalSummaryCard summary={forecast.rehearsal_summary} />
            )}

            {(forecast?.scenarios || []).length > 0 && (
                <div className="card">
                    <h3 style={{ margin: '0 0 1rem 0', fontSize: '0.95rem' }}>Scenarios</h3>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: '1rem' }}>
                        {forecast?.scenarios.map((scenario) => (
                            <div
                                key={scenario.name}
                                style={{
                                    padding: '0.8rem',
                                    borderRadius: '12px',
                                    background: 'rgba(15, 23, 42, 0.35)',
                                    border: '1px solid var(--border-default)',
                                }}
                            >
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                                    <span style={{ fontWeight: 600, textTransform: 'capitalize' }}>{scenario.name.replace(/_/g, ' ')}</span>
                                    <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                                        {formatProbability(scenario.probability)}
                                    </span>
                                </div>
                                <p style={{ margin: 0, fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                                    {scenario.description || 'No description available.'}
                                </p>
                                {scenario.recommended_action && (
                                    <div style={{ marginTop: '0.65rem', fontSize: '0.78rem', color: '#bae6fd' }}>
                                        Recommended: {scenario.recommended_action}
                                    </div>
                                )}
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}
