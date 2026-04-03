import { describe, expect, it } from 'vitest';

import {
    buildRagSearchPayload,
    DEFAULT_SEARCH_SETTINGS,
    getSearchPresetConfig,
    getSearchSettingsSummary,
    toggleRetriever,
} from './searchSettings';

describe('searchSettings', () => {
    it('builds a RAG payload with retrieval controls and custom history behavior', () => {
        const payload = buildRagSearchPayload(
            'riassumimi il problema di assegnamento',
            'qa',
            {
                ...DEFAULT_SEARCH_SETTINGS,
                topK: 8,
                retrievalTopK: 26,
                temperature: 0.45,
                saveHistory: false,
                retrievers: {
                    dense: true,
                    sparse: false,
                    graph: true,
                },
                fusionWeights: {
                    dense: 0.55,
                    sparse: 0.2,
                    graph: 0.45,
                },
            }
        );

        expect(payload).toEqual({
            query: 'riassumimi il problema di assegnamento',
            mode: 'qa',
            top_k: 8,
            retrieval_top_k: 26,
            temperature: 0.45,
            save_history: false,
            retrievers: {
                dense: true,
                sparse: false,
                graph: true,
            },
            fusion_weights: {
                dense: 0.55,
                sparse: 0.2,
                graph: 0.45,
            },
        });
    });

    it('never allows the last active retriever to be disabled', () => {
        const next = toggleRetriever(
            {
                ...DEFAULT_SEARCH_SETTINGS,
                retrievers: {
                    dense: true,
                    sparse: false,
                    graph: false,
                },
            },
            'dense'
        );

        expect(next.retrievers).toEqual({
            dense: true,
            sparse: false,
            graph: false,
        });
    });

    it('returns human-readable summary chips and balanced preset defaults', () => {
        expect(getSearchPresetConfig('balanced')).toEqual(DEFAULT_SEARCH_SETTINGS);
        expect(getSearchSettingsSummary(DEFAULT_SEARCH_SETTINGS)).toEqual([
            'Balanced',
            '5 final sources',
            'Recall 20',
            'Temp 0.30',
            'Vector + BM25 + Graph',
            'History on',
        ]);
    });
});
