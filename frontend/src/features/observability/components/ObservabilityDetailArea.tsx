import type { ReactNode } from 'react';
import type { KpiTenderSnapshot } from '../../../api/client';

interface ObservabilityDetailAreaProps {
    selectedTenderId: number | null;
    snapshot: KpiTenderSnapshot | null;
    isDetailLoading: boolean;
    children: ReactNode;
}

export default function ObservabilityDetailArea({
    selectedTenderId,
    snapshot,
    isDetailLoading,
    children,
}: ObservabilityDetailAreaProps) {
    return (
        <div className="observability-main">
            {isDetailLoading ? (
                <div className="card"><p style={{ margin: 0, color: 'var(--text-muted)' }}>Loading KPI detail...</p></div>
            ) : !selectedTenderId || !snapshot ? (
                <div className="card"><p style={{ margin: 0, color: 'var(--text-muted)' }}>Select a tender to inspect observability detail.</p></div>
            ) : (
                children
            )}
        </div>
    );
}
