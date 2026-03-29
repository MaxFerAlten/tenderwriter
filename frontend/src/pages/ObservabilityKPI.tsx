import { useEffect } from 'react';
import { useLocation, useNavigate, useParams } from 'react-router-dom';
import { Activity, AlertTriangle, RefreshCcw, Sparkles } from 'lucide-react';

import type { Tender } from '../api/client';
import ModeSelectorModal from '../features/observability/components/ModeSelectorModal';
import ObservabilityDetailArea from '../features/observability/components/ObservabilityDetailArea';
import PortfolioSidebar from '../features/observability/components/PortfolioSidebar';
import PortfolioStatsGrid from '../features/observability/components/PortfolioStatsGrid';
import ViewModeToggle from '../features/observability/components/ViewModeToggle';
import { useKpiViewMode, type KpiViewMode } from '../features/observability/hooks/useKpiViewMode';
import { useObservabilityPortfolio } from '../features/observability/hooks/useObservabilityPortfolio';
import { useObservabilityTenderDetail } from '../features/observability/hooks/useObservabilityTenderDetail';
import {
    buildObservabilityPath,
    findBottleneckByTenderId,
    isManagerialeSection,
    riskCount,
    type ManagerialeSection,
} from '../features/observability/shared';
import { AmministrativaView, ManagerialeView, OperativaView } from '../features/observability/views';

