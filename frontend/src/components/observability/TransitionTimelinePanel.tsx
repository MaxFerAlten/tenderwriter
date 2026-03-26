import { Activity, FileSearch, History } from 'lucide-react';

import type { KpiRequirementTransitionItem, KpiSnapshotHistoryItem, KpiTransitions } from '../../api/client';
import { chipStyle, formatDateTime, phaseLabel, signalTone } from '../../features/observability/shared';

interface TransitionTimelinePanelProps {
    transitions: KpiTransitions | null;
}

function phaseTone(phase: string | null): { accent: string; soft: string } {
    switch (phase) {
        case 'S5':
            return { accent: '#38bdf8', soft: 'rgba(56, 189, 248, 0.14)' };
        case 'S6':
            return { accent: '#f97316', soft: 'rgba(249, 115, 22, 0.14)' };
        case 'S8':
            return { accent: '#ef4444', soft: 'rgba(239, 68, 68, 0.14)' };
        case 'S9':
        case 'S11':
            return { accent: '#10b981', soft: 'rgba(16, 185, 129, 0.12)' };
        case 'S12':
        case 'S13':
            return { accent: '#dc2626', soft: 'rgba(220, 38, 38, 0.12)' };
        default:
            return { accent: '#64748b', soft: 'rgba(100, 116, 139, 0.14)' };
    }
}

function sourceTone(sourceType: string | null | undefined): { accent: string; soft: string } {
    return signalTone(sourceType);
}

function historyLabel(item: KpiSnapshotHistoryItem): string {
    if (item.reconstructed) {
        return 'reconstructed';
    }
    if (item.source_job_type) {
        return item.source_job_type.replace(/_/g, ' ');
    }
    return 'live snapshot';
}

