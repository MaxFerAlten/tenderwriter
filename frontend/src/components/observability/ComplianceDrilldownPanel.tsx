import { FileSearch, ShieldCheck } from 'lucide-react';

import type { OperationalWorkspace, Requirement, TenderDetail } from '../../api/client';
import {
    buildComplianceGateNarrative,
    findAutoComplianceGate,
    summarizeRequirements,
} from './observabilityUtils';
import RequirementWorkbenchPanel from './RequirementWorkbenchPanel';
import { formatDateTime, healthColors } from '../../features/observability/shared';

interface ComplianceDrilldownPanelProps {
    tenderDetail: TenderDetail | null;
    workspace: OperationalWorkspace | null;
    analyticalPhase: string | null;
}

function requirementStatusTone(status: string): { accent: string; soft: string } {
    switch (status) {
        case 'fully_addressed':
            return { accent: '#10b981', soft: 'rgba(16, 185, 129, 0.12)' };
        case 'partially_addressed':
            return { accent: '#f59e0b', soft: 'rgba(245, 158, 11, 0.14)' };
        default:
            return { accent: '#ef4444', soft: 'rgba(239, 68, 68, 0.14)' };
    }
}

function priorityTone(priority: string): { accent: string; soft: string } {
    switch (priority) {
        case 'high':
            return { accent: '#f97316', soft: 'rgba(249, 115, 22, 0.14)' };
        case 'low':
            return { accent: '#38bdf8', soft: 'rgba(56, 189, 248, 0.14)' };
        default:
            return { accent: '#c084fc', soft: 'rgba(192, 132, 252, 0.12)' };
    }
}

function gateHealth(status: string): string {
    switch (status) {
        case 'passed':
            return 'green';
        case 'open':
            return 'amber';
        case 'failed':
            return 'red';
        default:
            return 'unknown';
    }
}

function priorityRank(priority: string): number {
    switch (priority) {
        case 'high':
            return 0;
        case 'medium':
            return 1;
        case 'low':
            return 2;
        default:
            return 3;
    }
}

