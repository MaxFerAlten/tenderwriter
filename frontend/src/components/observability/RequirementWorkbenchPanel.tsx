import { useEffect, useRef, useState } from 'react';
import { AlertTriangle, CheckCircle2, GitMerge, RefreshCcw, ScanSearch, ShieldCheck, ShieldQuestion } from 'lucide-react';

import {
    tenderApi,
    type ConsolidatedRequirementRecord,
    type RequirementExtractionRunRecord,
    type RequirementRelationRecord,
} from '../../api/client';
import { formatDateTime } from '../../features/observability/shared';

type ReviewAction = 'approve' | 'request_changes' | 'reset_to_pending';

export interface RequirementWorkbenchData {
    candidateRuns: RequirementExtractionRunRecord[];
    consolidatedRequirements: ConsolidatedRequirementRecord[];
    obsoleteRequirements: ConsolidatedRequirementRecord[];
    reviewQueue: ConsolidatedRequirementRecord[];
    relationReviewQueue: RequirementRelationRecord[];
    relations: RequirementRelationRecord[];
    obsoleteRelations: RequirementRelationRecord[];
}

export interface RequirementWorkbenchSummary {
    extractionRuns: number;
    stagedCandidates: number;
    consolidatedRequirements: number;
    pendingReview: number;
    approved: number;
    changesRequested: number;
    totalRelations: number;
    pendingRelationReview: number;
    obsoleteRequirements: number;
    obsoleteRelations: number;
    overrideRelations: number;
    dependsOnRelations: number;
}

interface RequirementWorkbenchContentProps {
    tenderId: number | null;
    tenderTitle?: string | null;
    data: RequirementWorkbenchData;
    isLoading?: boolean;
    isRefreshing?: boolean;
    isRebuilding?: boolean;
    actionKey?: string | null;
    error?: string | null;
    message?: string | null;
    noteDrafts?: Record<number, string>;
    relationNoteDrafts?: Record<number, string>;
    onNoteChange?: (requirementId: number, value: string) => void;
    onRelationNoteChange?: (relationId: number, value: string) => void;
    onRefresh?: () => void;
    onRebuild?: () => void;
    onReview?: (requirementId: number, action: ReviewAction) => void;
    onRelationReview?: (relationId: number, action: ReviewAction) => void;
}

const EMPTY_DATA: RequirementWorkbenchData = {
    candidateRuns: [],
    consolidatedRequirements: [],
    obsoleteRequirements: [],
    reviewQueue: [],
    relationReviewQueue: [],
    relations: [],
    obsoleteRelations: [],
};

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

function reviewStateTone(state: string): { accent: string; soft: string } {
    switch (state) {
        case 'approved':
            return { accent: '#10b981', soft: 'rgba(16, 185, 129, 0.12)' };
        case 'changes_requested':
            return { accent: '#ef4444', soft: 'rgba(239, 68, 68, 0.12)' };
        case 'pending':
            return { accent: '#f59e0b', soft: 'rgba(245, 158, 11, 0.14)' };
        default:
            return { accent: '#64748b', soft: 'rgba(100, 116, 139, 0.16)' };
    }
}

function statusLabel(value: string): string {
    return value.replace(/_/g, ' ');
}

function formatConfidence(value: number | null): string {
    if (value === null || Number.isNaN(value)) {
        return 'n/a';
    }
    return `${Math.round(value * 100)}%`;
}

function runLabel(run: RequirementExtractionRunRecord): string {
    return run.filename || run.source_document_ref || `Run #${run.id}`;
}

function extractLifecycleReason(metadataJson: Record<string, unknown> | null | undefined): string | null {
    const lifecycle = metadataJson?.lifecycle;
    if (!lifecycle || typeof lifecycle !== 'object') {
        return null;
    }
    const reason = (lifecycle as Record<string, unknown>).reason;
    return typeof reason === 'string' && reason.trim() ? reason : null;
}

