import type { RAGQueryRequest, RAGRouteKey } from '../api/client';

export interface SearchScope {
    route_key: RAGRouteKey;
    tender_id: number | null;
}

export const GLOBAL_SEARCH_SCOPE: SearchScope = {
    route_key: 'global',
    tender_id: null,
};

export type SearchPreset = 'balanced' | 'precise' | 'exploratory' | 'custom';
export type RetrieverKey = 'dense' | 'sparse' | 'graph';
type BuiltInSearchPreset = Exclude<SearchPreset, 'custom'>;

export interface SearchSettingsState {
    preset: SearchPreset;
    topK: number;
    retrievalTopK: number;
    temperature: number;
    streamingEnabled: boolean;
    saveHistory: boolean;
    retrievers: Record<RetrieverKey, boolean>;
    fusionWeights: Record<RetrieverKey, number>;
}

export const DEFAULT_SEARCH_SETTINGS: SearchSettingsState = {
    preset: 'balanced',
    topK: 5,
    retrievalTopK: 20,
    temperature: 0.3,
    streamingEnabled: false,
    saveHistory: true,
    retrievers: {
        dense: true,
        sparse: true,
        graph: true,
    },
    fusionWeights: {
        dense: 0.4,
        sparse: 0.3,
        graph: 1.5,
    },
};

const PRESET_CONFIGS: Record<BuiltInSearchPreset, SearchSettingsState> = {
    balanced: DEFAULT_SEARCH_SETTINGS,
    precise: {
        preset: 'precise',
        topK: 4,
        retrievalTopK: 14,
        temperature: 0.15,
        streamingEnabled: false,
        saveHistory: true,
        retrievers: {
            dense: true,
            sparse: true,
            graph: true,
        },
        fusionWeights: {
            dense: 0.5,
            sparse: 0.35,
            graph: 0.15,
        },
    },
    exploratory: {
        preset: 'exploratory',
        topK: 8,
        retrievalTopK: 28,
        temperature: 0.45,
        streamingEnabled: false,
        saveHistory: true,
        retrievers: {
            dense: true,
            sparse: true,
            graph: true,
        },
        fusionWeights: {
            dense: 0.35,
            sparse: 0.2,
            graph: 0.45,
        },
    },
};

export function cloneSearchSettings(settings: SearchSettingsState): SearchSettingsState {
    return {
        ...settings,
        retrievers: { ...settings.retrievers },
        fusionWeights: { ...settings.fusionWeights },
    };
}

export function getSearchPresetConfig(preset: BuiltInSearchPreset): SearchSettingsState {
    return cloneSearchSettings(PRESET_CONFIGS[preset]);
}

export function getActiveRetrieverCount(settings: SearchSettingsState): number {
    return Object.values(settings.retrievers).filter(Boolean).length;
}

export function toggleRetriever(
    settings: SearchSettingsState,
    key: RetrieverKey,
): SearchSettingsState {
    const currentlyEnabled = settings.retrievers[key];
    if (currentlyEnabled && getActiveRetrieverCount(settings) === 1) {
        return cloneSearchSettings(settings);
    }

    return {
        ...settings,
        retrievers: {
            ...settings.retrievers,
            [key]: !currentlyEnabled,
        },
    };
}

export function normalizeSearchSettings(settings: SearchSettingsState): SearchSettingsState {
    const next = cloneSearchSettings(settings);

    next.topK = Math.max(3, Math.min(12, Math.round(next.topK)));
    next.retrievalTopK = Math.max(next.topK, Math.min(40, Math.round(next.retrievalTopK)));
    next.temperature = Math.max(0, Math.min(1, Number(next.temperature.toFixed(2))));

    if (getActiveRetrieverCount(next) === 0) {
        next.retrievers.dense = true;
    }

    (Object.keys(next.fusionWeights) as RetrieverKey[]).forEach((key) => {
        const value = next.fusionWeights[key];
        next.fusionWeights[key] = Math.max(0.05, Math.min(1.5, Number(value.toFixed(2))));
    });

    return next;
}

export function buildRagSearchPayload(
    query: string,
    mode: 'search' | 'qa',
    settings: SearchSettingsState,
    scope: SearchScope = GLOBAL_SEARCH_SCOPE,
    overrides: Partial<Pick<RAGQueryRequest, 'save_history'>> = {},
): RAGQueryRequest {
    const normalized = normalizeSearchSettings(settings);
    const payload: RAGQueryRequest = {
        query,
        mode,
        top_k: normalized.topK,
        temperature: normalized.temperature,
        stream: mode === 'qa' ? normalized.streamingEnabled : false,
        save_history: overrides.save_history ?? normalized.saveHistory,
        retrievers: { ...normalized.retrievers },
        fusion_weights: { ...normalized.fusionWeights },
        route_key: scope.route_key,
    };

    if (scope.route_key === 'tender' && scope.tender_id != null) {
        payload.tender_id = scope.tender_id;
    }

    if (normalized.retrievalTopK !== DEFAULT_SEARCH_SETTINGS.retrievalTopK) {
        payload.retrieval_top_k = normalized.retrievalTopK;
    }

    return payload;
}

export function getSearchSettingsSummary(settings: SearchSettingsState): string[] {
    const normalized = normalizeSearchSettings(settings);
    const presetLabel = {
        balanced: 'Balanced',
        precise: 'Precise',
        exploratory: 'Exploratory',
        custom: 'Custom',
    }[normalized.preset];

    const retrieverLabels = [
        normalized.retrievers.dense ? 'Vector' : null,
        normalized.retrievers.sparse ? 'BM25' : null,
        normalized.retrievers.graph ? 'Graph' : null,
    ].filter(Boolean).join(' + ');

    return [
        presetLabel,
        `${normalized.topK} final sources`,
        `Recall ${normalized.retrievalTopK}`,
        `Temp ${normalized.temperature.toFixed(2)}`,
        retrieverLabels,
        normalized.streamingEnabled ? 'Streaming on' : 'Streaming off',
        normalized.saveHistory ? 'History on' : 'History off',
    ];
}
