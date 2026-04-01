import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const keycloakMock = vi.hoisted(() => ({
    getKeycloakToken: vi.fn(),
}));

vi.mock('../auth/keycloak', () => keycloakMock);

import {
    authApi,
    kpiAdminApi,
    observabilityApi,
    prefetchTenderChatContext,
    prefetchTenderChatRetrospective,
    proposalApi,
    ragApi,
    resetTenderChatContextCacheForTest,
    resolveTenderChatContext,
    resolveTenderChatRetrospective,
    tenderApi,
} from './client';

const fetchMock = vi.fn();
const storage = new Map<string, string>();

const localStorageMock = {
    getItem: vi.fn((key: string) => storage.get(key) ?? null),
    setItem: vi.fn((key: string, value: string) => {
        storage.set(key, value);
    }),
    removeItem: vi.fn((key: string) => {
        storage.delete(key);
    }),
    clear: vi.fn(() => {
        storage.clear();
    }),
};

function createStreamResponse(chunks: string[]): Response {
    const encoder = new TextEncoder();
    return new Response(new ReadableStream({
        start(controller) {
            chunks.forEach((chunk) => controller.enqueue(encoder.encode(chunk)));
            controller.close();
        },
    }), {
        status: 200,
        headers: { 'Content-Type': 'text/event-stream' },
    });
}