export function summarizeRequirementWorkbench(data: RequirementWorkbenchData): RequirementWorkbenchSummary {
    return {
        extractionRuns: data.candidateRuns.length,
        stagedCandidates: data.candidateRuns.reduce((total, run) => total + run.candidate_count, 0),
        consolidatedRequirements: data.consolidatedRequirements.length,
        pendingReview: data.consolidatedRequirements.filter((item) => item.review_state === 'pending').length,
        approved: data.consolidatedRequirements.filter((item) => item.review_state === 'approved').length,
        changesRequested: data.consolidatedRequirements.filter((item) => item.review_state === 'changes_requested').length,
        totalRelations: data.relations.length,
        pendingRelationReview: data.relationReviewQueue.length,
        obsoleteRequirements: data.obsoleteRequirements.length,
        obsoleteRelations: data.obsoleteRelations.length,
        overrideRelations: data.relations.filter((item) => item.relation_type === 'overrides').length,
        dependsOnRelations: data.relations.filter((item) => item.relation_type === 'depends_on').length,
    };
}

function EmptyState({ text }: { text: string }) {
    return <p style={{ margin: 0, color: 'var(--text-muted)', fontSize: '0.82rem' }}>{text}</p>;
}

function MetricCard({ label, value, accent }: { label: string; value: number; accent: string }) {
    return (
        <div style={{ padding: '0.85rem', borderRadius: '12px', border: `1px solid ${accent}33`, background: `${accent}12` }}>
            <div style={{ fontSize: '0.74rem', color: 'var(--text-muted)', marginBottom: '0.25rem' }}>{label}</div>
            <div style={{ fontSize: '1.5rem', fontWeight: 700 }}>{value}</div>
        </div>
    );
}

