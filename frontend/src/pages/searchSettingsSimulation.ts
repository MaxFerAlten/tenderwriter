import {
    getSearchPresetConfig,
    type SearchPreset,
    type SearchSettingsState,
} from './searchSettings';

export type SimulatedSearchPreset = Exclude<SearchPreset, 'custom'>;

export interface SearchPresetScenario {
    key: SimulatedSearchPreset;
    title: string;
    description: string;
    target: {
        exactness: number;
        breadth: number;
        graphAffinity: number;
        answerDiscipline: number;
    };
    weights: {
        exactness: number;
        breadth: number;
        graphAffinity: number;
        answerDiscipline: number;
    };
}

export interface SearchPresetSimulationMetrics {
    exactness: number;
    breadth: number;
    graphAffinity: number;
    answerDiscipline: number;
}

export interface SearchPresetSimulationResult {
    preset: SimulatedSearchPreset;
    scenario: SimulatedSearchPreset;
    score: number;
    metrics: SearchPresetSimulationMetrics;
}

const MAX_FUSION_WEIGHT = 1.5;
const MIN_TOP_K = 3;
const MAX_TOP_K = 12;
const MIN_RETRIEVAL_TOP_K = 8;
const MAX_RETRIEVAL_TOP_K = 40;

export const SEARCH_PRESET_SCENARIOS: SearchPresetScenario[] = [
    {
        key: 'balanced',
        title: 'Balanced search',
        description: 'Mixed enterprise query where we want a reliable answer with healthy coverage and some graph help.',
        target: {
            exactness: 0.5,
            breadth: 0.3,
            graphAffinity: 0.24,
            answerDiscipline: 0.58,
        },
        weights: {
            exactness: 0.3,
            breadth: 0.25,
            graphAffinity: 0.15,
            answerDiscipline: 0.3,
        },
    },
    {
        key: 'precise',
        title: 'Precise search',
        description: 'Compliance or lookup query where lexical certainty and disciplined generation matter most.',
        target: {
            exactness: 0.88,
            breadth: 0.36,
            graphAffinity: 0.16,
            answerDiscipline: 0.90,
        },
        weights: {
            exactness: 0.4,
            breadth: 0.1,
            graphAffinity: 0.1,
            answerDiscipline: 0.4,
        },
    },
    {
        key: 'exploratory',
        title: 'Exploratory search',
        description: 'Discovery query where recall, synthesis breadth, and graph relations matter more than tight focus.',
        target: {
            exactness: 0.46,
            breadth: 0.90,
            graphAffinity: 0.84,
            answerDiscipline: 0.46,
        },
        weights: {
            exactness: 0.1,
            breadth: 0.4,
            graphAffinity: 0.3,
            answerDiscipline: 0.2,
        },
    },
];

function clamp01(value: number): number {
    return Math.max(0, Math.min(1, value));
}

function scaleBetween(value: number, min: number, max: number): number {
    if (max <= min) return 0;
    return clamp01((value - min) / (max - min));
}

export function derivePresetSimulationMetrics(
    settings: SearchSettingsState,
): SearchPresetSimulationMetrics {
    const denseEnabled = settings.retrievers.dense ? 1 : 0;
    const sparseEnabled = settings.retrievers.sparse ? 1 : 0;
    const graphEnabled = settings.retrievers.graph ? 1 : 0;

    const denseWeight = clamp01(settings.fusionWeights.dense / MAX_FUSION_WEIGHT) * denseEnabled;
    const sparseWeight = clamp01(settings.fusionWeights.sparse / MAX_FUSION_WEIGHT) * sparseEnabled;
    const graphWeight = clamp01(settings.fusionWeights.graph / MAX_FUSION_WEIGHT) * graphEnabled;
    const retrievalBreadth = scaleBetween(
        settings.retrievalTopK,
        MIN_RETRIEVAL_TOP_K,
        MAX_RETRIEVAL_TOP_K,
    );
    const finalSourceBreadth = scaleBetween(settings.topK, MIN_TOP_K, MAX_TOP_K);
    const temperature = clamp01(settings.temperature);

    return {
        exactness: clamp01(
            (1 - temperature) * 0.4
            + sparseWeight * 0.24
            + denseWeight * 0.2
            + (1 - finalSourceBreadth) * 0.1
            + (1 - retrievalBreadth) * 0.06
        ),
        breadth: clamp01(
            retrievalBreadth * 0.42
            + finalSourceBreadth * 0.22
            + graphWeight * 0.18
            + temperature * 0.18
        ),
        graphAffinity: clamp01(
            graphWeight * 0.72
            + retrievalBreadth * 0.18
            + finalSourceBreadth * 0.1
        ),
        answerDiscipline: clamp01(
            (1 - temperature) * 0.55
            + (1 - finalSourceBreadth) * 0.15
            + denseWeight * 0.15
            + sparseWeight * 0.15
        ),
    };
}

function closeness(actual: number, target: number): number {
    return clamp01(1 - Math.abs(actual - target));
}

export function scorePresetAgainstScenario(
    settings: SearchSettingsState,
    scenario: SearchPresetScenario,
): SearchPresetSimulationResult {
    const metrics = derivePresetSimulationMetrics(settings);
    const score = clamp01(
        closeness(metrics.exactness, scenario.target.exactness) * scenario.weights.exactness
        + closeness(metrics.breadth, scenario.target.breadth) * scenario.weights.breadth
        + closeness(metrics.graphAffinity, scenario.target.graphAffinity) * scenario.weights.graphAffinity
        + closeness(metrics.answerDiscipline, scenario.target.answerDiscipline) * scenario.weights.answerDiscipline
    );

    return {
        preset: settings.preset as SimulatedSearchPreset,
        scenario: scenario.key,
        score: Number(score.toFixed(4)),
        metrics,
    };
}

export function runSearchPresetSimulation(): Record<
    SimulatedSearchPreset,
    SearchPresetSimulationResult[]
> {
    const presets: SimulatedSearchPreset[] = ['balanced', 'precise', 'exploratory'];

    return Object.fromEntries(
        SEARCH_PRESET_SCENARIOS.map((scenario) => [
            scenario.key,
            presets
                .map((preset) => scorePresetAgainstScenario(getSearchPresetConfig(preset), scenario))
                .sort((left, right) => right.score - left.score),
        ])
    ) as Record<SimulatedSearchPreset, SearchPresetSimulationResult[]>;
}
