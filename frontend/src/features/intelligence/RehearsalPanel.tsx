import { CheckCircle2, Loader2, Play, Users, XCircle } from 'lucide-react';

import type {
    RehearsalMode,
    RehearsalRecommendation,
    RehearsalRun,
} from '../../api/client';

import { HEALTH_COLOR, StatusBadge } from './shared';

const REHEARSAL_MODES: RehearsalMode[] = ['full', 'section', 'pre_gate'];

const REHEARSAL_STATUS_COLOR: Record<string, string> = {
    pending: '#94a3b8',
    running: '#60a5fa',
    completed: '#10b981',
    failed: '#ef4444',
    cancelled: '#9ca3af',
};

const REHEARSAL_SEVERITY_COLOR: Record<string, string> = {
    high: '#ef4444',
    medium: '#f59e0b',
    low: '#60a5fa',
};

const REHEARSAL_REC_STATE_COLOR: Record<string, string> = {
    proposed: '#60a5fa',
    accepted: '#10b981',
    dismissed: '#9ca3af',
};

interface RehearsalPanelProps {
    runs: RehearsalRun[];
    loading: boolean;
    error: string | null;
    proposalId: string;
    onProposalIdChange: (value: string) => void;
    mode: RehearsalMode;
    onModeChange: (value: RehearsalMode) => void;
    creating: boolean;
    onCreate: () => void;
    selectedRunId: number | null;
    onSelectRun: (id: number) => void;
    recommendationBusyId: number | null;
    onAccept: (runId: number, recommendationId: number) => void;
    onDismiss: (runId: number, recommendationId: number) => void;
    disabled: boolean;
}

export function RehearsalPanel({
    runs,
    loading,
    error,
    proposalId,
    onProposalIdChange,
    mode,
    onModeChange,
    creating,
    onCreate,
    selectedRunId,
    onSelectRun,
    recommendationBusyId,
    onAccept,
    onDismiss,
    disabled,
}: RehearsalPanelProps) {
    const selectedRun = runs.find((r) => r.id === selectedRunId) ?? null;
    return (
        <section
            data-testid="rehearsal-panel"
            style={{
                padding: '1.25rem',
                background: 'rgba(17, 24, 39, 0.85)',
                border: '1px solid rgba(255, 255, 255, 0.08)',
                borderRadius: '0.75rem',
                marginBottom: '1rem',
                display: 'grid',
                gap: '0.75rem',
            }}
        >
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <Users size={18} color="#a78bfa" />
                <h2 style={{ fontSize: '1.05rem', color: 'white', margin: 0 }}>
                    Persona Rehearsal
                </h2>
            </div>
            <p style={{ color: '#9ca3af', margin: 0, fontSize: '0.85rem' }}>
                Simulates reviewer personas over the proposal. Findings drive recommendations
                that you can accept (becomes a rework action) or dismiss.
            </p>
            <form
                onSubmit={(e) => {
                    e.preventDefault();
                    onCreate();
                }}
                style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', alignItems: 'center' }}
            >
                <input
                    value={proposalId}
                    onChange={(e) => onProposalIdChange(e.target.value)}
                    placeholder="Proposal id"
                    inputMode="numeric"
                    pattern="[0-9]*"
                    data-testid="rehearsal-proposal-id"
                    style={{
                        width: '160px',
                        padding: '0.55rem 0.75rem',
                        background: 'rgba(15, 23, 42, 0.8)',
                        color: 'white',
                        border: '1px solid rgba(255, 255, 255, 0.1)',
                        borderRadius: '0.5rem',
                    }}
                />
                <select
                    value={mode}
                    onChange={(e) => onModeChange(e.target.value as RehearsalMode)}
                    data-testid="rehearsal-mode"
                    style={{
                        padding: '0.55rem 0.75rem',
                        background: 'rgba(15, 23, 42, 0.8)',
                        color: 'white',
                        border: '1px solid rgba(255, 255, 255, 0.1)',
                        borderRadius: '0.5rem',
                    }}
                >
                    {REHEARSAL_MODES.map((m) => (
                        <option key={m} value={m}>
                            {m}
                        </option>
                    ))}
                </select>
                <button
                    type="submit"
                    disabled={creating || disabled}
                    data-testid="rehearsal-create-btn"
                    style={{
                        padding: '0.55rem 1rem',
                        background: 'rgba(167, 139, 250, 0.18)',
                        color: 'white',
                        border: '1px solid rgba(167, 139, 250, 0.4)',
                        borderRadius: '0.5rem',
                        cursor: creating || disabled ? 'not-allowed' : 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '0.4rem',
                    }}
                >
                    {creating ? <Loader2 size={16} className="spin" /> : <Play size={16} />}
                    <span>Run rehearsal</span>
                </button>
                {loading && <Loader2 size={16} className="spin" color="#a78bfa" />}
            </form>
            {error && (
                <div data-testid="rehearsal-error" style={{ color: '#fca5a5', fontSize: '0.85rem' }}>
                    {error}
                </div>
            )}
            {runs.length === 0 ? (
                <div
                    data-testid="rehearsal-empty"
                    style={{ color: '#9ca3af', fontSize: '0.9rem' }}
                >
                    No rehearsal runs yet for this tender.
                </div>
            ) : (
                <div style={{ display: 'grid', gap: '0.75rem' }}>
                    <div
                        data-testid="rehearsal-run-list"
                        style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem' }}
                    >
                        {runs.map((run) => {
                            const isSelected = run.id === selectedRunId;
                            const color = REHEARSAL_STATUS_COLOR[run.status] ?? '#94a3b8';
                            return (
                                <button
                                    key={run.id}
                                    type="button"
                                    onClick={() => onSelectRun(run.id)}
                                    data-testid={`rehearsal-run-${run.id}`}
                                    style={{
                                        padding: '0.4rem 0.65rem',
                                        background: isSelected
                                            ? 'rgba(167, 139, 250, 0.25)'
                                            : 'rgba(15, 23, 42, 0.6)',
                                        border: `1px solid ${isSelected ? 'rgba(167, 139, 250, 0.6)' : 'rgba(148, 163, 184, 0.2)'}`,
                                        borderRadius: '0.5rem',
                                        color: 'white',
                                        cursor: 'pointer',
                                        display: 'flex',
                                        alignItems: 'center',
                                        gap: '0.4rem',
                                        fontSize: '0.8rem',
                                    }}
                                >
                                    <span>#{run.id}</span>
                                    <StatusBadge label={run.status} color={color} />
                                    <span style={{ color: '#9ca3af' }}>{run.mode}</span>
                                </button>
                            );
                        })}
                    </div>
                    {selectedRun && (
                        <RehearsalRunDetails
                            run={selectedRun}
                            recommendationBusyId={recommendationBusyId}
                            onAccept={onAccept}
                            onDismiss={onDismiss}
                        />
                    )}
                </div>
            )}
        </section>
    );
}

