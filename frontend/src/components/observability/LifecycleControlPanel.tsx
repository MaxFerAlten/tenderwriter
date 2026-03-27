import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { AlertTriangle, CheckCircle2, GitBranchPlus, Send, ShieldCheck } from 'lucide-react';

import {
    proposalApi,
    tenderApi,
    type ProposalSubmissionStatusRequest,
    type Tender,
    type TenderDetail,
    type TenderLifecycleClarificationRecord,
    type TenderLifecycleMetadata,
} from '../../api/client';

interface LifecycleControlPanelProps {
    tender: Tender | null;
    tenderDetail: TenderDetail | null;
    analyticalPhase: string | null;
    onDataChanged?: () => void;
}

function formatDateTime(value: string | null | undefined): string {
    if (!value) return 'n/a';
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return value;
    return parsed.toLocaleString('it-IT');
}

function toApiDate(value: string): string | undefined {
    if (!value) return undefined;
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return undefined;
    return parsed.toISOString();
}

function asNumber(value: string): number | undefined {
    if (!value.trim()) return undefined;
    const parsed = Number(value);
    return Number.isNaN(parsed) ? undefined : parsed;
}

function asNumberList(value: string): number[] {
    return value.split(',').map((item) => Number(item.trim())).filter((item) => !Number.isNaN(item));
}

const TERMINAL_OUTCOME_OPTIONS = ['won', 'lost', 'excluded', 'withdrawn', 'stopped'] as const;

function normalizeOutcomeSelection(value: string | null | undefined): string {
    return TERMINAL_OUTCOME_OPTIONS.includes(value as typeof TERMINAL_OUTCOME_OPTIONS[number]) ? value as string : 'won';
}

function statusTone(value: string | null | undefined): { border: string; text: string; soft: string } {
    switch (value) {
        case 'go':
        case 'approved':
        case 'acknowledged':
        case 'won':
        case 'submitted':
        case 'closed':
        case 'requested':
        case 'response_drafted':
            return { border: '#10b981', text: '#10b981', soft: 'rgba(16, 185, 129, 0.12)' };
        case 'no_bid':
        case 'failed':
        case 'excluded':
        case 'withdrawn':
        case 'stopped':
        case 'lost':
            return { border: '#ef4444', text: '#ef4444', soft: 'rgba(239, 68, 68, 0.12)' };
        default:
            return { border: '#f59e0b', text: '#f59e0b', soft: 'rgba(245, 158, 11, 0.12)' };
    }
}

function StatusBadge({ value }: { value: string }) {
    const tone = statusTone(value);
    return <span style={{ padding: '0.2rem 0.55rem', borderRadius: '999px', border: `1px solid ${tone.border}33`, background: tone.soft, color: tone.text, fontSize: '0.72rem', textTransform: 'capitalize' }}>{value.replace(/_/g, ' ')}</span>;
}

function SectionCard(props: { title: string; subtitle: string; children: ReactNode }) {
    return <div className="card" style={{ display: 'grid', gap: '0.9rem' }}><div><h3 style={{ margin: 0, fontSize: '0.98rem' }}>{props.title}</h3><p style={{ margin: '0.32rem 0 0 0', fontSize: '0.8rem', color: 'var(--text-muted)' }}>{props.subtitle}</p></div>{props.children}</div>;
}

const labelStyle = { display: 'grid', gap: '0.35rem', fontSize: '0.78rem', color: 'var(--text-muted)' } as const;
const inputStyle = { width: '100%', borderRadius: '10px', border: '1px solid var(--border-color)', background: 'rgba(15, 23, 42, 0.55)', color: 'var(--text-primary)', padding: '0.7rem 0.8rem', fontSize: '0.88rem' } as const;

