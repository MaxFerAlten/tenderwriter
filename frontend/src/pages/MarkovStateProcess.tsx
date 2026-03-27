import { useEffect, useRef, useState } from 'react';
import { AlertTriangle, GitBranch, RefreshCcw } from 'lucide-react';

import { kpiAdminApi, type KpiTenderSnapshot, type KpiTransitions, type Tender } from '../api/client';
import MarkovStateGraph, { type MarkovGraphVisualMode } from '../components/markov/MarkovStateGraph';
import { useObservabilityPortfolio } from '../features/observability/hooks/useObservabilityPortfolio';
import { formatDateTime, phaseLabel } from '../features/observability/shared';

const MARKOV_VISUAL_MODE_STORAGE_KEY = 'tw.markov-state-process.visual-mode';

interface MarkovTenderDetailState {
    snapshot: KpiTenderSnapshot | null;
    transitions: KpiTransitions | null;
    isLoading: boolean;
    error: string | null;
    load: (tenderId: number) => Promise<void>;
}

function resolveCurrentState(snapshot: KpiTenderSnapshot | null, transitions: KpiTransitions | null): string | null {
    if (snapshot?.analytical_phase) {
        return snapshot.analytical_phase;
    }
    if (transitions?.history_items?.[0]?.analytical_phase) {
        return transitions.history_items[0].analytical_phase;
    }
    if (transitions?.items?.[0]?.to_state) {
        return transitions.items[0].to_state;
    }
    return null;
}

function useMarkovTenderDetail(selectedTenderId: number | null): MarkovTenderDetailState {
    const [snapshot, setSnapshot] = useState<KpiTenderSnapshot | null>(null);
    const [transitions, setTransitions] = useState<KpiTransitions | null>(null);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const requestIdRef = useRef(0);

    const load = async (tenderId: number) => {
        const requestId = ++requestIdRef.current;
        setIsLoading(true);
        setError(null);

        try {
            const [snapshotResponse, transitionsResponse] = await Promise.all([
                kpiAdminApi.getTenderSnapshot(tenderId),
                kpiAdminApi.getTenderTransitions(tenderId),
            ]);

            if (requestId !== requestIdRef.current) {
                return;
            }

            setSnapshot(snapshotResponse);
            setTransitions(transitionsResponse);
        } catch (loadError) {
            if (requestId !== requestIdRef.current) {
                return;
            }
            setError(loadError instanceof Error ? loadError.message : 'Failed to load Markov tender state.');
        } finally {
            if (requestId === requestIdRef.current) {
                setIsLoading(false);
            }
        }
    };

    useEffect(() => {
        if (selectedTenderId === null) {
            setSnapshot(null);
            setTransitions(null);
            setError(null);
            return;
        }

        void load(selectedTenderId);
    }, [selectedTenderId]);

    return {
        snapshot,
        transitions,
        isLoading,
        error,
        load,
    };
}

function toneForHealth(health: string | null | undefined): { accent: string; soft: string } {
    switch (health) {
        case 'green':
            return { accent: '#10b981', soft: 'rgba(16, 185, 129, 0.12)' };
        case 'amber':
            return { accent: '#f59e0b', soft: 'rgba(245, 158, 11, 0.12)' };
        case 'red':
            return { accent: '#ef4444', soft: 'rgba(239, 68, 68, 0.12)' };
        default:
            return { accent: '#64748b', soft: 'rgba(100, 116, 139, 0.14)' };
    }
}

function renderStatePill(label: string, accent: string, soft: string) {
    return (
        <span
            style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.35rem',
                padding: '0.35rem 0.65rem',
                borderRadius: '999px',
                background: soft,
                border: `1px solid ${accent}33`,
                color: accent,
                fontSize: '0.76rem',
                fontWeight: 700,
                letterSpacing: '0.04em',
                textTransform: 'uppercase',
            }}
        >
            {label}
        </span>
    );
}

function resolveInitialGraphVisualMode(): MarkovGraphVisualMode {
    if (typeof window === 'undefined') {
        return 'analytical';
    }

    const savedMode = window.localStorage.getItem(MARKOV_VISUAL_MODE_STORAGE_KEY);
    return savedMode === 'presentation' ? 'presentation' : 'analytical';
}