describe('kpiAdminApi', () => {
    beforeEach(() => {
        storage.clear();
        fetchMock.mockReset();
        keycloakMock.getKeycloakToken.mockReset();
        vi.stubGlobal('fetch', fetchMock);
        vi.stubGlobal('localStorage', localStorageMock);
    });

    afterEach(() => {
        resetTenderChatContextCacheForTest();
        vi.unstubAllGlobals();
        vi.restoreAllMocks();
    });

    it('refreshes the bearer token for keycloak sessions before JSON requests', async () => {
        localStorageMock.setItem('token', 'stale-keycloak-token');
        localStorageMock.setItem('auth_session_kind', 'keycloak');
        keycloakMock.getKeycloakToken.mockResolvedValue('fresh-keycloak-token');
        fetchMock.mockResolvedValue(
            new Response(JSON.stringify({ id: 1, email: 'admin@test.local', name: 'Admin', role: 'admin', auth_source: 'keycloak' }), {
                status: 200,
                headers: { 'Content-Type': 'application/json' },
            })
        );

        const response = await authApi.me();

        expect(response.auth_source).toBe('keycloak');
        expect(keycloakMock.getKeycloakToken).toHaveBeenCalledTimes(1);
        expect(fetchMock).toHaveBeenCalledWith(
            '/api/auth/me',
            expect.objectContaining({
                method: 'GET',
                headers: expect.objectContaining({
                    Authorization: 'Bearer fresh-keycloak-token',
                }),
            })
        );
    });

    it('retries once after a 401 when a keycloak token can be refreshed', async () => {
        localStorageMock.setItem('token', 'expired-keycloak-token');
        localStorageMock.setItem('auth_session_kind', 'keycloak');
        keycloakMock.getKeycloakToken
            .mockResolvedValueOnce('expired-keycloak-token')
            .mockResolvedValueOnce('fresh-keycloak-token');
        fetchMock
            .mockResolvedValueOnce(
                new Response(JSON.stringify({ detail: 'Token expired' }), {
                    status: 401,
                    headers: { 'Content-Type': 'application/json' },
                })
            )
            .mockResolvedValueOnce(
                new Response(JSON.stringify({ id: 1, email: 'admin@test.local', name: 'Admin', role: 'admin', auth_source: 'keycloak' }), {
                    status: 200,
                    headers: { 'Content-Type': 'application/json' },
                })
            );

        const response = await authApi.me();

        expect(response.email).toBe('admin@test.local');
        expect(keycloakMock.getKeycloakToken).toHaveBeenCalledTimes(2);
        expect(fetchMock).toHaveBeenNthCalledWith(
            2,
            '/api/auth/me',
            expect.objectContaining({
                method: 'GET',
                headers: expect.objectContaining({
                    Authorization: 'Bearer fresh-keycloak-token',
                }),
            })
        );
    });

    it('queries portfolio overview through the admin KPI BFF', async () => {
        localStorageMock.setItem('token', 'admin-token');
        fetchMock.mockResolvedValue(
            new Response(JSON.stringify({ total_tenders: 3, status: 'not_ready' }), {
                status: 200,
                headers: { 'Content-Type': 'application/json' },
            })
        );

        const response = await kpiAdminApi.getPortfolioOverview();

        expect(response.total_tenders).toBe(3);
        expect(fetchMock).toHaveBeenCalledWith(
            '/api/admin/kpi/portfolio/overview',
            expect.objectContaining({
                method: 'GET',
                headers: expect.objectContaining({
                    Authorization: 'Bearer admin-token',
                    'Content-Type': 'application/json',
                }),
            })
        );
    });

    it('triggers a portfolio resync through the admin KPI BFF', async () => {
        fetchMock.mockResolvedValue(
            new Response(JSON.stringify({ status: 'completed', total_tenders: 4, synced_tenders: 4, failed_tenders: 0, items: [], notes: [] }), {
                status: 200,
                headers: { 'Content-Type': 'application/json' },
            })
        );

        const response = await kpiAdminApi.resyncPortfolio();

        expect(response.total_tenders).toBe(4);
        expect(response.synced_tenders).toBe(4);
        expect(fetchMock).toHaveBeenCalledWith(
            '/api/admin/kpi/portfolio/resync',
            expect.objectContaining({
                method: 'POST',
            })
        );
    });

    it('queries portfolio intelligence through the admin KPI BFF', async () => {
        fetchMock.mockResolvedValue(
            new Response(JSON.stringify({
                status: 'not_ready',
                generated_at: '2026-03-20T09:30:00Z',
                phase_hotspots: [{ phase: 'S6', count: 3, summary: '3 tenders are concentrated in Rework / Clarifications.' }],
                risk_hotspots: [{ code: 'A4', count: 2, severity: 'critical', summary: 'Compliance risk remains a dominant cross-tender blocker.' }],
                outcome_trends: { S11: 1, S12: 1, S13: 2 },
                watchlist: [{ external_tender_id: 'TEN-RED', title: 'Critical tender', analytical_phase: 'S8', health: 'red', summary: 'Compliance gate remains blocked.' }],
                notes: ['Primary hotspot is A4 with 2 mirrored tenders.'],
            }), {
                status: 200,
                headers: { 'Content-Type': 'application/json' },
            })
        );

        const response = await kpiAdminApi.getPortfolioIntelligence();

        expect(response.phase_hotspots[0].phase).toBe('S6');
        expect(response.risk_hotspots[0].code).toBe('A4');
        expect(response.watchlist[0].external_tender_id).toBe('TEN-RED');
        expect(fetchMock).toHaveBeenCalledWith(
            '/api/admin/kpi/portfolio/intelligence',
            expect.objectContaining({
                method: 'GET',
            })
        );
    });

    it('queries tender snapshot through the admin KPI BFF', async () => {
        fetchMock.mockResolvedValue(
            new Response(JSON.stringify({ external_tender_id: '12', status: 'not_ready' }), {
                status: 200,
                headers: { 'Content-Type': 'application/json' },
            })
        );

        const response = await kpiAdminApi.getTenderSnapshot(12);

        expect(response.external_tender_id).toBe('12');
        expect(fetchMock).toHaveBeenCalledWith(
            '/api/admin/kpi/tenders/12/snapshot',
            expect.objectContaining({
                method: 'GET',
            })
        );
    });

    it('queries tender transitions through the admin KPI BFF', async () => {
        fetchMock.mockResolvedValue(
            new Response(JSON.stringify({ external_tender_id: '12', status: 'not_ready', summary: 'ok', items: [{ from_state: 'S4', to_state: 'S5', source_type: 'observed', confidence: 0.82 }], requirement_items: [], history_items: [{ snapshot_id: 1, source_type: 'reconstructed', reconstructed: true }] }), {
                status: 200,
                headers: { 'Content-Type': 'application/json' },
            })
        );

        const response = await kpiAdminApi.getTenderTransitions(12);

        expect(response.external_tender_id).toBe('12');
        expect(response.items[0].source_type).toBe('observed');
        expect(response.history_items[0].source_type).toBe('reconstructed');
        expect(fetchMock).toHaveBeenCalledWith(
            '/api/admin/kpi/tenders/12/transitions',
            expect.objectContaining({
                method: 'GET',
            })
        );
    });

    it('queries tender forecast through the admin KPI BFF with analysis metadata', async () => {
        fetchMock.mockResolvedValue(
            new Response(JSON.stringify({
                external_tender_id: '12',
                status: 'not_ready',
                summary: 'Forecast leans toward submission.',
                overall_confidence: 0.72,
                scenarios: [],
                analysis_metadata: {
                    rollout_policy: 'full',
                    shadow_rollout_enabled: true,
                    markov_rollout_enabled: true,
                    calibrated_forecast_enabled: true,
                    forecast_engine_active: 'markov_full_lifecycle_v1',
                    forecast_signal_type: 'calibrated',
                    forecast_engine_candidates: ['markov_full_lifecycle_v1', 'heuristic_rule_v1'],
                    markov_model_active: true,
                    markov_model_version: 'markov-full-lifecycle-v1',
                    markov_phase_scope: ['S0', 'S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7', 'S8', 'S9', 'S10', 'S11', 'S12', 'S13'],
                    markov_reliable_phase_scope: ['S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7', 'S8', 'S9', 'S10', 'S11', 'S12', 'S13'],
                    semantic_priority: ['A1', 'A4'],
                    canonical_source_types: ['observed', 'inferred', 'reconstructed'],
                    shadow_kpis: ['A1', 'A4'],
                    markov_state_scope: ['S0', 'S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S7', 'S8', 'S9', 'S10', 'S11', 'S12', 'S13'],
                    markov_absorbing_states: ['S11', 'S12', 'S13'],
                    markov_source_mix: { observed: 4, reconstructed: 1 },
                    markov_bundle_kind: 'full_journey',
                    markov_full_journey_enabled: true,
                    markov_coverage_ratio: 0.56,
                    markov_projected_path: ['S6', 'S8', 'S9'],
                    markov_backtest_version: 'markov-backtest-v1',
                    markov_backtest_sample_count: 8,
                    markov_backtest_submission_accuracy: 0.75,
                    markov_backtest_calibration_gap: 0.19,
                    forecast_driver_kpis: ['A1', 'A4'],
                    forecast_driver_scores: { A1: 72.5, A4: 68.0 },
                    forecast_primary_action_code: 'protect_submission_corridor',
                    forecast_primary_action_confidence: 0.81,
                    forecast_decision_bundle_version: 'forecast-decision-support-v1',
                    scored_kpis: ['A1', 'A4'],
                    reconstructed: false,
                },
                next_best_actions: [
                    {
                        code: 'protect_submission_corridor',
                        title: 'Protect the submission corridor',
                        priority: 'now',
                        rationale: 'The tender is leaning toward the submission path.',
                        expected_impact: 'Keep the tender on the shortest path to submission.',
                        confidence: 0.81,
                        drivers: ['Projected path: S6 -> S8 -> S9'],
                    },
                ],
            }), {
                status: 200,
                headers: { 'Content-Type': 'application/json' },
            })
        );

        const response = await kpiAdminApi.getTenderForecast(12);

        expect(response.analysis_metadata.forecast_signal_type).toBe('calibrated');
        expect(response.analysis_metadata.forecast_engine_active).toBe('markov_full_lifecycle_v1');
        expect(response.analysis_metadata.markov_model_version).toBe('markov-full-lifecycle-v1');
        expect(response.analysis_metadata.markov_bundle_kind).toBe('full_journey');
        expect(response.analysis_metadata.markov_projected_path).toEqual(['S6', 'S8', 'S9']);
        expect(response.analysis_metadata.forecast_primary_action_code).toBe('protect_submission_corridor');
        expect(response.next_best_actions[0].code).toBe('protect_submission_corridor');
        expect(response.analysis_metadata.markov_rollout_enabled).toBe(true);
        expect(fetchMock).toHaveBeenCalledWith(
            '/api/admin/kpi/tenders/12/forecast',
            expect.objectContaining({
                method: 'GET',
            })
        );
    });

    it('triggers a recompute request through the admin KPI BFF', async () => {
        fetchMock.mockResolvedValue(
            new Response(JSON.stringify({ external_tender_id: '12', job_id: 77, job_type: 'full_recompute', job_status: 'queued' }), {
                status: 202,
                headers: { 'Content-Type': 'application/json' },
            })
        );

        const response = await kpiAdminApi.recomputeTender(12);

        expect(response.job_id).toBe(77);
        expect(response.job_status).toBe('queued');
        expect(fetchMock).toHaveBeenCalledWith(
            '/api/admin/kpi/tenders/12/recompute',
            expect.objectContaining({
                method: 'POST',
            })
        );
    });

    it('triggers a history backfill request through the admin KPI BFF', async () => {
        fetchMock.mockResolvedValue(
            new Response(JSON.stringify({ external_tender_id: '12', job_id: 91, job_type: 'history_backfill', job_status: 'queued' }), {
                status: 202,
                headers: { 'Content-Type': 'application/json' },
            })
        );

        const response = await kpiAdminApi.backfillTenderHistory(12);

        expect(response.job_id).toBe(91);
        expect(response.job_type).toBe('history_backfill');
        expect(fetchMock).toHaveBeenCalledWith(
            '/api/admin/kpi/tenders/12/history/backfill',
            expect.objectContaining({
                method: 'POST',
            })
        );
    });

    it('queries the latest recompute job through the admin KPI BFF', async () => {
        fetchMock.mockResolvedValue(
            new Response(JSON.stringify({ external_tender_id: '12', job_id: 77, job_type: 'full_recompute', job_status: 'running' }), {
                status: 200,
                headers: { 'Content-Type': 'application/json' },
            })
        );

        const response = await kpiAdminApi.getLatestAnalysisJob(12);

        expect(response.job_status).toBe('running');
        expect(fetchMock).toHaveBeenCalledWith(
            '/api/admin/kpi/tenders/12/analysis-jobs/latest',
            expect.objectContaining({
                method: 'GET',
            })
        );
    });
});

