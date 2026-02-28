import { useState, useEffect, FC } from 'react';
import { motion } from 'framer-motion';
import {
    Save,
    RefreshCw,
    CheckCircle,
    XCircle,
    Loader2,
    AlertCircle,
    Server,
    Shield,
    Clock,
} from 'lucide-react';
import { ragApi, systemApi } from '../api/client';
import { useAuth } from '../contexts/AuthContext';

interface RAGHealth {
    status: string;
    components?: Record<string, unknown>;
    model?: string;
    [key: string]: unknown;
}

const Settings: FC = () => {
    const { user } = useAuth();
    const [health, setHealth] = useState<RAGHealth | null>(null);
    const [loadingHealth, setLoadingHealth] = useState(true);
    const [healthError, setHealthError] = useState<string | null>(null);

    const [profileName, setProfileName] = useState(user?.name || '');
    const [profileEmail, setProfileEmail] = useState(user?.email || '');

    // Nginx Config State
    const [readTimeout, setReadTimeout] = useState(300);
    const [connectTimeout, setConnectTimeout] = useState(300);
    const [sendTimeout, setSendTimeout] = useState(300);
    const [isSavingNginx, setIsSavingNginx] = useState(false);
    const [nginxResult, setNginxResult] = useState<{ success: boolean, message: string } | null>(null);

    const checkHealth = async () => {
        try {
            setLoadingHealth(true);
            setHealthError(null);
            const data = await ragApi.health();
            setHealth(data as RAGHealth);
        } catch (err) {
            setHealthError(err instanceof Error ? err.message : 'Could not reach backend');
        } finally {
            setLoadingHealth(false);
        }
    };

    useEffect(() => {
        checkHealth();
    }, []);

    const handleSaveNginx = async () => {
        setIsSavingNginx(true);
        setNginxResult(null);
        try {
            await systemApi.updateNginx({
                read_timeout: readTimeout,
                connect_timeout: connectTimeout,
                send_timeout: sendTimeout
            });
            setNginxResult({ success: true, message: 'Nginx config aggiornata con successo!' });
        } catch (err) {
            setNginxResult({ success: false, message: 'Errore durante l\'aggiornamento Nginx.' });
        } finally {
            setIsSavingNginx(false);
        }
    };

    const statusIcon = (ok: boolean) =>
        ok ? <CheckCircle size={16} color="#10b981" /> : <XCircle size={16} color="#ef4444" />;

    return (
        <motion.div
            className="animate-in"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            transition={{ duration: 0.3 }}
            style={{ maxWidth: '56rem', margin: '0 auto' }}
        >
            <div className="page-header">
                <div>
                    <h1 className="page-title">Settings</h1>
                    <p className="page-subtitle">Manage your application preferences and configurations.</p>
                </div>
            </div>

            <div style={{ display: 'grid', gap: '1.5rem' }}>
                {/* System Status */}
                <div className="card">
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
                        <h2 style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '1.1rem' }}>
                            <Server size={20} />
                            System Status
                        </h2>
                        <button className="btn btn-ghost btn-sm" onClick={checkHealth} disabled={loadingHealth}>
                            {loadingHealth ? <Loader2 size={14} className="spin" /> : <RefreshCw size={14} />}
                            Refresh
                        </button>
                    </div>

                    {healthError && (
                        <div style={{ padding: '0.75rem', borderRadius: 'var(--radius-sm)', background: 'rgba(239, 68, 68, 0.1)', color: '#ef4444', fontSize: '0.85rem', display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem' }}>
                            <AlertCircle size={16} />
                            Backend unreachable — make sure the API server is running.
                        </div>
                    )}

                    {loadingHealth && !healthError && (
                        <div style={{ textAlign: 'center', padding: '1.5rem 0' }}>
                            <div className="spinner" style={{ margin: '0 auto' }} />
                            <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem', marginTop: '0.5rem' }}>Checking system health...</p>
                        </div>
                    )}

                    {health && !loadingHealth && (
                        <div style={{ display: 'grid', gap: '0.5rem' }}>
                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0.75rem', background: 'var(--bg-glass)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-default)' }}>
                                <span style={{ fontWeight: 500 }}>API Server</span>
                                <span style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', fontSize: '0.85rem' }}>
                                    {statusIcon(true)} Online
                                </span>
                            </div>

                            {health.components && typeof health.components === 'object' && (
                                Object.entries(health.components).map(([key, value]) => (
                                    <div key={key} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0.75rem', background: 'var(--bg-glass)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-default)' }}>
                                        <span style={{ fontWeight: 500, textTransform: 'capitalize' }}>{key.replace('_', ' ')}</span>
                                        <span style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', fontSize: '0.85rem' }}>
                                            {statusIcon(value === 'ok' || value === true || value === 'healthy')}
                                            {String(value)}
                                        </span>
                                    </div>
                                ))
                            )}

                            {/* Show raw health data if no components */}
                            {!health.components && (
                                Object.entries(health)
                                    .filter(([key]) => key !== 'status')
                                    .map(([key, value]) => (
                                        <div key={key} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0.75rem', background: 'var(--bg-glass)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-default)' }}>
                                            <span style={{ fontWeight: 500, textTransform: 'capitalize' }}>{key.replace(/_/g, ' ')}</span>
                                            <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>{String(value)}</span>
                                        </div>
                                    ))
                            )}
                        </div>
                    )}
                </div>

                {/* Profile Section */}
                <div className="card">
                    <h2 style={{ fontSize: '1.1rem', marginBottom: '1rem' }}>Profile Settings</h2>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                        <div className="form-group">
                            <label className="form-label">Full Name</label>
                            <input
                                type="text"
                                className="form-input"
                                placeholder="John Doe"
                                value={profileName}
                                onChange={(e) => setProfileName(e.target.value)}
                            />
                        </div>
                        <div className="form-group">
                            <label className="form-label">Email Address</label>
                            <input
                                type="email"
                                className="form-input"
                                placeholder="john@example.com"
                                value={profileEmail}
                                onChange={(e) => setProfileEmail(e.target.value)}
                            />
                        </div>
                    </div>
                    <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: '0.5rem' }}>
                        Profile updates will be available once authentication is fully integrated.
                    </p>
                </div>

                {/* RAG Configuration */}
                <div className="card">
                    <h2 style={{ fontSize: '1.1rem', marginBottom: '1rem' }}>RAG Engine Configuration</h2>
                    <div style={{ display: 'grid', gap: '0.75rem' }}>
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '1rem', background: 'var(--bg-glass)', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-default)' }}>
                            <div>
                                <h3 style={{ fontWeight: 500, fontSize: '0.9rem' }}>LLM Model</h3>
                                <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Select the model used for text generation</p>
                            </div>
                            <select className="form-select" style={{ maxWidth: 200 }} defaultValue="Llama 3 (8b)">
                                <option>Llama 3 (8b)</option>
                                <option>Mistral 7b</option>
                                <option>Qwen 2.5</option>
                            </select>
                        </div>
                    </div>
                </div>

                {/* Admin Only: Infrastructure Settings */}
                {user?.role === 'admin' && (
                    <div className="card" style={{ borderColor: 'var(--accent-blue)' }}>
                        <h2 style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '1.1rem', color: 'var(--accent-blue)' }}>
                            <Shield size={20} />
                            Infrastruttura (Admin)
                        </h2>
                        <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: '1.5rem' }}>
                            Configurazione avanzata dei componenti di sistema.
                        </p>

                        <div style={{ display: 'grid', gap: '1.25rem' }}>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', padding: '1rem', background: 'var(--bg-glass)', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-default)' }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                    <Clock size={16} />
                                    <h3 style={{ fontWeight: 600, fontSize: '0.9rem', margin: 0 }}>Nginx Proxy Timeouts (secondi)</h3>
                                </div>
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '1rem' }}>
                                    <div className="form-group">
                                        <label className="form-label" style={{ fontSize: '0.75rem' }}>Read Timeout</label>
                                        <input type="number" className="form-input" value={readTimeout} onChange={(e) => setReadTimeout(Number(e.target.value))} />
                                    </div>
                                    <div className="form-group">
                                        <label className="form-label" style={{ fontSize: '0.75rem' }}>Connect Timeout</label>
                                        <input type="number" className="form-input" value={connectTimeout} onChange={(e) => setConnectTimeout(Number(e.target.value))} />
                                    </div>
                                    <div className="form-group">
                                        <label className="form-label" style={{ fontSize: '0.75rem' }}>Send Timeout</label>
                                        <input type="number" className="form-input" value={sendTimeout} onChange={(e) => setSendTimeout(Number(e.target.value))} />
                                    </div>
                                </div>
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '0.5rem' }}>
                                    {nginxResult && (
                                        <span style={{ fontSize: '0.8rem', color: nginxResult.success ? 'var(--accent-green)' : '#ef4444' }}>
                                            {nginxResult.message}
                                        </span>
                                    )}
                                    <button
                                        className="btn btn-primary btn-sm"
                                        onClick={handleSaveNginx}
                                        disabled={isSavingNginx}
                                        style={{ background: 'var(--accent-blue)' }}
                                    >
                                        {isSavingNginx ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
                                        Applica a Caldo
                                    </button>
                                </div>
                            </div>

                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '1rem', background: 'var(--bg-glass)', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-default)' }}>
                                <div>
                                    <h3 style={{ fontWeight: 600, fontSize: '0.9rem', margin: 0 }}>Utenza Tecnica Admin</h3>
                                    <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', margin: '0.25rem 0 0 0' }}>Abilita o disabilita l'utenza admin/admin</p>
                                </div>
                                <label className="switch">
                                    <input type="checkbox" defaultChecked />
                                    <span className="slider round"></span>
                                </label>
                            </div>
                        </div>
                    </div>
                )}

                <div style={{ display: 'flex', justifyContent: 'flex-end', paddingTop: '0.5rem' }}>
                    <button
                        className="btn btn-primary"
                        disabled
                        title="Save endpoint not yet available"
                    >
                        <Save size={18} />
                        Save Changes
                    </button>
                </div>
            </div>
        </motion.div>
    );
};

export default Settings;
