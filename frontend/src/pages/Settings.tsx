import { useState, useEffect, useRef, FC } from 'react';
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
import {
    ragApi,
    systemApi,
    gatewayApi,
    llmSettingsApi,
    authApi,
    anonymizerApi,
    GatewayTarget,
    type SystemCapabilitiesData,
    type AnonymizerConfigData,
    type AnonymizerStatsData,
    type AnonymizerTestResult,
} from '../api/client';
import { useAuth } from '../contexts/AuthContext';

interface RAGHealth {
    status: string;
    components?: Record<string, unknown>;
    model?: string;
    [key: string]: unknown;
}

let tempIdCounter = -1;

const ANONYMIZER_ENTITY_OPTIONS = [
    { key: 'PERSON', label: 'Persone' },
    { key: 'ORGANIZATION', label: 'Organizzazioni' },
    { key: 'LOCATION', label: 'Luoghi' },
    { key: 'CODICE_FISCALE', label: 'Codice fiscale' },
    { key: 'PARTITA_IVA', label: 'Partita IVA' },
    { key: 'IBAN', label: 'IBAN' },
] as const;

const DEFAULT_ANONYMIZER_CONFIG: AnonymizerConfigData = {
    entities: ['PERSON', 'CODICE_FISCALE', 'PARTITA_IVA', 'IBAN'],
    ttl_seconds: 3600,
    strategy: 'redaction',
    min_confidence: 0.35,
    mask_cig: false,
};