describe('chat context prefetch', () => {
    beforeEach(() => {
        storage.clear();
        fetchMock.mockReset();
        resetTenderChatContextCacheForTest();
        vi.stubGlobal('fetch', fetchMock);
        vi.stubGlobal('localStorage', localStorageMock);
    });

    afterEach(() => {
        resetTenderChatContextCacheForTest();
        vi.unstubAllGlobals();
        vi.restoreAllMocks();
    });

    it('reuses prefetched TenderChat context without triggering duplicate requests', async () => {
        fetchMock
            .mockResolvedValueOnce(
                new Response(JSON.stringify({
                    id: 12,
                    title: 'Healthcare tender',
                    client: 'Region',
                    description: null,
                    deadline: null,
                    status: 'active',
                    category: null,
                    tags: [],
                    budget_estimate: null,
                    created_at: '2026-03-15T10:00:00Z',
                    created_by: 1,
                    created_by_name: 'Admin',
                    requirement_count: 0,
                    requirements: [],
                }), { status: 200, headers: { 'Content-Type': 'application/json' } })
            )
            .mockResolvedValueOnce(
                new Response(JSON.stringify({
                    id: 5,
                    tender_id: 12,
                    is_official: true,
                    status: 'open',
                    opened_at: null,
                    created_at: null,
                    participant_count: 3,
                }), { status: 200, headers: { 'Content-Type': 'application/json' } })
            )
            .mockResolvedValueOnce(
                new Response(JSON.stringify({
                    items: [
                        {
                            id: 101,
                            room_id: 5,
                            sender_id: 7,
                            sender_name: 'Alice',
                            sender_email: 'alice@example.com',
                            content: 'Latest upload received',
                            created_at: '2026-03-15T10:10:00Z',
                            updated_at: null,
                            attachments: [],
                        },
                    ],
                    next_before_id: null,
                }), { status: 200, headers: { 'Content-Type': 'application/json' } })
            );

        await prefetchTenderChatContext(12);
        const context = await resolveTenderChatContext(12, { preferCached: true });

        expect(context.tender.id).toBe(12);
        expect(context.room.id).toBe(5);
        expect(context.messages).toHaveLength(1);
        expect(fetchMock).toHaveBeenCalledTimes(3);
    });


    it('reuses prefetched TenderChat retrospective without triggering duplicate requests', async () => {
        fetchMock.mockResolvedValue(
            new Response(JSON.stringify({
                room: {
                    id: 5,
                    tender_id: 12,
                    is_official: true,
                    status: 'open',
                    opened_at: '2026-03-15T09:50:00Z',
                    created_at: '2026-03-15T09:45:00Z',
                    participant_count: 3,
                },
                participants: [],
                message_count: 6,
                attachment_count: 2,
                event_count: 4,
                first_message_at: '2026-03-15T09:55:00Z',
                last_message_at: '2026-03-15T10:15:00Z',
                generated_at: '2026-03-15T10:16:00Z',
                timeline: [],
            }), { status: 200, headers: { 'Content-Type': 'application/json' } })
        );

        await prefetchTenderChatRetrospective(12);
        const retrospective = await resolveTenderChatRetrospective(12, { preferCached: true });

        expect(retrospective.message_count).toBe(6);
        expect(retrospective.attachment_count).toBe(2);
        expect(fetchMock).toHaveBeenCalledTimes(1);
        expect(fetchMock).toHaveBeenCalledWith(
            '/api/tenders/12/chat/retrospective?timeline_limit=200',
            expect.objectContaining({
                method: 'GET',
            })
        );
    });
});

