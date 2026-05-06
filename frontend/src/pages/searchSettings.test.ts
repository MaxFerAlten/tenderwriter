import { describe, expect, it } from 'vitest';

import {
    buildRagSearchPayload,
    DEFAULT_SEARCH_SETTINGS,
    GLOBAL_SEARCH_SCOPE,
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
                streamingEnabled: true,
            }
        );

        expect(payload).toEqual({
            query: 'riassumimi il problema di assegnamento',
            mode: 'qa',
            top_k: 8,
            retrieval_top_k: 26,
            temperature: 0.45,
            stream: true,
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
            route_key: 'global',
        });
    });

    it('attaches tender scope when route_key is tender', () => {
        const payload = buildRagSearchPayload(
            'descrivi la gara',
            'qa',
            DEFAULT_SEARCH_SETTINGS,
            { route_key: 'tender', tender_id: 42 }
        );

        expect(payload.route_key).toBe('tender');
        expect(payload.tender_id).toBe(42);
    });

    it('omits tender_id for global scope', () => {
        const payload = buildRagSearchPayload(
            'descrivi la gara',
            'qa',
            DEFAULT_SEARCH_SETTINGS,
            GLOBAL_SEARCH_SCOPE
        );

        expect(payload.route_key).toBe('global');
        expect(payload.tender_id).toBeUndefined();
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
        expect(DEFAULT_SEARCH_SETTINGS.fusionWeights.graph).toBe(1.5);
        expect(getSearchSettingsSummary(DEFAULT_SEARCH_SETTINGS)).toEqual([
            'Balanced',
            '5 final sources',
            'Recall 20',
            'Temp 0.30',
            'Vector + BM25 + Graph',
            'Streaming off',
            'History on',
        ]);
    });

    it('disables streaming by default in the RAG payload', () => {
        const payload = buildRagSearchPayload(
            'descrivi la gara',
            'qa',
            DEFAULT_SEARCH_SETTINGS
        );

        expect(DEFAULT_SEARCH_SETTINGS.streamingEnabled).toBe(false);
        expect(payload.stream).toBe(false);
    });
});
