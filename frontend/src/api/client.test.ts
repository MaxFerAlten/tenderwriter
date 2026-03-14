import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { kpiAdminApi } from './client';

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
});