describe('tenderApi', () => {
    beforeEach(() => {
        storage.clear();
        fetchMock.mockReset();
        vi.stubGlobal('fetch', fetchMock);
        vi.stubGlobal('localStorage', localStorageMock);
    });

    afterEach(() => {
        resetTenderChatContextCacheForTest();
        vi.unstubAllGlobals();
        vi.restoreAllMocks();
    });

    it('loads tender detail with requirement mapping metadata', async () => {
        fetchMock.mockResolvedValue(
            new Response(JSON.stringify({
                id: 12,
                title: 'Healthcare tender',
                client: 'Region',
                description: null,
                deadline: null,
                status: 'active',
                category: null,
                tags: [],
                budget_estimate: null,
                created_at: '2026-03-15T10:00:00Z',
                created_by: 1,
                created_by_name: 'Admin',
                requirement_count: 1,
                lifecycle_metadata: { decision: { decision: 'go' } },
                requirements: [
                    {
                        id: 3,
                        requirement_text: 'Provide signed annex',
                        category: 'legal',
                        priority: 'high',
                        compliance_status: 'partially_addressed',
                        mapped_section_id: 44,
                        mapped_section_title: 'Compliance matrix',
                    },
                ],
            }), {
                status: 200,
                headers: { 'Content-Type': 'application/json' },
            })
        );

        const response = await tenderApi.get(12);

        expect(response.requirements[0].mapped_section_id).toBe(44);
        expect(response.requirements[0].mapped_section_title).toBe('Compliance matrix');
        expect(response.lifecycle_metadata?.decision?.decision).toBe('go');
        expect(fetchMock).toHaveBeenCalledWith(
            '/api/tenders/12',
            expect.objectContaining({
                method: 'GET',
            })
        );
    });

    it('records coordination risk through the tender lifecycle endpoint', async () => {
        fetchMock.mockResolvedValue(
            new Response(JSON.stringify({ status: 'accepted', event_type: 'coordination_risk_raised', tender_id: 12, payload: {} }), {
                status: 202,
                headers: { 'Content-Type': 'application/json' },
            })
        );

        const response = await tenderApi.raiseCoordinationRisk(12, {
            external_rework_id: 'rw-admin-1',
            external_contribution_id: '201',
            severity: 'high',
            reason_code: 'missing_owner_alignment',
        });

        expect(response.event_type).toBe('coordination_risk_raised');
        expect(fetchMock).toHaveBeenCalledWith(
            '/api/tenders/12/coordination-risk',
            expect.objectContaining({
                method: 'POST',
                body: JSON.stringify({
                    external_rework_id: 'rw-admin-1',
                    external_contribution_id: '201',
                    severity: 'high',
                    reason_code: 'missing_owner_alignment',
                }),
            })
        );
    });

    it('records gate stop through the tender lifecycle endpoint', async () => {
        fetchMock.mockResolvedValue(
            new Response(JSON.stringify({ status: 'accepted', event_type: 'tender_stopped_at_gate', tender_id: 12, payload: {} }), {
                status: 202,
                headers: { 'Content-Type': 'application/json' },
            })
        );

        const response = await tenderApi.stopAtGate(12, {
            external_gate_id: 'gate-1',
            gate_name: 'Auto compliance readiness',
            reason_code: 'compliance_gap_reopened',
        });

        expect(response.event_type).toBe('tender_stopped_at_gate');
        expect(fetchMock).toHaveBeenCalledWith(
            '/api/tenders/12/gate-stop',
            expect.objectContaining({
                method: 'POST',
                body: JSON.stringify({
                    external_gate_id: 'gate-1',
                    gate_name: 'Auto compliance readiness',
                    reason_code: 'compliance_gap_reopened',
                }),
            })
        );
    });
});


