import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { motion } from 'framer-motion';
import {
    AlertCircle,
    CheckCircle,
    Loader2,
    RefreshCw,
    Save,
    Search,
    SlidersHorizontal,
} from 'lucide-react';
import {
    planningCoverageApi,
    type PlanningCoverageConfigData,
    type PlanningCoverageMode,
    type PlanningCoverageTestResult,
} from '../api/client';

const SLOT_LABELS: Record<string, string> = {
    identification: 'Identificazione procedura',
    cig_lots: 'CIG e lotti',
    amounts: 'Importi e massimali',
    duration: 'Durata',
    deadlines: 'Scadenze',
    platform: 'Piattaforma e accesso',
    scoring: 'Punteggi e criteri',
    certifications: 'Certificazioni',
    sla_penalties: 'SLA e penali',
    documents: 'Documenti e vincoli',
};

const RETRIEVER_LABELS: Record<string, string> = {
    sparse: 'BM25',
    dense: 'Vector',
    graph: 'Graph',
};

const DEFAULT_CONFIG: PlanningCoverageConfigData = {
    enabled: false,
    mode: 'adaptive',
    slots: {
        identification: true,
        cig_lots: true,
        amounts: true,
        duration: true,
        deadlines: true,
        platform: false,
        scoring: false,
        certifications: false,
        sla_penalties: false,
        documents: false,
    },
    retrievers: {
        sparse: true,
        dense: true,
        graph: false,
    },
    topkPerSlot: 2,
    maxSourcesPerSlot: 2,
    globalMaxCoverageChunks: 8,
    minScore: 0.2,
    onlyTenderQueries: true,
    alwaysRunPlanner: true,
};

const MODE_OPTIONS: Array<{ value: PlanningCoverageMode; label: string }> = [
    { value: 'adaptive', label: 'Adaptive' },
    { value: 'always_on', label: 'Always on' },
    { value: 'disabled', label: 'Disabled' },
];

function normalizeConfig(config?: Partial<PlanningCoverageConfigData>): PlanningCoverageConfigData {
    return {
        ...DEFAULT_CONFIG,
        ...config,
        slots: {
            ...DEFAULT_CONFIG.slots,
            ...(config?.slots || {}),
        },
        retrievers: {
            ...DEFAULT_CONFIG.retrievers,
            ...(config?.retrievers || {}),
        },
    };
}

function StatusBanner({ kind, children }: { kind: 'error' | 'success'; children: ReactNode }) {
    const colors = kind === 'error'
        ? { bg: 'rgba(239, 68, 68, 0.1)', fg: '#ef4444', border: 'rgba(239, 68, 68, 0.3)' }
        : { bg: 'rgba(16, 185, 129, 0.1)', fg: '#10b981', border: 'rgba(16, 185, 129, 0.3)' };
    const Icon = kind === 'error' ? AlertCircle : CheckCircle;

    return (
        <div style={{
            padding: '0.75rem 1rem',
            borderRadius: 'var(--radius-sm)',
            background: colors.bg,
            color: colors.fg,
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
            border: `1px solid ${colors.border}`,
        }}>
            <Icon size={16} />
            <span>{children}</span>
        </div>
    );
}

