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
    Plus,
    Trash2,
    ToggleRight,
    ToggleLeft,
} from 'lucide-react';
import { ragApi, systemApi, gatewayApi, llmSettingsApi, GatewayTarget } from '../api/client';
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

    // Gateway targets (admin)
    const [gatewayTargets, setGatewayTargets] = useState<GatewayTarget[]>([]);
    const [gwLoading, setGwLoading] = useState(false);
    const [gwError, setGwError] = useState<string | null>(null);

    const [llmMaxTokens, setLlmMaxTokens] = useState<number | ''>(256);
    const [llmTemperature, setLlmTemperature] = useState<number | ''>(0.3);
    const [llmStopTokens, setLlmStopTokens] = useState<string>('');
    const [llmSaving, setLlmSaving] = useState(false);
    const [llmError, setLlmError] = useState<string | null>(null);
    const [gwForm, setGwForm] = useState<Partial<Omit<GatewayTarget, 'id'>>>({
        route_key: 'tender',
        target_kind: 'docker',
        provider: 'llama',
        base_url: '',
        model_name: '',
        priority: 1,
        timeout_ms: 30000,
        enabled: true,
        use_anonymizer: false,
    });

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
        if (user?.role === 'admin') {
            loadGatewayTargets();
            loadLlmSettings();
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [user?.role]);

    const loadGatewayTargets = async () => {
        try {
            setGwLoading(true);
            setGwError(null);
            const items = await gatewayApi.listTargets();
            setGatewayTargets(items.sort((a, b) => a.priority - b.priority));
        } catch (err) {
            setGwError('Impossibile caricare le configurazioni del gateway.');
        } finally {
            setGwLoading(false);
        }
    };


    const loadLlmSettings = async () => {
        try {
            const res = await llmSettingsApi.get();
            setLlmMaxTokens(res.max_tokens ?? '');
            setLlmTemperature(res.temperature ?? '');
            setLlmStopTokens(res.stop_tokens ?? '');
        } catch (err) {
            setLlmError('Impossibile caricare le impostazioni LLM');
        }
    };

    const saveLlmSettings = async () => {
        try {
            setLlmSaving(true);
            setLlmError(null);
            await llmSettingsApi.update({
                max_tokens: llmMaxTokens === '' ? null : Number(llmMaxTokens),
                temperature: llmTemperature === '' ? null : Number(llmTemperature),
                stop_tokens: llmStopTokens || null,
            });
        } catch (err) {
            setLlmError('Errore nel salvataggio delle impostazioni LLM');
        } finally {
            setLlmSaving(false);
        }
    };

    const handleAddTarget = async () => {
        if (!gwForm.base_url) {
            setGwError('Base URL obbligatoria');
            return;
        }
        try {
            setGwError(null);
            const created = await gatewayApi.createTarget({
                route_key: gwForm.route_key || 'tender',
                target_kind: gwForm.target_kind || 'docker',
                provider: gwForm.provider || 'llama',
                base_url: gwForm.base_url,
                model_name: gwForm.model_name || '',
                enabled: gwForm.enabled ?? true,
                priority: gwForm.priority ?? 1,
                timeout_ms: gwForm.timeout_ms ?? 30000,
                use_anonymizer: gwForm.use_anonymizer ?? false,
                metadata_json: {},
            } as any);
            setGatewayTargets((prev) => [...prev, created].sort((a, b) => a.priority - b.priority));
            setGwForm((f) => ({ ...f, base_url: '' }));
        } catch (err) {
            setGwError('Errore nel salvataggio del target.');
        }
    };

    const toggleEnable = async (t: GatewayTarget) => {
        try {
            const updated = await gatewayApi.updateTarget(t.id, { enabled: !t.enabled });
            setGatewayTargets((prev) => prev.map((x) => (x.id === t.id ? updated : x)));
        } catch (err) {
            setGwError('Errore nel salvataggio.');
        }
    };

    const removeTarget = async (id: number) => {
        try {
            await gatewayApi.deleteTarget(id);
            setGatewayTargets((prev) => prev.filter((x) => x.id !== id));
        } catch (err) {
            setGwError('Errore nella cancellazione.');
        }
    };

    const handleSaveNginx = async () => {
        setIsSavingNginx(true);
        setNginxResult(null);
        try {
            await systemApi.updateNginx({
                read_timeout: readTimeout,
                connect_timeout: connectTimeout,
                send_timeout: sendTimeout
            });
setNginxResult({ success: true, message: 'Nginx config updated successfully!' });
        } catch (err) {
            setNginxResult({ success: false, message: 'Error updating Nginx.' });
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


                            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', padding: '1rem', background: 'var(--bg-glass)', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-default)' }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                    <h3 style={{ fontWeight: 600, fontSize: '0.9rem', margin: 0 }}>LLM Settings (tender)</h3>
                                    <button className="btn btn-ghost btn-sm" onClick={saveLlmSettings} disabled={llmSaving}>
                                        {llmSaving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />} Salva
                                    </button>
                                </div>
                                {llmError && <div style={{ color: '#ef4444', fontSize: '0.85rem' }}>{llmError}</div>}
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
                                    <div className="form-group">
                                        <label className="form-label">Max tokens</label>
                                        <input type="number" className="form-input" value={llmMaxTokens} onChange={(e) => setLlmMaxTokens(e.target.value === '' ? '' : Number(e.target.value))} />
                                    </div>
                                    <div className="form-group">
                                        <label className="form-label">Temperature</label>
                                        <input type="number" step="0.01" className="form-input" value={llmTemperature} onChange={(e) => setLlmTemperature(e.target.value === '' ? '' : Number(e.target.value))} />
                                    </div>
                                    <div className="form-group" style={{ gridColumn: 'span 2' }}>
                                        <label className="form-label">Stop tokens (comma-separated)</label>
                                        <input className="form-input" value={llmStopTokens} onChange={(e) => setLlmStopTokens(e.target.value)} />
                                    </div>
                                </div>
                            </div>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', padding: '1rem', background: 'var(--bg-glass)', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-default)' }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                    <h3 style={{ fontWeight: 600, fontSize: '0.9rem', margin: 0 }}>AI Gateway Targets</h3>
                                    <button className="btn btn-ghost btn-sm" onClick={loadGatewayTargets} disabled={gwLoading}>
                                        <RefreshCw size={14} /> Aggiorna
                                    </button>
                                </div>
                                {gwError && <div style={{ color: '#ef4444', fontSize: '0.85rem' }}>{gwError}</div>}
                                <div style={{ display: 'grid', gap: '0.5rem' }}>
                                    {gatewayTargets.map((t) => (
                                        <div key={t.id} style={{ display: 'grid', gridTemplateColumns: '1fr auto auto', gap: '0.5rem', alignItems: 'center', padding: '0.75rem', border: '1px solid var(--border-default)', borderRadius: 'var(--radius-sm)', background: 'var(--bg-secondary)' }}>
                                            <div>
                                                <div style={{ fontWeight: 600 }}>{t.route_key} · {t.provider}</div>
                                                <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>{t.base_url}</div>
                                                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>prio {t.priority} · timeout {t.timeout_ms}ms · kind {t.target_kind}</div>
                                            </div>
                                            <button className="btn btn-ghost btn-sm" onClick={() => toggleEnable(t)} title="Abilita/Disabilita">
                                                {t.enabled ? <ToggleRight size={18} color="#10b981" /> : <ToggleLeft size={18} color="#ef4444" />}
                                            </button>
                                            <button className="btn btn-ghost btn-sm" onClick={() => removeTarget(t.id)} title="Elimina">
                                                <Trash2 size={16} />
                                            </button>
                                        </div>
                                    ))}
                                    {gatewayTargets.length === 0 && !gwLoading && (
                                        <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Nessun target configurato.</div>
                                    )}
                                </div>
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem', alignItems: 'center' }}>
                                    <select className="form-select" value={gwForm.route_key} onChange={(e) => setGwForm({ ...gwForm, route_key: e.target.value })}>
                                        <option value="tender">tender</option>
                                        <option value="opencode">opencode</option>
                                    </select>
                                    <input className="form-input" placeholder="Base URL" value={gwForm.base_url || ''} onChange={(e) => setGwForm({ ...gwForm, base_url: e.target.value })} />
                                    <input className="form-input" placeholder="Provider (llama/openai/anthropic)" value={gwForm.provider || ''} onChange={(e) => setGwForm({ ...gwForm, provider: e.target.value })} />
                                    <input className="form-input" placeholder="Modello (opzionale)" value={gwForm.model_name || ''} onChange={(e) => setGwForm({ ...gwForm, model_name: e.target.value })} />
                                    <input type="number" className="form-input" placeholder="Priorità" value={gwForm.priority ?? 1} onChange={(e) => setGwForm({ ...gwForm, priority: Number(e.target.value) })} />
                                    <input type="number" className="form-input" placeholder="Timeout ms" value={gwForm.timeout_ms ?? 30000} onChange={(e) => setGwForm({ ...gwForm, timeout_ms: Number(e.target.value) })} />
                                    <label style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', fontSize: '0.85rem' }}>
                                        <input type="checkbox" checked={gwForm.enabled ?? true} onChange={(e) => setGwForm({ ...gwForm, enabled: e.target.checked })} />
                                        Enabled
                                    </label>
                                    <label style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', fontSize: '0.85rem' }}>
                                        <input type="checkbox" checked={gwForm.use_anonymizer ?? false} onChange={(e) => setGwForm({ ...gwForm, use_anonymizer: e.target.checked })} />
                                        Usa anonymizer
                                    </label>
                                    <button className="btn btn-primary btn-sm" onClick={handleAddTarget} style={{ gridColumn: 'span 2', justifySelf: 'flex-start' }}>
                                        <Plus size={14} /> Aggiungi target
                                    </button>
                                </div>
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