function complianceRank(status: string): number {
    switch (status) {
        case 'not_addressed':
            return 0;
        case 'partially_addressed':
            return 1;
        case 'fully_addressed':
            return 2;
        default:
            return 3;
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

function statusLabel(value: string): string {
    return value.replace(/_/g, ' ');
}

export default function ComplianceDrilldownPanel({
    tenderDetail,
    workspace,
    analyticalPhase,
}: ComplianceDrilldownPanelProps) {
    const requirements = [...(tenderDetail?.requirements || [])].sort((left, right) => {
        const complianceDelta = complianceRank(left.compliance_status) - complianceRank(right.compliance_status);
        if (complianceDelta !== 0) {
            return complianceDelta;
        }
        return priorityRank(left.priority) - priorityRank(right.priority);
    });
    const requirementSummary = summarizeRequirements(requirements);
    const autoGate = findAutoComplianceGate(workspace?.gates || []);
    const autoGatePalette = healthColors(gateHealth(autoGate?.status || 'unknown'));
    const autoGateNarrative = buildComplianceGateNarrative(requirementSummary, autoGate, analyticalPhase);

    return (
        <div style={{ display: 'grid', gap: '1rem' }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1.15fr) minmax(320px, 0.85fr)', gap: '1rem' }}>
                <div className="card">
                    <h3 style={{ marginTop: 0, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                        <FileSearch size={18} color="#38bdf8" /> Requirement coverage
                    </h3>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '0.75rem', marginBottom: '1rem' }}>
                        {[
                            ['Fully addressed', requirementSummary.fullyAddressed, '#10b981'],
                            ['Partially addressed', requirementSummary.partiallyAddressed, '#f59e0b'],
                            ['Not addressed', requirementSummary.notAddressed, '#ef4444'],
                            ['Mapped sections', requirementSummary.mapped, '#38bdf8'],
                        ].map(([label, value, accent]) => (
                            <div key={String(label)} style={{ padding: '0.85rem', borderRadius: '12px', border: `1px solid ${accent}33`, background: `${accent}12` }}>
                                <div style={{ fontSize: '0.74rem', color: 'var(--text-muted)', marginBottom: '0.25rem' }}>{label}</div>
                                <div style={{ fontSize: '1.5rem', fontWeight: 700 }}>{value}</div>
                            </div>
                        ))}
                    </div>
                    {requirements.length === 0 ? (
                        <p style={{ margin: 0, color: 'var(--text-muted)', fontSize: '0.85rem' }}>No requirements mirrored yet for this tender.</p>
                    ) : (
                        <div style={{ display: 'grid', gap: '0.75rem' }}>
                            {requirements.map((requirement: Requirement) => {
                                const complianceTone = requirementStatusTone(requirement.compliance_status);
                                const requirementPriorityTone = priorityTone(requirement.priority);
                                return (
                                    <div key={requirement.id} style={{ padding: '0.85rem', borderRadius: '12px', background: 'rgba(15, 23, 42, 0.35)', border: '1px solid var(--border-color)' }}>
                                        <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.75rem', alignItems: 'flex-start' }}>
                                            <div>
                                                <div style={{ fontWeight: 600 }}>{requirement.requirement_text}</div>
                                                <div style={{ display: 'flex', gap: '0.45rem', flexWrap: 'wrap', marginTop: '0.5rem' }}>
                                                    <span style={badgeStyle(requirementPriorityTone.accent, requirementPriorityTone.soft)}>{requirement.priority}</span>
                                                    <span style={badgeStyle(complianceTone.accent, complianceTone.soft)}>{statusLabel(requirement.compliance_status)}</span>
                                                    {requirement.category && (
                                                        <span style={{ ...badgeStyle('#64748b', 'rgba(100, 116, 139, 0.14)'), textTransform: 'none' }}>
                                                            {requirement.category}
                                                        </span>
                                                    )}
                                                </div>
                                            </div>
                                        </div>
                                        <div style={{ marginTop: '0.7rem', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                                            {requirement.mapped_section_id ? (
                                                <>Mapped to section #{requirement.mapped_section_id}{requirement.mapped_section_title ? ` - ${requirement.mapped_section_title}` : ''}</>
                                            ) : (
                                                <span style={{ color: '#fca5a5' }}>Not mapped to a proposal section yet.</span>
                                            )}
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    )}
                </div>

                <div className="card" style={{ borderColor: `${autoGatePalette.accent}33` }}>
                    <h3 style={{ marginTop: 0, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                        <ShieldCheck size={18} color={autoGatePalette.accent} /> Automatic compliance gate
                    </h3>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '0.75rem' }}>
                        <div>
                            <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginBottom: '0.3rem' }}>Gate status</div>
                            <div style={{ fontSize: '1.5rem', fontWeight: 700 }}>{autoGate ? statusLabel(autoGate.status) : 'Not materialized'}</div>
                        </div>
                        <span style={badgeStyle(autoGatePalette.accent, autoGatePalette.soft)}>
                            {autoGate ? autoGate.gate_name : 'auto gate pending'}
                        </span>
                    </div>
                    <p style={{ margin: '0.9rem 0 0 0', fontSize: '0.84rem', color: 'var(--text-secondary)' }}>
                        {autoGateNarrative}
                    </p>
                    <div style={{ display: 'grid', gap: '0.6rem', marginTop: '1rem' }}>
                        <div style={{ padding: '0.75rem', borderRadius: '12px', background: 'rgba(255,255,255,0.02)' }}>
                            <div style={{ fontSize: '0.74rem', color: 'var(--text-muted)' }}>Due at</div>
                            <div style={{ marginTop: '0.25rem', fontSize: '0.84rem' }}>{formatDateTime(autoGate?.due_at || null)}</div>
                        </div>
                        <div style={{ padding: '0.75rem', borderRadius: '12px', background: 'rgba(255,255,255,0.02)' }}>
                            <div style={{ fontSize: '0.74rem', color: 'var(--text-muted)' }}>Evaluated at</div>
                            <div style={{ marginTop: '0.25rem', fontSize: '0.84rem' }}>{formatDateTime(autoGate?.evaluated_at || null)}</div>
                        </div>
                        <div style={{ padding: '0.75rem', borderRadius: '12px', background: 'rgba(255,255,255,0.02)' }}>
                            <div style={{ fontSize: '0.74rem', color: 'var(--text-muted)' }}>Decision notes</div>
                            <div style={{ marginTop: '0.25rem', fontSize: '0.84rem', color: 'var(--text-secondary)' }}>{autoGate?.decision_notes || 'No automatic decision note recorded yet.'}</div>
                        </div>
                        {analyticalPhase === 'S8' && (
                            <div style={{ padding: '0.75rem', borderRadius: '12px', background: 'rgba(245, 158, 11, 0.12)', border: '1px solid rgba(245, 158, 11, 0.25)', fontSize: '0.82rem', color: '#fef3c7' }}>
                                This tender is currently in compliance-gate phase, and the automatic gate is part of the operational explanation for that state.
                            </div>
                        )}
                    </div>
                </div>
            </div>

            <RequirementWorkbenchPanel
                tenderId={tenderDetail?.id ?? null}
                tenderTitle={tenderDetail?.title ?? null}
            />
        </div>
    );
}