interface RehearsalRunDetailsProps {
    run: RehearsalRun;
    recommendationBusyId: number | null;
    onAccept: (runId: number, recommendationId: number) => void;
    onDismiss: (runId: number, recommendationId: number) => void;
}

function RehearsalRunDetails({
    run,
    recommendationBusyId,
    onAccept,
    onDismiss,
}: RehearsalRunDetailsProps) {
    const healthColor = run.health_projection ? HEALTH_COLOR[run.health_projection] : '#94a3b8';
    return (
        <div data-testid="rehearsal-run-details" style={{ display: 'grid', gap: '0.75rem' }}>
            <div
                style={{
                    display: 'flex',
                    flexWrap: 'wrap',
                    gap: '0.4rem',
                    alignItems: 'center',
                    padding: '0.6rem 0.75rem',
                    background: 'rgba(15, 23, 42, 0.6)',
                    border: '1px solid rgba(148, 163, 184, 0.15)',
                    borderRadius: '0.5rem',
                }}
            >
                <strong style={{ color: 'white' }}>Run #{run.id}</strong>
                {run.health_projection && (
                    <StatusBadge label={`health: ${run.health_projection}`} color={healthColor} />
                )}
                {run.overall_score !== null && (
                    <StatusBadge label={`score: ${run.overall_score.toFixed(1)}`} color="#a78bfa" />
                )}
                {run.persona_divergence !== null && (
                    <StatusBadge
                        label={`divergence: ${run.persona_divergence.toFixed(2)}`}
                        color="#38bdf8"
                    />
                )}
                <span style={{ color: '#9ca3af', fontSize: '0.8rem' }}>
                    proposal #{run.proposal_id} · {run.mode}
                </span>
            </div>
            {run.error_message && (
                <div style={{ color: '#fca5a5', fontSize: '0.85rem' }}>{run.error_message}</div>
            )}
            <div style={{ display: 'grid', gap: '0.5rem' }}>
                <h3 style={{ color: 'white', fontSize: '0.95rem', margin: 0 }}>Personas</h3>
                {run.persona_results.length === 0 ? (
                    <div style={{ color: '#9ca3af', fontSize: '0.85rem' }}>
                        No persona evaluations yet.
                    </div>
                ) : (
                    <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'grid', gap: '0.4rem' }}>
                        {run.persona_results.map((p) => (
                            <li
                                key={p.persona_id}
                                style={{
                                    padding: '0.5rem 0.75rem',
                                    background: 'rgba(15, 23, 42, 0.6)',
                                    border: '1px solid rgba(148, 163, 184, 0.15)',
                                    borderRadius: '0.5rem',
                                    display: 'flex',
                                    flexWrap: 'wrap',
                                    gap: '0.4rem',
                                    alignItems: 'center',
                                }}
                            >
                                <strong style={{ color: 'white' }}>{p.display_name}</strong>
                                <span style={{ color: '#9ca3af', fontSize: '0.8rem' }}>
                                    {p.reviewer_type}
                                </span>
                                <StatusBadge label={`score ${p.score.toFixed(1)}`} color="#a78bfa" />
                                <StatusBadge
                                    label={`${p.findings.length} findings`}
                                    color="#f59e0b"
                                />
                                <StatusBadge
                                    label={`${p.questions.length} questions`}
                                    color="#60a5fa"
                                />
                            </li>
                        ))}
                    </ul>
                )}
            </div>
            <div style={{ display: 'grid', gap: '0.5rem' }}>
                <h3 style={{ color: 'white', fontSize: '0.95rem', margin: 0 }}>Recommendations</h3>
                {run.recommendations.length === 0 ? (
                    <div
                        data-testid="rehearsal-recs-empty"
                        style={{ color: '#9ca3af', fontSize: '0.85rem' }}
                    >
                        No recommendations.
                    </div>
                ) : (
                    <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'grid', gap: '0.4rem' }}>
                        {run.recommendations.map((rec) => (
                            <RehearsalRecommendationItem
                                key={rec.id ?? `${rec.scope_type}-${rec.scope_id}-${rec.source_persona_id}`}
                                runId={run.id}
                                rec={rec}
                                busy={recommendationBusyId !== null && recommendationBusyId === rec.id}
                                onAccept={onAccept}
                                onDismiss={onDismiss}
                            />
                        ))}
                    </ul>
                )}
            </div>
        </div>
    );
}