export default function TransitionTimelinePanel({ transitions }: TransitionTimelinePanelProps) {
    if (!transitions) {
        return null;
    }

    return (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1rem' }}>
            <div className="card">
                <h3 style={{ marginTop: 0, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <Activity size={18} color="#38bdf8" /> Phase drivers
                </h3>
                <p style={{ marginTop: 0, fontSize: '0.84rem', color: 'var(--text-secondary)' }}>{transitions.summary}</p>
                {transitions.items.length === 0 ? (
                    <p style={{ margin: 0, color: 'var(--text-muted)', fontSize: '0.84rem' }}>No explicit phase-driver transitions are mirrored yet.</p>
                ) : (
                    <div style={{ display: 'grid', gap: '0.75rem' }}>
                        {transitions.items.map((item, index) => {
                            const toTone = phaseTone(item.to_state);
                            const provenanceTone = sourceTone(item.source_type);
                            return (
                                <div key={`${item.source_event_type || 'transition'}-${index}`} style={{ padding: '0.85rem', borderRadius: '12px', background: 'rgba(15, 23, 42, 0.35)', border: '1px solid var(--border-color)' }}>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '0.75rem' }}>
                                        <div>
                                            <div style={{ fontWeight: 600 }}>{phaseLabel(item.from_state)} {' -> '} {phaseLabel(item.to_state)}</div>
                                            <div style={{ marginTop: '0.3rem', fontSize: '0.78rem', color: 'var(--text-muted)' }}>{formatDateTime(item.occurred_at)}</div>
                                        </div>
                                        <div style={{ display: 'flex', gap: '0.45rem', flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                                            <span style={chipStyle(provenanceTone.accent, provenanceTone.soft)}>{item.source_type || 'unknown'}</span>
                                            <span style={chipStyle(toTone.accent, toTone.soft)}>{item.to_state}</span>
                                        </div>
                                    </div>
                                    <div style={{ marginTop: '0.65rem', fontSize: '0.83rem', color: 'var(--text-secondary)' }}>{item.cause || 'No cause recorded.'}</div>
                                    <div style={{ marginTop: '0.55rem', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                                        Event: {item.source_event_type || 'n/a'} | Confidence: {item.confidence ?? '--'}
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                )}
            </div>

            <div className="card">
                <h3 style={{ marginTop: 0, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <History size={18} color="#38bdf8" /> Persisted history
                </h3>
                {transitions.history_items.length === 0 ? (
                    <p style={{ margin: 0, color: 'var(--text-muted)', fontSize: '0.84rem' }}>No persisted analytical history is available yet.</p>
                ) : (
                    <div style={{ display: 'grid', gap: '0.75rem' }}>
                        {transitions.history_items.map((item: KpiSnapshotHistoryItem) => {
                            const tone = phaseTone(item.analytical_phase);
                            const provenanceTone = sourceTone(item.source_type);
                            return (
                                <div key={item.snapshot_id} style={{ padding: '0.85rem', borderRadius: '12px', background: 'rgba(15, 23, 42, 0.35)', border: '1px solid var(--border-color)' }}>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.75rem', alignItems: 'flex-start' }}>
                                        <div>
                                            <div style={{ fontWeight: 600 }}>{phaseLabel(item.analytical_phase)}</div>
                                            <div style={{ marginTop: '0.3rem', fontSize: '0.78rem', color: 'var(--text-muted)' }}>{formatDateTime(item.generated_at)}</div>
                                        </div>
                                        <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                                            <span style={chipStyle(tone.accent, tone.soft)}>{item.health}</span>
                                            <span style={chipStyle(provenanceTone.accent, provenanceTone.soft)}>{item.source_type || 'unknown'}</span>
                                            <span style={chipStyle(item.reconstructed ? '#f59e0b' : '#64748b', item.reconstructed ? 'rgba(245, 158, 11, 0.14)' : 'rgba(100, 116, 139, 0.14)')}>
                                                {historyLabel(item)}
                                            </span>
                                        </div>
                                    </div>
                                    <div style={{ marginTop: '0.65rem', fontSize: '0.83rem', color: 'var(--text-secondary)' }}>{item.summary || 'No summary recorded.'}</div>
                                    <div style={{ marginTop: '0.55rem', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                                        Replay until: {formatDateTime(item.replay_until)} | Source event: {item.replay_source_event_type || 'n/a'}
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                )}
            </div>

            <div className="card">
                <h3 style={{ marginTop: 0, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <FileSearch size={18} color="#38bdf8" /> Requirement transition focus
                </h3>
                {transitions.requirement_items.length === 0 ? (
                    <p style={{ margin: 0, color: 'var(--text-muted)', fontSize: '0.84rem' }}>No requirement transition drivers are mirrored yet.</p>
                ) : (
                    <div style={{ display: 'grid', gap: '0.75rem' }}>
                        {transitions.requirement_items.slice(0, 6).map((item: KpiRequirementTransitionItem) => {
                            const tone = phaseTone(item.driver_phase);
                            return (
                                <div key={item.external_requirement_id} style={{ padding: '0.85rem', borderRadius: '12px', background: 'rgba(15, 23, 42, 0.35)', border: '1px solid var(--border-color)' }}>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.75rem', alignItems: 'flex-start' }}>
                                        <div>
                                            <div style={{ fontWeight: 600 }}>{item.summary || item.external_requirement_id}</div>
                                            <div style={{ marginTop: '0.3rem', fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                                                {item.mapped_section_title ? `Section: ${item.mapped_section_title}` : 'Section not mapped yet'}
                                            </div>
                                        </div>
                                        <span style={chipStyle(tone.accent, tone.soft)}>{item.driver_phase || 'n/a'}</span>
                                    </div>
                                    <div style={{ display: 'flex', gap: '0.45rem', flexWrap: 'wrap', marginTop: '0.55rem' }}>
                                        {item.priority && <span style={chipStyle('#c084fc', 'rgba(192, 132, 252, 0.12)')}>{item.priority}</span>}
                                        {item.compliance_status && <span style={chipStyle('#64748b', 'rgba(100, 116, 139, 0.14)')}>{item.compliance_status.replace(/_/g, ' ')}</span>}
                                        {item.section_status && <span style={chipStyle('#38bdf8', 'rgba(56, 189, 248, 0.14)')}>{item.section_status.replace(/_/g, ' ')}</span>}
                                    </div>
                                    <div style={{ marginTop: '0.65rem', fontSize: '0.83rem', color: 'var(--text-secondary)' }}>{item.driver}</div>
                                    <div style={{ marginTop: '0.5rem', fontSize: '0.75rem', color: 'var(--text-muted)' }}>Last driver event: {item.last_event_type || 'n/a'}</div>
                                </div>
                            );
                        })}
                    </div>
                )}
            </div>
        </div>
    );
}
