import { motion } from 'framer-motion';
import { Activity, Gauge, ShieldAlert, TrendingUp } from 'lucide-react';

import type { KpiPortfolioOverview } from '../../../api/client';
import { healthColors } from '../shared';

interface PortfolioStatsGridProps {
    overview: KpiPortfolioOverview | null;
    redCount: number;
    amberCount: number;
    watchlistCount: number;
}

export default function PortfolioStatsGrid({
    overview,
    redCount,
    amberCount,
    watchlistCount,
}: PortfolioStatsGridProps) {
    return (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: '1rem', marginBottom: '1.5rem' }}>
            <motion.div className="card" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div>
                        <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '0.35rem' }}>Tracked tenders</div>
                        <div style={{ fontSize: '2rem', fontWeight: 700 }}>{overview?.total_tenders ?? 0}</div>
                    </div>
                    <Activity size={22} color="#38bdf8" />
                </div>
            </motion.div>
            <motion.div className="card" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.04 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div>
                        <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '0.35rem' }}>Portfolio health</div>
                        <div style={{ fontSize: '2rem', fontWeight: 700, textTransform: 'capitalize' }}>{overview?.portfolio_health || 'unknown'}</div>
                    </div>
                    <Gauge size={22} color={healthColors(overview?.portfolio_health || 'unknown').accent} />
                </div>
            </motion.div>
            <motion.div className="card" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.08 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div>
                        <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '0.35rem' }}>Red bottlenecks</div>
                        <div style={{ fontSize: '2rem', fontWeight: 700 }}>{redCount}</div>
                    </div>
                    <ShieldAlert size={22} color="#ef4444" />
                </div>
            </motion.div>
            <motion.div className="card" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.12 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div>
                        <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '0.35rem' }}>Amber watchlist</div>
                        <div style={{ fontSize: '2rem', fontWeight: 700 }}>{Math.max(amberCount, watchlistCount)}</div>
                    </div>
                    <TrendingUp size={22} color="#f59e0b" />
                </div>
            </motion.div>
        </div>
    );
}
