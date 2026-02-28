import { useState, useEffect } from 'react';
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
import { systemApi } from '../api/client';

interface Container {
    id: string;
    name: string;
    status: string;
    health: string;
}

interface Stats {
    cpu_percent: number;
    memory_usage_mb: number;
    memory_limit_mb: number;
    memory_percent: number;
}

export default function SystemMonitor() {
    const [containers, setContainers] = useState<Container[]>([]);
    const [selectedContainer, setSelectedContainer] = useState<string | null>(null);
    const [logs, setLogs] = useState<string>('');
    const [stats, setStats] = useState<Record<string, Stats>>({});
    const [isLoading, setIsLoading] = useState(true);
    const [isRefreshing, setIsRefreshing] = useState(false);

    useEffect(() => {
        fetchData();
        const interval = setInterval(fetchStats, 5000);
        return () => clearInterval(interval);
    }, []);

    const fetchData = async () => {
        setIsLoading(true);
        try {
            const data = await systemApi.getContainers();
            setContainers(data);
            if (data.length > 0 && !selectedContainer) {
                setSelectedContainer(data[0].name);
            }
        } catch (e) {
            console.error('Failed to fetch containers', e);
        } finally {
            setIsLoading(false);
        }
    };

    const fetchStats = async () => {
        setIsRefreshing(true);
        try {
            const data = await systemApi.getContainers();
            setContainers(data);

            // Fetch stats for all active containers
            const newStats: Record<string, Stats> = {};
            for (const c of data) {
                if (c.status === 'running') {
                    try {
                        const s = await systemApi.getStats(c.name);
                        newStats[c.name] = s;
                    } catch (e) {
                        // ignore error for single stat
                    }
                }
            }
            setStats(newStats);
        } catch (e) {
            console.error('Failed to refresh stats', e);
        } finally {
            setIsRefreshing(false);
        }
    };

    useEffect(() => {
        if (selectedContainer) {
            fetchLogs(selectedContainer);
        }
    }, [selectedContainer]);

    const fetchLogs = async (name: string) => {
        try {
            const { logs } = await systemApi.getLogs(name, 100);
            setLogs(logs);
        } catch (e) {
            setLogs('Errore durante il caricamento dei log.');
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
                    <p className="page-subtitle">Monitoring in tempo reale dell'infrastruttura Docker</p>
                </div>
                <button
                    className={`btn btn-secondary btn-sm ${isRefreshing ? 'animate-pulse' : ''}`}
                    onClick={fetchStats}
                >
                    <RefreshCcw size={14} /> Refresh
                </button>
            </div>

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
                            <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', margin: 0 }}>Statistiche non disponibili</p>
                        )}
                    </motion.div>
                ))}
            </div>

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
                        {logs || 'Nessun log disponibile.'}
                    </pre>
                </div>
            </div>
        </div>
    );
}