describe('proposalApi', () => {
    beforeEach(() => {
        storage.clear();
        fetchMock.mockReset();
        vi.stubGlobal('fetch', fetchMock);
        vi.stubGlobal('localStorage', localStorageMock);
    });

    afterEach(() => {
        resetTenderChatContextCacheForTest();
        vi.unstubAllGlobals();
        vi.restoreAllMocks();
    });

    it('records draft readiness through the proposal lifecycle endpoint', async () => {
        fetchMock.mockResolvedValue(
            new Response(JSON.stringify({ status: 'accepted', event_type: 'draft_integrated_ready', proposal_id: 44, payload: {} }), {
                status: 202,
                headers: { 'Content-Type': 'application/json' },
            })
        );

        const response = await proposalApi.markDraftReady(44, {});

        expect(response.event_type).toBe('draft_integrated_ready');
        expect(fetchMock).toHaveBeenCalledWith(
            '/api/proposals/44/draft-ready',
            expect.objectContaining({
                method: 'POST',
            })
        );
    });

    it('records submission reliability through the proposal lifecycle endpoint', async () => {
        fetchMock.mockResolvedValue(
            new Response(JSON.stringify({ status: 'accepted', event_type: 'submission_acknowledged', proposal_id: 44, payload: {} }), {
                status: 202,
                headers: { 'Content-Type': 'application/json' },
            })
        );

        const response = await proposalApi.updateSubmissionStatus(44, { submission_status: 'acknowledged', channel: 'manual_admin_update', reference_id: 'ACK-1' });

        expect(response.event_type).toBe('submission_acknowledged');
        expect(fetchMock).toHaveBeenCalledWith(
            '/api/proposals/44/submission-status',
            expect.objectContaining({
                method: 'POST',
                body: JSON.stringify({ submission_status: 'acknowledged', channel: 'manual_admin_update', reference_id: 'ACK-1' }),
            })
        );
    });
});

