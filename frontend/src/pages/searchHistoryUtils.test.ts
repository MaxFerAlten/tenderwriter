import { describe, expect, it } from 'vitest';

import { collapseDuplicateSearchHistory } from './searchHistoryUtils';

describe('collapseDuplicateSearchHistory', () => {
    it('collapses adjacent duplicate entries generated within the same search window', () => {
        const items = [
            {
                id: 2,
                query: 'riassumimi il problema di assegnamento',
                response: 'risposta',
                created_at: '2026-04-03T00:51:26Z',
            },
            {
                id: 1,
                query: 'riassumimi il problema di assegnamento',
                response: 'risposta',
                created_at: '2026-04-03T00:51:25Z',
            },
        ];

        expect(collapseDuplicateSearchHistory(items)).toEqual([items[0]]);
    });

    it('keeps entries when the same query is repeated outside the dedupe window', () => {
        const items = [
            {
                id: 2,
                query: 'same query',
                response: 'same response',
                created_at: '2026-04-03T00:51:26Z',
            },
            {
                id: 1,
                query: 'same query',
                response: 'same response',
                created_at: '2026-04-03T00:50:20Z',
            },
        ];

        expect(collapseDuplicateSearchHistory(items)).toEqual(items);
    });
});
