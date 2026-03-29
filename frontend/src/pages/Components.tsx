import { motion } from 'framer-motion';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
    Activity,
    AlertCircle,
    Box,
    CheckCircle2,
    Cpu,
    Database,
    ExternalLink,
    Globe,
    HardDrive,
    Key,
    Layers,
    Mail,
    RefreshCcw,
    Server,
    ShieldCheck,
} from 'lucide-react';

import {
    anonymizerApi,
    gatewayApi,
    ragApi,
    systemApi,
    type AnonymizerConfigData,
    type AnonymizerStatsData,
    type EffectiveAnonymizerPolicyData,
    type GatewayTarget,
    type SystemCapabilitiesData,
    type SystemContainer,
} from '../api/client';
import { buildLocalServiceUrl, getAuthRuntimeConfig, type AuthRuntimeConfig } from '../config/runtime';
import { useAuth } from '../contexts/AuthContext';

function FileText(props: any) {
    return (
        <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}>
            <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z" />
            <polyline points="14 2 14 8 20 8" />
            <line x1="16" x2="8" y1="13" y2="13" />
            <line x1="16" x2="8" y1="17" y2="17" />
            <line x1="10" x2="8" y1="9" y2="9" />
        </svg>
    );
}

type Tone = 'healthy' | 'degraded' | 'inactive' | 'unknown';
type IconType = typeof Globe;

interface RagHealthData {
    engine_initialized?: boolean;
    dense_retriever?: boolean;
    sparse_retriever?: boolean;
    sparse_corpus_size?: number;
    graph_retriever?: boolean;
    generator?: boolean;
    ollama_available?: boolean;
}

interface ServiceDef {
    key: string;
    name: string;
    description: string;
    endpoint: string;
    url?: string;
    icon: IconType | typeof FileText;
    color: string;
    containerName?: string;
}

const cardStyle = {
    background: 'rgba(15, 23, 42, 0.78)',
    border: '1px solid rgba(148, 163, 184, 0.16)',
    borderRadius: '1rem',
    backdropFilter: 'blur(24px)',
};

function toneStyles(tone: Tone) {
    if (tone === 'healthy') return { bg: 'rgba(16,185,129,.14)', color: '#34d399', border: 'rgba(16,185,129,.28)', label: 'Operativo' };
    if (tone === 'degraded') return { bg: 'rgba(245,158,11,.14)', color: '#fbbf24', border: 'rgba(245,158,11,.28)', label: 'Da verificare' };
    if (tone === 'inactive') return { bg: 'rgba(71,85,105,.16)', color: '#cbd5e1', border: 'rgba(100,116,139,.22)', label: 'Non attivo' };
    return { bg: 'rgba(59,130,246,.12)', color: '#93c5fd', border: 'rgba(59,130,246,.22)', label: 'Non rilevato' };
}

