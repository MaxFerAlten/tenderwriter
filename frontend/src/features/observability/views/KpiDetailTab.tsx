import { Gauge } from 'lucide-react';
import type { KpiTenderSnapshot, KpiAnalysisJob, Tender } from '../../../api/client';
import {
    formatConfidenceValue,
    formatScoreValue,
    healthColor,
    selectOperationalKpis,
    selectQualitativeKpis,
} from '../shared';

interface KpiDetailTabProps {
    snapshot: KpiTenderSnapshot | null;
    analysisJob: KpiAnalysisJob | null;
    tender: Tender | null;
    selectedHealth: string;
}

export default function KpiDetailTab({ snapshot, analysisJob: _analysisJob, tender: _tender, selectedHealth: _selectedHealth }: KpiDetailTabProps) {
    const qualitativeKpis = selectQualitativeKpis(snapshot);
    const operationalKpis = selectOperationalKpis(snapshot);

    return (
        <div>
            <div style={{ marginBottom: '1.5rem' }}>
                <h3 style={{ margin: '0 0 1rem 0', fontSize: '0.95rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <Gauge size={16} color="#38bdf8" /> Qualitative KPIs
                </h3>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1rem' }}>
                    {qualitativeKpis.map((kpi) => {
                        const kpiPalette = healthColor(kpi.health || 'unknown');
                        return (
                            <div
                                key={kpi.kpi_code}
                                className="card"
                                style={{ borderColor: `${kpiPalette}33` }}
                            >
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.75rem' }}>
                                    <div>
                                        <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>{kpi.kpi_code}</div>
                                        <div style={{ fontSize: '2rem', fontWeight: 700, color: kpiPalette }}>
                                            {formatScoreValue(kpi.value)}
                                        </div>
                                    </div>
                                    <div style={{ textAlign: 'right' }}>
                                        <span
                                            style={{
                                                padding: '0.2rem 0.55rem',
                                                borderRadius: '999px',
                                                fontSize: '0.72rem',
                                                textTransform: 'capitalize',
                                                background: `${kpiPalette}15`,
                                                color: kpiPalette,
                                            }}
                                        >
                                            {kpi.health || 'unknown'}
                                        </span>
                                        <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: '0.25rem', textTransform: 'capitalize' }}>
                                            Severity: {kpi.severity}
                                        </div>
                                    </div>
                                </div>
                                <div style={{ display: 'flex', gap: '0.45rem', flexWrap: 'wrap', marginBottom: '0.75rem' }}>
                                    <span
                                        style={{
                                            padding: '0.2rem 0.5rem',
                                            borderRadius: '999px',
                                            fontSize: '0.7rem',
                                            background: 'rgba(56, 189, 248, 0.12)',
                                            color: '#38bdf8',
                                        }}
                                    >
                                        {kpi.source_type || 'unknown'}
                                    </span>
                                    {kpi.semantic && (
                                        <span
                                            style={{
                                                padding: '0.2rem 0.5rem',
                                                borderRadius: '999px',
                                                fontSize: '0.7rem',
                                                background: 'rgba(34, 197, 94, 0.12)',
                                                color: '#22c55e',
                                            }}
                                        >
                                            semantic {kpi.semantic.status}
                                        </span>
                                    )}
                                </div>
                                <p style={{ margin: 0, fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
                                    {kpi.label || 'No label available.'}
                                </p>
                                {kpi.recommendations.length > 0 && (
                                    <p style={{ margin: '0.6rem 0 0 0', fontSize: '0.78rem', color: '#dbeafe' }}>
                                        Recommendation: {kpi.recommendations[0]}
                                    </p>
                                )}
                                <p style={{ margin: '0.6rem 0 0 0', fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                                    Confidence: {formatConfidenceValue(kpi.confidence)} | Formula: {kpi.formula_version || 'n/a'}
                                </p>
                            </div>
                        );
                    })}
                </div>
            </div>

            <div>
                <h3 style={{ margin: '0 0 1rem 0', fontSize: '0.95rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <Gauge size={16} color="#38bdf8" /> Operational Scorecards
                </h3>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '0.85rem' }}>
                    {operationalKpis.map((kpi) => {
                        const kpiPalette = healthColor(kpi.health || 'unknown');
                        return (
                            <div
                                key={kpi.kpi_code}
                                style={{
                                    padding: '0.85rem',
                                    borderRadius: '12px',
                                    border: `1px solid ${kpiPalette}22`,
                                    background: 'rgba(15, 23, 42, 0.3)',
                                }}
                            >
                                <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.5rem', alignItems: 'center' }}>
                                    <span style={{ fontWeight: 600 }}>{kpi.kpi_code}</span>
                                    <span style={{ fontSize: '0.78rem', color: kpiPalette, textTransform: 'capitalize' }}>
                                        {kpi.health}
                                    </span>
                                </div>
                                <div style={{ fontSize: '1.4rem', fontWeight: 700, marginTop: '0.45rem' }}>
                                    {formatScoreValue(kpi.value)}
                                </div>
                                <div style={{ marginTop: '0.35rem', fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                                    {kpi.recommendation || kpi.label || 'No recommendation available.'}
                                </div>
                            </div>
                        );
                    })}
                </div>
            </div>
        </div>
    );
}