export default function LifecycleControlPanel({ tender, tenderDetail, analyticalPhase, onDataChanged }: LifecycleControlPanelProps) {
    const lifecycle: TenderLifecycleMetadata | null = tenderDetail?.lifecycle_metadata ?? tender?.lifecycle_metadata ?? null;
    const proposalId = tenderDetail?.proposal_id ?? tender?.proposal_id ?? null;
    const clarifications = useMemo(() => [...(lifecycle?.clarifications || [])].sort((left, right) => left.request_id.localeCompare(right.request_id)), [lifecycle?.clarifications]);
    const [submitKey, setSubmitKey] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [message, setMessage] = useState<string | null>(null);
    const [selectedClarificationId, setSelectedClarificationId] = useState('');
    const [decisionForm, setDecisionForm] = useState({ decision: 'go', reason_code: '', notes: '' });
    const [bidPlanForm, setBidPlanForm] = useState({ plan_status: 'created', owner_user_ids: '', milestone_count: '', notes: '' });
    const [waveForm, setWaveForm] = useState({ contribution_count: '', department_count: '', notes: '' });
    const [coordinationForm, setCoordinationForm] = useState({ external_rework_id: '', external_contribution_id: '', severity: 'high', reason_code: '', notes: '' });
    const [gateForm, setGateForm] = useState({ external_gate_id: '', gate_name: '', external_rework_id: '', reason_code: '', notes: '' });
    const [submissionForm, setSubmissionForm] = useState({ submission_status: 'acknowledged', channel: 'manual_admin_update', reference_id: '', error_code: '', error_message: '' });
    const [outcomeForm, setOutcomeForm] = useState({ outcome: 'won', reason_code: '', notes: '' });
    const [clarificationCreateForm, setClarificationCreateForm] = useState({ request_id: '', request_summary: '', deadline_at: '', source_label: '' });
    const [clarificationUpdateForm, setClarificationUpdateForm] = useState({ response_summary: '', source_label: '' });

    useEffect(() => {
        if (!tender) return;
        setDecisionForm({ decision: lifecycle?.decision?.decision || 'go', reason_code: lifecycle?.decision?.reason_code || '', notes: lifecycle?.decision?.notes || '' });
        setBidPlanForm({ plan_status: lifecycle?.bid_plan?.plan_status || 'created', owner_user_ids: (lifecycle?.bid_plan?.owner_user_ids || []).join(', '), milestone_count: lifecycle?.bid_plan?.milestone_count?.toString() || '', notes: lifecycle?.bid_plan?.notes || '' });
        setWaveForm({ contribution_count: lifecycle?.contribution_wave?.contribution_count?.toString() || '', department_count: lifecycle?.contribution_wave?.department_count?.toString() || '', notes: lifecycle?.contribution_wave?.notes || '' });
        setCoordinationForm({ external_rework_id: '', external_contribution_id: '', severity: 'high', reason_code: '', notes: '' });
        setGateForm({ external_gate_id: '', gate_name: '', external_rework_id: '', reason_code: '', notes: '' });
        setSubmissionForm({ submission_status: lifecycle?.submission_status?.submission_status || 'acknowledged', channel: lifecycle?.submission_status?.channel || 'manual_admin_update', reference_id: lifecycle?.submission_status?.reference_id || '', error_code: lifecycle?.submission_status?.error_code || '', error_message: lifecycle?.submission_status?.error_message || '' });
        setOutcomeForm({ outcome: normalizeOutcomeSelection(lifecycle?.structured_outcome?.outcome), reason_code: lifecycle?.structured_outcome?.reason_code || '', notes: lifecycle?.structured_outcome?.notes || '' });
        setClarificationCreateForm({ request_id: '', request_summary: '', deadline_at: '', source_label: '' });
        setClarificationUpdateForm({ response_summary: '', source_label: '' });
    }, [tender?.id, lifecycle]);

    useEffect(() => {
        if (clarifications.length === 0) {
            setSelectedClarificationId('');
            return;
        }
        setSelectedClarificationId((current) => current && clarifications.some((item) => item.request_id === current) ? current : clarifications[0].request_id);
    }, [clarifications]);

    const selectedClarification: TenderLifecycleClarificationRecord | null = clarifications.find((item) => item.request_id === selectedClarificationId) || null;
    const runAction = async (key: string, action: () => Promise<void>, successMessage: string) => {
        setSubmitKey(key);
        setError(null);
        setMessage(null);
        try {
            await action();
            onDataChanged?.();
            setMessage(successMessage);
        } catch (actionError) {
            setError(actionError instanceof Error ? actionError.message : 'Lifecycle action failed.');
        } finally {
            setSubmitKey(null);
        }
    };

    const triggerSubmissionAction = async () => {
        if (!proposalId) throw new Error('No linked proposal is available for submission reliability actions.');
        const payload: ProposalSubmissionStatusRequest = {
            submission_status: submissionForm.submission_status,
            channel: submissionForm.channel || 'manual_admin_update',
            reference_id: submissionForm.reference_id || undefined,
            error_code: submissionForm.error_code || undefined,
            error_message: submissionForm.error_message || undefined,
        };
        await proposalApi.updateSubmissionStatus(proposalId, payload);
    };

    if (!tender) return <div className="card"><p style={{ margin: 0, color: 'var(--text-muted)' }}>Select a tender to unlock the lifecycle control panel.</p></div>;

    return (
        <div style={{ display: 'grid', gap: '1rem' }}>
            <div className="card" style={{ borderColor: 'rgba(56, 189, 248, 0.28)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: '1rem', alignItems: 'flex-start' }}>
                    <div>
                        <h2 style={{ margin: 0, display: 'flex', alignItems: 'center', gap: '0.55rem' }}><GitBranchPlus size={20} color="#38bdf8" />Lifecycle Control</h2>
                        <p style={{ margin: '0.35rem 0 0 0', color: 'var(--text-muted)', fontSize: '0.85rem' }}>Canonical Sprint 18 controls for decision, planning, submission reliability, clarifications and final outcome.</p>
                    </div>
                    <div style={{ display: 'grid', gap: '0.45rem', justifyItems: 'end' }}>
                        <StatusBadge value={analyticalPhase || 's0'} />
                        <span style={{ fontSize: '0.74rem', color: 'var(--text-muted)' }}>Timeline refreshes after each action.</span>
                    </div>
                </div>
                {(error || message) && <div style={{ display: 'grid', gap: '0.65rem', marginTop: '1rem' }}>
                    {error && <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', padding: '0.75rem 0.85rem', borderRadius: '12px', background: 'rgba(127, 29, 29, 0.18)', border: '1px solid rgba(239, 68, 68, 0.3)', color: '#fecaca' }}><AlertTriangle size={16} /> {error}</div>}
                    {message && <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', padding: '0.75rem 0.85rem', borderRadius: '12px', background: 'rgba(6, 78, 59, 0.18)', border: '1px solid rgba(16, 185, 129, 0.25)', color: '#d1fae5' }}><CheckCircle2 size={16} /> {message}</div>}
                </div>}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '0.8rem', marginTop: '1rem' }}>
                    <div style={{ padding: '0.85rem', borderRadius: '12px', background: 'rgba(15, 23, 42, 0.32)', border: '1px solid var(--border-color)' }}><div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Decision</div><div style={{ marginTop: '0.4rem' }}>{lifecycle?.decision?.decision ? <StatusBadge value={lifecycle.decision.decision} /> : 'n/a'}</div></div>
                    <div style={{ padding: '0.85rem', borderRadius: '12px', background: 'rgba(15, 23, 42, 0.32)', border: '1px solid var(--border-color)' }}><div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Bid plan</div><div style={{ marginTop: '0.4rem' }}>{lifecycle?.bid_plan?.plan_status ? <StatusBadge value={lifecycle.bid_plan.plan_status} /> : 'n/a'}</div></div>
                    <div style={{ padding: '0.85rem', borderRadius: '12px', background: 'rgba(15, 23, 42, 0.32)', border: '1px solid var(--border-color)' }}><div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Submission</div><div style={{ marginTop: '0.4rem' }}>{lifecycle?.submission_status?.submission_status ? <StatusBadge value={lifecycle.submission_status.submission_status} /> : 'n/a'}</div></div>
                    <div style={{ padding: '0.85rem', borderRadius: '12px', background: 'rgba(15, 23, 42, 0.32)', border: '1px solid var(--border-color)' }}><div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Clarifications</div><div style={{ marginTop: '0.4rem', fontWeight: 600 }}>{clarifications.length}</div></div>
                    <div style={{ padding: '0.85rem', borderRadius: '12px', background: 'rgba(15, 23, 42, 0.32)', border: '1px solid var(--border-color)' }}><div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Outcome</div><div style={{ marginTop: '0.4rem' }}>{lifecycle?.structured_outcome?.outcome ? <StatusBadge value={lifecycle.structured_outcome.outcome} /> : 'n/a'}</div></div>
                </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '1rem' }}>
                <SectionCard title="Decision and planning" subtitle="Drive S1, S2 and S3 with canonical lifecycle events.">
                    <label style={labelStyle}>Decision<select value={decisionForm.decision} onChange={(event) => setDecisionForm((current) => ({ ...current, decision: event.target.value }))} style={inputStyle}><option value="go">Go</option><option value="no_bid">No Bid</option></select></label>
                    <label style={labelStyle}>Reason code<input value={decisionForm.reason_code} onChange={(event) => setDecisionForm((current) => ({ ...current, reason_code: event.target.value }))} style={inputStyle} placeholder="strategic_fit" /></label>
                    <label style={labelStyle}>Notes<textarea value={decisionForm.notes} onChange={(event) => setDecisionForm((current) => ({ ...current, notes: event.target.value }))} style={{ ...inputStyle, minHeight: '90px', resize: 'vertical' }} /></label>
                    <button className="btn btn-primary btn-sm" disabled={submitKey === 'decision'} onClick={() => void runAction('decision', async () => {
                        await tenderApi.recordDecision(tender.id, { decision: decisionForm.decision, reason_code: decisionForm.reason_code || undefined, notes: decisionForm.notes || undefined });
                    }, `Decision '${decisionForm.decision}' recorded.`)}><ShieldCheck size={14} /> {submitKey === 'decision' ? 'Recording...' : 'Record decision'}</button>
                    <label style={labelStyle}>Bid plan status<select value={bidPlanForm.plan_status} onChange={(event) => setBidPlanForm((current) => ({ ...current, plan_status: event.target.value }))} style={inputStyle}><option value="created">Created</option><option value="approved">Approved</option></select></label>
                    <label style={labelStyle}>Owner user ids<input value={bidPlanForm.owner_user_ids} onChange={(event) => setBidPlanForm((current) => ({ ...current, owner_user_ids: event.target.value }))} style={inputStyle} placeholder="12, 18" /></label>
                    <label style={labelStyle}>Milestone count<input value={bidPlanForm.milestone_count} onChange={(event) => setBidPlanForm((current) => ({ ...current, milestone_count: event.target.value }))} style={inputStyle} placeholder="5" /></label>
                    <label style={labelStyle}>Planning notes<textarea value={bidPlanForm.notes} onChange={(event) => setBidPlanForm((current) => ({ ...current, notes: event.target.value }))} style={{ ...inputStyle, minHeight: '84px', resize: 'vertical' }} /></label>
                    <button className="btn btn-secondary btn-sm" disabled={submitKey === 'bid-plan'} onClick={() => void runAction('bid-plan', async () => {
                        await tenderApi.recordBidPlan(tender.id, { plan_status: bidPlanForm.plan_status, owner_user_ids: asNumberList(bidPlanForm.owner_user_ids), milestone_count: asNumber(bidPlanForm.milestone_count), notes: bidPlanForm.notes || undefined });
                    }, `Bid plan '${bidPlanForm.plan_status}' recorded.`)}><GitBranchPlus size={14} /> {submitKey === 'bid-plan' ? 'Recording...' : 'Record bid plan'}</button>
                    <label style={labelStyle}>Contribution wave coverage<div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: '0.6rem' }}><input value={waveForm.contribution_count} onChange={(event) => setWaveForm((current) => ({ ...current, contribution_count: event.target.value }))} style={inputStyle} placeholder="Contributions" /><input value={waveForm.department_count} onChange={(event) => setWaveForm((current) => ({ ...current, department_count: event.target.value }))} style={inputStyle} placeholder="Departments" /></div></label>
                    <label style={labelStyle}>Wave notes<textarea value={waveForm.notes} onChange={(event) => setWaveForm((current) => ({ ...current, notes: event.target.value }))} style={{ ...inputStyle, minHeight: '72px', resize: 'vertical' }} /></label>
                    <button className="btn btn-secondary btn-sm" disabled={submitKey === 'wave'} onClick={() => void runAction('wave', async () => {
                        await tenderApi.openContributionWave(tender.id, { contribution_count: asNumber(waveForm.contribution_count), department_count: asNumber(waveForm.department_count), notes: waveForm.notes || undefined });
                    }, 'Contribution wave opened.')}><Send size={14} /> {submitKey === 'wave' ? 'Recording...' : 'Open contribution wave'}</button>
                </SectionCard>

                <SectionCard title="Coordination and rework" subtitle="Drive S4 <-> S6 explicitly when manual recovery or escalation is needed.">
                    <label style={labelStyle}>External rework id<input value={coordinationForm.external_rework_id} onChange={(event) => setCoordinationForm((current) => ({ ...current, external_rework_id: event.target.value }))} style={inputStyle} placeholder="rw-admin-1" /></label>
                    <label style={labelStyle}>Contribution id<input value={coordinationForm.external_contribution_id} onChange={(event) => setCoordinationForm((current) => ({ ...current, external_contribution_id: event.target.value }))} style={inputStyle} placeholder="201" /></label>
                    <label style={labelStyle}>Severity<select value={coordinationForm.severity} onChange={(event) => setCoordinationForm((current) => ({ ...current, severity: event.target.value }))} style={inputStyle}><option value="high">High</option><option value="medium">Medium</option><option value="low">Low</option></select></label>
                    <label style={labelStyle}>Reason code<input value={coordinationForm.reason_code} onChange={(event) => setCoordinationForm((current) => ({ ...current, reason_code: event.target.value }))} style={inputStyle} placeholder="missing_owner_alignment" /></label>
                    <label style={labelStyle}>Notes<textarea value={coordinationForm.notes} onChange={(event) => setCoordinationForm((current) => ({ ...current, notes: event.target.value }))} style={{ ...inputStyle, minHeight: '90px', resize: 'vertical' }} /></label>
                    <div style={{ display: 'flex', gap: '0.65rem', flexWrap: 'wrap' }}>
                        <button className="btn btn-secondary btn-sm" disabled={submitKey === 'coordination-risk'} onClick={() => void runAction('coordination-risk', async () => {
                            await tenderApi.raiseCoordinationRisk(tender.id, {
                                external_rework_id: coordinationForm.external_rework_id || undefined,
                                external_contribution_id: coordinationForm.external_contribution_id || undefined,
                                severity: coordinationForm.severity || undefined,
                                reason_code: coordinationForm.reason_code || undefined,
                                notes: coordinationForm.notes || undefined,
                            });
                        }, 'Coordination risk raised.')}><AlertTriangle size={14} /> {submitKey === 'coordination-risk' ? 'Recording...' : 'Raise coordination risk'}</button>
                        <button className="btn btn-primary btn-sm" disabled={submitKey === 'coordination-recovery'} onClick={() => void runAction('coordination-recovery', async () => {
                            await tenderApi.returnToCoordination(tender.id, {
                                external_rework_id: coordinationForm.external_rework_id || undefined,
                                external_contribution_id: coordinationForm.external_contribution_id || undefined,
                                severity: coordinationForm.severity || undefined,
                                reason_code: coordinationForm.reason_code || undefined,
                                notes: coordinationForm.notes || undefined,
                            });
                        }, 'Tender returned to coordination.')}><CheckCircle2 size={14} /> {submitKey === 'coordination-recovery' ? 'Recording...' : 'Return to coordination'}</button>
                    </div>
                </SectionCard>

                <SectionCard title="Gate exceptions" subtitle="Drive S8 -> S6 and S8 -> S13 explicitly; gate pass only reopens S7 and submission stays manual.">
                    <label style={labelStyle}>Gate id<input value={gateForm.external_gate_id} onChange={(event) => setGateForm((current) => ({ ...current, external_gate_id: event.target.value }))} style={inputStyle} placeholder="gate-1" /></label>
                    <label style={labelStyle}>Gate name<input value={gateForm.gate_name} onChange={(event) => setGateForm((current) => ({ ...current, gate_name: event.target.value }))} style={inputStyle} placeholder="Auto compliance readiness" /></label>
                    <label style={labelStyle}>Linked rework id<input value={gateForm.external_rework_id} onChange={(event) => setGateForm((current) => ({ ...current, external_rework_id: event.target.value }))} style={inputStyle} placeholder="gate-rw-1" /></label>
                    <label style={labelStyle}>Reason code<input value={gateForm.reason_code} onChange={(event) => setGateForm((current) => ({ ...current, reason_code: event.target.value }))} style={inputStyle} placeholder="compliance_gap_reopened" /></label>
                    <label style={labelStyle}>Notes<textarea value={gateForm.notes} onChange={(event) => setGateForm((current) => ({ ...current, notes: event.target.value }))} style={{ ...inputStyle, minHeight: '90px', resize: 'vertical' }} /></label>
                    <div style={{ display: 'flex', gap: '0.65rem', flexWrap: 'wrap' }}>
                        <button className="btn btn-secondary btn-sm" disabled={submitKey === 'gate-rework'} onClick={() => void runAction('gate-rework', async () => {
                            await tenderApi.requestGateRework(tender.id, {
                                external_gate_id: gateForm.external_gate_id || undefined,
                                gate_name: gateForm.gate_name || undefined,
                                external_rework_id: gateForm.external_rework_id || undefined,
                                reason_code: gateForm.reason_code || undefined,
                                notes: gateForm.notes || undefined,
                            });
                        }, 'Gate rework requested.')}><ShieldCheck size={14} /> {submitKey === 'gate-rework' ? 'Recording...' : 'Request gate rework'}</button>
                        <button className="btn btn-primary btn-sm" disabled={submitKey === 'gate-stop'} onClick={() => void runAction('gate-stop', async () => {
                            await tenderApi.stopAtGate(tender.id, {
                                external_gate_id: gateForm.external_gate_id || undefined,
                                gate_name: gateForm.gate_name || undefined,
                                external_rework_id: gateForm.external_rework_id || undefined,
                                reason_code: gateForm.reason_code || undefined,
                                notes: gateForm.notes || undefined,
                            });
                        }, 'Tender stopped at gate.')}><AlertTriangle size={14} /> {submitKey === 'gate-stop' ? 'Recording...' : 'Stop at gate'}</button>
                    </div>
                </SectionCard>

                <SectionCard title="Draft and submission reliability" subtitle="Drive S7, S9 and the submission reliability corridor.">
                    <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Linked proposal: <strong style={{ color: 'var(--text-primary)' }}>{proposalId ?? 'n/a'}</strong></div>
                    <button className="btn btn-secondary btn-sm" disabled={submitKey === 'draft-ready' || !proposalId} onClick={() => void runAction('draft-ready', async () => {
                        if (!proposalId) throw new Error('No linked proposal is available for draft readiness.');
                        await proposalApi.markDraftReady(proposalId, {});
                    }, 'Integrated draft marked as ready.')}><CheckCircle2 size={14} /> {submitKey === 'draft-ready' ? 'Recording...' : 'Mark draft ready'}</button>
                    <label style={labelStyle}>Submission status<select value={submissionForm.submission_status} onChange={(event) => setSubmissionForm((current) => ({ ...current, submission_status: event.target.value }))} style={inputStyle}><option value="acknowledged">Acknowledged</option><option value="failed">Failed</option></select></label>
                    <label style={labelStyle}>Channel<input value={submissionForm.channel} onChange={(event) => setSubmissionForm((current) => ({ ...current, channel: event.target.value }))} style={inputStyle} placeholder="manual_admin_update" /></label>
                    <label style={labelStyle}>Reference id<input value={submissionForm.reference_id} onChange={(event) => setSubmissionForm((current) => ({ ...current, reference_id: event.target.value }))} style={inputStyle} placeholder="ACK-2026-001" /></label>
                    <label style={labelStyle}>Error code<input value={submissionForm.error_code} onChange={(event) => setSubmissionForm((current) => ({ ...current, error_code: event.target.value }))} style={inputStyle} placeholder="gateway_timeout" /></label>
                    <label style={labelStyle}>Error message<textarea value={submissionForm.error_message} onChange={(event) => setSubmissionForm((current) => ({ ...current, error_message: event.target.value }))} style={{ ...inputStyle, minHeight: '84px', resize: 'vertical' }} /></label>
                    <button className="btn btn-primary btn-sm" disabled={submitKey === 'submission' || !proposalId} onClick={() => void runAction('submission', triggerSubmissionAction, `Submission status '${submissionForm.submission_status}' recorded.`)}><Send size={14} /> {submitKey === 'submission' ? 'Recording...' : 'Record submission status'}</button>
                </SectionCard>

                <SectionCard title="Terminal outcome" subtitle="Close the tender with the final structured outcome taxonomy.">
                    <label style={labelStyle}>Outcome<select value={outcomeForm.outcome} onChange={(event) => setOutcomeForm((current) => ({ ...current, outcome: event.target.value }))} style={inputStyle}><option value="won">Won</option><option value="lost">Lost</option><option value="excluded">Excluded</option><option value="withdrawn">Withdrawn</option><option value="stopped">Stopped</option></select></label>
                    <label style={labelStyle}>Reason code<input value={outcomeForm.reason_code} onChange={(event) => setOutcomeForm((current) => ({ ...current, reason_code: event.target.value }))} style={inputStyle} placeholder="missing_annex" /></label>
                    <label style={labelStyle}>Notes<textarea value={outcomeForm.notes} onChange={(event) => setOutcomeForm((current) => ({ ...current, notes: event.target.value }))} style={{ ...inputStyle, minHeight: '92px', resize: 'vertical' }} /></label>
                    <button className="btn btn-primary btn-sm" disabled={submitKey === 'outcome'} onClick={() => void runAction('outcome', async () => {
                        await tenderApi.recordOutcome(tender.id, { outcome: outcomeForm.outcome, reason_code: outcomeForm.reason_code || undefined, notes: outcomeForm.notes || undefined });
                    }, `Outcome '${outcomeForm.outcome}' recorded.`)}><ShieldCheck size={14} /> {submitKey === 'outcome' ? 'Recording...' : 'Record final outcome'}</button>
                </SectionCard>

                <SectionCard title="Post-submission clarifications" subtitle="Open and manage real S10 clarification loops from the KPI cockpit.">
                    <label style={labelStyle}>New clarification id<input value={clarificationCreateForm.request_id} onChange={(event) => setClarificationCreateForm((current) => ({ ...current, request_id: event.target.value }))} style={inputStyle} placeholder="clar-1" /></label>
                    <label style={labelStyle}>Request summary<textarea value={clarificationCreateForm.request_summary} onChange={(event) => setClarificationCreateForm((current) => ({ ...current, request_summary: event.target.value }))} style={{ ...inputStyle, minHeight: '88px', resize: 'vertical' }} /></label>
                    <label style={labelStyle}>Deadline<input type="datetime-local" value={clarificationCreateForm.deadline_at} onChange={(event) => setClarificationCreateForm((current) => ({ ...current, deadline_at: event.target.value }))} style={inputStyle} /></label>
                    <label style={labelStyle}>Source label<input value={clarificationCreateForm.source_label} onChange={(event) => setClarificationCreateForm((current) => ({ ...current, source_label: event.target.value }))} style={inputStyle} placeholder="buyer_portal" /></label>
                    <button className="btn btn-secondary btn-sm" disabled={submitKey === 'clarification-create' || !clarificationCreateForm.request_summary.trim()} onClick={() => void runAction('clarification-create', async () => {
                        await tenderApi.createClarification(tender.id, { request_id: clarificationCreateForm.request_id || undefined, request_summary: clarificationCreateForm.request_summary, deadline_at: toApiDate(clarificationCreateForm.deadline_at), source_label: clarificationCreateForm.source_label || undefined });
                    }, 'Clarification request opened.')}><GitBranchPlus size={14} /> {submitKey === 'clarification-create' ? 'Creating...' : 'Open clarification'}</button>
                    <label style={labelStyle}>Existing clarification<select value={selectedClarificationId} onChange={(event) => setSelectedClarificationId(event.target.value)} style={inputStyle} disabled={clarifications.length === 0}>{clarifications.length === 0 ? <option value="">No clarifications yet</option> : clarifications.map((item) => <option key={item.request_id} value={item.request_id}>{item.request_id}</option>)}</select></label>
                    {selectedClarification && <div style={{ padding: '0.8rem', borderRadius: '12px', background: 'rgba(15, 23, 42, 0.35)', border: '1px solid var(--border-color)', fontSize: '0.8rem', color: 'var(--text-secondary)' }}><div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.75rem', alignItems: 'center' }}><strong style={{ color: 'var(--text-primary)' }}>{selectedClarification.request_id}</strong><StatusBadge value={selectedClarification.status} /></div><div style={{ marginTop: '0.45rem' }}>{selectedClarification.request_summary || 'No request summary available.'}</div><div style={{ marginTop: '0.45rem', color: 'var(--text-muted)' }}>Deadline {formatDateTime(selectedClarification.deadline_at)} | Updated {formatDateTime(selectedClarification.updated_at)}</div></div>}
                    <label style={labelStyle}>Response summary<textarea value={clarificationUpdateForm.response_summary} onChange={(event) => setClarificationUpdateForm((current) => ({ ...current, response_summary: event.target.value }))} style={{ ...inputStyle, minHeight: '88px', resize: 'vertical' }} /></label>
                    <label style={labelStyle}>Source label<input value={clarificationUpdateForm.source_label} onChange={(event) => setClarificationUpdateForm((current) => ({ ...current, source_label: event.target.value }))} style={inputStyle} placeholder="buyer_portal" /></label>
                    <div style={{ display: 'flex', gap: '0.65rem', flexWrap: 'wrap' }}>
                        <button className="btn btn-secondary btn-sm" disabled={submitKey === 'clarification-draft' || !selectedClarificationId} onClick={() => void runAction('clarification-draft', async () => {
                            await tenderApi.draftClarification(tender.id, selectedClarificationId, { response_summary: clarificationUpdateForm.response_summary || undefined, source_label: clarificationUpdateForm.source_label || undefined });
                        }, `Clarification '${selectedClarificationId}' drafted.`)}>{submitKey === 'clarification-draft' ? 'Saving...' : 'Draft response'}</button>
                        <button className="btn btn-primary btn-sm" disabled={submitKey === 'clarification-submit' || !selectedClarificationId} onClick={() => void runAction('clarification-submit', async () => {
                            await tenderApi.submitClarification(tender.id, selectedClarificationId, { response_summary: clarificationUpdateForm.response_summary || undefined, source_label: clarificationUpdateForm.source_label || undefined });
                        }, `Clarification '${selectedClarificationId}' submitted.`)}>{submitKey === 'clarification-submit' ? 'Submitting...' : 'Submit clarification'}</button>
                        <button className="btn btn-secondary btn-sm" disabled={submitKey === 'clarification-close' || !selectedClarificationId} onClick={() => void runAction('clarification-close', async () => {
                            await tenderApi.closeClarification(tender.id, selectedClarificationId, { response_summary: clarificationUpdateForm.response_summary || undefined, source_label: clarificationUpdateForm.source_label || undefined });
                        }, `Clarification '${selectedClarificationId}' closed.`)}>{submitKey === 'clarification-close' ? 'Closing...' : 'Close clarification'}</button>
                    </div>
                </SectionCard>
            </div>
        </div>
    );
}