export default function PlanningCoverage() {
    const [config, setConfig] = useState<PlanningCoverageConfigData>(() => normalizeConfig());
    const [query, setQuery] = useState('Analizza questa gara e recupera CIG, importi e scadenze');
    const [testResult, setTestResult] = useState<PlanningCoverageTestResult | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [isSaving, setIsSaving] = useState(false);
    const [isTesting, setIsTesting] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [message, setMessage] = useState<string | null>(null);

    const enabledSlotCount = useMemo(
        () => Object.values(config.slots).filter(Boolean).length,
        [config.slots],
    );

    const loadConfig = async () => {
        try {
            setIsLoading(true);
            setError(null);
            const data = await planningCoverageApi.getConfig();
            setConfig(normalizeConfig(data));
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Unable to load planning coverage.');
        } finally {
            setIsLoading(false);
        }
    };

    useEffect(() => {
        void loadConfig();
    }, []);

    const updateSlot = (key: string, value: boolean) => {
        setConfig((prev) => ({
            ...prev,
            slots: {
                ...prev.slots,
                [key]: value,
            },
        }));
    };

    const updateRetriever = (key: string, value: boolean) => {
        setConfig((prev) => ({
            ...prev,
            retrievers: {
                ...prev.retrievers,
                [key]: value,
            },
        }));
    };

    const updateNumber = (
        key: 'topkPerSlot' | 'maxSourcesPerSlot' | 'globalMaxCoverageChunks' | 'minScore',
        value: string,
    ) => {
        const parsed = Number(value);
        if (!Number.isFinite(parsed)) {
            return;
        }
        setConfig((prev) => ({
            ...prev,
            [key]: parsed,
        }));
    };

    const saveConfig = async () => {
        try {
            setIsSaving(true);
            setError(null);
            setMessage(null);
            const saved = await planningCoverageApi.updateConfig(normalizeConfig(config));
            setConfig(normalizeConfig(saved));
            setMessage('Planning coverage saved.');
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Unable to save planning coverage.');
        } finally {
            setIsSaving(false);
        }
    };

    const testPlanner = async () => {
        if (!query.trim()) {
            setError('Query required.');
            return;
        }
        try {
            setIsTesting(true);
            setError(null);
            setTestResult(null);
            const result = await planningCoverageApi.test({
                query: query.trim(),
                config: normalizeConfig(config),
            });
            setTestResult(result);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Unable to test planning coverage.');
        } finally {
            setIsTesting(false);
        }
    };

    if (isLoading) {
        return (
            <div style={{
                minHeight: '360px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: 'var(--text-muted)',
                gap: '0.75rem',
            }}>
                <Loader2 size={24} className="animate-spin" />
                Loading planning coverage...
            </div>
        );
    }

    return (
        <motion.div
            className="animate-in"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            transition={{ duration: 0.3 }}
            style={{ maxWidth: '72rem', margin: '0 auto', paddingBottom: '3rem' }}
        >
            <div
                className="page-header"
                style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'flex-start',
                    gap: '1rem',
                }}
            >
                <div>
                    <h1 className="page-title">
                        <SlidersHorizontal
                            size={28}
                            color="var(--accent-blue)"
                            style={{ verticalAlign: 'middle', marginRight: 8 }}
                        />
                        Planning Coverage
                    </h1>
                    <p className="page-subtitle">{enabledSlotCount} slots enabled</p>
                </div>
                <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
                    <button className="btn btn-ghost" onClick={loadConfig} disabled={isSaving || isTesting}>
                        <RefreshCw size={18} /> Reload
                    </button>
                    <button className="btn btn-primary" onClick={saveConfig} disabled={isSaving || isTesting}>
                        {isSaving ? <Loader2 size={18} className="animate-spin" /> : <Save size={18} />}
                        Save
                    </button>
                </div>
            </div>

            <div style={{ display: 'grid', gap: '1rem', marginBottom: '1rem' }}>
                {error && <StatusBanner kind="error">{error}</StatusBanner>}
                {message && <StatusBanner kind="success">{message}</StatusBanner>}
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr)', gap: '1rem' }}>
                <section className="card" style={{ padding: '1.5rem', display: 'grid', gap: '1.25rem' }}>
                    <div style={{
                        display: 'grid',
                        gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
                        gap: '1rem',
                    }}>
                        <label className="form-label" style={{ display: 'grid', gap: '0.5rem' }}>
                            Stato
                            <span style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                <input
                                    type="checkbox"
                                    checked={config.enabled}
                                    onChange={(event) => setConfig((prev) => ({
                                        ...prev,
                                        enabled: event.target.checked,
                                    }))}
                                />
                                <span>{config.enabled ? 'Enabled' : 'Disabled'}</span>
                            </span>
                        </label>
                        <label className="form-label" style={{ display: 'grid', gap: '0.5rem' }}>
                            Mode
                            <select
                                className="form-input"
                                value={config.mode}
                                onChange={(event) => setConfig((prev) => ({
                                    ...prev,
                                    mode: event.target.value as PlanningCoverageMode,
                                }))}
                            >
                                {MODE_OPTIONS.map((option) => (
                                    <option key={option.value} value={option.value}>{option.label}</option>
                                ))}
                            </select>
                        </label>
                        <label className="form-label" style={{ display: 'grid', gap: '0.5rem' }}>
                            Tender only
                            <span style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                <input
                                    type="checkbox"
                                    checked={config.onlyTenderQueries}
                                    onChange={(event) => setConfig((prev) => ({
                                        ...prev,
                                        onlyTenderQueries: event.target.checked,
                                    }))}
                                />
                                <span>{config.onlyTenderQueries ? 'On' : 'Off'}</span>
                            </span>
                        </label>
                        <label className="form-label" style={{ display: 'grid', gap: '0.5rem' }}>
                            Broad overview
                            <span style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                <input
                                    type="checkbox"
                                    checked={config.alwaysRunPlanner}
                                    onChange={(event) => setConfig((prev) => ({
                                        ...prev,
                                        alwaysRunPlanner: event.target.checked,
                                    }))}
                                />
                                <span>{config.alwaysRunPlanner ? 'All enabled slots' : 'Triggered slots'}</span>
                            </span>
                        </label>
                    </div>
                </section>

                <section className="card" style={{ padding: '1.5rem', display: 'grid', gap: '1rem' }}>
                    <h2 style={{ margin: 0, fontSize: '1.1rem' }}>Coverage slots</h2>
                    <div style={{
                        display: 'grid',
                        gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
                        gap: '0.75rem',
                    }}>
                        {Object.entries(config.slots).map(([key, checked]) => (
                            <label
                                key={key}
                                style={{
                                    display: 'flex',
                                    alignItems: 'center',
                                    gap: '0.65rem',
                                    padding: '0.75rem',
                                    border: '1px solid var(--border)',
                                    borderRadius: 'var(--radius-sm)',
                                    color: 'var(--text-primary)',
                                }}
                            >
                                <input
                                    type="checkbox"
                                    checked={checked}
                                    onChange={(event) => updateSlot(key, event.target.checked)}
                                />
                                <span>{SLOT_LABELS[key] || key}</span>
                            </label>
                        ))}
                    </div>
                </section>

                <section className="card" style={{ padding: '1.5rem', display: 'grid', gap: '1rem' }}>
                    <h2 style={{ margin: 0, fontSize: '1.1rem' }}>Retrievers and limits</h2>
                    <div style={{
                        display: 'grid',
                        gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
                        gap: '0.75rem',
                    }}>
                        {Object.entries(config.retrievers).map(([key, checked]) => (
                            <label key={key} className="form-label" style={{ display: 'flex', gap: '0.5rem' }}>
                                <input
                                    type="checkbox"
                                    checked={checked}
                                    onChange={(event) => updateRetriever(key, event.target.checked)}
                                />
                                {RETRIEVER_LABELS[key] || key}
                            </label>
                        ))}
                    </div>
                    <div style={{
                        display: 'grid',
                        gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
                        gap: '1rem',
                    }}>
                        <label className="form-label" style={{ display: 'grid', gap: '0.4rem' }}>
                            Top-k per slot
                            <input
                                className="form-input"
                                type="number"
                                min={1}
                                max={10}
                                value={config.topkPerSlot}
                                onChange={(event) => updateNumber('topkPerSlot', event.target.value)}
                            />
                        </label>
                        <label className="form-label" style={{ display: 'grid', gap: '0.4rem' }}>
                            Sources per slot
                            <input
                                className="form-input"
                                type="number"
                                min={1}
                                max={10}
                                value={config.maxSourcesPerSlot}
                                onChange={(event) => updateNumber('maxSourcesPerSlot', event.target.value)}
                            />
                        </label>
                        <label className="form-label" style={{ display: 'grid', gap: '0.4rem' }}>
                            Global coverage cap
                            <input
                                className="form-input"
                                type="number"
                                min={1}
                                max={30}
                                value={config.globalMaxCoverageChunks}
                                onChange={(event) => updateNumber('globalMaxCoverageChunks', event.target.value)}
                            />
                        </label>
                        <label className="form-label" style={{ display: 'grid', gap: '0.4rem' }}>
                            Min score
                            <input
                                className="form-input"
                                type="number"
                                min={0}
                                max={1}
                                step={0.05}
                                value={config.minScore}
                                onChange={(event) => updateNumber('minScore', event.target.value)}
                            />
                        </label>
                    </div>
                </section>

                <section className="card" style={{ padding: '1.5rem', display: 'grid', gap: '1rem' }}>
                    <h2 style={{ margin: 0, fontSize: '1.1rem' }}>Planner test</h2>
                    <div style={{ display: 'grid', gap: '0.75rem' }}>
                        <textarea
                            className="form-input"
                            rows={3}
                            value={query}
                            onChange={(event) => setQuery(event.target.value)}
                            style={{ resize: 'vertical' }}
                        />
                        <div>
                            <button className="btn btn-secondary" onClick={testPlanner} disabled={isTesting || isSaving}>
                                {isTesting ? <Loader2 size={18} className="animate-spin" /> : <Search size={18} />}
                                Test
                            </button>
                        </div>
                    </div>

                    {testResult && (
                        <div style={{
                            display: 'grid',
                            gap: '0.75rem',
                            borderTop: '1px solid var(--border)',
                            paddingTop: '1rem',
                        }}>
                            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
                                <span className="badge">{testResult.queryClass}</span>
                                <span className="badge">{testResult.activated ? 'Activated' : 'Inactive'}</span>
                            </div>
                            <div style={{ color: 'var(--text-secondary)' }}>
                                Slots: {testResult.slotsTriggered.length > 0
                                    ? testResult.slotsTriggered.map((slot) => SLOT_LABELS[slot] || slot).join(', ')
                                    : 'none'}
                            </div>
                            {Object.entries(testResult.generatedQueries).length > 0 && (
                                <div style={{ display: 'grid', gap: '0.75rem' }}>
                                    {Object.entries(testResult.generatedQueries).map(([slot, queries]) => (
                                        <div key={slot} style={{ display: 'grid', gap: '0.35rem' }}>
                                            <strong>{SLOT_LABELS[slot] || slot}</strong>
                                            <ul style={{ margin: 0, paddingLeft: '1.25rem', color: 'var(--text-secondary)' }}>
                                                {queries.map((generatedQuery) => (
                                                    <li key={generatedQuery}>{generatedQuery}</li>
                                                ))}
                                            </ul>
                                        </div>
                                    ))}
                                </div>
                            )}
                            {testResult.notes.length > 0 && (
                                <div style={{ color: 'var(--text-muted)' }}>
                                    {testResult.notes.join(' ')}
                                </div>
                            )}
                        </div>
                    )}
                </section>
            </div>
        </motion.div>
    );
}
