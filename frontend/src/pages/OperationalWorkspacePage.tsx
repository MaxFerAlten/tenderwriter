import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, ClipboardList, AlertTriangle } from 'lucide-react';
import { tenderApi, type Tender } from '../api/client';
import OperationalWorkspacePanel from '../components/observability/OperationalWorkspacePanel';
import { buildObservabilityPath } from '../features/observability/shared';

export default function OperationalWorkspacePage() {
    const { tenderId } = useParams<{ tenderId: string }>();
    const navigate = useNavigate();
    const [tender, setTender] = useState<Tender | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const parsedTenderId = tenderId ? Number.parseInt(tenderId, 10) : null;

    useEffect(() => {
        const fetchTender = async () => {
            if (!tenderId) return;
            const id = parseInt(tenderId, 10);
            if (isNaN(id)) {
                setError('Invalid tender ID.');
                setIsLoading(false);
                return;
            }

            try {
                // Fetch full tender detail to pass to OperationalWorkspacePanel
                // We use tenderApi.get for consistency, as the panel expects a Tender object.
                const tenderData = await tenderApi.get(id);
                setTender(tenderData as unknown as Tender); // Cast fallback 
            } catch (err) {
                setError(err instanceof Error ? err.message : 'Failed to load tender details.');
            } finally {
                setIsLoading(false);
            }
        };

        void fetchTender();
    }, [tenderId]);

    const goBack = () => {
        navigate(buildObservabilityPath(tender?.id ?? parsedTenderId, 'operations'));
    };

    if (isLoading) {
        return (
            <div className="animate-in" style={{ padding: '2rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', color: 'var(--text-secondary)' }}>
                    Loading specialized operational workspace...
                </div>
            </div>
        );
    }

    if (error || !tender) {
        return (
            <div className="animate-in" style={{ padding: '2rem' }}>
                <div className="card" style={{ borderColor: 'rgba(239, 68, 68, 0.35)', background: 'rgba(127, 29, 29, 0.18)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', color: '#fecaca' }}>
                        <AlertTriangle size={18} />
                        <div>
                            <h3 style={{ margin: 0, fontSize: '1rem' }}>Failed to load workspace</h3>
                            <p style={{ margin: '0.25rem 0 0 0', fontSize: '0.85rem' }}>{error || 'Tender not found.'}</p>
                            <button className="btn btn-secondary btn-sm" style={{ marginTop: '1rem' }} onClick={goBack}>
                                <ArrowLeft size={16} /> Back to KPI Dashboard
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        );
    }

    return (
        <div className="animate-in">
            <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '1rem', marginBottom: '1.5rem' }}>
                <div>
                    <button 
                        onClick={goBack}
                        style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '0.35rem',
                            background: 'transparent',
                            border: 'none',
                            color: 'var(--text-muted)',
                            cursor: 'pointer',
                            fontSize: '0.85rem',
                            padding: 0,
                            marginBottom: '0.75rem',
                        }}
                    >
                        <ArrowLeft size={14} /> Back to KPI Dashboard
                    </button>
                    <h1 className="page-title" style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                        <ClipboardList size={28} color="#38bdf8" />
                        Dedicated Operational Workspace
                    </h1>
                    <p className="page-subtitle" style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                        <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{tender.title}</span> 
                        <span style={{ color: 'var(--text-muted)' }}>— Workspace for contributions, requests, gates, and rework.</span>
                    </p>
                </div>
            </div>

            <OperationalWorkspacePanel tender={tender} />
        </div>
    );
}
