import type { KpiBottleneckItem, KpiPortfolioIntelligence, Tender } from '../../../api/client';
import { findBottleneckByTenderId, healthColors, phaseLabel } from '../shared';

interface PortfolioSidebarProps {
    tenders: Tender[];
    bottlenecks: KpiBottleneckItem[];
    portfolioIntelligence: KpiPortfolioIntelligence | null;
    selectedTenderId: number | null;
    onSelectTender: (tenderId: number) => void;
}

export default function PortfolioSidebar({
    tenders,
    bottlenecks,
    portfolioIntelligence,
    selectedTenderId,
    onSelectTender,
}: PortfolioSidebarProps) {
    return (
        <div className="observability-sidebar">
            <div className="card observability-focus-card">
                <div style={{ padding: '1rem 1rem 0.5rem 1rem' }}>
                    <h3 style={{ margin: 0, fontSize: '0.95rem' }}>Tender focus list</h3>
                    <p style={{ margin: '0.35rem 0 0 0', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                        Admin drilldown on the tenders already mirrored by the KPI engine.
                    </p>
                </div>
                <div className="observability-focus-list">
                    {tenders.length === 0 ? (
                        <div style={{ padding: '1rem', color: 'var(--text-muted)', fontSize: '0.9rem' }}>No tenders available yet.</div>
                    ) : (
                        tenders.map((tender) => {
                            const itemBottleneck = findBottleneckByTenderId(bottlenecks, tender.id);
                            const itemPalette = healthColors(itemBottleneck?.health || 'unknown');
                            const isSelected = tender.id === selectedTenderId;
                            return (
                                <button
                                    key={tender.id}
                                    onClick={() => onSelectTender(tender.id)}
                                    style={{
                                        width: '100%',
                                        textAlign: 'left',
                                        border: `1px solid ${isSelected ? itemPalette.accent : 'var(--border-color)'}`,
                                        background: isSelected ? itemPalette.soft : 'rgba(255,255,255,0.02)',
                                        borderRadius: '14px',
                                        padding: '0.9rem',
                                        marginBottom: 0,
                                        cursor: 'pointer',
                                        color: 'inherit',
                                    }}
                                >
                                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.75rem', alignItems: 'flex-start' }}>
                                        <div>
                                            <div style={{ fontWeight: 600, marginBottom: '0.25rem' }}>{tender.title}</div>
                                            <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>{tender.client || 'Client not set'}</div>
                                        </div>
                                        <span style={{
                                            padding: '0.2rem 0.55rem',
                                            borderRadius: '999px',
                                            fontSize: '0.72rem',
                                            textTransform: 'capitalize',
                                            background: itemPalette.soft,
                                            color: itemPalette.accent,
                                            border: `1px solid ${itemPalette.accent}33`,
                                        }}>
                                            {itemBottleneck?.health || 'unknown'}
                                        </span>
                                    </div>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '0.75rem', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                                        <span>Status: {tender.status.replace('_', ' ')}</span>
                                        <span>Deadline: {tender.deadline ? new Date(tender.deadline).toLocaleDateString('it-IT') : 'n/a'}</span>
                                    </div>
                                    {itemBottleneck && (
                                        <div style={{ marginTop: '0.6rem', fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                                            {itemBottleneck.summary}
                                        </div>
                                    )}
                                </button>
                            );
                        })
                    )}
                </div>
            </div>

            <div className="card">
                <h3 style={{ marginTop: 0, marginBottom: '0.6rem', fontSize: '0.95rem' }}>Current bottlenecks</h3>
                {bottlenecks.length === 0 ? (
                    <p style={{ margin: 0, color: 'var(--text-muted)', fontSize: '0.85rem' }}>No bottlenecks surfaced yet.</p>
                ) : (
                    <div style={{ display: 'grid', gap: '0.75rem' }}>
                        {bottlenecks.slice(0, 5).map((item) => {
                            const itemPalette = healthColors(item.health);
                            return (
                                <div key={`${item.external_tender_id}-${item.bottleneck_type}`} style={{ borderLeft: `3px solid ${itemPalette.accent}`, paddingLeft: '0.75rem' }}>
                                    <div style={{ fontSize: '0.78rem', color: itemPalette.accent, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                                        {item.bottleneck_type}
                                    </div>
                                    <div style={{ fontSize: '0.85rem', marginTop: '0.2rem' }}>{item.summary}</div>
                                </div>
                            );
                        })}
                    </div>
                )}
            </div>

            <div className="card">
                <h3 style={{ marginTop: 0, marginBottom: '0.6rem', fontSize: '0.95rem' }}>Portfolio intelligence</h3>
                {!portfolioIntelligence ? (
                    <p style={{ margin: 0, color: 'var(--text-muted)', fontSize: '0.85rem' }}>Portfolio intelligence not available yet.</p>
                ) : (
                    <div style={{ display: 'grid', gap: '0.9rem' }}>
                        <div>
                            <div style={{ fontSize: '0.76rem', color: 'var(--text-muted)', marginBottom: '0.45rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Phase hotspots</div>
                            <div style={{ display: 'grid', gap: '0.55rem' }}>
                                {portfolioIntelligence.phase_hotspots.slice(0, 3).map((item) => (
                                    <div key={`phase-${item.phase}`} style={{ padding: '0.7rem 0.8rem', borderRadius: '12px', background: 'rgba(15, 23, 42, 0.28)', border: '1px solid var(--border-color)' }}>
                                        <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.5rem', alignItems: 'center' }}>
                                            <span style={{ fontWeight: 600 }}>{phaseLabel(item.phase)}</span>
                                            <span style={{ fontSize: '0.74rem', color: '#38bdf8' }}>{item.count}</span>
                                        </div>
                                        <div style={{ marginTop: '0.35rem', fontSize: '0.76rem', color: 'var(--text-muted)' }}>{item.summary}</div>
                                    </div>
                                ))}
                            </div>
                        </div>

                        <div>
                            <div style={{ fontSize: '0.76rem', color: 'var(--text-muted)', marginBottom: '0.45rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Risk hotspots</div>
                            <div style={{ display: 'grid', gap: '0.55rem' }}>
                                {portfolioIntelligence.risk_hotspots.slice(0, 3).map((item) => {
                                    const tone = healthColors(
                                        item.severity === 'critical' || item.severity === 'high'
                                            ? 'red'
                                            : item.severity === 'medium'
                                                ? 'amber'
                                                : 'green'
                                    );
                                    return (
                                        <div key={`risk-${item.code}`} style={{ padding: '0.7rem 0.8rem', borderRadius: '12px', background: tone.soft, border: `1px solid ${tone.accent}33` }}>
                                            <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.5rem', alignItems: 'center' }}>
                                                <span style={{ fontWeight: 600 }}>{item.code}</span>
                                                <span style={{ fontSize: '0.74rem', color: tone.accent }}>{item.count}</span>
                                            </div>
                                            <div style={{ marginTop: '0.35rem', fontSize: '0.76rem', color: 'var(--text-secondary)' }}>{item.summary}</div>
                                        </div>
                                    );
                                })}
                            </div>
                        </div>

                        <div>
                            <div style={{ fontSize: '0.76rem', color: 'var(--text-muted)', marginBottom: '0.45rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Admin watchlist</div>
                            <div style={{ display: 'grid', gap: '0.55rem' }}>
                                {portfolioIntelligence.watchlist.slice(0, 3).map((item) => {
                                    const tone = healthColors(item.health);
                                    return (
                                        <div key={`watch-${item.external_tender_id}`} style={{ padding: '0.7rem 0.8rem', borderRadius: '12px', background: 'rgba(15, 23, 42, 0.28)', border: `1px solid ${tone.accent}33` }}>
                                            <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.5rem', alignItems: 'center' }}>
                                                <span style={{ fontWeight: 600 }}>{item.title}</span>
                                                <span style={{ fontSize: '0.74rem', color: tone.accent, textTransform: 'capitalize' }}>{item.health}</span>
                                            </div>
                                            <div style={{ marginTop: '0.35rem', fontSize: '0.74rem', color: 'var(--text-muted)' }}>{phaseLabel(item.analytical_phase)}</div>
                                            <div style={{ marginTop: '0.35rem', fontSize: '0.76rem', color: 'var(--text-secondary)' }}>{item.summary}</div>
                                        </div>
                                    );
                                })}
                            </div>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