describe('ragApi streaming', () => {
    beforeEach(() => {
        storage.clear();
        fetchMock.mockReset();
        vi.stubGlobal('fetch', fetchMock);
        vi.stubGlobal('localStorage', localStorageMock);
    });

    afterEach(() => {
        resetTenderChatContextCacheForTest();
        vi.unstubAllGlobals();
        vi.restoreAllMocks();
    });

    it('preserves leading spaces emitted by SSE tokens', async () => {
        const tokens: string[] = [];

        fetchMock.mockResolvedValue(
            createStreamResponse([
                'data: Il problema\n\n',
                'data:  di assegnamento\n\n',
                'data:  continua\n\n',
                'data: [DONE]\n\n',
            ])
        );

        await ragApi.streamQuery(
            { query: 'assignment', mode: 'qa' },
            { onToken: (token) => tokens.push(token) }
        );

        expect(tokens.join('')).toBe('Il problema di assegnamento continua');
    });

    it('preserves multiline SSE payloads without trimming formatting', async () => {
        const tokens: string[] = [];

        fetchMock.mockResolvedValue(
            createStreamResponse([
                'data:  Prima riga\n',
                'data: seconda riga\n\n',
                'data:  \n\n',
                'data: [DONE]\n\n',
            ])
        );

        await ragApi.streamQuery(
            { query: 'assignment', mode: 'qa' },
            { onToken: (token) => tokens.push(token) }
        );

        expect(tokens).toEqual([' Prima riga\nseconda riga', ' ']);
    });
});