export default function ObservabilityKPI() {
    const location = useLocation();
    const navigate = useNavigate();
    const params = useParams<'tenderId' | 'section'>();
    const { mode, setMode, isFirstAccess, dismissFirstAccess } = useKpiViewMode();
    const portfolio = useObservabilityPortfolio();
    const detail = useObservabilityTenderDetail({
        selectedTenderId: portfolio.selectedTenderId,
        onPortfolioRefresh: () => portfolio.loadPortfolio(true),
    });

    const routeTenderId = params.tenderId ? Number.parseInt(params.tenderId, 10) : null;
    const hasValidRouteTenderId = routeTenderId !== null && !Number.isNaN(routeTenderId);
    const routeSection = isManagerialeSection(params.section) ? params.section : null;
    const activeManagerialeSection: ManagerialeSection = routeSection || 'overview';

    const selectedTender: Tender | null = portfolio.tenders.find((item) => item.id === portfolio.selectedTenderId) || null;
    const selectedBottleneck = findBottleneckByTenderId(portfolio.bottlenecks, portfolio.selectedTenderId);
    const selectedHealth = detail.snapshot?.health || selectedBottleneck?.health || 'unknown';
    const redCount = riskCount(portfolio.bottlenecks, 'red');
    const amberCount = riskCount(portfolio.bottlenecks, 'amber');
    const watchlistCount = portfolio.portfolioIntelligence?.watchlist.length ?? 0;
    const activeJobType = detail.analysisJob?.job_type || null;
    const isBackfilling = detail.isRecomputing && activeJobType === 'history_backfill';
    const portfolioResyncDisabled = portfolio.isPortfolioResyncing || portfolio.isRefreshing || portfolio.isLoading;
    const pageError = detail.error || portfolio.error;

    useEffect(() => {
        if (params.tenderId && !hasValidRouteTenderId) {
            navigate('/observability-kpi', { replace: true });
        }
    }, [hasValidRouteTenderId, navigate, params.tenderId]);

    useEffect(() => {
        if (params.section && !routeSection && hasValidRouteTenderId) {
            navigate(buildObservabilityPath(routeTenderId), { replace: true });
        }
    }, [hasValidRouteTenderId, navigate, params.section, routeSection, routeTenderId]);

    useEffect(() => {
        if (!params.tenderId && !routeSection) {
            return;
        }

        if (isFirstAccess) {
            dismissFirstAccess();
        }

        if (routeSection && mode !== 'manageriale') {
            setMode('manageriale');
        }
    }, [dismissFirstAccess, isFirstAccess, mode, params.tenderId, routeSection, setMode]);

    useEffect(() => {
        if (!hasValidRouteTenderId || portfolio.tenders.length === 0) {
            return;
        }

        const routeTenderExists = portfolio.tenders.some((item) => item.id === routeTenderId);
        if (!routeTenderExists) {
            const fallbackTenderId = portfolio.selectedTenderId ?? portfolio.tenders[0]?.id ?? null;
            navigate(
                mode === 'manageriale'
                    ? buildObservabilityPath(fallbackTenderId, routeSection)
                    : buildObservabilityPath(fallbackTenderId),
                { replace: true }
            );
            return;
        }

        if (portfolio.selectedTenderId !== routeTenderId) {
            portfolio.setSelectedTenderId(routeTenderId);
        }
    }, [
        hasValidRouteTenderId,
        mode,
        navigate,
        portfolio.selectedTenderId,
        portfolio.setSelectedTenderId,
        portfolio.tenders,
        routeSection,
        routeTenderId,
    ]);

    const handleRefresh = async () => {
        const tenderId = await portfolio.loadPortfolio(true);
        if (tenderId !== null) {
            await detail.loadTenderDetail(tenderId);
        }
    };

    const handlePortfolioResync = async () => {
        const tenderId = await portfolio.handlePortfolioResync();
        if (tenderId !== null) {
            await detail.loadTenderDetail(tenderId);
        }
    };

    const handleModeChange = (nextMode: KpiViewMode) => {
        setMode(nextMode);
        const nextPath = nextMode === 'manageriale'
            ? buildObservabilityPath(portfolio.selectedTenderId, activeManagerialeSection)
            : buildObservabilityPath(portfolio.selectedTenderId);

        if (location.pathname !== nextPath) {
            navigate(nextPath);
        }
    };

    const handleTenderSelection = (tenderId: number) => {
        portfolio.setSelectedTenderId(tenderId);
        const nextPath = mode === 'manageriale'
            ? buildObservabilityPath(tenderId, activeManagerialeSection)
            : buildObservabilityPath(tenderId);

        if (location.pathname !== nextPath) {
            navigate(nextPath);
        }
    };

    const handleManagerialeTabChange = (section: ManagerialeSection) => {
        if (portfolio.selectedTenderId === null) {
            return;
        }

        if (mode !== 'manageriale') {
            setMode('manageriale');
        }

        const nextPath = buildObservabilityPath(portfolio.selectedTenderId, section);
        if (location.pathname !== nextPath) {
            navigate(nextPath);
        }
    };

    if (portfolio.isLoading) {
        return <div className="loading-spinner"><div className="spinner" /></div>;
    }

    const commonProps = {
        snapshot: detail.snapshot,
        forecast: detail.forecast,
        diagnostics: detail.diagnostics,
        transitions: detail.transitions,
        analysisJob: detail.analysisJob,
        tender: selectedTender,
        tenderDetail: detail.tenderDetail,
        workspace: detail.workspace,
        selectedHealth,
        bottlenecks: portfolio.bottlenecks,
        overview: portfolio.overview,
        onRefresh: handleRefresh,
    };

    const renderView = () => {
        switch (mode) {
            case 'manageriale':
                return (
                    <ManagerialeView
                        {...commonProps}
                        onRecompute={detail.handleRecompute}
                        activeTab={activeManagerialeSection}
                        onTabChange={handleManagerialeTabChange}
                    />
                );
            case 'amministrativa':
                return <AmministrativaView {...commonProps} onRecompute={detail.handleRecompute} />;
            case 'operativa':
                return (
                    <OperativaView
                        {...commonProps}
                        onRecompute={detail.handleRecompute}
                        onHistoryBackfill={detail.handleHistoryBackfill}
                        isRecomputing={detail.isRecomputing}
                        isBackfilling={isBackfilling}
                    />
                );
            default:
                return null;
        }
    };

    return (
        <>
            {isFirstAccess && !params.tenderId && !params.section && (
                <ModeSelectorModal
                    onSelect={(selectedMode) => {
                        handleModeChange(selectedMode);
                        dismissFirstAccess();
                    }}
                    onDismiss={dismissFirstAccess}
                />
            )}

            <div className="animate-in">
                <div className="page-header" style={{ position: 'relative', zIndex: 100, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '1rem' }}>
                    <div>
                        <h1 className="page-title" style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                            <Sparkles size={28} color="#38bdf8" />
                            Observability KPI
                        </h1>
                        <p className="page-subtitle">
                            Portfolio observability for the KPI reason engine, exposed through the TenderWriter admin BFF.
                        </p>
                    </div>
                    <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', justifyContent: 'flex-end', alignItems: 'center' }}>
                        <ViewModeToggle mode={mode} onModeChange={handleModeChange} />
                        <button
                            className={`btn btn-secondary btn-sm ${portfolio.isRefreshing ? 'animate-pulse' : ''}`}
                            onClick={() => void handleRefresh()}
                        >
                            <RefreshCcw size={14} /> Refresh
                        </button>
                        <button
                            className={`btn btn-secondary btn-sm ${portfolio.isPortfolioResyncing ? 'animate-pulse' : ''}`}
                            onClick={() => void handlePortfolioResync()}
                            disabled={portfolioResyncDisabled}
                        >
                            <RefreshCcw size={14} /> {portfolio.isPortfolioResyncing ? 'Resyncing portfolio...' : 'Resync Portfolio'}
                        </button>
                    </div>
                </div>

                {pageError && (
                    <div className="card" style={{ borderColor: 'rgba(239, 68, 68, 0.35)', background: 'rgba(127, 29, 29, 0.18)', marginBottom: '1.5rem' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', color: '#fecaca' }}>
                            <AlertTriangle size={18} />
                            <span>{pageError}</span>
                        </div>
                    </div>
                )}

                {portfolio.actionNotice && (
                    <div className="card" style={{ borderColor: 'rgba(16, 185, 129, 0.28)', background: 'rgba(6, 78, 59, 0.18)', marginBottom: '1.5rem' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', color: '#bbf7d0' }}>
                            <Activity size={18} />
                            <span>{portfolio.actionNotice}</span>
                        </div>
                    </div>
                )}

                <PortfolioStatsGrid
                    overview={portfolio.overview}
                    redCount={redCount}
                    amberCount={amberCount}
                    watchlistCount={watchlistCount}
                />

                <div className="observability-layout">
                    <PortfolioSidebar
                        tenders={portfolio.tenders}
                        bottlenecks={portfolio.bottlenecks}
                        portfolioIntelligence={portfolio.portfolioIntelligence}
                        selectedTenderId={portfolio.selectedTenderId}
                        onSelectTender={handleTenderSelection}
                    />

                    <ObservabilityDetailArea
                        selectedTenderId={portfolio.selectedTenderId}
                        snapshot={detail.snapshot}
                        isDetailLoading={detail.isDetailLoading}
                    >
                        {renderView()}
                    </ObservabilityDetailArea>
                </div>
            </div>
        </>
    );
}