export function RequirementWorkbenchContent({
    tenderId,
    tenderTitle,
    data,
    isLoading = false,
    isRefreshing = false,
    isRebuilding = false,
    actionKey = null,
    error = null,
    message = null,
    noteDrafts = {},
    relationNoteDrafts = {},
    onNoteChange,
    onRelationNoteChange,
    onRefresh,
    onRebuild,
    onReview,
    onRelationReview,
}: RequirementWorkbenchContentProps) {
    const summary = summarizeRequirementWorkbench(data);

    return (
        <div className="card" style={{ borderColor: 'rgba(56, 189, 248, 0.24)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '1rem', marginBottom: '1rem' }}>
                <div>
                    <h3 style={{ margin: 0, display: 'flex', alignItems: 'center', gap: '0.55rem' }}>
                        <ScanSearch size={18} color="#38bdf8" /> Requirement pipeline workbench
                    </h3>
                    <p style={{ margin: '0.4rem 0 0 0', color: 'var(--text-muted)', fontSize: '0.83rem' }}>
                        Review staged extraction runs, consolidated requirements and manual triage without touching the mirrored compliance coverage.
                        {tenderTitle ? ` Current tender: ${tenderTitle}.` : ''}
                    </p>
                </div>
                <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                    <button className={`btn btn-secondary btn-sm ${isRefreshing ? 'animate-pulse' : ''}`} disabled={!tenderId || isLoading || isRefreshing || isRebuilding} onClick={onRefresh}>
                        <RefreshCcw size={14} /> Refresh pipeline
                    </button>
                    <button className={`btn btn-primary btn-sm ${isRebuilding ? 'animate-pulse' : ''}`} disabled={!tenderId || isLoading || isRefreshing || isRebuilding} onClick={onRebuild}>
                        <GitMerge size={14} /> Rebuild consolidated set
                    </button>
                </div>
            </div>

            {!tenderId ? (
                <EmptyState text="Select a tender to inspect the requirement pipeline." />
            ) : isLoading ? (
                <EmptyState text="Loading requirement pipeline..." />
            ) : (
                <>
                    {(error || message) && (
                        <div style={{ display: 'grid', gap: '0.65rem', marginBottom: '1rem' }}>
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

                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '0.75rem', marginBottom: '1rem' }}>
                        <MetricCard label="Extraction runs" value={summary.extractionRuns} accent="#38bdf8" />
                        <MetricCard label="Staged candidates" value={summary.stagedCandidates} accent="#818cf8" />
                        <MetricCard label="Consolidated" value={summary.consolidatedRequirements} accent="#10b981" />
                        <MetricCard label="Pending review" value={summary.pendingReview} accent="#f59e0b" />
                        <MetricCard label="Relation review" value={summary.pendingRelationReview} accent="#fb7185" />
                        <MetricCard label="Relations" value={summary.totalRelations} accent="#f97316" />
                        <MetricCard label="Obsolete graph" value={summary.obsoleteRequirements + summary.obsoleteRelations} accent="#64748b" />
                    </div>

                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '1rem', alignItems: 'start' }}>
                        <div style={{ padding: '0.95rem', borderRadius: '16px', border: '1px solid var(--border-color)', background: 'rgba(255,255,255,0.02)' }}>
                            <div style={{ fontSize: '0.95rem', fontWeight: 700, marginBottom: '0.7rem' }}>Latest extraction runs</div>
                            <div style={{ display: 'grid', gap: '0.75rem' }}>
                                {data.candidateRuns.length === 0 ? (
                                    <EmptyState text="No staged extraction runs yet." />
                                ) : data.candidateRuns.map((run) => (
                                    <div key={run.id} style={{ padding: '0.85rem', borderRadius: '12px', background: 'rgba(15, 23, 42, 0.35)', border: '1px solid var(--border-color)' }}>
                                        <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.75rem', alignItems: 'flex-start' }}>
                                            <div>
                                                <div style={{ fontWeight: 600 }}>{runLabel(run)}</div>
                                                <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
                                                    {statusLabel(run.extraction_method)} | {run.candidate_count} candidates | {formatDateTime(run.created_at)}
                                                </div>
                                            </div>
                                            <span style={badgeStyle('#38bdf8', 'rgba(56, 189, 248, 0.12)')}>Run #{run.id}</span>
                                        </div>
                                        <div style={{ display: 'grid', gap: '0.45rem', marginTop: '0.75rem' }}>
                                            {run.candidates.slice(0, 3).map((candidate) => (
                                                <div key={candidate.id} style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                                                    <span style={{ color: '#cbd5e1' }}>{candidate.candidate_position}.</span> {candidate.summary_text}
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>

                        <div style={{ padding: '0.95rem', borderRadius: '16px', border: '1px solid var(--border-color)', background: 'rgba(255,255,255,0.02)' }}>
                            <div style={{ fontSize: '0.95rem', fontWeight: 700, marginBottom: '0.7rem' }}>Consolidated requirement set</div>
                            <div style={{ display: 'grid', gap: '0.75rem' }}>
                                {data.consolidatedRequirements.length === 0 ? (
                                    <EmptyState text="No consolidated requirements available yet." />
                                ) : data.consolidatedRequirements.map((requirement) => {
                                    const stateTone = reviewStateTone(requirement.review_state);
                                    const requirementPriorityTone = priorityTone(requirement.priority);
                                    return (
                                        <div key={requirement.id} style={{ padding: '0.85rem', borderRadius: '12px', background: 'rgba(15, 23, 42, 0.35)', border: '1px solid var(--border-color)' }}>
                                            <div style={{ fontWeight: 600 }}>{requirement.canonical_text}</div>
                                            <div style={{ display: 'flex', gap: '0.45rem', flexWrap: 'wrap', marginTop: '0.55rem' }}>
                                                <span style={badgeStyle(requirementPriorityTone.accent, requirementPriorityTone.soft)}>{requirement.priority}</span>
                                                <span style={badgeStyle(stateTone.accent, stateTone.soft)}>{statusLabel(requirement.review_state)}</span>
                                                <span style={badgeStyle('#38bdf8', 'rgba(56, 189, 248, 0.12)')}>{requirement.graph_state}</span>
                                                {requirement.category && <span style={{ ...badgeStyle('#64748b', 'rgba(100, 116, 139, 0.14)'), textTransform: 'none' }}>{requirement.category}</span>}
                                            </div>
                                            <div style={{ display: 'grid', gap: '0.25rem', marginTop: '0.7rem', fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
                                                <div>Sources linked: {requirement.source_count}</div>
                                                <div>Confidence: {formatConfidence(requirement.confidence)}</div>
                                                <div>Method: {statusLabel(requirement.consolidation_method)}</div>
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>
                        </div>

                        <div style={{ padding: '0.95rem', borderRadius: '16px', border: '1px solid var(--border-color)', background: 'rgba(255,255,255,0.02)' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.75rem', alignItems: 'center', marginBottom: '0.7rem' }}>
                                <div style={{ fontSize: '0.95rem', fontWeight: 700 }}>Review queue</div>
                                <span style={badgeStyle('#f59e0b', 'rgba(245, 158, 11, 0.14)')}>{data.reviewQueue.length} pending</span>
                            </div>
                            <div style={{ display: 'grid', gap: '0.75rem' }}>
                                {data.reviewQueue.length === 0 ? (
                                    <EmptyState text="No pending consolidated requirements to review." />
                                ) : data.reviewQueue.map((requirement) => (
                                    <div key={requirement.id} style={{ padding: '0.85rem', borderRadius: '12px', background: 'rgba(15, 23, 42, 0.35)', border: '1px solid rgba(245, 158, 11, 0.25)' }}>
                                        <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0.55rem' }}>
                                            <ShieldQuestion size={18} color="#f59e0b" style={{ marginTop: '0.05rem', flexShrink: 0 }} />
                                            <div style={{ minWidth: 0 }}>
                                                <div style={{ fontWeight: 600 }}>{requirement.canonical_text}</div>
                                                <div style={{ marginTop: '0.35rem', fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                                                    Confidence {formatConfidence(requirement.confidence)} | Sources {requirement.source_count}
                                                </div>
                                            </div>
                                        </div>
                                        <textarea className="input" rows={3} placeholder="Reviewer notes" style={{ marginTop: '0.7rem', width: '100%' }} readOnly={!onNoteChange} value={noteDrafts[requirement.id] || ''} onChange={(event) => onNoteChange?.(requirement.id, event.target.value)} />
                                        <div style={{ display: 'flex', gap: '0.6rem', flexWrap: 'wrap', marginTop: '0.7rem' }}>
                                            <button className={`btn btn-primary btn-sm ${actionKey === `approve-${requirement.id}` ? 'animate-pulse' : ''}`} disabled={!onReview || !!actionKey} onClick={() => onReview?.(requirement.id, 'approve')}>
                                                <ShieldCheck size={14} /> Approve
                                            </button>
                                            <button className={`btn btn-secondary btn-sm ${actionKey === `request_changes-${requirement.id}` ? 'animate-pulse' : ''}`} disabled={!onReview || !!actionKey} onClick={() => onReview?.(requirement.id, 'request_changes')}>
                                                <AlertTriangle size={14} /> Request changes
                                            </button>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>

                        <div style={{ padding: '0.95rem', borderRadius: '16px', border: '1px solid var(--border-color)', background: 'rgba(255,255,255,0.02)' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.75rem', alignItems: 'center', marginBottom: '0.7rem' }}>
                                <div style={{ fontSize: '0.95rem', fontWeight: 700 }}>Requirement relations</div>
                                <div style={{ display: 'flex', gap: '0.45rem', flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                                    <span style={badgeStyle('#f97316', 'rgba(249, 115, 22, 0.14)')}>{summary.overrideRelations} overrides</span>
                                    <span style={badgeStyle('#38bdf8', 'rgba(56, 189, 248, 0.12)')}>{summary.dependsOnRelations} depends on</span>
                                </div>
                            </div>
                            <div style={{ display: 'grid', gap: '0.75rem' }}>
                                {data.relations.length === 0 ? (
                                    <EmptyState text="No inferred requirement relations yet." />
                                ) : data.relations.map((relation) => (
                                    <div key={relation.id} style={{ padding: '0.85rem', borderRadius: '12px', background: 'rgba(15, 23, 42, 0.35)', border: '1px solid var(--border-color)' }}>
                                        <div style={{ display: 'flex', gap: '0.45rem', flexWrap: 'wrap', marginBottom: '0.65rem' }}>
                                            <span style={badgeStyle('#f97316', 'rgba(249, 115, 22, 0.14)')}>{statusLabel(relation.relation_type)}</span>
                                            <span style={badgeStyle('#38bdf8', 'rgba(56, 189, 248, 0.12)')}>Confidence {formatConfidence(relation.confidence)}</span>
                                            <span style={badgeStyle(reviewStateTone(relation.review_state).accent, reviewStateTone(relation.review_state).soft)}>{statusLabel(relation.review_state)}</span>
                                            <span style={badgeStyle('#38bdf8', 'rgba(56, 189, 248, 0.12)')}>{relation.graph_state}</span>
                                        </div>
                                        <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Source requirement</div>
                                        <div style={{ fontSize: '0.86rem', fontWeight: 600, marginTop: '0.2rem' }}>{relation.source_requirement_text}</div>
                                        <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: '0.65rem' }}>Target requirement</div>
                                        <div style={{ fontSize: '0.86rem', fontWeight: 600, marginTop: '0.2rem' }}>{relation.target_requirement_text}</div>
                                    </div>
                                ))}
                            </div>
                        </div>

                        <div style={{ padding: '0.95rem', borderRadius: '16px', border: '1px solid var(--border-color)', background: 'rgba(255,255,255,0.02)' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.75rem', alignItems: 'center', marginBottom: '0.7rem' }}>
                                <div style={{ fontSize: '0.95rem', fontWeight: 700 }}>Relation review queue</div>
                                <span style={badgeStyle('#fb7185', 'rgba(251, 113, 133, 0.12)')}>{data.relationReviewQueue.length} pending</span>
                            </div>
                            <div style={{ display: 'grid', gap: '0.75rem' }}>
                                {data.relationReviewQueue.length === 0 ? (
                                    <EmptyState text="No pending inferred relations to review." />
                                ) : data.relationReviewQueue.map((relation) => (
                                    <div key={relation.id} style={{ padding: '0.85rem', borderRadius: '12px', background: 'rgba(15, 23, 42, 0.35)', border: '1px solid rgba(251, 113, 133, 0.22)' }}>
                                        <div style={{ display: 'flex', gap: '0.45rem', flexWrap: 'wrap', marginBottom: '0.65rem' }}>
                                            <span style={badgeStyle('#fb7185', 'rgba(251, 113, 133, 0.12)')}>{statusLabel(relation.relation_type)}</span>
                                            <span style={badgeStyle('#38bdf8', 'rgba(56, 189, 248, 0.12)')}>Confidence {formatConfidence(relation.confidence)}</span>
                                        </div>
                                        <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Source requirement</div>
                                        <div style={{ fontSize: '0.86rem', fontWeight: 600, marginTop: '0.2rem' }}>{relation.source_requirement_text}</div>
                                        <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: '0.65rem' }}>Target requirement</div>
                                        <div style={{ fontSize: '0.86rem', fontWeight: 600, marginTop: '0.2rem' }}>{relation.target_requirement_text}</div>
                                        <textarea
                                            className="input"
                                            rows={3}
                                            placeholder="Reviewer notes for this relation"
                                            style={{ marginTop: '0.7rem', width: '100%' }}
                                            readOnly={!onRelationNoteChange}
                                            value={relationNoteDrafts[relation.id] || ''}
                                            onChange={(event) => onRelationNoteChange?.(relation.id, event.target.value)}
                                        />
                                        <div style={{ display: 'flex', gap: '0.6rem', flexWrap: 'wrap', marginTop: '0.7rem' }}>
                                            <button
                                                className={`btn btn-primary btn-sm ${actionKey === `relation-approve-${relation.id}` ? 'animate-pulse' : ''}`}
                                                disabled={!onRelationReview || !!actionKey}
                                                onClick={() => onRelationReview?.(relation.id, 'approve')}
                                            >
                                                <ShieldCheck size={14} /> Approve
                                            </button>
                                            <button
                                                className={`btn btn-secondary btn-sm ${actionKey === `relation-request_changes-${relation.id}` ? 'animate-pulse' : ''}`}
                                                disabled={!onRelationReview || !!actionKey}
                                                onClick={() => onRelationReview?.(relation.id, 'request_changes')}
                                            >
                                                <AlertTriangle size={14} /> Request changes
                                            </button>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>

                        <div style={{ padding: '0.95rem', borderRadius: '16px', border: '1px solid rgba(100, 116, 139, 0.24)', background: 'rgba(148, 163, 184, 0.06)' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.75rem', alignItems: 'center', marginBottom: '0.7rem' }}>
                                <div style={{ fontSize: '0.95rem', fontWeight: 700 }}>Graph audit trail</div>
                                <div style={{ display: 'flex', gap: '0.45rem', flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                                    <span style={badgeStyle('#64748b', 'rgba(100, 116, 139, 0.16)')}>{summary.obsoleteRequirements} obsolete requirements</span>
                                    <span style={badgeStyle('#94a3b8', 'rgba(148, 163, 184, 0.16)')}>{summary.obsoleteRelations} obsolete relations</span>
                                </div>
                            </div>
                            <div style={{ display: 'grid', gap: '1rem' }}>
                                <div style={{ display: 'grid', gap: '0.75rem' }}>
                                    <div style={{ fontSize: '0.86rem', fontWeight: 700 }}>Obsolete consolidated requirements</div>
                                    {data.obsoleteRequirements.length === 0 ? (
                                        <EmptyState text="No obsolete consolidated requirements recorded yet." />
                                    ) : data.obsoleteRequirements.map((requirement) => (
                                        <div key={requirement.id} style={{ padding: '0.85rem', borderRadius: '12px', background: 'rgba(15, 23, 42, 0.28)', border: '1px dashed rgba(148, 163, 184, 0.26)' }}>
                                            <div style={{ fontWeight: 600 }}>{requirement.canonical_text}</div>
                                            <div style={{ display: 'flex', gap: '0.45rem', flexWrap: 'wrap', marginTop: '0.55rem' }}>
                                                <span style={badgeStyle('#64748b', 'rgba(100, 116, 139, 0.16)')}>{requirement.graph_state}</span>
                                                <span style={badgeStyle(reviewStateTone(requirement.review_state).accent, reviewStateTone(requirement.review_state).soft)}>{statusLabel(requirement.review_state)}</span>
                                            </div>
                                            <div style={{ display: 'grid', gap: '0.25rem', marginTop: '0.7rem', fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
                                                <div>Confidence: {formatConfidence(requirement.confidence)}</div>
                                                <div>Lifecycle reason: {extractLifecycleReason(requirement.metadata_json) || 'n/a'}</div>
                                            </div>
                                        </div>
                                    ))}
                                </div>

                                <div style={{ display: 'grid', gap: '0.75rem' }}>
                                    <div style={{ fontSize: '0.86rem', fontWeight: 700 }}>Obsolete requirement relations</div>
                                    {data.obsoleteRelations.length === 0 ? (
                                        <EmptyState text="No obsolete requirement relations recorded yet." />
                                    ) : data.obsoleteRelations.map((relation) => (
                                        <div key={relation.id} style={{ padding: '0.85rem', borderRadius: '12px', background: 'rgba(15, 23, 42, 0.28)', border: '1px dashed rgba(148, 163, 184, 0.26)' }}>
                                            <div style={{ display: 'flex', gap: '0.45rem', flexWrap: 'wrap', marginBottom: '0.65rem' }}>
                                                <span style={badgeStyle('#94a3b8', 'rgba(148, 163, 184, 0.16)')}>{relation.graph_state}</span>
                                                <span style={badgeStyle('#f97316', 'rgba(249, 115, 22, 0.14)')}>{statusLabel(relation.relation_type)}</span>
                                                <span style={badgeStyle(reviewStateTone(relation.review_state).accent, reviewStateTone(relation.review_state).soft)}>{statusLabel(relation.review_state)}</span>
                                            </div>
                                            <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Source requirement</div>
                                            <div style={{ fontSize: '0.86rem', fontWeight: 600, marginTop: '0.2rem' }}>{relation.source_requirement_text}</div>
                                            <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: '0.65rem' }}>Target requirement</div>
                                            <div style={{ fontSize: '0.86rem', fontWeight: 600, marginTop: '0.2rem' }}>{relation.target_requirement_text}</div>
                                            <div style={{ display: 'grid', gap: '0.25rem', marginTop: '0.7rem', fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
                                                <div>Confidence: {formatConfidence(relation.confidence)}</div>
                                                <div>Lifecycle reason: {extractLifecycleReason(relation.metadata_json) || 'n/a'}</div>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        </div>
                    </div>
                </>
            )}
        </div>
    );
}

interface RequirementWorkbenchPanelProps {
    tenderId: number | null;
    tenderTitle?: string | null;
}

export default function RequirementWorkbenchPanel({ tenderId, tenderTitle }: RequirementWorkbenchPanelProps) {
    const [data, setData] = useState<RequirementWorkbenchData>(EMPTY_DATA);
    const [isLoading, setIsLoading] = useState(false);
    const [isRefreshing, setIsRefreshing] = useState(false);
    const [isRebuilding, setIsRebuilding] = useState(false);
    const [actionKey, setActionKey] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [message, setMessage] = useState<string | null>(null);
    const [noteDrafts, setNoteDrafts] = useState<Record<number, string>>({});
    const [relationNoteDrafts, setRelationNoteDrafts] = useState<Record<number, string>>({});
    const requestIdRef = useRef(0);

    const loadPipeline = async (refresh = false) => {
        if (!tenderId) {
            setData(EMPTY_DATA);
            setNoteDrafts({});
            setRelationNoteDrafts({});
            return;
        }

        const requestId = ++requestIdRef.current;
        setError(null);
        setMessage(null);
        if (refresh) {
            setIsRefreshing(true);
        } else {
            setIsLoading(true);
        }

        try {
            const [
                candidateRuns,
                consolidatedRequirements,
                obsoleteRequirements,
                reviewQueue,
                relationReviewQueue,
                relations,
                obsoleteRelations,
            ] = await Promise.all([
                tenderApi.getRequirementCandidateRuns(tenderId, { limit_runs: 3 }),
                tenderApi.getConsolidatedRequirements(tenderId),
                tenderApi.getConsolidatedRequirements(tenderId, { graph_state: 'obsolete' }),
                tenderApi.getConsolidatedRequirementReviewQueue(tenderId, { review_state: 'pending', limit: 10 }),
                tenderApi.getConsolidatedRequirementRelationReviewQueue(tenderId, { review_state: 'pending', limit: 10 }),
                tenderApi.getConsolidatedRequirementRelations(tenderId),
                tenderApi.getConsolidatedRequirementRelations(tenderId, { graph_state: 'obsolete' }),
            ]);

            if (requestId !== requestIdRef.current) {
                return;
            }

            setData({
                candidateRuns: candidateRuns.items,
                consolidatedRequirements: consolidatedRequirements.items,
                obsoleteRequirements: obsoleteRequirements.items,
                reviewQueue: reviewQueue.items,
                relationReviewQueue: relationReviewQueue.items,
                relations: relations.items,
                obsoleteRelations: obsoleteRelations.items,
            });
            setNoteDrafts((current) => {
                const nextDrafts: Record<number, string> = {};
                reviewQueue.items.forEach((item) => {
                    nextDrafts[item.id] = current[item.id] || '';
                });
                return nextDrafts;
            });
            setRelationNoteDrafts((current) => {
                const nextDrafts: Record<number, string> = {};
                relationReviewQueue.items.forEach((item) => {
                    nextDrafts[item.id] = current[item.id] || '';
                });
                return nextDrafts;
            });
        } catch (pipelineError) {
            if (requestId !== requestIdRef.current) {
                return;
            }
            setError(pipelineError instanceof Error ? pipelineError.message : 'Failed to load requirement pipeline.');
        } finally {
            if (requestId === requestIdRef.current) {
                setIsLoading(false);
                setIsRefreshing(false);
            }
        }
    };

    useEffect(() => {
        if (!tenderId) {
            setData(EMPTY_DATA);
            setError(null);
            setMessage(null);
            setNoteDrafts({});
            setRelationNoteDrafts({});
            return;
        }
        void loadPipeline();
    }, [tenderId]);

    const handleRebuild = async () => {
        if (!tenderId) {
            return;
        }
        setIsRebuilding(true);
        setError(null);
        setMessage(null);
        try {
            const rebuilt = await tenderApi.rebuildConsolidatedRequirements(tenderId, { limit_runs: 5 });
            await loadPipeline(true);
            setMessage(`Consolidated set rebuilt from ${rebuilt.total_items} requirement candidates.`);
        } catch (rebuildError) {
            setError(rebuildError instanceof Error ? rebuildError.message : 'Failed to rebuild consolidated requirements.');
        } finally {
            setIsRebuilding(false);
        }
    };

    const handleReview = async (requirementId: number, action: ReviewAction) => {
        if (!tenderId) {
            return;
        }
        setActionKey(`${action}-${requirementId}`);
        setError(null);
        setMessage(null);
        try {
            const reviewResult = await tenderApi.reviewConsolidatedRequirement(tenderId, requirementId, {
                action,
                notes: noteDrafts[requirementId]?.trim() || undefined,
            });
            setNoteDrafts((current) => ({ ...current, [requirementId]: '' }));
            await loadPipeline(true);
            setMessage(`Requirement #${reviewResult.requirement.id} moved to ${statusLabel(reviewResult.review.new_review_state)}.`);
        } catch (reviewError) {
            setError(reviewError instanceof Error ? reviewError.message : 'Failed to review consolidated requirement.');
        } finally {
            setActionKey(null);
        }
    };

    const handleRelationReview = async (relationId: number, action: ReviewAction) => {
        if (!tenderId) {
            return;
        }
        setActionKey(`relation-${action}-${relationId}`);
        setError(null);
        setMessage(null);
        try {
            const reviewResult = await tenderApi.reviewConsolidatedRequirementRelation(tenderId, relationId, {
                action,
                notes: relationNoteDrafts[relationId]?.trim() || undefined,
            });
            setRelationNoteDrafts((current) => ({ ...current, [relationId]: '' }));
            await loadPipeline(true);
            setMessage(`Relation #${reviewResult.relation.id} moved to ${statusLabel(reviewResult.review.new_review_state)}.`);
        } catch (reviewError) {
            setError(reviewError instanceof Error ? reviewError.message : 'Failed to review inferred requirement relation.');
        } finally {
            setActionKey(null);
        }
    };

    return (
        <RequirementWorkbenchContent
            tenderId={tenderId}
            tenderTitle={tenderTitle}
            data={data}
            isLoading={isLoading}
            isRefreshing={isRefreshing}
            isRebuilding={isRebuilding}
            actionKey={actionKey}
            error={error}
            message={message}
            noteDrafts={noteDrafts}
            relationNoteDrafts={relationNoteDrafts}
            onNoteChange={(requirementId, value) => {
                setNoteDrafts((current) => ({ ...current, [requirementId]: value }));
            }}
            onRelationNoteChange={(relationId, value) => {
                setRelationNoteDrafts((current) => ({ ...current, [relationId]: value }));
            }}
            onRefresh={() => {
                void loadPipeline(true);
            }}
            onRebuild={() => {
                void handleRebuild();
            }}
            onReview={(requirementId, action) => {
                void handleReview(requirementId, action);
            }}
            onRelationReview={(relationId, action) => {
                void handleRelationReview(relationId, action);
            }}
        />
    );
}