describe('observabilityApi', () => {
    beforeEach(() => {
        storage.clear();
        fetchMock.mockReset();
        vi.stubGlobal('fetch', fetchMock);
        vi.stubGlobal('localStorage', localStorageMock);
    });

    afterEach(() => {
        resetTenderChatContextCacheForTest();
        vi.unstubAllGlobals();
        vi.restoreAllMocks();
    });

    it('queries the operational workspace through the tender observability endpoint', async () => {
        fetchMock.mockResolvedValue(
            new Response(JSON.stringify({ summary: { tender_id: 12, contribution_count: 1, request_count: 0, open_rework_count: 0, open_gate_count: 0, call_count: 0 }, contributions: [], requests: [], reviews: [], reworks: [], gates: [], calls: [] }), {
                status: 200,
                headers: { 'Content-Type': 'application/json' },
            })
        );

        const response = await observabilityApi.getWorkspace(12);

        expect(response.summary.tender_id).toBe(12);
        expect(fetchMock).toHaveBeenCalledWith(
            '/api/tenders/12/observability/workspace',
            expect.objectContaining({
                method: 'GET',
            })
        );
    });

    it('creates a contribution through the tender observability endpoint', async () => {
        localStorageMock.setItem('token', 'editor-token');
        fetchMock.mockResolvedValue(
            new Response(JSON.stringify({ id: 91, tender_id: 12, title: 'Legal annex', status: 'open' }), {
                status: 201,
                headers: { 'Content-Type': 'application/json' },
            })
        );

        const response = await observabilityApi.createContribution(12, { title: 'Legal annex', department_name: 'legal' });

        expect(response.id).toBe(91);
        expect(fetchMock).toHaveBeenCalledWith(
            '/api/tenders/12/observability/contributions',
            expect.objectContaining({
                method: 'POST',
                headers: expect.objectContaining({
                    Authorization: 'Bearer editor-token',
                }),
                body: JSON.stringify({ title: 'Legal annex', department_name: 'legal' }),
            })
        );
    });

    it('marks a contribution request as received through the tender observability endpoint', async () => {
        localStorageMock.setItem('token', 'editor-token');
        fetchMock.mockResolvedValue(
            new Response(JSON.stringify({ id: 55, contribution_unit_id: 91, status: 'received' }), {
                status: 200,
                headers: { 'Content-Type': 'application/json' },
            })
        );

        const response = await observabilityApi.receiveRequest(12, 91, 55, {
            response_received_at: '2026-03-15T16:00:00Z',
            response_summary: 'Received through workspace',
        });

        expect(response.status).toBe('received');
        expect(fetchMock).toHaveBeenCalledWith(
            '/api/tenders/12/observability/contributions/91/requests/55/receive',
            expect.objectContaining({
                method: 'POST',
                headers: expect.objectContaining({
                    Authorization: 'Bearer editor-token',
                }),
                body: JSON.stringify({
                    response_received_at: '2026-03-15T16:00:00Z',
                    response_summary: 'Received through workspace',
                }),
            })
        );
    });

    it('starts a review cycle through the tender observability endpoint', async () => {
        localStorageMock.setItem('token', 'editor-token');
        fetchMock.mockResolvedValue(
            new Response(JSON.stringify({ id: 71, contribution_unit_id: 91, status: 'in_review', stage_name: 'quality_review' }), {
                status: 201,
                headers: { 'Content-Type': 'application/json' },
            })
        );

        const response = await observabilityApi.createReview(12, 91, {
            stage_name: 'quality_review',
            notes: 'Start review from workspace',
        });

        expect(response.stage_name).toBe('quality_review');
        expect(fetchMock).toHaveBeenCalledWith(
            '/api/tenders/12/observability/contributions/91/reviews',
            expect.objectContaining({
                method: 'POST',
                headers: expect.objectContaining({
                    Authorization: 'Bearer editor-token',
                }),
                body: JSON.stringify({
                    stage_name: 'quality_review',
                    notes: 'Start review from workspace',
                }),
            })
        );
    });
});



