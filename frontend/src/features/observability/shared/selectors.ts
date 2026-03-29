import type { KpiAnalysisMetadata, KpiBottleneckItem, KpiScore, KpiTenderSnapshot, Tender } from '../../../api/client';

export function riskCount(items: KpiBottleneckItem[], health: string): number {
    return items.filter((item) => item.health === health).length;
}

export function scoreEvidenceItems(score: KpiScore): string[] {
    return score.evidences.length > 0 ? score.evidences : score.evidence;
}

export function scoreRecommendations(score: KpiScore): string[] {
    return score.recommendations.length > 0
        ? score.recommendations
        : (score.recommendation ? [score.recommendation] : []);
}

export function mergeAnalysisMetadata(...items: Array<KpiAnalysisMetadata | null | undefined>): KpiAnalysisMetadata | null {
    const present = items.filter(Boolean) as KpiAnalysisMetadata[];
    if (present.length === 0) {
        return null;
    }

    return present.reduce<KpiAnalysisMetadata>((accumulator, current) => ({
        ...accumulator,
        ...current,
        markov_phase_scope: current.markov_phase_scope.length > 0 ? current.markov_phase_scope : accumulator.markov_phase_scope,
        markov_reliable_phase_scope: current.markov_reliable_phase_scope.length > 0 ? current.markov_reliable_phase_scope : accumulator.markov_reliable_phase_scope,
        semantic_priority: current.semantic_priority.length > 0 ? current.semantic_priority : accumulator.semantic_priority,
        canonical_source_types: current.canonical_source_types.length > 0 ? current.canonical_source_types : accumulator.canonical_source_types,
        semantic_kpis: current.semantic_kpis.length > 0 ? current.semantic_kpis : accumulator.semantic_kpis,
        semantic_fallback_kpis: current.semantic_fallback_kpis.length > 0 ? current.semantic_fallback_kpis : accumulator.semantic_fallback_kpis,
        shadow_kpis: current.shadow_kpis.length > 0 ? current.shadow_kpis : accumulator.shadow_kpis,
        forecast_engine_candidates: current.forecast_engine_candidates.length > 0 ? current.forecast_engine_candidates : accumulator.forecast_engine_candidates,
        markov_state_scope: current.markov_state_scope.length > 0 ? current.markov_state_scope : accumulator.markov_state_scope,
        markov_absorbing_states: current.markov_absorbing_states.length > 0 ? current.markov_absorbing_states : accumulator.markov_absorbing_states,
        markov_projected_path: current.markov_projected_path.length > 0 ? current.markov_projected_path : accumulator.markov_projected_path,
        forecast_driver_kpis: current.forecast_driver_kpis.length > 0 ? current.forecast_driver_kpis : accumulator.forecast_driver_kpis,
        scored_kpis: current.scored_kpis.length > 0 ? current.scored_kpis : accumulator.scored_kpis,
        markov_source_mix: Object.keys(current.markov_source_mix).length > 0 ? current.markov_source_mix : accumulator.markov_source_mix,
        forecast_driver_scores: Object.keys(current.forecast_driver_scores).length > 0 ? current.forecast_driver_scores : accumulator.forecast_driver_scores,
    }), present[0]);
}

export function isAnalysisJobActive(job: { job_status?: string | null } | null): boolean {
    return job?.job_status === 'queued' || job?.job_status === 'running';
}

export function findBottleneckByTenderId(
    bottlenecks: KpiBottleneckItem[],
    tenderId: number | null
): KpiBottleneckItem | null {
    if (tenderId === null) {
        return null;
    }
    return bottlenecks.find((item) => item.external_tender_id === String(tenderId)) || null;
}

export function resolvePreferredTenderId(
    tenders: Tender[],
    bottlenecks: KpiBottleneckItem[],
    currentSelectedTenderId: number | null
): number | null {
    if (tenders.length === 0) {
        return null;
    }

    if (currentSelectedTenderId !== null && tenders.some((item) => item.id === currentSelectedTenderId)) {
        return currentSelectedTenderId;
    }

    const bottleneckTenderId = bottlenecks[0]?.external_tender_id;
    if (bottleneckTenderId) {
        const preferred = Number.parseInt(bottleneckTenderId, 10);
        if (!Number.isNaN(preferred) && tenders.some((item) => item.id === preferred)) {
            return preferred;
        }
    }

    return tenders[0].id;
}

export function selectQualitativeKpis(snapshot: KpiTenderSnapshot | null): KpiScore[] {
    return (snapshot?.kpis || []).filter((score) => ['A1', 'A2', 'A3', 'A4', 'Q'].includes(score.kpi_code));
}

export function selectOperationalKpis(snapshot: KpiTenderSnapshot | null): KpiScore[] {
    return (snapshot?.kpis || []).filter((score) => ['B1', 'B2', 'B3', 'B4', 'E'].includes(score.kpi_code));
}

export function selectScoredKpis(snapshot: KpiTenderSnapshot | null): KpiScore[] {
    return (snapshot?.kpis || []).filter((score) =>
        score.value !== null ||
        scoreEvidenceItems(score).length > 0 ||
        scoreRecommendations(score).length > 0 ||
        Boolean(score.semantic) ||
        Boolean(score.shadow)
    );
}
