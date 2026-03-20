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

export default function SystemMonitor() {
    const [containers, setContainers] = useState<SystemContainer[]>([]);
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
            setContainers(data);
            setMonitorError(null);
            if (data.length > 0 && !selectedContainer) {
                setSelectedContainer(data[0].name);
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
            setContainers(data);
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
        if (selectedContainer && capabilities?.ops_monitoring.available) {
            void fetchLogs(selectedContainer);
        }
    }, [selectedContainer, capabilities?.ops_monitoring.available]);

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
                                <h3 style={{ margin: 0, fontSize: '0.95rem' }}>{container.name}</h3>
                            </div>
                            <span style={{
                                display: 'flex',
                                alignItems: 'center',
                                gap: '0.25rem',
                                fontSize: '0.7rem',
                                color: container.status === 'running' ? 'var(--accent-green)' : 'var(--text-muted)'
                            }}>
                                {container.status === 'running' ? <CheckCircle2 size={12} /> : <AlertCircle size={12} />}
                                {container.status.toUpperCase()}
                            </span>
                        </div>

                        {stats[container.name] ? (
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
                        <span style={{ fontSize: '0.85rem', fontWeight: 600, color: '#e2e8f0' }}>Logs: {selectedContainer}</span>
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