function browserUrl(url?: string) {
    return Boolean(url && /^https?:\/\//i.test(url));
}

function containerTone(container?: SystemContainer | null): Tone {
    if (!container) return 'unknown';
    if (container.status === 'running') return !container.health || container.health === 'healthy' ? 'healthy' : 'degraded';
    if (container.status === 'created' || container.status === 'restarting') return 'degraded';
    return 'inactive';
}

function containerLabel(container?: SystemContainer | null) {
    if (!container) return 'Monitoraggio container non disponibile';
    return [container.status, container.health].filter(Boolean).join(' / ');
}

function targetMethod(target: GatewayTarget) {
    return target.connection_method === 'openrouter' || target.provider === 'openrouter' ? 'OpenRouter' : 'Metodo attuale';
}

export default function ComponentsPage() {
    const { user } = useAuth();
    const navigate = useNavigate();

    const [isLoading, setIsLoading] = useState(true);
    const [isRefreshing, setIsRefreshing] = useState(false);
    const [updatedAt, setUpdatedAt] = useState<string | null>(null);
    const [warnings, setWarnings] = useState<string[]>([]);
    const [authConfig, setAuthConfig] = useState<AuthRuntimeConfig | null>(null);
    const [capabilities, setCapabilities] = useState<SystemCapabilitiesData | null>(null);
    const [containers, setContainers] = useState<SystemContainer[]>([]);
    const [ragHealth, setRagHealth] = useState<RagHealthData | null>(null);
    const [targets, setTargets] = useState<GatewayTarget[]>([]);
    const [anonymizerConfig, setAnonymizerConfig] = useState<AnonymizerConfigData | null>(null);
    const [anonymizerStats, setAnonymizerStats] = useState<AnonymizerStatsData | null>(null);
    const [effectivePolicy, setEffectivePolicy] = useState<EffectiveAnonymizerPolicyData | null>(null);

    useEffect(() => {
        if (user && user.role !== 'admin') navigate('/');
    }, [navigate, user]);

    const loadRuntime = async (refresh = false) => {
        if (user?.role !== 'admin') return;
        refresh ? setIsRefreshing(true) : setIsLoading(true);
        const notes: string[] = [];

        const results = await Promise.allSettled([
            getAuthRuntimeConfig(),
            systemApi.getCapabilities(),
            systemApi.getContainers(),
            ragApi.health(),
            gatewayApi.listTargets(),
            anonymizerApi.getConfig(),
            anonymizerApi.getStats(),
            anonymizerApi.getEffectivePolicy({ route_key: 'tender' }),
        ]);

        const [auth, caps, conts, rag, gtw, anonCfg, anonStats, policy] = results;

        if (auth.status === 'fulfilled') setAuthConfig(auth.value); else notes.push('Config auth runtime non disponibile.');
        if (caps.status === 'fulfilled') setCapabilities(caps.value); else notes.push('Capabilities ops non disponibili.');
        if (conts.status === 'fulfilled') setContainers(conts.value); else { setContainers([]); notes.push(`Container runtime: ${conts.reason instanceof Error ? conts.reason.message : 'non disponibile'}`); }
        if (rag.status === 'fulfilled') setRagHealth(rag.value as RagHealthData); else { setRagHealth(null); notes.push(`RAG health: ${rag.reason instanceof Error ? rag.reason.message : 'non disponibile'}`); }
        if (gtw.status === 'fulfilled') setTargets(gtw.value); else { setTargets([]); notes.push(`Gateway targets: ${gtw.reason instanceof Error ? gtw.reason.message : 'non disponibili'}`); }
        if (anonCfg.status === 'fulfilled') setAnonymizerConfig(anonCfg.value); else setAnonymizerConfig(null);
        if (anonStats.status === 'fulfilled') setAnonymizerStats(anonStats.value); else setAnonymizerStats(null);
        if (anonCfg.status === 'rejected' || anonStats.status === 'rejected') notes.push('Stato anonymizer non completamente disponibile.');
        if (policy.status === 'fulfilled') setEffectivePolicy(policy.value); else setEffectivePolicy(null);

        setWarnings(notes);
        setUpdatedAt(new Date().toISOString());
        setIsLoading(false);
        setIsRefreshing(false);
    };

    useEffect(() => {
        if (user?.role === 'admin') void loadRuntime(false);
    }, [user?.role]);

    const containerMap = useMemo(() => new Map(containers.map((item) => [item.name, item])), [containers]);
    const enabledTargets = useMemo(() => targets.filter((item) => item.enabled), [targets]);

    const ragTone: Tone = !ragHealth ? 'unknown' : ragHealth.engine_initialized && ragHealth.generator && ragHealth.ollama_available ? 'healthy' : 'degraded';
    const anonymizerTone: Tone = !anonymizerConfig && !anonymizerStats ? 'unknown' : anonymizerStats?.circuit_open || (anonymizerStats?.runtime_failure_count || 0) > 0 ? 'degraded' : 'healthy';
    const opsTone: Tone = !capabilities ? 'unknown' : capabilities.ops_agent.available && capabilities.ops_monitoring.available ? 'healthy' : capabilities.ops_agent.available ? 'degraded' : 'inactive';
    const targetsTone: Tone = !targets.length ? 'unknown' : enabledTargets.length > 0 ? 'healthy' : 'inactive';

    const services: ServiceDef[] = useMemo(() => [
        { key: 'frontend', name: 'Frontend', description: 'React + Vite', endpoint: buildLocalServiceUrl(3000), url: buildLocalServiceUrl(3000), icon: Globe, color: '#3b82f6', containerName: 'tw-frontend' },
        { key: 'backend', name: 'Backend API', description: 'FastAPI e orchestrazione RAG', endpoint: buildLocalServiceUrl(8000, '/docs'), url: buildLocalServiceUrl(8000, '/docs'), icon: Server, color: '#10b981', containerName: 'tw-backend' },
        { key: 'gateway', name: 'AI Gateway', description: 'Router AI per llama.cpp / LM Studio / OpenRouter', endpoint: buildLocalServiceUrl(8085, '/health'), url: buildLocalServiceUrl(8085, '/health'), icon: Layers, color: '#8b5cf6', containerName: 'tw-gateway' },
        { key: 'anonymizer', name: 'Anonymizer', description: 'Relay e anonimizzazione provider esterni', endpoint: buildLocalServiceUrl(8090, '/health'), url: buildLocalServiceUrl(8090, '/health'), icon: ShieldCheck, color: '#f59e0b', containerName: 'tw-anonymizer' },
        { key: 'ops', name: 'Ops Agent', description: 'Monitoraggio privilegiato e hot reload', endpoint: buildLocalServiceUrl(8070, '/health'), url: buildLocalServiceUrl(8070, '/health'), icon: Activity, color: '#60a5fa', containerName: 'tw-ops-agent' },
        { key: 'llama', name: 'llama.cpp Tender', description: 'Server locale legacy tender', endpoint: buildLocalServiceUrl(8080), url: buildLocalServiceUrl(8080), icon: Cpu, color: '#84cc16', containerName: 'tw-llama-tender' },
        { key: 'kpi', name: 'KPI Reason Engine', description: 'Motore analitico KPI', endpoint: buildLocalServiceUrl(8010, '/health'), url: buildLocalServiceUrl(8010, '/health'), icon: Activity, color: '#14b8a6', containerName: 'tw-kpi-reason-engine' },
        { key: 'postgres', name: 'PostgreSQL', description: 'Database relazionale', endpoint: `${window.location.hostname}:5432`, icon: Database, color: '#6366f1', containerName: 'tw-postgres' },
        { key: 'qdrant', name: 'Qdrant', description: 'Vector database', endpoint: buildLocalServiceUrl(6333), url: buildLocalServiceUrl(6333), icon: Database, color: '#a855f7', containerName: 'tw-qdrant' },
        { key: 'neo4j', name: 'Neo4j', description: 'Knowledge graph', endpoint: buildLocalServiceUrl(7474), url: buildLocalServiceUrl(7474), icon: Layers, color: '#ec4899', containerName: 'tw-neo4j' },
        { key: 'redis', name: 'Redis', description: 'Queue backend e cache', endpoint: `${window.location.hostname}:6379`, icon: HardDrive, color: '#ef4444', containerName: 'tw-redis' },
        { key: 'redis-ui', name: 'Redis Insight', description: 'Interfaccia Redis', endpoint: buildLocalServiceUrl(8001), url: buildLocalServiceUrl(8001), icon: Box, color: '#f97316', containerName: 'tw-redis-insight' },
        { key: 'minio', name: 'MinIO API', description: 'Object storage', endpoint: buildLocalServiceUrl(9000), url: buildLocalServiceUrl(9000), icon: HardDrive, color: '#14b8a6', containerName: 'minio' },
        { key: 'minio-console', name: 'MinIO Console', description: 'Console amministrativa', endpoint: buildLocalServiceUrl(9001), url: buildLocalServiceUrl(9001), icon: Box, color: '#0ea5e9', containerName: 'minio' },
        { key: 'onlyoffice', name: 'OnlyOffice', description: 'Document server', endpoint: buildLocalServiceUrl(8443), url: buildLocalServiceUrl(8443), icon: FileText, color: '#f43f5e', containerName: 'tw-onlyoffice' },
        { key: 'mailpit', name: 'Mailpit', description: 'SMTP test UI', endpoint: buildLocalServiceUrl(8025), url: buildLocalServiceUrl(8025), icon: Mail, color: '#c084fc', containerName: 'tw-mailpit' },
        { key: 'celery-worker', name: 'Celery Worker', description: 'Job runner backend', endpoint: 'tw-celery-worker', icon: Box, color: '#22c55e', containerName: 'tw-celery-worker' },
        { key: 'celery-beat', name: 'Celery Beat', description: 'Scheduler backend', endpoint: 'tw-celery-beat', icon: Box, color: '#38bdf8', containerName: 'tw-celery-beat' },
        { key: 'keycloak', name: 'Keycloak', description: 'Identity provider opzionale', endpoint: authConfig?.keycloak_url || buildLocalServiceUrl(8180), url: authConfig?.auth_mode === 'legacy' ? undefined : authConfig?.keycloak_url || buildLocalServiceUrl(8180), icon: Key, color: '#facc15', containerName: 'tw-keycloak' },
    ], [authConfig]);

    if (user?.role !== 'admin') return null;
    if (isLoading) return <div className="loading-spinner"><div className="spinner" /></div>;

    return (
        <div style={{ minHeight: '100vh', padding: '2rem', background: 'radial-gradient(circle at 10% 10%, rgba(59,130,246,.12) 0%, transparent 35%), radial-gradient(circle at 90% 90%, rgba(168,85,247,.12) 0%, transparent 40%), linear-gradient(180deg, rgba(15,23,42,.98) 0%, rgba(2,6,23,1) 100%)' }}>
            <motion.div initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} style={{ maxWidth: '1280px', margin: '0 auto', display: 'grid', gap: '1.5rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '1rem', flexWrap: 'wrap' }}>
                    <div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.75rem' }}>
                            <Server size={38} color="#60a5fa" />
                            <div>
                                <h1 style={{ margin: 0, fontSize: '1.9rem', color: 'white' }}>Componenti</h1>
                                <p style={{ margin: '0.25rem 0 0', color: '#94a3b8' }}>Snapshot live dei servizi, della catena AI e dei target configurati.</p>
                            </div>
                        </div>
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
                            {authConfig && <span style={{ padding: '0.35rem 0.65rem', borderRadius: '999px', border: '1px solid rgba(148,163,184,.18)', background: 'rgba(30,41,59,.55)', color: '#cbd5e1', fontSize: '0.8rem' }}>Auth mode: {authConfig.auth_mode}</span>}
                            {updatedAt && <span style={{ padding: '0.35rem 0.65rem', borderRadius: '999px', border: '1px solid rgba(148,163,184,.18)', background: 'rgba(30,41,59,.55)', color: '#cbd5e1', fontSize: '0.8rem' }}>Aggiornato alle {new Date(updatedAt).toLocaleTimeString('it-IT')}</span>}
                        </div>
                    </div>
                    <button className={`btn btn-secondary ${isRefreshing ? 'animate-pulse' : ''}`} onClick={() => void loadRuntime(true)} disabled={isRefreshing}>
                        <RefreshCcw size={16} />
                        {isRefreshing ? 'Aggiornamento...' : 'Aggiorna stato'}
                    </button>
                </div>

                {warnings.length > 0 && (
                    <div style={{ ...cardStyle, padding: '1rem 1.1rem', borderColor: 'rgba(245,158,11,.3)', background: 'rgba(120,53,15,.14)' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.55rem', marginBottom: '0.6rem', color: '#fbbf24' }}>
                            <AlertCircle size={18} />
                            <strong>Alcuni segnali runtime sono degradati</strong>
                        </div>
                        {warnings.map((warning) => <div key={warning} style={{ color: '#fde68a', fontSize: '0.88rem', marginTop: '0.2rem' }}>{warning}</div>)}
                    </div>
                )}

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1rem' }}>
                    {[
                        { label: 'Ops Agent', value: capabilities?.ops_agent.available ? 'Attivo' : 'Non disponibile', note: capabilities?.ops_monitoring.available ? 'Docker monitoring disponibile' : capabilities?.ops_monitoring.reason || 'Docker monitoring non disponibile', tone: opsTone, icon: Activity, color: '#60a5fa' },
                        { label: 'RAG Engine', value: ragHealth?.engine_initialized ? 'Inizializzato' : 'Non inizializzato', note: ragHealth ? `LLM endpoint ${ragHealth.ollama_available ? 'raggiungibile' : 'non raggiungibile'}` : 'Health non disponibile', tone: ragTone, icon: Cpu, color: '#22c55e' },
                        { label: 'Anonymizer', value: anonymizerConfig?.strategy || 'n/d', note: anonymizerStats ? `fallback ${anonymizerStats.fallback_events ?? 0} · circuit ${anonymizerStats.circuit_open ? 'open' : 'closed'}` : 'Stats non disponibili', tone: anonymizerTone, icon: ShieldCheck, color: '#f59e0b' },
                        { label: 'Gateway Targets', value: `${enabledTargets.length}/${targets.length}`, note: targets.length ? `${targets.filter((x) => x.connection_method === 'openrouter').length} OpenRouter · ${targets.filter((x) => x.connection_method !== 'openrouter').length} metodo attuale` : 'Nessun target configurato', tone: targetsTone, icon: Layers, color: '#a78bfa' },
                    ].map((item) => {
                        const tone = toneStyles(item.tone);
                        return (
                            <div key={item.label} style={{ ...cardStyle, padding: '1rem 1.1rem' }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '0.75rem' }}>
                                    <div style={{ width: 42, height: 42, borderRadius: '0.8rem', background: `${item.color}18`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                                        <item.icon size={19} color={item.color} />
                                    </div>
                                    <span style={{ padding: '0.28rem 0.55rem', borderRadius: '999px', background: tone.bg, color: tone.color, border: `1px solid ${tone.border}`, fontSize: '0.73rem', fontWeight: 600 }}>{tone.label}</span>
                                </div>
                                <div style={{ marginTop: '1rem' }}>
                                    <div style={{ color: '#94a3b8', fontSize: '0.82rem' }}>{item.label}</div>
                                    <div style={{ color: 'white', fontSize: '1.1rem', fontWeight: 700, margin: '0.3rem 0' }}>{item.value}</div>
                                    <div style={{ color: '#cbd5e1', fontSize: '0.84rem', lineHeight: 1.45 }}>{item.note}</div>
                                </div>
                            </div>
                        );
                    })}
                </div>

                <div style={{ ...cardStyle, padding: '1.15rem' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: '1rem', alignItems: 'center', flexWrap: 'wrap', marginBottom: '1rem' }}>
                        <div>
                            <h2 style={{ margin: 0, color: 'white', fontSize: '1.1rem' }}>Routing AI attuale</h2>
                            <p style={{ margin: '0.3rem 0 0', color: '#94a3b8', fontSize: '0.88rem' }}>Policy route `tender`, target configurati e stato provider.</p>
                        </div>
                        {effectivePolicy && <div style={{ padding: '0.55rem 0.8rem', borderRadius: '0.85rem', background: 'rgba(30,41,59,.65)', border: '1px solid rgba(148,163,184,.14)', color: '#e2e8f0', fontSize: '0.83rem' }}>mode: <strong>{effectivePolicy.mode}</strong>{' · '}anonymizer: <strong>{effectivePolicy.anonymizer_enabled ? 'on' : 'off'}</strong></div>}
                    </div>

                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '1rem' }}>
                        {targets.map((target) => {
                            const tone = toneStyles(target.enabled ? 'healthy' : 'inactive');
                            return (
                                <div key={target.id} style={{ borderRadius: '0.95rem', border: '1px solid rgba(148,163,184,.14)', background: 'rgba(15,23,42,.58)', padding: '1rem' }}>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.75rem', alignItems: 'flex-start' }}>
                                        <div>
                                            <div style={{ color: 'white', fontWeight: 600 }}>{target.route_key} · {targetMethod(target)}</div>
                                            <div style={{ color: '#94a3b8', fontSize: '0.82rem', marginTop: '0.2rem' }}>{target.model_name || 'model non definito'}</div>
                                        </div>
                                        <span style={{ padding: '0.28rem 0.55rem', borderRadius: '999px', background: tone.bg, color: tone.color, border: `1px solid ${tone.border}`, fontSize: '0.73rem', fontWeight: 600 }}>{target.enabled ? 'Abilitato' : 'Disabilitato'}</span>
                                    </div>
                                    <div style={{ marginTop: '0.85rem', display: 'grid', gap: '0.45rem', color: '#cbd5e1', fontSize: '0.84rem' }}>
                                        <div>Provider: <strong>{target.provider}</strong></div>
                                        <div>Timeout: <strong>{target.timeout_ms}ms</strong></div>
                                        <div>API key: <strong>{target.has_api_key ? 'configurata' : 'assente'}</strong></div>
                                        <div>Anonymizer: <strong>{target.use_anonymizer ? 'on' : 'off'}</strong></div>
                                        <div style={{ marginTop: '0.25rem', padding: '0.65rem', borderRadius: '0.75rem', background: 'rgba(30,41,59,.55)', fontFamily: 'monospace', fontSize: '0.74rem', color: '#93c5fd', wordBreak: 'break-all' }}>{target.base_url}</div>
                                    </div>
                                </div>
                            );
                        })}
                        {targets.length === 0 && <div style={{ borderRadius: '0.95rem', border: '1px dashed rgba(148,163,184,.2)', background: 'rgba(15,23,42,.4)', padding: '1rem', color: '#94a3b8', fontSize: '0.88rem' }}>Nessun target gateway configurato.</div>}
                    </div>
                </div>

                <div style={{ ...cardStyle, padding: '1.15rem' }}>
                    <div style={{ marginBottom: '1rem' }}>
                        <h2 style={{ margin: 0, color: 'white', fontSize: '1.1rem' }}>Servizi e componenti del sistema</h2>
                        <p style={{ margin: '0.3rem 0 0', color: '#94a3b8', fontSize: '0.88rem' }}>Inventario allineato al compose attuale, con badge runtime quando disponibili.</p>
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: '1rem' }}>
                        {services.map((service) => {
                            const container = service.containerName ? containerMap.get(service.containerName) : undefined;
                            let tone = containerTone(container);
                            let status = containerLabel(container);
                            const details: string[] = [];

                            if (service.key === 'frontend') {
                                tone = container ? containerTone(container) : 'healthy';
                                status = container ? containerLabel(container) : 'pagina attualmente raggiungibile';
                            }
                            if (service.key === 'backend' && ragHealth) {
                                tone = ragTone;
                                status = ragTone === 'healthy' ? 'RAG inizializzato e endpoint LLM raggiungibile' : 'RAG disponibile ma degradato';
                                details.push(`dense: ${ragHealth.dense_retriever ? 'ok' : 'no'}`);
                                details.push(`graph: ${ragHealth.graph_retriever ? 'ok' : 'no'}`);
                                details.push(`sparse corpus: ${ragHealth.sparse_corpus_size ?? 0}`);
                            }
                            if (service.key === 'gateway') {
                                tone = targetsTone;
                                status = targets.length ? `${enabledTargets.length}/${targets.length} target abilitati` : 'Nessun target configurato';
                            }
                            if (service.key === 'anonymizer') {
                                tone = anonymizerTone;
                                status = anonymizerConfig ? `strategia ${anonymizerConfig.strategy}` : 'Configurazione non disponibile';
                                if (anonymizerStats) details.push(`fallback: ${anonymizerStats.fallback_events ?? 0}`);
                            }
                            if (service.key === 'ops' && capabilities) {
                                tone = opsTone;
                                status = capabilities.ops_agent.available ? 'Ops agent disponibile' : capabilities.ops_agent.reason || 'Ops agent non disponibile';
                                details.push(`docker monitoring: ${capabilities.ops_monitoring.available ? 'on' : 'off'}`);
                            }
                            if (service.key === 'keycloak') {
                                if (authConfig?.auth_mode === 'legacy') {
                                    tone = 'inactive';
                                    status = 'Auth mode legacy';
                                    details.push('Keycloak non richiesto nel runtime corrente.');
                                } else {
                                    status = `Auth mode ${authConfig?.auth_mode || 'hybrid'}`;
                                }
                            }
                            if (container && !['backend', 'gateway', 'anonymizer', 'ops', 'keycloak'].includes(service.key)) {
                                details.push(`container: ${container.name}`);
                                if (container.health) details.push(`health: ${container.health}`);
                            }

                            const cfg = toneStyles(tone);
                            const content = (
                                <div style={{ height: '100%', display: 'flex', flexDirection: 'column', gap: '0.9rem', padding: '1rem', borderRadius: '1rem', border: '1px solid rgba(148,163,184,.14)', background: 'rgba(15,23,42,.62)' }}>
                                    <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0.8rem' }}>
                                        <div style={{ width: 42, height: 42, borderRadius: '0.8rem', background: `${service.color}18`, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                                            <service.icon size={20} color={service.color} />
                                        </div>
                                        <div style={{ flex: 1 }}>
                                            <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.6rem', alignItems: 'flex-start' }}>
                                                <div>
                                                    <h3 style={{ margin: 0, color: 'white', fontSize: '1rem' }}>{service.name}</h3>
                                                    <p style={{ margin: '0.22rem 0 0', color: '#94a3b8', fontSize: '0.8rem', lineHeight: 1.45 }}>{service.description}</p>
                                                </div>
                                                <span style={{ padding: '0.25rem 0.5rem', borderRadius: '999px', background: cfg.bg, color: cfg.color, border: `1px solid ${cfg.border}`, fontSize: '0.72rem', fontWeight: 600 }}>{cfg.label}</span>
                                            </div>
                                        </div>
                                    </div>
                                    <div style={{ padding: '0.7rem', borderRadius: '0.75rem', background: 'rgba(30,41,59,.55)', fontFamily: 'monospace', color: '#93c5fd', fontSize: '0.76rem', wordBreak: 'break-all' }}>{service.endpoint}</div>
                                    <div style={{ color: '#e2e8f0', fontSize: '0.84rem', lineHeight: 1.45 }}>{status}</div>
                                    {details.length > 0 && <div style={{ display: 'grid', gap: '0.35rem' }}>{details.slice(0, 4).map((detail) => <div key={detail} style={{ display: 'flex', gap: '0.4rem', color: '#94a3b8', fontSize: '0.78rem' }}><CheckCircle2 size={13} color={cfg.color} style={{ marginTop: 1, flexShrink: 0 }} /><span>{detail}</span></div>)}</div>}
                                </div>
                            );

                            return browserUrl(service.url)
                                ? <a key={service.key} href={service.url} target="_blank" rel="noopener noreferrer" style={{ textDecoration: 'none', position: 'relative' }}>{content}<div style={{ position: 'absolute', right: 16, top: 16, pointerEvents: 'none' }}><ExternalLink size={14} color="#64748b" /></div></a>
                                : <div key={service.key}>{content}</div>;
                        })}
                    </div>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1.2fr) minmax(320px, .8fr)', gap: '1rem' }}>
                    <div style={{ ...cardStyle, padding: '1.15rem' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginBottom: '0.9rem' }}><ShieldCheck size={18} color="#fbbf24" /><h2 style={{ margin: 0, color: 'white', fontSize: '1.05rem' }}>Privacy e anonimizzazione</h2></div>
                        <div style={{ display: 'grid', gap: '0.65rem', color: '#cbd5e1', fontSize: '0.88rem' }}>
                            <div>Strategia: <strong>{anonymizerConfig?.strategy || 'n/d'}</strong></div>
                            <div>TTL sessione: <strong>{anonymizerConfig?.ttl_seconds || 0}s</strong></div>
                            <div>Entita: <strong>{anonymizerConfig?.entities.join(', ') || 'n/d'}</strong></div>
                            <div>Mask CIG: <strong>{anonymizerConfig?.mask_cig ? 'si' : 'no'}</strong></div>
                            <div>Requests: <strong>{anonymizerStats?.requests ?? 0}</strong></div>
                            <div>Sessions: <strong>{anonymizerStats?.sessions ?? 0}</strong></div>
                            <div>Runtime failure count: <strong>{anonymizerStats?.runtime_failure_count ?? 0}</strong></div>
                            <div>Last error: <strong>{anonymizerStats?.last_error_reason || 'nessuno'}</strong></div>
                        </div>
                    </div>

                    <div style={{ ...cardStyle, padding: '1.15rem' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginBottom: '0.9rem' }}><Key size={18} color="#f59e0b" /><h2 style={{ margin: 0, color: 'white', fontSize: '1.05rem' }}>Credenziali base</h2></div>
                        <div style={{ display: 'grid', gap: '0.75rem' }}>
                            {[
                                { service: 'Admin', user: 'admin@admin.com', pass: 'vN7pQ3wL9xR5tY2uA4bC6dE8fG1hJ0' },
                                { service: 'PostgreSQL', user: 'tenderwriter', pass: 'DefaultPg2024Pass' },
                                { service: 'Neo4j', user: 'neo4j', pass: 'DefaultNEO4J2024Pass' },
                                { service: 'MinIO', user: 'minioadmin', pass: 'DefaultMinIO2024Pass' },
                            ].map((cred) => (
                                <div key={cred.service} style={{ padding: '0.8rem', borderRadius: '0.85rem', background: 'rgba(30,41,59,.55)', border: '1px solid rgba(148,163,184,.12)' }}>
                                    <div style={{ color: '#94a3b8', fontSize: '0.75rem', marginBottom: '0.2rem' }}>{cred.service}</div>
                                    <div style={{ color: 'white', fontSize: '0.82rem', fontFamily: 'monospace' }}>{cred.user}</div>
                                    <div style={{ color: '#60a5fa', fontSize: '0.82rem', fontFamily: 'monospace' }}>{cred.pass}</div>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            </motion.div>
        </div>
    );
}
