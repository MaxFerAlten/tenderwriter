import { useEffect, useRef, useState } from 'react';

import {
    kpiAdminApi,
    tenderApi,
    type KpiBottleneckItem,
    type KpiPortfolioIntelligence,
    type KpiPortfolioOverview,
    type Tender,
} from '../../../api/client';
import { resolvePreferredTenderId } from '../shared';

export interface UseObservabilityPortfolioResult {
    overview: KpiPortfolioOverview | null;
    bottlenecks: KpiBottleneckItem[];
    portfolioIntelligence: KpiPortfolioIntelligence | null;
    tenders: Tender[];
    selectedTenderId: number | null;
    setSelectedTenderId: React.Dispatch<React.SetStateAction<number | null>>;
    isLoading: boolean;
    isRefreshing: boolean;
    isPortfolioResyncing: boolean;
    error: string | null;
    actionNotice: string | null;
    loadPortfolio: (refresh?: boolean) => Promise<number | null>;
    handlePortfolioResync: () => Promise<number | null>;
}

export function useObservabilityPortfolio(): UseObservabilityPortfolioResult {
    const [overview, setOverview] = useState<KpiPortfolioOverview | null>(null);
    const [bottlenecks, setBottlenecks] = useState<KpiBottleneckItem[]>([]);
    const [portfolioIntelligence, setPortfolioIntelligence] = useState<KpiPortfolioIntelligence | null>(null);
    const [tenders, setTenders] = useState<Tender[]>([]);
    const [selectedTenderId, setSelectedTenderId] = useState<number | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [isRefreshing, setIsRefreshing] = useState(false);
    const [isPortfolioResyncing, setIsPortfolioResyncing] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [actionNotice, setActionNotice] = useState<string | null>(null);
    const portfolioRequestIdRef = useRef(0);

    const loadPortfolio = async (refresh = false): Promise<number | null> => {
        const requestId = ++portfolioRequestIdRef.current;
        if (refresh) {
            setIsRefreshing(true);
        } else {
            setIsLoading(true);
        }
        setError(null);

        try {
            const [overviewResponse, bottlenecksResponse, intelligenceResponse, tendersResponse] = await Promise.all([
                kpiAdminApi.getPortfolioOverview(),
                kpiAdminApi.getPortfolioBottlenecks(),
                kpiAdminApi.getPortfolioIntelligence(),
                tenderApi.list({ limit: '100' }),
            ]);

            if (requestId !== portfolioRequestIdRef.current) {
                return null;
            }

            setOverview(overviewResponse);
            setBottlenecks(bottlenecksResponse.items);
            setPortfolioIntelligence(intelligenceResponse);
            setTenders(tendersResponse.items);

            let nextSelectedTenderId: number | null = null;
            setSelectedTenderId((current) => {
                nextSelectedTenderId = resolvePreferredTenderId(
                    tendersResponse.items,
                    bottlenecksResponse.items,
                    current
                );
                return nextSelectedTenderId;
            });

            return nextSelectedTenderId;
        } catch (loadError) {
            if (requestId !== portfolioRequestIdRef.current) {
                return null;
            }
            setError(loadError instanceof Error ? loadError.message : 'Failed to load KPI observability.');
            return null;
        } finally {
            if (requestId === portfolioRequestIdRef.current) {
                setIsLoading(false);
                setIsRefreshing(false);
            }
        }
    };

    const handlePortfolioResync = async (): Promise<number | null> => {
        setError(null);
        setActionNotice(null);
        setIsPortfolioResyncing(true);
        try {
            const response = await kpiAdminApi.resyncPortfolio();
            const total = response.total_tenders ?? 0;
            const synced = response.synced_tenders ?? 0;
            const failed = response.failed_tenders ?? 0;
            setActionNotice(
                failed > 0
                    ? `Portfolio resync completed: ${synced}/${total} synced, ${failed} failed.`
                    : `Portfolio resync completed: ${synced}/${total} tenders synced into the KPI engine.`
            );
            return await loadPortfolio(true);
        } catch (resyncError) {
            setError(resyncError instanceof Error ? resyncError.message : 'Failed to resync the KPI portfolio.');
            return null;
        } finally {
            setIsPortfolioResyncing(false);
        }
    };

    useEffect(() => {
        void loadPortfolio();
    }, []);

    return {
        overview,
        bottlenecks,
        portfolioIntelligence,
        tenders,
        selectedTenderId,
        setSelectedTenderId,
        isLoading,
        isRefreshing,
        isPortfolioResyncing,
        error,
        actionNotice,
        loadPortfolio,
        handlePortfolioResync,
    };
}
