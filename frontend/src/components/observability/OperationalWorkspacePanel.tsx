import { useEffect, useState, type ReactNode } from 'react';
import {
    AlertTriangle,
    CheckCircle2,
    ClipboardList,
    MessagesSquare,
    RefreshCcw,
    ShieldCheck,
    Wrench,
} from 'lucide-react';
import {
    observabilityApi,
    type AttendanceRecordItem,
    type CallSessionRecord,
    type OperationalWorkspace,
    type Tender,
} from '../../api/client';

interface OperationalWorkspacePanelProps {
    tender: Tender | null;
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

function statusPalette(status: string): { border: string; text: string; soft: string } {
    switch (status) {
        case 'completed':
        case 'received':
        case 'passed':
        case 'attended':
        case 'resolved':
        case 'approved':
            return { border: '#10b981', text: '#10b981', soft: 'rgba(16, 185, 129, 0.12)' };
        case 'rework':
        case 'failed':
        case 'open':
        case 'blocked':
        case 'absent':
            return { border: '#ef4444', text: '#ef4444', soft: 'rgba(239, 68, 68, 0.12)' };
        case 'requested':
        case 'in_review':
        case 'scheduled':
        case 'invited':
            return { border: '#f59e0b', text: '#f59e0b', soft: 'rgba(245, 158, 11, 0.12)' };
        default:
            return { border: '#64748b', text: '#cbd5e1', soft: 'rgba(100, 116, 139, 0.14)' };
    }
}

function StatusBadge({ value }: { value: string }) {
    const palette = statusPalette(value);
    return (
        <span
            style={{
                padding: '0.2rem 0.55rem',
                borderRadius: '999px',
                border: `1px solid ${palette.border}33`,
                background: palette.soft,
                color: palette.text,
                fontSize: '0.72rem',
                textTransform: 'capitalize',
            }}
        >
            {value.replace(/_/g, ' ')}
        </span>
    );
}

function SectionCard(props: { title: string; subtitle?: string; children: ReactNode }) {
    return (
        <div className="card">
            <div style={{ marginBottom: '0.8rem' }}>
                <h3 style={{ margin: 0, fontSize: '1rem' }}>{props.title}</h3>
                {props.subtitle && <p style={{ margin: '0.3rem 0 0 0', fontSize: '0.8rem', color: 'var(--text-muted)' }}>{props.subtitle}</p>}
            </div>
            {props.children}
        </div>
    );
}

function AttendanceList({ attendance }: { attendance: AttendanceRecordItem[] | undefined }) {
    if (!attendance || attendance.length === 0) {
        return <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>No attendance recorded yet.</div>;
    }

    return (
        <div style={{ display: 'grid', gap: '0.45rem', marginTop: '0.55rem' }}>
            {attendance.map((record) => (
                <div key={record.id} style={{ display: 'flex', justifyContent: 'space-between', gap: '0.75rem', alignItems: 'center', fontSize: '0.78rem' }}>
                    <div>
                        <div>{record.attendee_label || `User ${record.user_id ?? 'n/a'}`}</div>
                        <div style={{ color: 'var(--text-muted)', marginTop: '0.2rem' }}>{formatDateTime(record.recorded_at)}</div>
                    </div>
                    <StatusBadge value={record.attendance_status} />
                </div>
            ))}
        </div>
    );
}

export default function OperationalWorkspacePanel({ tender, onDataChanged }: OperationalWorkspacePanelProps) {
    const [workspace, setWorkspace] = useState<OperationalWorkspace | null>(null);
    const [isLoading, setIsLoading] = useState(false);
    const [isRefreshing, setIsRefreshing] = useState(false);
    const [submitKey, setSubmitKey] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [message, setMessage] = useState<string | null>(null);
    const [selectedContributionId, setSelectedContributionId] = useState<number | null>(null);
    const [selectedCallId, setSelectedCallId] = useState<number | null>(null);
    const [contributionForm, setContributionForm] = useState({ title: '', department_name: '', description: '', due_at: '' });
    const [requestForm, setRequestForm] = useState({ requested_to_label: '', request_channel: 'chat', due_at: '', sla_target_hours: '8', sla_max_hours: '24' });
    const [reviewForm, setReviewForm] = useState({ stage_name: 'quality_review', notes: '' });
    const [reworkForm, setReworkForm] = useState({ severity: 'medium', reason: '', due_at: '', is_blocking: true });
    const [gateForm, setGateForm] = useState({ gate_name: '', due_at: '' });
    const [callForm, setCallForm] = useState({ title: '', scheduled_at: '' });
    const [attendanceForm, setAttendanceForm] = useState({ attendee_label: '', attendance_status: 'attended', notes: '' });

    const loadWorkspace = async (refresh = false) => {
        if (!tender) {
            setWorkspace(null);
            return;
        }
        setError(null);
        setMessage(null);
        if (refresh) {
            setIsRefreshing(true);
        } else {
            setIsLoading(true);
        }
        try {
            const response = await observabilityApi.getWorkspace(tender.id);
            setWorkspace(response);
            if (response.contributions.length > 0) {
                setSelectedContributionId((current) => current ?? response.contributions[0].id);
            } else {
                setSelectedContributionId(null);
            }
            if (response.calls.length > 0) {
                setSelectedCallId((current) => current ?? response.calls[0].id);
            } else {
                setSelectedCallId(null);
            }
        } catch (workspaceError) {
            setError(workspaceError instanceof Error ? workspaceError.message : 'Failed to load operational workspace.');
        } finally {
            setIsLoading(false);
            setIsRefreshing(false);
        }
    };

    useEffect(() => {
        void loadWorkspace();
    }, [tender?.id]);

    const selectedContribution = workspace?.contributions.find((item) => item.id === selectedContributionId) || null;
    const selectedCall: CallSessionRecord | null = workspace?.calls.find((item) => item.id === selectedCallId) || null;
    const contributionRequests = (workspace?.requests || []).filter((item) => item.contribution_unit_id === selectedContributionId);
    const contributionReviews = (workspace?.reviews || []).filter((item) => item.contribution_unit_id === selectedContributionId);
    const contributionReworks = (workspace?.reworks || []).filter((item) => item.contribution_unit_id === selectedContributionId);

    const runAction = async (key: string, action: () => Promise<void>, successMessage: string) => {
        if (!tender) return;
        setSubmitKey(key);
        setError(null);
        setMessage(null);
        try {
            await action();
            await loadWorkspace(true);
            onDataChanged?.();
            setMessage(successMessage);
        } catch (actionError) {
            setError(actionError instanceof Error ? actionError.message : 'Operational action failed.');
        } finally {
            setSubmitKey(null);
        }
    };

    if (!tender) {
        return (
            <div className="card">
                <p style={{ margin: 0, color: 'var(--text-muted)' }}>Select a tender to unlock the operational workspace.</p>
            </div>
        );
    }

    const summary = workspace?.summary;

    return (
        <div style={{ display: 'grid', gap: '1rem' }}>
            <div className="card" style={{ borderColor: 'rgba(56, 189, 248, 0.28)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '1rem' }}>
                    <div>
                        <h2 style={{ margin: 0, display: 'flex', alignItems: 'center', gap: '0.55rem' }}>
                            <ClipboardList size={20} color="#38bdf8" />
                            Operational Workspace
                        </h2>
                        <p style={{ margin: '0.35rem 0 0 0', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                            Manual control surface for contribution requests, reviews, rework, gates and call attendance on {tender.title}.
                        </p>
                    </div>
                    <button className={`btn btn-secondary btn-sm ${isRefreshing ? 'animate-pulse' : ''}`} onClick={() => void loadWorkspace(true)}>
                        <RefreshCcw size={14} /> Refresh workspace
                    </button>
                </div>

                {(error || message) && (
                    <div style={{ display: 'grid', gap: '0.65rem', marginTop: '1rem' }}>
                        {error && (
                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', padding: '0.75rem 0.85rem', borderRadius: '12px', background: 'rgba(127, 29, 29, 0.18)', border: '1px solid rgba(239, 68, 68, 0.3)', color: '#fecaca' }}>
                                <AlertTriangle size={16} /> {error}
                            </div>
                        )}
                        {message && (
                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', padding: '0.75rem 0.85rem', borderRadius: '12px', background: 'rgba(6, 78, 59, 0.18)', border: '1px solid rgba(16, 185, 129, 0.25)', color: '#d1fae5' }}>
                                <CheckCircle2 size={16} /> {message}
                            </div>
                        )}
                    </div>
                )}
            </div>

            {isLoading || !workspace ? (
                <div className="card"><p style={{ margin: 0, color: 'var(--text-muted)' }}>Loading operational workspace...</p></div>
            ) : (
                <>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '0.9rem' }}>
                        {[
                            ['Contributions', summary?.contribution_count ?? 0],
                            ['Requests', summary?.request_count ?? 0],
                            ['Open rework', summary?.open_rework_count ?? 0],
                            ['Open gates', summary?.open_gate_count ?? 0],
                            ['Calls', summary?.call_count ?? 0],
                        ].map(([label, value]) => (
                            <div key={String(label)} className="card" style={{ padding: '1rem' }}>
                                <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginBottom: '0.3rem' }}>{label}</div>
                                <div style={{ fontSize: '1.8rem', fontWeight: 700 }}>{value}</div>
                            </div>
                        ))}
                    </div>

                    <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1.1fr) minmax(320px, 0.9fr)', gap: '1rem', alignItems: 'start' }}>
                        <div style={{ display: 'grid', gap: '1rem' }}>
                            <SectionCard title="Contributions" subtitle="Select one contribution to drive requests, reviews and rework.">
                                <div style={{ display: 'grid', gap: '0.75rem' }}>
                                    {workspace.contributions.length === 0 ? (
                                        <div style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>No contribution units created yet.</div>
                                    ) : workspace.contributions.map((item) => (
                                        <button
                                            key={item.id}
                                            onClick={() => setSelectedContributionId(item.id)}
                                            style={{
                                                textAlign: 'left',
                                                border: `1px solid ${item.id === selectedContributionId ? '#38bdf8' : 'var(--border-color)'}`,
                                                background: item.id === selectedContributionId ? 'rgba(56, 189, 248, 0.08)' : 'rgba(255,255,255,0.02)',
                                                borderRadius: '14px',
                                                padding: '0.85rem',
                                                color: 'inherit',
                                                cursor: 'pointer',
                                            }}
                                        >
                                            <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.75rem', alignItems: 'flex-start' }}>
                                                <div>
                                                    <div style={{ fontWeight: 600 }}>{item.title}</div>
                                                    <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: '0.2rem' }}>
                                                        {item.department_name || 'Department n/a'} | Due {formatDateTime(item.due_at)}
                                                    </div>
                                                </div>
                                                <StatusBadge value={item.status} />
                                            </div>
                                            {item.description && <div style={{ marginTop: '0.55rem', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>{item.description}</div>}
                                        </button>
                                    ))}
                                </div>
                            </SectionCard>

                            <SectionCard title="Workflow stream" subtitle={selectedContribution ? `Events linked to contribution #${selectedContribution.id}` : 'Select a contribution to inspect requests, reviews and rework.'}>
                                <div style={{ display: 'grid', gap: '0.85rem' }}>
                                    <div>
                                        <div style={{ fontSize: '0.8rem', fontWeight: 600, marginBottom: '0.4rem' }}>Requests</div>
                                        {contributionRequests.length === 0 ? (
                                            <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>No requests yet.</div>
                                        ) : contributionRequests.map((item) => (
                                            <div key={item.id} style={{ padding: '0.75rem', borderRadius: '12px', background: 'rgba(15, 23, 42, 0.35)', border: '1px solid var(--border-color)', marginBottom: '0.55rem' }}>
                                                <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.75rem', alignItems: 'flex-start' }}>
                                                    <div>
                                                        <div style={{ fontWeight: 600 }}>{item.requested_to_label || `Request #${item.id}`}</div>
                                                        <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
                                                            Requested {formatDateTime(item.requested_at)} | Due {formatDateTime(item.due_at)}
                                                        </div>
                                                    </div>
                                                    <StatusBadge value={item.status} />
                                                </div>
                                                <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', marginTop: '0.45rem' }}>
                                                    Channel: {item.request_channel || 'n/a'} | SLA {item.sla_target_hours ?? '--'} / {item.sla_max_hours ?? '--'} hours
                                                </div>
                                                {item.status !== 'received' && selectedContribution && (
                                                    <button
                                                        className="btn btn-secondary btn-sm"
                                                        style={{ marginTop: '0.6rem' }}
                                                        disabled={submitKey === `receive-${item.id}`}
                                                        onClick={() => void runAction(`receive-${item.id}`, async () => {
                                                            await observabilityApi.receiveRequest(tender.id, selectedContribution.id, item.id, { response_received_at: new Date().toISOString(), response_summary: 'Received through admin workspace' });
                                                        }, `Request #${item.id} marked as received.`)}
                                                    >
                                                        Mark received
                                                    </button>
                                                )}
                                            </div>
                                        ))}
                                    </div>

                                    <div>
                                        <div style={{ fontSize: '0.8rem', fontWeight: 600, marginBottom: '0.4rem' }}>Reviews</div>
                                        {contributionReviews.length === 0 ? (
                                            <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>No reviews yet.</div>
                                        ) : contributionReviews.map((item) => (
                                            <div key={item.id} style={{ padding: '0.75rem', borderRadius: '12px', background: 'rgba(15, 23, 42, 0.35)', border: '1px solid var(--border-color)', marginBottom: '0.55rem' }}>
                                                <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.75rem', alignItems: 'flex-start' }}>
                                                    <div>
                                                        <div style={{ fontWeight: 600 }}>{item.stage_name}</div>
                                                        <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>Started {formatDateTime(item.started_at)}</div>
                                                    </div>
                                                    <StatusBadge value={item.status} />
                                                </div>
                                                {item.notes && <div style={{ marginTop: '0.45rem', fontSize: '0.78rem', color: 'var(--text-secondary)' }}>{item.notes}</div>}
                                                {item.status !== 'completed' && selectedContribution && (
                                                    <button
                                                        className="btn btn-secondary btn-sm"
                                                        style={{ marginTop: '0.6rem' }}
                                                        disabled={submitKey === `review-${item.id}`}
                                                        onClick={() => void runAction(`review-${item.id}`, async () => {
                                                            await observabilityApi.completeReview(tender.id, selectedContribution.id, item.id, { completed_at: new Date().toISOString(), outcome: 'approved', notes: 'Approved from admin workspace' });
                                                        }, `Review #${item.id} completed.`)}
                                                    >
                                                        Complete as approved
                                                    </button>
                                                )}
                                            </div>
                                        ))}
                                    </div>

                                    <div>
                                        <div style={{ fontSize: '0.8rem', fontWeight: 600, marginBottom: '0.4rem' }}>Rework</div>
                                        {contributionReworks.length === 0 ? (
                                            <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>No rework actions yet.</div>
                                        ) : contributionReworks.map((item) => (
                                            <div key={item.id} style={{ padding: '0.75rem', borderRadius: '12px', background: 'rgba(15, 23, 42, 0.35)', border: '1px solid var(--border-color)', marginBottom: '0.55rem' }}>
                                                <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.75rem', alignItems: 'flex-start' }}>
                                                    <div>
                                                        <div style={{ fontWeight: 600 }}>{item.severity} severity</div>
                                                        <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>Requested {formatDateTime(item.requested_at)}</div>
                                                    </div>
                                                    <StatusBadge value={item.status} />
                                                </div>
                                                {item.reason && <div style={{ marginTop: '0.45rem', fontSize: '0.78rem', color: 'var(--text-secondary)' }}>{item.reason}</div>}
                                                {item.status !== 'resolved' && selectedContribution && (
                                                    <button
                                                        className="btn btn-secondary btn-sm"
                                                        style={{ marginTop: '0.6rem' }}
                                                        disabled={submitKey === `rework-${item.id}`}
                                                        onClick={() => void runAction(`rework-${item.id}`, async () => {
                                                            await observabilityApi.resolveRework(tender.id, selectedContribution.id, item.id, { resolved_at: new Date().toISOString(), resolution_notes: 'Resolved from admin workspace' });
                                                        }, `Rework #${item.id} resolved.`)}
                                                    >
                                                        Resolve rework
                                                    </button>
                                                )}
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            </SectionCard>

                            <SectionCard title="Gates and calls" subtitle="Operational meeting rhythm and compliance decisions for the selected tender.">
                                <div style={{ display: 'grid', gap: '0.85rem' }}>
                                    <div>
                                        <div style={{ fontSize: '0.8rem', fontWeight: 600, marginBottom: '0.4rem' }}>Compliance gates</div>
                                        {workspace.gates.length === 0 ? (
                                            <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>No compliance gates yet.</div>
                                        ) : workspace.gates.map((item) => (
                                            <div key={item.id} style={{ padding: '0.75rem', borderRadius: '12px', background: 'rgba(15, 23, 42, 0.35)', border: '1px solid var(--border-color)', marginBottom: '0.55rem' }}>
                                                <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.75rem', alignItems: 'flex-start' }}>
                                                    <div>
                                                        <div style={{ fontWeight: 600 }}>{item.gate_name}</div>
                                                        <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>Due {formatDateTime(item.due_at)}</div>
                                                    </div>
                                                    <StatusBadge value={item.status} />
                                                </div>
                                                {item.status === 'open' && (
                                                    <div style={{ display: 'flex', gap: '0.55rem', marginTop: '0.7rem' }}>
                                                        <button
                                                            className="btn btn-secondary btn-sm"
                                                            disabled={submitKey === `gate-pass-${item.id}`}
                                                            onClick={() => void runAction(`gate-pass-${item.id}`, async () => {
                                                                await observabilityApi.decideGate(tender.id, item.id, { status: 'passed', evaluated_at: new Date().toISOString(), decision_notes: 'Passed from admin workspace' });
                                                            }, `Gate #${item.id} passed.`)}
                                                        >
                                                            Mark passed
                                                        </button>
                                                        <button
                                                            className="btn btn-secondary btn-sm"
                                                            disabled={submitKey === `gate-fail-${item.id}`}
                                                            onClick={() => void runAction(`gate-fail-${item.id}`, async () => {
                                                                await observabilityApi.decideGate(tender.id, item.id, { status: 'failed', evaluated_at: new Date().toISOString(), decision_notes: 'Failed from admin workspace' });
                                                            }, `Gate #${item.id} failed.`)}
                                                        >
                                                            Mark failed
                                                        </button>
                                                    </div>
                                                )}
                                            </div>
                                        ))}
                                    </div>

                                    <div>
                                        <div style={{ fontSize: '0.8rem', fontWeight: 600, marginBottom: '0.4rem' }}>Calls</div>
                                        {workspace.calls.length === 0 ? (
                                            <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>No calls scheduled yet.</div>
                                        ) : workspace.calls.map((item) => (
                                            <button
                                                key={item.id}
                                                onClick={() => setSelectedCallId(item.id)}
                                                style={{
                                                    width: '100%',
                                                    textAlign: 'left',
                                                    border: `1px solid ${item.id === selectedCallId ? '#38bdf8' : 'var(--border-color)'}`,
                                                    background: item.id === selectedCallId ? 'rgba(56, 189, 248, 0.08)' : 'rgba(15, 23, 42, 0.35)',
                                                    borderRadius: '12px',
                                                    padding: '0.75rem',
                                                    color: 'inherit',
                                                    marginBottom: '0.55rem',
                                                    cursor: 'pointer',
                                                }}
                                            >
                                                <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.75rem', alignItems: 'flex-start' }}>
                                                    <div>
                                                        <div style={{ fontWeight: 600 }}>{item.title}</div>
                                                        <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>{formatDateTime(item.scheduled_at)}</div>
                                                    </div>
                                                    <StatusBadge value={item.status} />
                                                </div>
                                                <AttendanceList attendance={item.attendance} />
                                            </button>
                                        ))}
                                    </div>
                                </div>
                            </SectionCard>
                        </div>

                        <div style={{ display: 'grid', gap: '1rem' }}>
                            <SectionCard title="Create contribution" subtitle="Seed a contribution unit before starting operational tracking.">
                                <div style={{ display: 'grid', gap: '0.65rem' }}>
                                    <input className="input" placeholder="Contribution title" value={contributionForm.title} onChange={(event) => setContributionForm((current) => ({ ...current, title: event.target.value }))} />
                                    <input className="input" placeholder="Department" value={contributionForm.department_name} onChange={(event) => setContributionForm((current) => ({ ...current, department_name: event.target.value }))} />
                                    <textarea className="input" placeholder="Description" value={contributionForm.description} onChange={(event) => setContributionForm((current) => ({ ...current, description: event.target.value }))} rows={3} />
                                    <input className="input" type="datetime-local" value={contributionForm.due_at} onChange={(event) => setContributionForm((current) => ({ ...current, due_at: event.target.value }))} />
                                    <button
                                        className="btn btn-primary"
                                        disabled={!contributionForm.title.trim() || submitKey === 'create-contribution'}
                                        onClick={() => void runAction('create-contribution', async () => {
                                            await observabilityApi.createContribution(tender.id, {
                                                title: contributionForm.title.trim(),
                                                department_name: contributionForm.department_name.trim() || undefined,
                                                description: contributionForm.description.trim() || undefined,
                                                due_at: toApiDate(contributionForm.due_at),
                                            });
                                            setContributionForm({ title: '', department_name: '', description: '', due_at: '' });
                                        }, 'Contribution created.')}
                                    >
                                        Create contribution
                                    </button>
                                </div>
                            </SectionCard>

                            <SectionCard title="Selected contribution actions" subtitle={selectedContribution ? `Working on #${selectedContribution.id} - ${selectedContribution.title}` : 'Pick a contribution to unlock request, review and rework actions.'}>
                                {!selectedContribution ? (
                                    <div style={{ color: 'var(--text-muted)', fontSize: '0.84rem' }}>No contribution selected.</div>
                                ) : (
                                    <div style={{ display: 'grid', gap: '1rem' }}>
                                        <div style={{ display: 'grid', gap: '0.65rem' }}>
                                            <div style={{ fontSize: '0.82rem', fontWeight: 600 }}>Create request</div>
                                            <input className="input" placeholder="Requested to" value={requestForm.requested_to_label} onChange={(event) => setRequestForm((current) => ({ ...current, requested_to_label: event.target.value }))} />
                                            <input className="input" placeholder="Channel" value={requestForm.request_channel} onChange={(event) => setRequestForm((current) => ({ ...current, request_channel: event.target.value }))} />
                                            <input className="input" type="datetime-local" value={requestForm.due_at} onChange={(event) => setRequestForm((current) => ({ ...current, due_at: event.target.value }))} />
                                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.65rem' }}>
                                                <input className="input" placeholder="SLA target hours" value={requestForm.sla_target_hours} onChange={(event) => setRequestForm((current) => ({ ...current, sla_target_hours: event.target.value }))} />
                                                <input className="input" placeholder="SLA max hours" value={requestForm.sla_max_hours} onChange={(event) => setRequestForm((current) => ({ ...current, sla_max_hours: event.target.value }))} />
                                            </div>
                                            <button
                                                className="btn btn-secondary"
                                                disabled={submitKey === 'create-request'}
                                                onClick={() => void runAction('create-request', async () => {
                                                    await observabilityApi.createRequest(tender.id, selectedContribution.id, {
                                                        requested_to_label: requestForm.requested_to_label.trim() || undefined,
                                                        request_channel: requestForm.request_channel.trim() || undefined,
                                                        due_at: toApiDate(requestForm.due_at),
                                                        sla_target_hours: asNumber(requestForm.sla_target_hours),
                                                        sla_max_hours: asNumber(requestForm.sla_max_hours),
                                                    });
                                                    setRequestForm({ requested_to_label: '', request_channel: 'chat', due_at: '', sla_target_hours: '8', sla_max_hours: '24' });
                                                }, 'Contribution request created.')}
                                            >
                                                <MessagesSquare size={15} /> Create request
                                            </button>
                                        </div>

                                        <div style={{ display: 'grid', gap: '0.65rem' }}>
                                            <div style={{ fontSize: '0.82rem', fontWeight: 600 }}>Start review</div>
                                            <input className="input" placeholder="Stage name" value={reviewForm.stage_name} onChange={(event) => setReviewForm((current) => ({ ...current, stage_name: event.target.value }))} />
                                            <textarea className="input" placeholder="Review notes" rows={3} value={reviewForm.notes} onChange={(event) => setReviewForm((current) => ({ ...current, notes: event.target.value }))} />
                                            <button
                                                className="btn btn-secondary"
                                                disabled={submitKey === 'create-review'}
                                                onClick={() => void runAction('create-review', async () => {
                                                    await observabilityApi.createReview(tender.id, selectedContribution.id, {
                                                        stage_name: reviewForm.stage_name.trim() || 'quality_review',
                                                        notes: reviewForm.notes.trim() || undefined,
                                                    });
                                                    setReviewForm({ stage_name: 'quality_review', notes: '' });
                                                }, 'Review cycle started.')}
                                            >
                                                <ShieldCheck size={15} /> Start review
                                            </button>
                                        </div>

                                        <div style={{ display: 'grid', gap: '0.65rem' }}>
                                            <div style={{ fontSize: '0.82rem', fontWeight: 600 }}>Create rework</div>
                                            <select className="input" value={reworkForm.severity} onChange={(event) => setReworkForm((current) => ({ ...current, severity: event.target.value }))}>
                                                <option value="low">Low</option>
                                                <option value="medium">Medium</option>
                                                <option value="high">High</option>
                                            </select>
                                            <textarea className="input" placeholder="Reason" rows={3} value={reworkForm.reason} onChange={(event) => setReworkForm((current) => ({ ...current, reason: event.target.value }))} />
                                            <input className="input" type="datetime-local" value={reworkForm.due_at} onChange={(event) => setReworkForm((current) => ({ ...current, due_at: event.target.value }))} />
                                            <label style={{ display: 'flex', alignItems: 'center', gap: '0.55rem', fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
                                                <input type="checkbox" checked={reworkForm.is_blocking} onChange={(event) => setReworkForm((current) => ({ ...current, is_blocking: event.target.checked }))} />
                                                Blocking rework
                                            </label>
                                            <button
                                                className="btn btn-secondary"
                                                disabled={!reworkForm.reason.trim() || submitKey === 'create-rework'}
                                                onClick={() => void runAction('create-rework', async () => {
                                                    await observabilityApi.createRework(tender.id, selectedContribution.id, {
                                                        severity: reworkForm.severity,
                                                        reason: reworkForm.reason.trim(),
                                                        due_at: toApiDate(reworkForm.due_at),
                                                        is_blocking: reworkForm.is_blocking,
                                                    });
                                                    setReworkForm({ severity: 'medium', reason: '', due_at: '', is_blocking: true });
                                                }, 'Rework action created.')}
                                            >
                                                <Wrench size={15} /> Create rework
                                            </button>
                                        </div>
                                    </div>
                                )}
                            </SectionCard>

                            <SectionCard title="Tender-wide actions" subtitle="Use these controls for compliance gates and call attendance.">
                                <div style={{ display: 'grid', gap: '1rem' }}>
                                    <div style={{ display: 'grid', gap: '0.65rem' }}>
                                        <div style={{ fontSize: '0.82rem', fontWeight: 600 }}>Create gate</div>
                                        <input className="input" placeholder="Gate name" value={gateForm.gate_name} onChange={(event) => setGateForm((current) => ({ ...current, gate_name: event.target.value }))} />
                                        <input className="input" type="datetime-local" value={gateForm.due_at} onChange={(event) => setGateForm((current) => ({ ...current, due_at: event.target.value }))} />
                                        <button
                                            className="btn btn-secondary"
                                            disabled={!gateForm.gate_name.trim() || submitKey === 'create-gate'}
                                            onClick={() => void runAction('create-gate', async () => {
                                                await observabilityApi.createGate(tender.id, {
                                                    gate_name: gateForm.gate_name.trim(),
                                                    contribution_unit_id: selectedContribution?.id,
                                                    due_at: toApiDate(gateForm.due_at),
                                                });
                                                setGateForm({ gate_name: '', due_at: '' });
                                            }, 'Compliance gate created.')}
                                        >
                                            <ShieldCheck size={15} /> Create gate
                                        </button>
                                    </div>

                                    <div style={{ display: 'grid', gap: '0.65rem' }}>
                                        <div style={{ fontSize: '0.82rem', fontWeight: 600 }}>Schedule call</div>
                                        <input className="input" placeholder="Call title" value={callForm.title} onChange={(event) => setCallForm((current) => ({ ...current, title: event.target.value }))} />
                                        <input className="input" type="datetime-local" value={callForm.scheduled_at} onChange={(event) => setCallForm((current) => ({ ...current, scheduled_at: event.target.value }))} />
                                        <button
                                            className="btn btn-secondary"
                                            disabled={!callForm.title.trim() || !callForm.scheduled_at || submitKey === 'create-call'}
                                            onClick={() => void runAction('create-call', async () => {
                                                await observabilityApi.createCall(tender.id, {
                                                    title: callForm.title.trim(),
                                                    scheduled_at: toApiDate(callForm.scheduled_at)!,
                                                });
                                                setCallForm({ title: '', scheduled_at: '' });
                                            }, 'Call scheduled.')}
                                        >
                                            <MessagesSquare size={15} /> Schedule call
                                        </button>
                                    </div>

                                    <div style={{ display: 'grid', gap: '0.65rem' }}>
                                        <div style={{ fontSize: '0.82rem', fontWeight: 600 }}>Record attendance</div>
                                        <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>{selectedCall ? `Selected call: ${selectedCall.title}` : 'Select a call from the list to record attendance.'}</div>
                                        <input className="input" placeholder="Attendee label" value={attendanceForm.attendee_label} onChange={(event) => setAttendanceForm((current) => ({ ...current, attendee_label: event.target.value }))} />
                                        <select className="input" value={attendanceForm.attendance_status} onChange={(event) => setAttendanceForm((current) => ({ ...current, attendance_status: event.target.value }))}>
                                            <option value="attended">Attended</option>
                                            <option value="absent">Absent</option>
                                            <option value="invited">Invited</option>
                                            <option value="excused">Excused</option>
                                        </select>
                                        <textarea className="input" placeholder="Attendance notes" rows={2} value={attendanceForm.notes} onChange={(event) => setAttendanceForm((current) => ({ ...current, notes: event.target.value }))} />
                                        <button
                                            className="btn btn-secondary"
                                            disabled={!selectedCall || !attendanceForm.attendee_label.trim() || submitKey === 'create-attendance'}
                                            onClick={() => void runAction('create-attendance', async () => {
                                                await observabilityApi.upsertAttendance(tender.id, selectedCall!.id, {
                                                    attendee_label: attendanceForm.attendee_label.trim(),
                                                    attendance_status: attendanceForm.attendance_status,
                                                    notes: attendanceForm.notes.trim() || undefined,
                                                });
                                                setAttendanceForm({ attendee_label: '', attendance_status: 'attended', notes: '' });
                                            }, 'Attendance recorded.')}
                                        >
                                            Record attendance
                                        </button>
                                    </div>
                                </div>
                            </SectionCard>
                        </div>
                    </div>
                </>
            )}
        </div>
    );
}


