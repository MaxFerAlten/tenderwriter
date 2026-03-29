import { useEffect, useRef, useState } from 'react';

import {
    kpiAdminApi,
    observabilityApi,
    tenderApi,
    type KpiAnalysisJob,
    type KpiDiagnostics,
    type KpiForecast,
    type KpiTenderSnapshot,
    type KpiTransitions,
    type OperationalWorkspace,
    type TenderDetail,
} from '../../../api/client';
import { isAnalysisJobActive } from '../shared';
import { useAnalysisJobPolling } from './useAnalysisJobPolling';

interface UseObservabilityTenderDetailOptions {
    selectedTenderId: number | null;
    onPortfolioRefresh?: () => Promise<number | null> | Promise<void> | void;
}

export interface UseObservabilityTenderDetailResult {
    tenderDetail: TenderDetail | null;
    workspace: OperationalWorkspace | null;
    snapshot: KpiTenderSnapshot | null;
    diagnostics: KpiDiagnostics | null;
    transitions: KpiTransitions | null;
    forecast: KpiForecast | null;
    analysisJob: KpiAnalysisJob | null;
    isDetailLoading: boolean;
    isRecomputing: boolean;
    error: string | null;
    loadTenderDetail: (tenderId: number) => Promise<void>;
    handleRecompute: () => Promise<void>;
    handleHistoryBackfill: () => Promise<void>;
}

export function useObservabilityTenderDetail({
    selectedTenderId,
    onPortfolioRefresh,
}: UseObservabilityTenderDetailOptions): UseObservabilityTenderDetailResult {
    const [tenderDetail, setTenderDetail] = useState<TenderDetail | null>(null);
    const [workspace, setWorkspace] = useState<OperationalWorkspace | null>(null);
    const [snapshot, setSnapshot] = useState<KpiTenderSnapshot | null>(null);
    const [diagnostics, setDiagnostics] = useState<KpiDiagnostics | null>(null);
    const [transitions, setTransitions] = useState<KpiTransitions | null>(null);
    const [forecast, setForecast] = useState<KpiForecast | null>(null);
    const [analysisJob, setAnalysisJob] = useState<KpiAnalysisJob | null>(null);
    const [isDetailLoading, setIsDetailLoading] = useState(false);
    const [isRecomputing, setIsRecomputing] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const detailRequestIdRef = useRef(0);

    const loadTenderDetail = async (tenderId: number) => {
        const requestId = ++detailRequestIdRef.current;
        setIsDetailLoading(true);
        try {
            const [
                snapshotResponse,
                diagnosticsResponse,
                transitionsResponse,
                forecastResponse,
                tenderResponse,
                workspaceResponse,
                analysisJobResponse,
            ] = await Promise.all([
                kpiAdminApi.getTenderSnapshot(tenderId),
                kpiAdminApi.getTenderDiagnostics(tenderId),
                kpiAdminApi.getTenderTransitions(tenderId),
                kpiAdminApi.getTenderForecast(tenderId),
                tenderApi.get(tenderId),
                observabilityApi.getWorkspace(tenderId),
                kpiAdminApi.getLatestAnalysisJob(tenderId),
            ]);

            if (requestId !== detailRequestIdRef.current) {
                return;
            }

            setSnapshot(snapshotResponse);
            setDiagnostics(diagnosticsResponse);
            setTransitions(transitionsResponse);
            setForecast(forecastResponse);
            setTenderDetail(tenderResponse);
            setWorkspace(workspaceResponse);
            setAnalysisJob(analysisJobResponse);
            setIsRecomputing(isAnalysisJobActive(analysisJobResponse));
        } catch (detailError) {
            if (requestId !== detailRequestIdRef.current) {
                return;
            }
            setError(detailError instanceof Error ? detailError.message : 'Failed to load KPI tender detail.');
        } finally {
            if (requestId === detailRequestIdRef.current) {
                setIsDetailLoading(false);
            }
        }
    };

    const handleRecompute = async () => {
        if (selectedTenderId === null) {
            return;
        }
        setError(null);
        setIsRecomputing(true);
        try {
            const response = await kpiAdminApi.recomputeTender(selectedTenderId);
            setAnalysisJob(response);
            setIsRecomputing(isAnalysisJobActive(response));
        } catch (recomputeError) {
            setIsRecomputing(false);
            setError(recomputeError instanceof Error ? recomputeError.message : 'Failed to trigger KPI recompute.');
        }
    };

    const handleHistoryBackfill = async () => {
        if (selectedTenderId === null) {
            return;
        }
        setError(null);
        setIsRecomputing(true);
        try {
            const response = await kpiAdminApi.backfillTenderHistory(selectedTenderId);
            setAnalysisJob(response);
            setIsRecomputing(isAnalysisJobActive(response));
        } catch (backfillError) {
            setIsRecomputing(false);
            setError(backfillError instanceof Error ? backfillError.message : 'Failed to trigger KPI history backfill.');
        }
    };

    useEffect(() => {
        if (selectedTenderId === null) {
            return;
        }

        void loadTenderDetail(selectedTenderId);
    }, [selectedTenderId]);

    useAnalysisJobPolling({
        selectedTenderId,
        analysisJob,
        onAnalysisJobChange: setAnalysisJob,
        onRecomputingChange: setIsRecomputing,
        onJobSucceeded: async () => {
            if (selectedTenderId === null) {
                return;
            }
            await loadTenderDetail(selectedTenderId);
            await onPortfolioRefresh?.();
        },
        onError: setError,
    });

    return {
        tenderDetail,
        workspace,
        snapshot,
        diagnostics,
        transitions,
        forecast,
        analysisJob,
        isDetailLoading,
        isRecomputing,
        error,
        loadTenderDetail,
        handleRecompute,
        handleHistoryBackfill,
    };
}