export default function MarkovStateProcess() {
    const portfolio = useObservabilityPortfolio();
    const detail = useMarkovTenderDetail(portfolio.selectedTenderId);
    const [graphVisualMode, setGraphVisualMode] = useState<MarkovGraphVisualMode>(resolveInitialGraphVisualMode);
    const selectedTender: Tender | null = portfolio.tenders.find((item) => item.id === portfolio.selectedTenderId) || null;

    useEffect(() => {
        if (typeof window !== 'undefined') {
            window.localStorage.setItem(MARKOV_VISUAL_MODE_STORAGE_KEY, graphVisualMode);
        }
    }, [graphVisualMode]);

    useEffect(() => {
        if (portfolio.tenders.length === 0) {
            return;
        }

        if (portfolio.selectedTenderId === null) {
            const fallbackTenderId = portfolio.tenders[0]?.id ?? null;
            if (fallbackTenderId !== null) {
                portfolio.setSelectedTenderId(fallbackTenderId);
            }
        }
    }, [portfolio.selectedTenderId, portfolio.setSelectedTenderId, portfolio.tenders]);

    const handleRefresh = async () => {
        const tenderId = await portfolio.loadPortfolio(true);
        const targetId = tenderId ?? portfolio.selectedTenderId;
        if (targetId !== null) {
            await detail.load(targetId);
        }
    };

    const handlePortfolioResync = async () => {
        const tenderId = await portfolio.handlePortfolioResync();
        const targetId = tenderId ?? portfolio.selectedTenderId;
        if (targetId !== null) {
            await detail.load(targetId);
        }
    };

    const currentState = resolveCurrentState(detail.snapshot, detail.transitions);
    const latestTransition = detail.transitions?.items[0] || null;
    const healthTone = toneForHealth(detail.snapshot?.health);
    const isBusy = portfolio.isRefreshing || portfolio.isPortfolioResyncing || detail.isLoading;
    const graphDescription = graphVisualMode === 'presentation'
        ? 'Presentation view focuses on the observed tender journey, fading canonical alternatives so the storyline reads more clearly.'
        : 'The highlighted node is the current analytical phase. Only observed events for the selected tender are labelled; inactive canonical arcs stay intentionally muted.';

    if (portfolio.isLoading) {
        return <div className="loading-spinner"><div className="spinner" /></div>;
    }

    return (
        <div className="animate-in">
            <div
                className="page-header"
                style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'flex-start',
                    gap: '1rem',
                    marginBottom: '1.5rem',
                }}
            >
                <div>
                    <h1 className="page-title" style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                        <GitBranch size={28} color="#67e8f9" />
                        Markov State Process
                    </h1>
                    <p className="page-subtitle">
                        Tender-by-tender lifecycle graph with the current KPI analytical phase highlighted on the Markov journey.
                    </p>
                </div>
                <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                    <button
                        className={`btn btn-secondary btn-sm ${portfolio.isRefreshing ? 'animate-pulse' : ''}`}
                        onClick={() => void handleRefresh()}
                        disabled={isBusy}
                    >
                        <RefreshCcw size={14} /> Refresh
                    </button>
                    <button
                        className={`btn btn-secondary btn-sm ${portfolio.isPortfolioResyncing ? 'animate-pulse' : ''}`}
                        onClick={() => void handlePortfolioResync()}
                        disabled={isBusy}
                    >
                        <RefreshCcw size={14} /> {portfolio.isPortfolioResyncing ? 'Resyncing portfolio...' : 'Resync Portfolio'}
                    </button>
                </div>
            </div>

            {(portfolio.error || detail.error) && (
                <div className="card" style={{ borderColor: 'rgba(239, 68, 68, 0.35)', background: 'rgba(127, 29, 29, 0.18)', marginBottom: '1.5rem' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', color: '#fecaca' }}>
                        <AlertTriangle size={18} />
                        <span>{detail.error || portfolio.error}</span>
                    </div>
                </div>
            )}

            {portfolio.actionNotice && (
                <div className="card" style={{ borderColor: 'rgba(16, 185, 129, 0.28)', background: 'rgba(6, 78, 59, 0.18)', marginBottom: '1.5rem' }}>
                    <div style={{ color: '#bbf7d0' }}>{portfolio.actionNotice}</div>
                </div>
            )}

            {portfolio.tenders.length === 0 ? (
                <div className="card">
                    <p style={{ margin: 0, color: 'var(--text-secondary)' }}>No tenders are available yet for Markov state inspection.</p>
                </div>
            ) : (
                <div className="markov-state-layout">
                    <aside className="card markov-state-sidebar" style={{ padding: '1rem' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.85rem' }}>
                            <h3 style={{ margin: 0 }}>Tender Portfolio</h3>
                            <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>{portfolio.tenders.length} items</span>
                        </div>
                        <div style={{ display: 'grid', gap: '0.65rem', maxHeight: '72vh', overflowY: 'auto', paddingRight: '0.15rem' }}>
                            {portfolio.tenders.map((tender) => {
                                const isSelected = tender.id === portfolio.selectedTenderId;
                                return (
                                    <button
                                        key={tender.id}
                                        type="button"
                                        onClick={() => portfolio.setSelectedTenderId(tender.id)}
                                        style={{
                                            textAlign: 'left',
                                            background: isSelected ? 'rgba(103, 232, 249, 0.12)' : 'rgba(15, 23, 42, 0.34)',
                                            border: isSelected ? '1px solid rgba(103, 232, 249, 0.45)' : '1px solid var(--border-default)',
                                            borderRadius: '14px',
                                            padding: '0.85rem 0.95rem',
                                            color: 'inherit',
                                            cursor: 'pointer',
                                            transition: 'all 180ms ease',
                                        }}
                                    >
                                        <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.75rem', alignItems: 'flex-start' }}>
                                            <div>
                                                <div style={{ fontWeight: 700, color: 'var(--text-primary)' }}>{tender.title}</div>
                                                <div style={{ marginTop: '0.2rem', fontSize: '0.78rem', color: 'var(--text-muted)' }}>{tender.client || 'No client provided'}</div>
                                            </div>
                                            <span style={{ fontSize: '0.76rem', color: isSelected ? '#67e8f9' : 'var(--text-muted)' }}>#{tender.id}</span>
                                        </div>
                                        <div style={{ marginTop: '0.55rem', display: 'flex', justifyContent: 'space-between', gap: '0.5rem', alignItems: 'center' }}>
                                            <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>{tender.status.replace(/_/g, ' ')}</span>
                                            {isSelected && currentState && renderStatePill(currentState, '#67e8f9', 'rgba(103, 232, 249, 0.14)')}
                                        </div>
                                    </button>
                                );
                            })}
                        </div>
                    </aside>

                    <div style={{ display: 'grid', gap: '1rem' }}>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1rem' }}>
                            <div className="card" style={{ padding: '1.1rem' }}>
                                <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>Current state</div>
                                <div style={{ marginTop: '0.55rem', fontSize: '1.2rem', fontWeight: 700 }}>
                                    {currentState ? `${currentState} ${phaseLabel(currentState)}` : 'State unavailable'}
                                </div>
                            </div>
                            <div className="card" style={{ padding: '1.1rem' }}>
                                <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>Health</div>
                                <div style={{ marginTop: '0.55rem' }}>
                                    {renderStatePill(detail.snapshot?.health || 'unknown', healthTone.accent, healthTone.soft)}
                                </div>
                            </div>
                            <div className="card" style={{ padding: '1.1rem' }}>
                                <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>Latest event</div>
                                <div style={{ marginTop: '0.55rem', fontSize: '1rem', fontWeight: 700 }}>
                                    {latestTransition?.source_event_type || 'No explicit transition yet'}
                                </div>
                                <div style={{ marginTop: '0.3rem', fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                                    {formatDateTime(latestTransition?.occurred_at || detail.snapshot?.generated_at || null)}
                                </div>
                            </div>
                            <div className="card" style={{ padding: '1.1rem' }}>
                                <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>Observed transitions</div>
                                <div style={{ marginTop: '0.55rem', fontSize: '1.2rem', fontWeight: 700 }}>
                                    {detail.transitions?.items.length || 0}
                                </div>
                                <div style={{ marginTop: '0.3rem', fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                                    {selectedTender ? `Tender #${selectedTender.id}` : 'No tender selected'}
                                </div>
                            </div>
                        </div>

                        <div className="card" style={{ padding: '1rem 1rem 1.25rem 1rem' }}>
                            <div
                                style={{
                                    display: 'grid',
                                    gridTemplateColumns: 'minmax(0, 1fr) auto',
                                    alignItems: 'start',
                                    gap: '1rem',
                                    marginBottom: '0.75rem',
                                }}
                            >
                                <div>
                                    <h3 style={{ margin: 0 }}>Markov graph</h3>
                                    <p style={{ marginTop: '0.35rem', fontSize: '0.84rem', color: 'var(--text-secondary)' }}>
                                        {graphDescription}
                                    </p>
                                </div>
                                <div
                                    style={{
                                        display: 'inline-flex',
                                        alignItems: 'center',
                                        gap: '0.2rem',
                                        padding: '0.25rem',
                                        borderRadius: '999px',
                                        background: 'rgba(15, 23, 42, 0.55)',
                                        border: '1px solid var(--border-default)',
                                        justifySelf: 'end',
                                        alignSelf: 'start',
                                    }}
                                >
                                    {[
                                        { value: 'analytical', label: 'Analytical' },
                                        { value: 'presentation', label: 'Presentation' },
                                    ].map((mode) => {
                                        const isActive = graphVisualMode === mode.value;

                                        return (
                                            <button
                                                key={mode.value}
                                                type="button"
                                                aria-pressed={isActive}
                                                onClick={() => setGraphVisualMode(mode.value as MarkovGraphVisualMode)}
                                                style={{
                                                    border: 'none',
                                                    borderRadius: '999px',
                                                    padding: '0.42rem 0.8rem',
                                                    fontSize: '0.76rem',
                                                    fontWeight: 700,
                                                    letterSpacing: '0.04em',
                                                    cursor: 'pointer',
                                                    transition: 'all 180ms ease',
                                                    background: isActive ? 'rgba(103, 232, 249, 0.16)' : 'transparent',
                                                    color: isActive ? '#67e8f9' : 'var(--text-muted)',
                                                    boxShadow: isActive ? 'inset 0 0 0 1px rgba(103, 232, 249, 0.3)' : 'none',
                                                }}
                                            >
                                                {mode.label}
                                            </button>
                                        );
                                    })}
                                </div>
                            </div>

                            <div style={{ display: 'flex', gap: '0.45rem', flexWrap: 'wrap', marginBottom: '0.85rem' }}>
                                {renderStatePill('current state', '#67e8f9', 'rgba(103, 232, 249, 0.14)')}
                                {renderStatePill('visited states', '#93c5fd', 'rgba(147, 197, 253, 0.12)')}
                                {renderStatePill('latest transition', '#f59e0b', 'rgba(245, 158, 11, 0.14)')}
                                {renderStatePill('absorbing states', '#fca5a5', 'rgba(252, 165, 165, 0.12)')}
                            </div>

                            <div style={{ overflowX: 'auto' }}>
                                <div style={{ minWidth: 0 }}>
                                    <MarkovStateGraph
                                        currentState={currentState}
                                        transitions={detail.transitions}
                                        visualMode={graphVisualMode}
                                    />
                                </div>
                            </div>
                        </div>

                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1rem' }}>
                            <div className="card">
                                <h3 style={{ marginTop: 0 }}>Current tender</h3>
                                {selectedTender ? (
                                    <div style={{ display: 'grid', gap: '0.6rem' }}>
                                        <div>
                                            <div style={{ fontWeight: 700 }}>{selectedTender.title}</div>
                                            <div style={{ fontSize: '0.84rem', color: 'var(--text-muted)' }}>{selectedTender.client || 'No client provided'}</div>
                                        </div>
                                        <div style={{ display: 'flex', gap: '0.45rem', flexWrap: 'wrap' }}>
                                            {renderStatePill(selectedTender.status.replace(/_/g, ' '), '#cbd5e1', 'rgba(148, 163, 184, 0.14)')}
                                            {currentState && renderStatePill(currentState, '#67e8f9', 'rgba(103, 232, 249, 0.14)')}
                                        </div>
                                        <div style={{ fontSize: '0.84rem', color: 'var(--text-secondary)' }}>
                                            Snapshot generated: {formatDateTime(detail.snapshot?.generated_at || null)}
                                        </div>
                                        {detail.transitions?.summary && (
                                            <div style={{ fontSize: '0.84rem', color: 'var(--text-secondary)' }}>{detail.transitions.summary}</div>
                                        )}
                                    </div>
                                ) : (
                                    <p style={{ margin: 0, color: 'var(--text-muted)' }}>Select a tender to inspect its Markov state.</p>
                                )}
                            </div>

                            <div className="card">
                                <h3 style={{ marginTop: 0 }}>Recent transition drivers</h3>
                                {!detail.transitions || detail.transitions.items.length === 0 ? (
                                    <p style={{ margin: 0, color: 'var(--text-muted)' }}>No explicit transition drivers are mirrored yet for this tender.</p>
                                ) : (
                                    <div style={{ display: 'grid', gap: '0.7rem' }}>
                                        {detail.transitions.items.slice(0, 6).map((item, index) => (
                                            <div
                                                key={`${item.source_event_type || 'event'}-${index}`}
                                                style={{
                                                    padding: '0.85rem',
                                                    borderRadius: '14px',
                                                    background: 'rgba(15, 23, 42, 0.34)',
                                                    border: '1px solid var(--border-default)',
                                                }}
                                            >
                                                <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.75rem', alignItems: 'flex-start' }}>
                                                    <div>
                                                        <div style={{ fontWeight: 700 }}>{item.source_event_type || 'n/a'}</div>
                                                        <div style={{ marginTop: '0.2rem', fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                                                            {item.from_state} {' -> '} {item.to_state}
                                                        </div>
                                                    </div>
                                                    <span style={{ fontSize: '0.76rem', color: 'var(--text-muted)' }}>{formatDateTime(item.occurred_at)}</span>
                                                </div>
                                                <div style={{ marginTop: '0.55rem', fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
                                                    {item.cause || 'No detailed cause recorded.'}
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                )}
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