const Settings: FC = () => {
    const { user } = useAuth();
    const [health, setHealth] = useState<RAGHealth | null>(null);
    const [loadingHealth, setLoadingHealth] = useState(true);
    const [healthError, setHealthError] = useState<string | null>(null);

    // ── All settings state ──
    const [profileName, setProfileName] = useState(user?.name || '');
    const [profileEmail, setProfileEmail] = useState(user?.email || '');
    const [ragModel, setRagModel] = useState('Llama 3 (8b)');
    const [readTimeout, setReadTimeout] = useState(300);
    const [connectTimeout, setConnectTimeout] = useState(300);
    const [sendTimeout, setSendTimeout] = useState(300);
    const [adminEnabled, setAdminEnabled] = useState(true);
    const [anonymizerEnabled, setAnonymizerEnabled] = useState(false);
    const [llmMaxTokens, setLlmMaxTokens] = useState<number | ''>(256);
    const [llmTemperature, setLlmTemperature] = useState<number | ''>(0.3);
    const [llmStopTokens, setLlmStopTokens] = useState<string>('');
    const [systemCapabilities, setSystemCapabilities] = useState<SystemCapabilitiesData | null>(null);
    const [capabilitiesLoading, setCapabilitiesLoading] = useState(false);
    const [capabilitiesError, setCapabilitiesError] = useState<string | null>(null);
    const [anonymizerConfig, setAnonymizerConfig] = useState<AnonymizerConfigData>(DEFAULT_ANONYMIZER_CONFIG);
    const [anonymizerStats, setAnonymizerStats] = useState<AnonymizerStatsData | null>(null);
    const [anonymizerLoading, setAnonymizerLoading] = useState(false);
    const [anonymizerError, setAnonymizerError] = useState<string | null>(null);
    const [anonymizerTesting, setAnonymizerTesting] = useState(false);
    const [anonymizerTestInput, setAnonymizerTestInput] = useState(
        'Mario Rossi ha CF RSSMRA85M01H501Z e coordina la gara CIG A1B2C3D4E5.'
    );
    const [anonymizerTestResult, setAnonymizerTestResult] = useState<AnonymizerTestResult | null>(null);
    const [anonymizerTestError, setAnonymizerTestError] = useState<string | null>(null);

    // ── Global save state ──
    const [isSaving, setIsSaving] = useState(false);
    const [saveResult, setSaveResult] = useState<{ tone: 'success' | 'warning' | 'error'; message: string } | null>(null);

    // ── Gateway targets (local state, saved globally) ──
    const [gatewayTargets, setGatewayTargets] = useState<GatewayTarget[]>([]);
    const savedTargetsRef = useRef<GatewayTarget[]>([]);  // snapshot of DB state
    const [gwLoading, setGwLoading] = useState(false);
    const [gwError, setGwError] = useState<string | null>(null);
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

    // ── Load functions ──

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

    const loadAllSettings = async () => {
        // Load profile
        try {
            const me = await authApi.me();
            setProfileName(me.name || '');
            setProfileEmail(me.email || '');
        } catch {
            // fallback to context user
        }

        // Load app settings
        try {
            const s = await systemApi.getAppSettings();
            if (s.rag_model) setRagModel(s.rag_model);
            if (s.nginx_read_timeout !== undefined) setReadTimeout(s.nginx_read_timeout);
            if (s.nginx_connect_timeout !== undefined) setConnectTimeout(s.nginx_connect_timeout);
            if (s.nginx_send_timeout !== undefined) setSendTimeout(s.nginx_send_timeout);
            if (s.admin_enabled !== undefined) setAdminEnabled(s.admin_enabled);
            if (s.anonymizer_enabled !== undefined) setAnonymizerEnabled(s.anonymizer_enabled);
        } catch {
            // defaults already set
        }

        // Load LLM settings (admin only)
        if (user?.role === 'admin') {
            try {
                const res = await llmSettingsApi.get();
                setLlmMaxTokens(res.max_tokens ?? '');
                setLlmTemperature(res.temperature ?? '');
                setLlmStopTokens(res.stop_tokens ?? '');
            } catch {
                // defaults
            }
        }
    };

    const loadAnonymizerPanel = async () => {
        if (user?.role !== 'admin') {
            return;
        }
        try {
            setAnonymizerLoading(true);
            setAnonymizerError(null);
            const [config, stats] = await Promise.all([
                anonymizerApi.getConfig(),
                anonymizerApi.getStats(),
            ]);
            setAnonymizerConfig({
                entities: config.entities?.length ? config.entities : DEFAULT_ANONYMIZER_CONFIG.entities,
                ttl_seconds: config.ttl_seconds ?? DEFAULT_ANONYMIZER_CONFIG.ttl_seconds,
                strategy: config.strategy ?? DEFAULT_ANONYMIZER_CONFIG.strategy,
                min_confidence: config.min_confidence ?? DEFAULT_ANONYMIZER_CONFIG.min_confidence,
                mask_cig: config.mask_cig ?? DEFAULT_ANONYMIZER_CONFIG.mask_cig,
            });
            setAnonymizerStats(stats);
        } catch (err) {
            setAnonymizerError(err instanceof Error ? err.message : 'Impossibile caricare il modulo anonymizer.');
        } finally {
            setAnonymizerLoading(false);
        }
    };

    const loadGatewayTargets = async () => {
        try {
            setGwLoading(true);
            setGwError(null);
            const items = await gatewayApi.listTargets();
            const sorted = items.sort((a, b) => a.priority - b.priority);
            setGatewayTargets(sorted);
            savedTargetsRef.current = sorted.map((t) => ({ ...t })); // deep copy snapshot
        } catch {
            setGwError('Impossibile caricare le configurazioni del gateway.');
        } finally {
            setGwLoading(false);
        }
    };

    const loadSystemCapabilities = async () => {
        if (user?.role !== 'admin') {
            return;
        }
        try {
            setCapabilitiesLoading(true);
            setCapabilitiesError(null);
            const capabilities = await systemApi.getCapabilities();
            setSystemCapabilities(capabilities);
        } catch (err) {
            setCapabilitiesError(err instanceof Error ? err.message : 'Impossibile rilevare le capability infrastrutturali.');
        } finally {
            setCapabilitiesLoading(false);
        }
    };

    useEffect(() => {
        checkHealth();
        loadAllSettings();
        if (user?.role === 'admin') {
            loadGatewayTargets();
            loadSystemCapabilities();
            loadAnonymizerPanel();
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [user?.role]);

    // ── Gateway local-only operations ──

    const handleAddTarget = () => {
        if (!gwForm.base_url) {
            setGwError('Base URL obbligatoria');
            return;
        }
        setGwError(null);
        const newTarget: GatewayTarget = {
            id: tempIdCounter--,  // negative temporary ID
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
        };
        setGatewayTargets((prev) => [...prev, newTarget].sort((a, b) => a.priority - b.priority));
        setGwForm((f) => ({ ...f, base_url: '', model_name: '' }));
    };

    const toggleEnable = (t: GatewayTarget) => {
        setGatewayTargets((prev) =>
            prev.map((x) => (x.id === t.id ? { ...x, enabled: !x.enabled } : x))
        );
    };

    const removeTarget = (id: number) => {
        setGatewayTargets((prev) => prev.filter((x) => x.id !== id));
    };

    const toggleAnonymizerEntity = (entity: string) => {
        setAnonymizerConfig((prev) => {
            const alreadyEnabled = prev.entities.includes(entity);
            return {
                ...prev,
                entities: alreadyEnabled
                    ? prev.entities.filter((item) => item !== entity)
                    : [...prev.entities, entity],
            };
        });
    };

    const handleRunAnonymizerTest = async () => {
        try {
            setAnonymizerTesting(true);
            setAnonymizerTestError(null);
            const result = await anonymizerApi.test({
                text: anonymizerTestInput,
                config: anonymizerConfig,
            });
            setAnonymizerTestResult(result);
            await loadAnonymizerPanel();
        } catch (err) {
            setAnonymizerTestError(err instanceof Error ? err.message : 'Test anonymizer fallito.');
        } finally {
            setAnonymizerTesting(false);
        }
    };

    // ── Single global save ──

    const handleSaveAll = async () => {
        setIsSaving(true);
        setSaveResult(null);
        const errors: string[] = [];
        const warnings: string[] = [];

        // 1) Save profile
        try {
            await authApi.updateProfile({ name: profileName, email: profileEmail });
        } catch (err) {
            errors.push(err instanceof Error ? err.message : 'Errore salvataggio profilo');
        }

        // 2) Save app settings
        try {
                await systemApi.updateAppSettings({
                    rag_model: ragModel,
                    nginx_read_timeout: readTimeout,
                    nginx_connect_timeout: connectTimeout,
                    nginx_send_timeout: sendTimeout,
                    admin_enabled: adminEnabled,
                    anonymizer_enabled: anonymizerEnabled,
                });
        } catch (err) {
            errors.push(err instanceof Error ? err.message : 'Errore salvataggio impostazioni app');
        }

        // 3) Save LLM settings (admin only)
        if (user?.role === 'admin') {
            try {
                await llmSettingsApi.update({
                    max_tokens: llmMaxTokens === '' ? null : Number(llmMaxTokens),
                    temperature: llmTemperature === '' ? null : Number(llmTemperature),
                    stop_tokens: llmStopTokens || null,
                });
            } catch (err) {
                errors.push(err instanceof Error ? err.message : 'Errore salvataggio LLM settings');
            }

            try {
                await anonymizerApi.updateConfig(anonymizerConfig);
            } catch (err) {
                errors.push(err instanceof Error ? err.message : 'Errore salvataggio configurazione anonymizer');
            }
        }

        // 4) Apply nginx hot-reload (best-effort)
        if (user?.role === 'admin') {
            if (systemCapabilities?.nginx_hot_reload.available) {
                try {
                    await systemApi.updateNginx({
                        read_timeout: readTimeout,
                        connect_timeout: connectTimeout,
                        send_timeout: sendTimeout,
                    });
                } catch (err) {
                    warnings.push(err instanceof Error ? `Timeout salvati, ma non applicati live: ${err.message}` : 'Timeout salvati, ma hot-reload Nginx non disponibile.');
                }
            } else {
                warnings.push(systemCapabilities?.nginx_hot_reload.reason || 'Timeout salvati, ma hot-reload Nginx non disponibile in questo ambiente.');
            }
        }

        // 5) Sync gateway targets
        if (user?.role === 'admin') {
            const saved = savedTargetsRef.current;
            const current = gatewayTargets;
            const savedIds = new Set(saved.map((t) => t.id));
            const currentIds = new Set(current.map((t) => t.id));

            // Delete: in saved but not in current
            for (const t of saved) {
                if (!currentIds.has(t.id)) {
                    try {
                        await gatewayApi.deleteTarget(t.id);
                    } catch (err) {
                        errors.push(`Errore cancellazione target ${t.base_url}`);
                    }
                }
            }

            // Create: in current with negative IDs (new)
            for (const t of current) {
                if (t.id < 0) {
                    try {
                        await gatewayApi.createTarget({
                            route_key: t.route_key,
                            target_kind: t.target_kind,
                            provider: t.provider,
                            base_url: t.base_url,
                            model_name: t.model_name || '',
                            enabled: t.enabled,
                            priority: t.priority,
                            timeout_ms: t.timeout_ms,
                            use_anonymizer: t.use_anonymizer,
                            metadata_json: {},
                        } as any);
                    } catch (err) {
                        errors.push(`Errore creazione target ${t.base_url}`);
                    }
                }
            }

            // Update: in both but with changed enabled
            for (const t of current) {
                if (t.id > 0 && savedIds.has(t.id)) {
                    const original = saved.find((s) => s.id === t.id);
                    if (original && original.enabled !== t.enabled) {
                        try {
                            await gatewayApi.updateTarget(t.id, { enabled: t.enabled });
                        } catch (err) {
                            errors.push(`Errore aggiornamento target ${t.base_url}`);
                        }
                    }
                }
            }

            // Reload gateway targets from DB to get real IDs
            try {
                const items = await gatewayApi.listTargets();
                const sorted = items.sort((a, b) => a.priority - b.priority);
                setGatewayTargets(sorted);
                savedTargetsRef.current = sorted.map((t) => ({ ...t }));
            } catch {
                // ignore reload error
            }

            try {
                await loadAnonymizerPanel();
            } catch {
                // ignore refresh error
            }
        }

        if (errors.length > 0) {
            const message = warnings.length > 0 ? `${errors.join(' · ')} · ${warnings.join(' · ')}` : errors.join(' · ');
            setSaveResult({ tone: 'error', message });
        } else if (warnings.length > 0) {
            setSaveResult({ tone: 'warning', message: `Impostazioni salvate. ${warnings.join(' · ')}` });
        } else {
            setSaveResult({ tone: 'success', message: 'Tutte le impostazioni sono state salvate con successo!' });
        }
        setIsSaving(false);
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
            <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div>
                    <h1 className="page-title">Settings</h1>
                    <p className="page-subtitle">Manage your application preferences and configurations.</p>
                </div>
                <button
                    className="btn btn-primary"
                    onClick={handleSaveAll}
                    disabled={isSaving}
                    style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', minWidth: '180px', justifyContent: 'center' }}
                >
                    {isSaving ? <Loader2 size={18} className="animate-spin" /> : <Save size={18} />}
                    {isSaving ? 'Salvataggio...' : 'Salva Impostazioni'}
                </button>
            </div>

            {/* Global save feedback */}
            {saveResult && (
                <div style={{
                    padding: '0.75rem 1rem',
                    borderRadius: 'var(--radius-sm)',
                    background: saveResult.tone === 'success'
                        ? 'rgba(16, 185, 129, 0.1)'
                        : saveResult.tone === 'warning'
                            ? 'rgba(245, 158, 11, 0.1)'
                            : 'rgba(239, 68, 68, 0.1)',
                    color: saveResult.tone === 'success'
                        ? '#10b981'
                        : saveResult.tone === 'warning'
                            ? '#d97706'
                            : '#ef4444',
                    fontSize: '0.85rem',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.5rem',
                    marginBottom: '1.5rem',
                    border: saveResult.tone === 'success'
                        ? '1px solid rgba(16, 185, 129, 0.3)'
                        : saveResult.tone === 'warning'
                            ? '1px solid rgba(245, 158, 11, 0.3)'
                            : '1px solid rgba(239, 68, 68, 0.3)',
                }}>
                    {saveResult.tone === 'success' ? <CheckCircle size={16} /> : <AlertCircle size={16} />}
                    {saveResult.message}
                </div>
            )}

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
                            <select
                                className="form-select"
                                style={{ maxWidth: 200 }}
                                value={ragModel}
                                onChange={(e) => setRagModel(e.target.value)}
                            >
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
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '1rem' }}>
                            <h2 style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '1.1rem', color: 'var(--accent-blue)', margin: 0 }}>
                                <Shield size={20} />
                                Infrastruttura (Admin)
                            </h2>
                            <button className="btn btn-ghost btn-sm" onClick={loadSystemCapabilities} disabled={capabilitiesLoading}>
                                {capabilitiesLoading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
                                Ops Status
                            </button>
                        </div>
                        <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: '1.5rem' }}>
                            Configurazione avanzata dei componenti di sistema.
                        </p>

                        {capabilitiesError && (
                            <div style={{ marginBottom: '1rem', padding: '0.75rem', borderRadius: 'var(--radius-sm)', background: 'rgba(239, 68, 68, 0.1)', color: '#ef4444', fontSize: '0.85rem' }}>
                                {capabilitiesError}
                            </div>
                        )}

                        {systemCapabilities && (
                            <div style={{ display: 'grid', gap: '0.75rem', marginBottom: '1.25rem' }}>
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: '0.75rem', alignItems: 'center', padding: '0.85rem 1rem', background: 'var(--bg-glass)', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-default)' }}>
                                    <div>
                                        <div style={{ fontWeight: 600, fontSize: '0.9rem' }}>Ops Agent</div>
                                        <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                                            {systemCapabilities.ops_agent.reason || 'Servizio privilegiato interno disponibile.'}
                                        </div>
                                    </div>
                                    <span style={{ fontSize: '0.8rem', color: systemCapabilities.ops_agent.available ? '#10b981' : '#d97706' }}>
                                        {systemCapabilities.ops_agent.available ? 'Connected' : 'Unavailable'}
                                    </span>
                                </div>
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: '0.75rem', alignItems: 'center', padding: '0.85rem 1rem', background: 'var(--bg-glass)', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-default)' }}>
                                    <div>
                                        <div style={{ fontWeight: 600, fontSize: '0.9rem' }}>Live Nginx Apply</div>
                                        <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                                            {systemCapabilities.nginx_hot_reload.reason || 'I timeout possono essere applicati live sul container frontend.'}
                                        </div>
                                    </div>
                                    <span style={{ fontSize: '0.8rem', color: systemCapabilities.nginx_hot_reload.available ? '#10b981' : '#d97706' }}>
                                        {systemCapabilities.nginx_hot_reload.available ? 'Enabled' : 'Disabled'}
                                    </span>
                                </div>
                            </div>
                        )}

                        <div style={{ display: 'grid', gap: '1.25rem' }}>
                            {/* Nginx Timeouts */}
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
                            </div>

                            {/* Admin Toggle */}
                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '1rem', background: 'var(--bg-glass)', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-default)' }}>
                                <div>
                                    <h3 style={{ fontWeight: 600, fontSize: '0.9rem', margin: 0 }}>Utenza Tecnica Admin</h3>
                                    <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', margin: '0.25rem 0 0 0' }}>Abilita o disabilita l'utenza admin/admin</p>
                                </div>
                                <label className="switch">
                                    <input
                                        type="checkbox"
                                        checked={adminEnabled}
                                        onChange={(e) => setAdminEnabled(e.target.checked)}
                                    />
                                    <span className="slider round"></span>
                                </label>
                            </div>

                            {/* LLM Settings */}
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', padding: '1rem', background: 'var(--bg-glass)', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-default)' }}>
                                <h3 style={{ fontWeight: 600, fontSize: '0.9rem', margin: 0 }}>LLM Settings (tender)</h3>
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

                            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', padding: '1rem', background: 'var(--bg-glass)', borderRadius: 'var(--radius-md)', border: '1px solid rgba(14, 116, 144, 0.28)' }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '1rem' }}>
                                    <div>
                                        <h3 style={{ fontWeight: 600, fontSize: '0.9rem', margin: 0 }}>Privacy Gateway / Anonymizer</h3>
                                        <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', margin: '0.35rem 0 0 0' }}>
                                            Governa anonimizzazione, strategy, entita da mascherare e test rapido prima di usare LLM esterne.
                                        </p>
                                    </div>
                                    <button className="btn btn-ghost btn-sm" onClick={loadAnonymizerPanel} disabled={anonymizerLoading}>
                                        {anonymizerLoading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
                                        Aggiorna
                                    </button>
                                </div>

                                {anonymizerError && (
                                    <div style={{ padding: '0.75rem', borderRadius: 'var(--radius-sm)', background: 'rgba(239, 68, 68, 0.1)', color: '#ef4444', fontSize: '0.85rem' }}>
                                        {anonymizerError}
                                    </div>
                                )}

                                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '1rem', background: 'rgba(14, 116, 144, 0.08)', borderRadius: 'var(--radius-md)', border: '1px solid rgba(14, 116, 144, 0.2)' }}>
                                    <div>
                                        <h4 style={{ fontWeight: 600, fontSize: '0.9rem', margin: 0 }}>Anonymizer globale</h4>
                                        <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', margin: '0.25rem 0 0 0' }}>
                                            Se attivo, il backend prova a anonimizzare prima di usare route esterne e ripiega sull&apos;LLM interna in caso di errore.
                                        </p>
                                    </div>
                                    <label className="switch">
                                        <input
                                            type="checkbox"
                                            checked={anonymizerEnabled}
                                            onChange={(e) => setAnonymizerEnabled(e.target.checked)}
                                        />
                                        <span className="slider round"></span>
                                    </label>
                                </div>

                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
                                    <div className="form-group">
                                        <label className="form-label">Strategy</label>
                                        <select
                                            className="form-select"
                                            value={anonymizerConfig.strategy}
                                            onChange={(e) => setAnonymizerConfig((prev) => ({ ...prev, strategy: e.target.value as AnonymizerConfigData['strategy'] }))}
                                        >
                                            <option value="redaction">Redaction</option>
                                            <option value="faking">Faking</option>
                                        </select>
                                    </div>
                                    <div className="form-group">
                                        <label className="form-label">TTL sessione (s)</label>
                                        <input
                                            type="number"
                                            className="form-input"
                                            min={1}
                                            value={anonymizerConfig.ttl_seconds}
                                            onChange={(e) => setAnonymizerConfig((prev) => ({ ...prev, ttl_seconds: Math.max(1, Number(e.target.value) || 1) }))}
                                        />
                                    </div>
                                    <div className="form-group" style={{ gridColumn: 'span 2' }}>
                                        <label className="form-label">Soglia confidence: {anonymizerConfig.min_confidence.toFixed(2)}</label>
                                        <input
                                            type="range"
                                            min={0}
                                            max={1}
                                            step={0.05}
                                            value={anonymizerConfig.min_confidence}
                                            onChange={(e) => setAnonymizerConfig((prev) => ({ ...prev, min_confidence: Number(e.target.value) }))}
                                            style={{ width: '100%' }}
                                        />
                                    </div>
                                </div>

                                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: '0.75rem' }}>
                                    {ANONYMIZER_ENTITY_OPTIONS.map((option) => (
                                        <label
                                            key={option.key}
                                            style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.75rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-default)', background: 'var(--bg-secondary)', fontSize: '0.85rem' }}
                                        >
                                            <input
                                                type="checkbox"
                                                checked={anonymizerConfig.entities.includes(option.key)}
                                                onChange={() => toggleAnonymizerEntity(option.key)}
                                            />
                                            {option.label}
                                        </label>
                                    ))}
                                    <label
                                        style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.75rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-default)', background: 'var(--bg-secondary)', fontSize: '0.85rem' }}
                                    >
                                        <input
                                            type="checkbox"
                                            checked={anonymizerConfig.mask_cig}
                                            onChange={(e) => setAnonymizerConfig((prev) => ({ ...prev, mask_cig: e.target.checked }))}
                                        />
                                        Maschera CIG
                                    </label>
                                </div>

                                {anonymizerStats && (
                                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: '0.75rem' }}>
                                        {[
                                            { label: 'Richieste', value: anonymizerStats.requests },
                                            { label: 'Sessioni', value: anonymizerStats.sessions },
                                            { label: 'Entita rilevate', value: anonymizerStats.entities_detected },
                                            { label: 'Deanonymize', value: anonymizerStats.deanonymize_requests },
                                            { label: 'Fallback backend', value: anonymizerStats.fallback_events ?? 0 },
                                            { label: 'Faking requests', value: anonymizerStats.faking_requests ?? 0 },
                                        ].map((item) => (
                                            <div key={item.label} style={{ padding: '0.85rem 1rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-default)', background: 'var(--bg-secondary)' }}>
                                                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{item.label}</div>
                                                <div style={{ fontWeight: 700, fontSize: '1.1rem', marginTop: '0.15rem' }}>{item.value}</div>
                                            </div>
                                        ))}
                                    </div>
                                )}

                                {anonymizerStats && (
                                    <div style={{ padding: '0.85rem 1rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-default)', background: 'var(--bg-secondary)', fontSize: '0.82rem', color: 'var(--text-muted)' }}>
                                        Circuit breaker: <strong style={{ color: anonymizerStats.circuit_open ? '#ef4444' : 'var(--text-primary)' }}>{anonymizerStats.circuit_open ? 'OPEN' : 'CLOSED'}</strong>
                                        {' · '}failure count: <strong style={{ color: 'var(--text-primary)' }}>{anonymizerStats.runtime_failure_count ?? 0}</strong>
                                        {' · '}last error: <strong style={{ color: 'var(--text-primary)' }}>{anonymizerStats.last_error_reason || 'none'}</strong>
                                    </div>
                                )}

                                <div style={{ display: 'grid', gap: '0.75rem', padding: '1rem', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-default)', background: 'var(--bg-secondary)' }}>
                                    <div>
                                        <h4 style={{ fontWeight: 600, fontSize: '0.9rem', margin: 0 }}>Area test</h4>
                                        <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', margin: '0.25rem 0 0 0' }}>
                                            Prova la resa della configurazione corrente senza toccare il flusso utente.
                                        </p>
                                    </div>
                                    <textarea
                                        className="form-input"
                                        rows={5}
                                        value={anonymizerTestInput}
                                        onChange={(e) => setAnonymizerTestInput(e.target.value)}
                                        style={{ resize: 'vertical' }}
                                    />
                                    <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', flexWrap: 'wrap' }}>
                                        <button className="btn btn-primary btn-sm" onClick={handleRunAnonymizerTest} disabled={anonymizerTesting || !anonymizerTestInput.trim()}>
                                            {anonymizerTesting ? <Loader2 size={14} className="animate-spin" /> : <Shield size={14} />}
                                            Test Anonimizzazione
                                        </button>
                                        {anonymizerTestError && <span style={{ color: '#ef4444', fontSize: '0.85rem' }}>{anonymizerTestError}</span>}
                                    </div>
                                    {anonymizerTestResult && (
                                        <div style={{ display: 'grid', gap: '0.75rem' }}>
                                            <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                                                Sessione: <strong style={{ color: 'var(--text-primary)' }}>{anonymizerTestResult.session_id}</strong>
                                            </div>
                                            <div style={{ padding: '0.85rem 1rem', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-default)', background: '#0f172a', color: '#e2e8f0', fontFamily: 'monospace', whiteSpace: 'pre-wrap' }}>
                                                {anonymizerTestResult.chunk?.anonymized_text || anonymizerTestResult.chunks?.map((item) => item.anonymized_text).join('\n\n---\n\n') || 'Nessun output'}
                                            </div>
                                        </div>
                                    )}
                                </div>
                            </div>

                            {/* Gateway Targets */}
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
                                        <div
                                            key={t.id}
                                            style={{
                                                display: 'grid',
                                                gridTemplateColumns: '1fr auto auto',
                                                gap: '0.5rem',
                                                alignItems: 'center',
                                                padding: '0.75rem',
                                                border: `1px solid ${t.id < 0 ? 'rgba(59, 130, 246, 0.4)' : 'var(--border-default)'}`,
                                                borderRadius: 'var(--radius-sm)',
                                                background: t.id < 0 ? 'rgba(59, 130, 246, 0.05)' : 'var(--bg-secondary)',
                                            }}
                                        >
                                            <div>
                                                <div style={{ fontWeight: 600, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                                    {t.route_key} · {t.provider}
                                                    {t.id < 0 && (
                                                        <span style={{ fontSize: '0.7rem', background: 'var(--accent-blue)', color: '#fff', padding: '0.1rem 0.4rem', borderRadius: '4px' }}>
                                                            nuovo
                                                        </span>
                                                    )}
                                                </div>
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

                {/* Bottom save button */}
                <div style={{ display: 'flex', justifyContent: 'flex-end', paddingTop: '0.5rem', paddingBottom: '2rem' }}>
                    <button
                        className="btn btn-primary"
                        onClick={handleSaveAll}
                        disabled={isSaving}
                        style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', minWidth: '180px', justifyContent: 'center' }}
                    >
                        {isSaving ? <Loader2 size={18} className="animate-spin" /> : <Save size={18} />}
                        {isSaving ? 'Salvataggio...' : 'Salva Impostazioni'}
                    </button>
                </div>
            </div>
        </motion.div>
    );
};

export default Settings;
