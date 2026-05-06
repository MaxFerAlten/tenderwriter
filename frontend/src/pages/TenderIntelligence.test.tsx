import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';

import { RehearsalPanel } from '../features/intelligence/RehearsalPanel';
import type {
    RehearsalRecommendation,
    RehearsalRun,
} from '../api/client';

function makeRecommendation(over: Partial<RehearsalRecommendation> = {}): RehearsalRecommendation {
    return {
        id: 11,
        scope_type: 'proposal_section',
        scope_id: 'sec-1',
        severity: 'high',
        is_blocking: true,
        rationale: 'Section is missing measurable acceptance criteria.',
        suggested_owner_role: 'bid_manager',
        source_persona_id: 'auditor',
        status: 'proposed',
        linked_rework_action_id: null,
        ...over,
    };
}

function makeRun(over: Partial<RehearsalRun> = {}): RehearsalRun {
    return {
        id: 7,
        tender_id: 10,
        proposal_id: 3,
        mode: 'full',
        status: 'completed',
        overall_score: 72.5,
        health_projection: 'amber',
        persona_divergence: 0.31,
        started_at: '2026-04-19T18:30:00Z',
        completed_at: '2026-04-19T18:40:00Z',
        persona_results: [
            {
                persona_id: 'auditor',
                display_name: 'Lead Auditor',
                reviewer_type: 'compliance',
                score: 71.2,
                findings: [
                    {
                        category: 'compliance_risk',
                        severity: 'high',
                        summary: 'Missing audit trail.',
                        scope_type: 'proposal_section',
                        scope_id: 'sec-1',
                        supporting_refs: [],
                    },
                ],
                questions: [{ question: 'Where is the audit trail?', rationale: null }],
                metrics: {},
            },
        ],
        recommendations: [makeRecommendation()],
        error_message: null,
        version: 'tw-rehearsal-v1',
        ...over,
    };
}

const noop = () => {};

describe('RehearsalPanel', () => {
    it('renders empty state when no runs exist', () => {
        const html = renderToStaticMarkup(
            <RehearsalPanel
                runs={[]}
                loading={false}
                error={null}
                proposalId=""
                onProposalIdChange={noop}
                mode="full"
                onModeChange={noop}
                creating={false}
                onCreate={noop}
                selectedRunId={null}
                onSelectRun={noop}
                recommendationBusyId={null}
                onAccept={noop}
                onDismiss={noop}
                disabled={false}
            />,
        );
        expect(html).toContain('Persona Rehearsal');
        expect(html).toContain('No rehearsal runs yet');
        expect(html).not.toContain('Run #');
    });

    it('renders run list with status, score and persona summary when a run is selected', () => {
        const run = makeRun();
        const html = renderToStaticMarkup(
            <RehearsalPanel
                runs={[run]}
                loading={false}
                error={null}
                proposalId="3"
                onProposalIdChange={noop}
                mode="full"
                onModeChange={noop}
                creating={false}
                onCreate={noop}
                selectedRunId={run.id}
                onSelectRun={noop}
                recommendationBusyId={null}
                onAccept={noop}
                onDismiss={noop}
                disabled={false}
            />,
        );
        expect(html).toContain('Run #7');
        expect(html).toContain('completed');
        expect(html).toContain('health: amber');
        expect(html).toContain('score: 72.5');
        expect(html).toContain('divergence: 0.31');
        expect(html).toContain('Lead Auditor');
        expect(html).toContain('Section is missing measurable acceptance criteria.');
    });

    it('shows Accept and Dismiss buttons only for proposed recommendations with id', () => {
        const proposed = makeRecommendation({ id: 1, status: 'proposed' });
        const accepted = makeRecommendation({ id: 2, status: 'accepted', linked_rework_action_id: 99 });
        const unsaved = makeRecommendation({ id: null, status: 'proposed' });
        const run = makeRun({ recommendations: [proposed, accepted, unsaved] });
        const html = renderToStaticMarkup(
            <RehearsalPanel
                runs={[run]}
                loading={false}
                error={null}
                proposalId="3"
                onProposalIdChange={noop}
                mode="full"
                onModeChange={noop}
                creating={false}
                onCreate={noop}
                selectedRunId={run.id}
                onSelectRun={noop}
                recommendationBusyId={null}
                onAccept={noop}
                onDismiss={noop}
                disabled={false}
            />,
        );
        expect(html).toContain('rehearsal-accept-1');
        expect(html).toContain('rehearsal-dismiss-1');
        expect(html).not.toContain('rehearsal-accept-2');
        expect(html).not.toContain('rehearsal-dismiss-2');
        expect(html).toContain('Linked rework action #99');
        expect(html).toContain('rehearsal-rec-unsaved');
    });

    it('renders error message when error prop is set', () => {
        const html = renderToStaticMarkup(
            <RehearsalPanel
                runs={[]}
                loading={false}
                error="Something failed"
                proposalId=""
                onProposalIdChange={noop}
                mode="full"
                onModeChange={noop}
                creating={false}
                onCreate={noop}
                selectedRunId={null}
                onSelectRun={noop}
                recommendationBusyId={null}
                onAccept={noop}
                onDismiss={noop}
                disabled={false}
            />,
        );
        expect(html).toContain('Something failed');
    });

    it('does not crash with vi spy callbacks (smoke)', () => {
        const onCreate = vi.fn();
        const html = renderToStaticMarkup(
            <RehearsalPanel
                runs={[]}
                loading={false}
                error={null}
                proposalId=""
                onProposalIdChange={noop}
                mode="full"
                onModeChange={noop}
                creating={false}
                onCreate={onCreate}
                selectedRunId={null}
                onSelectRun={noop}
                recommendationBusyId={null}
                onAccept={noop}
                onDismiss={noop}
                disabled={true}
            />,
        );
        expect(html).toContain('Run rehearsal');
        expect(onCreate).not.toHaveBeenCalled();
    });
});