interface RehearsalRecommendationItemProps {
    runId: number;
    rec: RehearsalRecommendation;
    busy: boolean;
    onAccept: (runId: number, recommendationId: number) => void;
    onDismiss: (runId: number, recommendationId: number) => void;
}

function RehearsalRecommendationItem({
    runId,
    rec,
    busy,
    onAccept,
    onDismiss,
}: RehearsalRecommendationItemProps) {
    const sevColor = REHEARSAL_SEVERITY_COLOR[rec.severity] ?? '#94a3b8';
    const stateColor = REHEARSAL_REC_STATE_COLOR[rec.status] ?? '#94a3b8';
    const actionable = rec.id !== null && rec.status === 'proposed';
    return (
        <li
            data-testid={`rehearsal-rec-${rec.id ?? 'unsaved'}`}
            style={{
                padding: '0.6rem 0.75rem',
                background: 'rgba(15, 23, 42, 0.6)',
                border: '1px solid rgba(148, 163, 184, 0.15)',
                borderRadius: '0.5rem',
                display: 'grid',
                gap: '0.4rem',
            }}
        >
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem', alignItems: 'center' }}>
                <StatusBadge label={rec.severity} color={sevColor} />
                <StatusBadge label={rec.status} color={stateColor} />
                {rec.is_blocking && <StatusBadge label="blocking" color="#ef4444" />}
                <span style={{ color: '#9ca3af', fontSize: '0.8rem' }}>
                    {rec.scope_type} · {rec.scope_id}
                </span>
                {rec.suggested_owner_role && (
                    <span style={{ color: '#9ca3af', fontSize: '0.8rem' }}>
                        owner: {rec.suggested_owner_role}
                    </span>
                )}
            </div>
            <div style={{ color: 'white', fontSize: '0.9rem' }}>{rec.rationale}</div>
            {rec.linked_rework_action_id !== null && (
                <div style={{ color: '#9ca3af', fontSize: '0.8rem' }}>
                    Linked rework action #{rec.linked_rework_action_id}
                </div>
            )}
            {actionable && rec.id !== null && (
                <div style={{ display: 'flex', gap: '0.4rem' }}>
                    <button
                        type="button"
                        disabled={busy}
                        onClick={() => onAccept(runId, rec.id as number)}
                        data-testid={`rehearsal-accept-${rec.id}`}
                        style={{
                            padding: '0.35rem 0.65rem',
                            background: 'rgba(16, 185, 129, 0.18)',
                            color: 'white',
                            border: '1px solid rgba(16, 185, 129, 0.4)',
                            borderRadius: '0.4rem',
                            cursor: busy ? 'not-allowed' : 'pointer',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '0.3rem',
                            fontSize: '0.8rem',
                        }}
                    >
                        {busy ? <Loader2 size={14} className="spin" /> : <CheckCircle2 size={14} />}
                        <span>Accept</span>
                    </button>
                    <button
                        type="button"
                        disabled={busy}
                        onClick={() => onDismiss(runId, rec.id as number)}
                        data-testid={`rehearsal-dismiss-${rec.id}`}
                        style={{
                            padding: '0.35rem 0.65rem',
                            background: 'rgba(148, 163, 184, 0.18)',
                            color: 'white',
                            border: '1px solid rgba(148, 163, 184, 0.4)',
                            borderRadius: '0.4rem',
                            cursor: busy ? 'not-allowed' : 'pointer',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '0.3rem',
                            fontSize: '0.8rem',
                        }}
                    >
                        {busy ? <Loader2 size={14} className="spin" /> : <XCircle size={14} />}
                        <span>Dismiss</span>
                    </button>
                </div>
            )}
        </li>
    );
}
