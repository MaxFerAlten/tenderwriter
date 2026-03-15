import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
    kpiAdminApi,
    observabilityApi,
    prefetchTenderChatContext,
    prefetchTenderChatRetrospective,
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

describe('kpiAdminApi', () => {
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
            new Response(JSON.stringify({ external_tender_id: '12', status: 'not_ready', summary: 'ok', items: [], requirement_items: [], history_items: [] }), {
                status: 200,
                headers: { 'Content-Type': 'application/json' },
            })
        );

        const response = await kpiAdminApi.getTenderTransitions(12);

        expect(response.external_tender_id).toBe('12');
        expect(fetchMock).toHaveBeenCalledWith(
            '/api/admin/kpi/tenders/12/transitions',
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
        expect(fetchMock).toHaveBeenCalledWith(
            '/api/tenders/12',
            expect.objectContaining({
                method: 'GET',
            })
        );
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
});
