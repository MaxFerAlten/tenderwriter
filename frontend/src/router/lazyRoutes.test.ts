import { afterEach, describe, expect, it } from 'vitest';

import { getLikelyRoutePaths, normalizeRoutePath, resetWarmedRoutesForTest } from './lazyRoutes';

afterEach(() => {
    resetWarmedRoutesForTest();
});

describe('normalizeRoutePath', () => {
    it('normalizes dynamic proposal and chat routes to their lazy module key', () => {
        expect(normalizeRoutePath('/proposals/42')).toBe('/proposals');
        expect(normalizeRoutePath('/tenders/18/chat')).toBe('/tenders/:id/chat');
    });

    it('normalizes observability nested routes to the page module key', () => {
        expect(normalizeRoutePath('/observability-kpi/42')).toBe('/observability-kpi');
        expect(normalizeRoutePath('/observability-kpi/42/compliance')).toBe('/observability-kpi');
        expect(normalizeRoutePath('/observability-kpi/42/operational-workspace')).toBe('/observability-kpi/:tenderId/operational-workspace');
    });

    it('normalizes markov state tender routes to the page module key', () => {
        expect(normalizeRoutePath('/markov-state-process/42')).toBe('/markov-state-process');
    });

    it('returns null for unsupported paths', () => {
        expect(normalizeRoutePath('/unknown')).toBeNull();
        expect(normalizeRoutePath('')).toBeNull();
    });
});

describe('getLikelyRoutePaths', () => {
    it('returns the common likely routes for non-admin users', () => {
        expect(getLikelyRoutePaths('user')).toEqual(['/proposals', '/library', '/tasks']);
    });

    it('extends likely routes for admin users', () => {
        expect(getLikelyRoutePaths('admin')).toEqual(['/proposals', '/library', '/tasks', '/observability-kpi', '/markov-state-process', '/monitor']);
    });
});
