import { useState, useEffect, useRef } from 'react';
import { motion } from 'framer-motion';
import {
    Activity,
    Terminal,
    RefreshCcw,
    CheckCircle2,
    AlertCircle,
    Cpu,
    Database as MemoryIcon,
    Box
} from 'lucide-react';
import { systemApi, type SystemCapabilitiesData, type SystemContainer, type SystemContainerStats } from '../api/client';
import { buildUnavailableCapabilities, isOpsMonitoringUnavailableError } from './systemMonitorUtils';

type ComposeProfile = 'default' | 'keycloak' | 'videochat';

interface ComposeComponent {
    name: string;
    service: string;
    profile: ComposeProfile;
}

interface MonitorContainer extends SystemContainer {
    service: string;
    profile: ComposeProfile;
    expected: boolean;
}

const COMPOSE_COMPONENTS: ComposeComponent[] = [
    { name: 'postgres', service: 'postgres', profile: 'default' },
    { name: 'qdrant', service: 'qdrant', profile: 'default' },
    { name: 'neo4j', service: 'neo4j', profile: 'default' },
    { name: 'llama-tender', service: 'llama-tender', profile: 'default' },
    { name: 'gpt4free', service: 'gpt4free', profile: 'default' },
    { name: 'redis', service: 'redis', profile: 'default' },
    { name: 'redis-insight', service: 'redis-insight', profile: 'default' },
    { name: 'celery-worker', service: 'celery-worker', profile: 'default' },
    { name: 'celery-beat', service: 'celery-beat', profile: 'default' },
    { name: 'mailpit', service: 'mailpit', profile: 'default' },
    { name: 'ops-agent', service: 'ops-agent', profile: 'default' },
    { name: 'backend', service: 'backend', profile: 'default' },
    { name: 'onlyoffice', service: 'onlyoffice', profile: 'default' },
    { name: 'kpi-reason-engine', service: 'kpi-reason-engine', profile: 'default' },
    { name: 'frontend', service: 'frontend', profile: 'default' },
    { name: 'mock-external-llm', service: 'mock-external-llm', profile: 'default' },
    { name: 'gateway', service: 'gateway', profile: 'default' },
    { name: 'anonymizer', service: 'anonymizer', profile: 'default' },
    { name: 'kc-postgres', service: 'kc-postgres', profile: 'keycloak' },
    { name: 'keycloak', service: 'keycloak', profile: 'keycloak' },
    { name: 'keycloak-bootstrap', service: 'keycloak-bootstrap', profile: 'keycloak' },
    { name: 'mm-postgres', service: 'mm-postgres', profile: 'videochat' },
    { name: 'mm-plugin-oidc', service: 'mm-plugin-oidc', profile: 'videochat' },
    { name: 'mattermost', service: 'mattermost', profile: 'videochat' },
    { name: 'mattermost-bootstrap', service: 'mattermost-bootstrap', profile: 'videochat' },
    { name: 'jitsi-prosody', service: 'jitsi-prosody', profile: 'videochat' },
    { name: 'jitsi-jicofo', service: 'jitsi-jicofo', profile: 'videochat' },
    { name: 'jitsi-jvb', service: 'jitsi-jvb', profile: 'videochat' },
    { name: 'jitsi-web', service: 'jitsi-web', profile: 'videochat' },
    { name: 'vosk', service: 'vosk', profile: 'videochat' },
    { name: 'jitsi-jigasi', service: 'jitsi-jigasi', profile: 'videochat' },
    { name: 'transcript-forwarder', service: 'transcript-forwarder', profile: 'videochat' },
];

