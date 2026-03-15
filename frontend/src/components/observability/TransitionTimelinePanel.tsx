import { Activity, FileSearch } from 'lucide-react';

import type { KpiRequirementTransitionItem, KpiTransitions } from '../../api/client';

interface TransitionTimelinePanelProps {
    transitions: KpiTransitions | null;
}

function phaseLabel(phase: string | null): string {
    const labels: Record<string, string> = {
        S5: 'Quality / Technical Review',
        S6: 'Rework / Clarifications',
        S8: 'Compliance Gate',
        S9: 'Submission',
    };
    if (!phase) return 'Unknown phase';
    return labels[phase] || phase;
}

function formatDateTime(value: string | null): string {
    if (!value) return 'n/a';
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return value;
    return parsed.toLocaleString('it-IT');
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
            return { accent: '#10b981', soft: 'rgba(16, 185, 129, 0.12)' };
        default:
            return { accent: '#64748b', soft: 'rgba(100, 116, 139, 0.14)' };
    }
}

function badgeStyle(accent: string, soft: string) {
    return {
        padding: '0.22rem 0.6rem',
        borderRadius: '999px',
        fontSize: '0.72rem',
        border: `1px solid ${accent}33`,
        background: soft,
        color: accent,
        textTransform: 'capitalize' as const,
    };
}

export default function TransitionTimelinePanel({ transitions }: TransitionTimelinePanelProps) {
    if (!transitions) {
        return null;
    }

    return (
        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) minmax(320px, 0.9fr)', gap: '1rem' }}>
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
                            return (
                                <div key={`${item.source_event_type || 'transition'}-${index}`} style={{ padding: '0.85rem', borderRadius: '12px', background: 'rgba(15, 23, 42, 0.35)', border: '1px solid var(--border-color)' }}>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '0.75rem' }}>
                                        <div>
                                            <div style={{ fontWeight: 600 }}>{phaseLabel(item.from_state)} {' -> '} {phaseLabel(item.to_state)}</div>
                                            <div style={{ marginTop: '0.3rem', fontSize: '0.78rem', color: 'var(--text-muted)' }}>{formatDateTime(item.occurred_at)}</div>
                                        </div>
                                        <span style={badgeStyle(toTone.accent, toTone.soft)}>{item.to_state}</span>
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
                                        <span style={badgeStyle(tone.accent, tone.soft)}>{item.driver_phase || 'n/a'}</span>
                                    </div>
                                    <div style={{ display: 'flex', gap: '0.45rem', flexWrap: 'wrap', marginTop: '0.55rem' }}>
                                        {item.priority && <span style={badgeStyle('#c084fc', 'rgba(192, 132, 252, 0.12)')}>{item.priority}</span>}
                                        {item.compliance_status && <span style={badgeStyle('#64748b', 'rgba(100, 116, 139, 0.14)')}>{item.compliance_status.replace(/_/g, ' ')}</span>}
                                        {item.section_status && <span style={badgeStyle('#38bdf8', 'rgba(56, 189, 248, 0.14)')}>{item.section_status.replace(/_/g, ' ')}</span>}
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
