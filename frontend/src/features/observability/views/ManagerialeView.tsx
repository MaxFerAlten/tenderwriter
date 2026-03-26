import { lazy, Suspense } from 'react';
import { motion } from 'framer-motion';
import {
    KpiTenderSnapshot,
    KpiForecast,
    KpiDiagnostics,
    KpiAnalysisJob,
    KpiTransitions,
    Tender,
    OperationalWorkspace,
    TenderDetail,
    KpiBottleneckItem,
    KpiPortfolioOverview,
} from '../../../api/client';
import OverviewTab from './OverviewTab';
import KpiDetailTab from './KpiDetailTab';
import ForecastTab from './ForecastTab';
import type { ManagerialeSection } from '../shared';

const ComplianceDrilldownPanel = lazy(() => import('../../../components/observability/ComplianceDrilldownPanel'));
const OperationalWorkspacePanel = lazy(() => import('../../../components/observability/OperationalWorkspacePanel'));
const LifecycleControlPanel = lazy(() => import('../../../components/observability/LifecycleControlPanel'));
const TransitionTimelinePanel = lazy(() => import('../../../components/observability/TransitionTimelinePanel'));

interface ManagerialeViewProps {
    snapshot: KpiTenderSnapshot | null;
    forecast: KpiForecast | null;
    diagnostics: KpiDiagnostics | null;
    transitions: KpiTransitions | null;
    analysisJob: KpiAnalysisJob | null;
    tender: Tender | null;
    tenderDetail: TenderDetail | null;
    workspace: OperationalWorkspace | null;
    selectedHealth: string;
    bottlenecks: KpiBottleneckItem[];
    overview: KpiPortfolioOverview | null;
    onRefresh: () => void;
    onRecompute: () => void;
    activeTab: ManagerialeSection;
    onTabChange: (tab: ManagerialeSection) => void;
}

const TABS: { id: ManagerialeSection; label: string; badge?: boolean }[] = [
    { id: 'overview', label: 'Overview' },
    { id: 'kpi', label: 'KPI Detail' },
    { id: 'forecast', label: 'Forecast' },
    { id: 'compliance', label: 'Compliance' },
    { id: 'lifecycle', label: 'Lifecycle' },
    { id: 'operations', label: 'Operations' },
];

export default function ManagerialeView({
    snapshot,
    forecast,
    diagnostics,
    transitions,
    analysisJob,
    tender,
    tenderDetail,
    workspace,
    selectedHealth,
    bottlenecks: _bottlenecks,
    overview: _overview,
    onRefresh,
    onRecompute: _onRecompute,
    activeTab,
    onTabChange,
}: ManagerialeViewProps) {
    const renderTabContent = () => {
        switch (activeTab) {
            case 'overview':
                return (
                    <OverviewTab
                        snapshot={snapshot}
                        forecast={forecast}
                        diagnostics={diagnostics}
                        analysisJob={analysisJob}
                        tender={tender}
                        selectedHealth={selectedHealth}
                    />
                );
            case 'kpi':
                return (
                    <KpiDetailTab
                        snapshot={snapshot}
                        analysisJob={analysisJob}
                        tender={tender}
                        selectedHealth={selectedHealth}
                    />
                );
            case 'forecast':
                return (
                    <ForecastTab
                        forecast={forecast}
                        diagnostics={diagnostics}
                        analysisJob={analysisJob}
                        tender={tender}
                    />
                );
            case 'compliance':
                return (
                    <Suspense fallback={<div className="card"><p style={{ margin: 0, color: 'var(--text-muted)' }}>Loading compliance panel...</p></div>}>
                        <ComplianceDrilldownPanel
                            tenderDetail={tenderDetail}
                            workspace={workspace}
                            analyticalPhase={snapshot?.analytical_phase || null}
                        />
                    </Suspense>
                );
            case 'lifecycle':
                return (
                    <Suspense fallback={<div className="card"><p style={{ margin: 0, color: 'var(--text-muted)' }}>Loading lifecycle panels...</p></div>}>
                        <>
                            <LifecycleControlPanel
                                tender={tender}
                                tenderDetail={tenderDetail}
                                analyticalPhase={snapshot?.analytical_phase || null}
                                onDataChanged={onRefresh}
                            />
                            <TransitionTimelinePanel transitions={transitions} />
                        </>
                    </Suspense>
                );
            case 'operations':
                return (
                    <Suspense fallback={<div className="card"><p style={{ margin: 0, color: 'var(--text-muted)' }}>Loading operational workspace...</p></div>}>
                        <OperationalWorkspacePanel
                            tender={tender}
                            onDataChanged={onRefresh}
                        />
                    </Suspense>
                );
            default:
                return null;
        }
    };

    return (
        <div>
            <nav
                style={{
                    display: 'flex',
                    gap: '0.25rem',
                    padding: '0 1.5rem',
                    background: 'var(--bg-card)',
                    borderBottom: '1px solid var(--border-default)',
                }}
            >
                {TABS.map((tab) => (
                    <button
                        key={tab.id}
                        onClick={() => onTabChange(tab.id)}
                        style={{
                            padding: '0.75rem 1.125rem',
                            background: 'none',
                            border: 'none',
                            borderBottom: `2px solid ${activeTab === tab.id ? 'var(--color-primary)' : 'transparent'}`,
                            color: activeTab === tab.id ? 'var(--color-primary)' : 'var(--text-muted)',
                            fontSize: '0.875rem',
                            fontWeight: 500,
                            cursor: 'pointer',
                            transition: 'all 0.2s',
                            position: 'relative',
                        }}
                    >
                        {tab.label}
                        {tab.badge && (
                            <span
                                style={{
                                    position: 'absolute',
                                    top: '8px',
                                    right: '4px',
                                    width: '6px',
                                    height: '6px',
                                    borderRadius: '50%',
                                    background: '#ef4444',
                                }}
                            />
                        )}
                    </button>
                ))}
            </nav>

            <div style={{ padding: '1.5rem' }}>
                <motion.div
                    key={activeTab}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.2 }}
                >
                    {renderTabContent()}
                </motion.div>
            </div>
        </div>
    );
}