function mergeComposeContainers(liveContainers: SystemContainer[]): MonitorContainer[] {
    const liveByName = new Map(liveContainers.map((container) => [container.name, container]));
    const merged: MonitorContainer[] = [];

    for (const component of COMPOSE_COMPONENTS) {
        const live = liveByName.get(component.name);
        if (live) {
            merged.push({
                ...live,
                service: component.service,
                profile: component.profile,
                expected: true,
            });
        } else {
            merged.push({
                id: `expected-${component.name}`,
                name: component.name,
                status: 'not_detected',
                health: 'unknown',
                service: component.service,
                profile: component.profile,
                expected: true,
            });
        }
    }

    return merged;
}

export default function SystemMonitor() {
    const [containers, setContainers] = useState<MonitorContainer[]>([]);
    const [liveContainerByName, setLiveContainerByName] = useState<Record<string, SystemContainer>>({});
    const [selectedContainer, setSelectedContainer] = useState<string | null>(null);
    const [logs, setLogs] = useState<string>('');
    const [stats, setStats] = useState<Record<string, SystemContainerStats>>({});
    const [capabilities, setCapabilities] = useState<SystemCapabilitiesData | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [isRefreshing, setIsRefreshing] = useState(false);
    const [monitorError, setMonitorError] = useState<string | null>(null);
    const refreshInFlightRef = useRef(false);

    const degradeMonitor = (reason: string) => {
        setCapabilities((current) => buildUnavailableCapabilities(current, reason));
        setContainers([]);
        setSelectedContainer(null);
        setLogs('');
        setStats({});
        setMonitorError(reason);
    };

    const handleMonitoringFailure = (error: unknown, fallbackMessage: string): boolean => {
        const message = error instanceof Error ? error.message : fallbackMessage;
        if (isOpsMonitoringUnavailableError(error)) {
            degradeMonitor(message);
            return true;
        }

        setMonitorError(message);
        return false;
    };

    useEffect(() => {
        let cancelled = false;

        const initialize = async () => {
            setIsLoading(true);
            try {
                const caps = await systemApi.getCapabilities();
                if (cancelled) return;
                setCapabilities(caps);
                if (!caps.ops_monitoring.available) {
                    setMonitorError(caps.ops_monitoring.reason || 'Docker monitoring is disabled in this environment.');
                    return;
                }
                await fetchData();
            } catch (e) {
                if (!cancelled) {
                    setMonitorError(e instanceof Error ? e.message : 'Unable to load system capabilities.');
                }
            } finally {
                if (!cancelled) {
                    setIsLoading(false);
                }
            }
        };

        void initialize();
        return () => {
            cancelled = true;
        };
    }, []);

    useEffect(() => {
        if (!capabilities?.ops_monitoring.available) {
            return;
        }

        const interval = window.setInterval(() => {
            void fetchStats();
        }, 5000);

        return () => window.clearInterval(interval);
    }, [capabilities?.ops_monitoring.available]);

    const fetchStatsForContainers = async (items: SystemContainer[]) => {
        const nextStats: Record<string, SystemContainerStats> = {};
        for (const container of items) {
            if (container.status !== 'running') {
                continue;
            }
            try {
                nextStats[container.name] = await systemApi.getStats(container.name);
            } catch (error) {
                if (handleMonitoringFailure(error, 'Unable to refresh container stats.')) {
                    return false;
                }
            }
        }
        setStats(nextStats);
        return true;
    };

    const fetchData = async () => {
        if (refreshInFlightRef.current) {
            return;
        }

        refreshInFlightRef.current = true;
        try {
            const data = await systemApi.getContainers();
            setLiveContainerByName(Object.fromEntries(data.map((container) => [container.name, container])));
            const merged = mergeComposeContainers(data);
            setContainers(merged);
            setMonitorError(null);
            if (merged.length > 0 && !selectedContainer) {
                const preferred = merged.find((container) => container.status === 'running') ?? merged[0];
                setSelectedContainer(preferred.name);
            }
            await fetchStatsForContainers(data);
        } catch (e) {
            handleMonitoringFailure(e, 'Failed to fetch containers.');
        } finally {
            refreshInFlightRef.current = false;
        }
    };

    const fetchStats = async () => {
        if (!capabilities?.ops_monitoring.available) {
            return;
        }

        if (refreshInFlightRef.current) {
            return;
        }

        refreshInFlightRef.current = true;
        setIsRefreshing(true);
        try {
            const data = await systemApi.getContainers();
            setLiveContainerByName(Object.fromEntries(data.map((container) => [container.name, container])));
            setContainers(mergeComposeContainers(data));
            setMonitorError(null);
            await fetchStatsForContainers(data);
        } catch (e) {
            handleMonitoringFailure(e, 'Failed to refresh stats.');
        } finally {
            refreshInFlightRef.current = false;
            setIsRefreshing(false);
        }
    };

    useEffect(() => {
        if (!selectedContainer || !capabilities?.ops_monitoring.available) {
            return;
        }

        if (liveContainerByName[selectedContainer]) {
            void fetchLogs(selectedContainer);
            return;
        }

        setLogs("Container non rilevato dall'ops-agent: log live non disponibili.");
    }, [selectedContainer, capabilities?.ops_monitoring.available, liveContainerByName]);

    const fetchLogs = async (name: string) => {
        try {
            const { logs } = await systemApi.getLogs(name, 100);
            setLogs(logs);
        } catch (e) {
            if (handleMonitoringFailure(e, 'Logs non disponibili in questo ambiente.')) {
                return;
            }
            setLogs('Logs non disponibili in questo ambiente.');
        }
    };

    if (isLoading) {
        return <div className="loading-spinner"><div className="spinner" /></div>;
    }

    return (
        <div className="animate-in">
            <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                    <h1 className="page-title">
                        <Activity size={28} color="#60a5fa" style={{ verticalAlign: 'middle', marginRight: 8 }} />
                        System Monitor
                    </h1>
                    <p className="page-subtitle">Real-time monitoring of Docker infrastructure</p>
                </div>
                <button
                    className={`btn btn-secondary btn-sm ${isRefreshing ? 'animate-pulse' : ''}`}
                    onClick={fetchStats}
                    disabled={!capabilities?.ops_monitoring.available}
                >
                    <RefreshCcw size={14} /> Refresh
                </button>
            </div>

            {monitorError && (
                <div
                    className="card"
                    style={{
                        marginBottom: '1.5rem',
                        background: 'rgba(245, 158, 11, 0.08)',
                        border: '1px solid rgba(245, 158, 11, 0.35)',
                        color: '#d97706',
                    }}
                >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                        <AlertCircle size={16} />
                        <span style={{ fontSize: '0.9rem' }}>{monitorError}</span>
                    </div>
                </div>
            )}

            {!capabilities?.ops_monitoring.available && (
                <div className="card" style={{ padding: '1.25rem' }}>
                    <p style={{ margin: 0, color: 'var(--text-muted)' }}>
                        Il monitoraggio container è disabilitato o non disponibile in questo ambiente. Il backend resta operativo,
                        ma le metriche live Docker passano solo tramite l&apos;ops-agent privilegiato.
                    </p>
                </div>
            )}

            {capabilities?.ops_monitoring.available && (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '1rem', marginBottom: '2rem' }}>
                {containers.map(container => (
                    <motion.div
                        key={container.id}
                        className={`card ${selectedContainer === container.name ? 'active' : ''}`}
                        onClick={() => setSelectedContainer(container.name)}
                        style={{
                            cursor: 'pointer',
                            borderColor: selectedContainer === container.name ? 'var(--accent-blue)' : 'var(--border-color)',
                            backgroundColor: selectedContainer === container.name ? 'color-mix(in srgb, var(--accent-blue) 5%, transparent)' : 'var(--bg-secondary)'
                        }}
                        initial={{ opacity: 0, scale: 0.95 }}
                        animate={{ opacity: 1, scale: 1 }}
                    >
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1rem' }}>
                            <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
                                <Box size={20} color="var(--accent-blue)" />
                                <div>
                                    <h3 style={{ margin: 0, fontSize: '0.95rem' }}>{`tw-${container.name}`}</h3>
                                    <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                                        service: {container.service}
                                    </div>
                                </div>
                            </div>
                            <span style={{
                                display: 'flex',
                                alignItems: 'center',
                                gap: '0.25rem',
                                fontSize: '0.7rem',
                                color: container.status === 'running' ? 'var(--accent-green)' : 'var(--text-muted)'
                            }}>
                                {container.status === 'running' ? <CheckCircle2 size={12} /> : <AlertCircle size={12} />}
                                {container.status === 'not_detected' ? 'NOT DETECTED' : container.status.toUpperCase()}
                            </span>
                        </div>

                        <div style={{ display: 'flex', gap: '0.4rem', marginBottom: '0.6rem' }}>
                            <span className="badge badge-draft" style={{ fontSize: '0.65rem' }}>
                                {container.profile}
                            </span>
                            {!container.expected && (
                                <span className="badge badge-failed" style={{ fontSize: '0.65rem' }}>
                                    extra
                                </span>
                            )}
                        </div>

                        {container.status !== 'running' ? (
                            <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', margin: 0 }}>
                                {container.status === 'not_detected'
                                    ? 'Componente definito in docker-compose ma non rilevato/avviato.'
                                    : 'Container non in esecuzione.'}
                            </p>
                        ) : stats[container.name] ? (
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem' }}>
                                    <span style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}><Cpu size={12} /> CPU</span>
                                    <span>{stats[container.name].cpu_percent}%</span>
                                </div>
                                <div className="progress-bar-bg" style={{ height: 4, background: 'var(--border-color)', borderRadius: 2 }}>
                                    <div style={{ width: `${stats[container.name].cpu_percent}%`, height: '100%', background: 'var(--accent-blue)', borderRadius: 2 }} />
                                </div>

                                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', marginTop: '0.25rem' }}>
                                    <span style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}><MemoryIcon size={12} /> RAM</span>
                                    <span>{stats[container.name].memory_usage_mb}MB / {stats[container.name].memory_limit_mb}MB</span>
                                </div>
                                <div className="progress-bar-bg" style={{ height: 4, background: 'var(--border-color)', borderRadius: 2 }}>
                                    <div style={{ width: `${stats[container.name].memory_percent}%`, height: '100%', background: 'var(--accent-purple)', borderRadius: 2 }} />
                                </div>
                            </div>
                        ) : (
                            <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', margin: 0 }}>Stats not available</p>
                        )}
                    </motion.div>
                ))}
                {containers.length === 0 && (
                    <div className="card">
                        <p style={{ margin: 0, color: 'var(--text-muted)' }}>Nessun container allowlistato disponibile.</p>
                    </div>
                )}
                </div>
            )}

            {capabilities?.ops_monitoring.available && (
                <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr)', gap: '1.5rem' }}>
                <div className="card" style={{ padding: 0, overflow: 'hidden', background: '#0f172a', border: '1px solid #1e293b' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.75rem 1rem', background: '#1e293b', borderBottom: '1px solid #334155' }}>
                        <Terminal size={14} color="#60a5fa" />
                        <span style={{ fontSize: '0.85rem', fontWeight: 600, color: '#e2e8f0' }}>
                            Logs: {selectedContainer ? `tw-${selectedContainer}` : '—'}
                        </span>
                    </div>
                    <pre style={{
                        margin: 0,
                        padding: '1rem',
                        fontSize: '0.8rem',
                        color: '#94a3b8',
                        fontFamily: 'monospace',
                        maxHeight: '400px',
                        overflowY: 'auto',
                        whiteSpace: 'pre-wrap',
                        background: '#0f172a'
                    }}>
                        {logs || 'No logs available.'}
                    </pre>
                </div>
                </div>
            )}
        </div>
    );
}
