import { useState, useEffect, useCallback } from 'react';
import { motion } from 'framer-motion';
import {
    Plus,
    Clock,
    TrendingUp,
    FileText,
    CheckCircle,
    AlertCircle,
    Loader2,
} from 'lucide-react';
import { tenderApi, type Tender, type TenderCreate } from '../api/client';

const PIPELINE_COLUMNS = [
    { key: 'draft', label: 'Draft', color: '#64748b' },
    { key: 'active', label: 'Active', color: '#3b82f6' },
    { key: 'in_progress', label: 'In Progress', color: '#f59e0b' },
    { key: 'submitted', label: 'Submitted', color: '#8b5cf6' },
    { key: 'won', label: 'Won', color: '#10b981' },
];

function getDaysUntil(dateStr: string | null): number | null {
    if (!dateStr) return null;
    const target = new Date(dateStr);
    const now = new Date();
    return Math.ceil((target.getTime() - now.getTime()) / (1000 * 60 * 60 * 24));
}

function TenderCard({ tender, index }: { tender: Tender; index: number }) {
    const days = getDaysUntil(tender.deadline);
    const isUrgent = days !== null && days <= 7 && days > 0;
    const isPast = days !== null && days < 0;

    return (
        <motion.div
            className="tender-card"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: index * 0.05 }}
        >
            <div className="tender-card-title">{tender.title}</div>
            <div className="tender-card-client">{tender.client || 'No client'}</div>
            <div className="tender-card-footer">
                <span className={isUrgent ? 'deadline-urgent' : ''}>
                    <Clock size={12} style={{ marginRight: 4, verticalAlign: 'middle' }} />
                    {days === null
                        ? 'No deadline'
                        : isPast
                            ? 'Past due'
                            : isUrgent
                                ? `${days}d left!`
                                : `${days} days`}
                </span>
                <span className={`badge badge-${tender.status.replace('_', '-')}`}>
                    {tender.status.replace('_', ' ')}
                </span>
            </div>
        </motion.div>
    );
}

const EMPTY_FORM: TenderCreate = {
    title: '',
    client: '',
    description: '',
    deadline: '',
    category: '',
    tags: [],
    budget_estimate: undefined,
};

export default function Dashboard() {
    const [tenders, setTenders] = useState<Tender[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [showNewTender, setShowNewTender] = useState(false);
    const [form, setForm] = useState<TenderCreate>({ ...EMPTY_FORM });
    const [creating, setCreating] = useState(false);

    const loadTenders = useCallback(async () => {
        try {
            setLoading(true);
            setError(null);
            const data = await tenderApi.list({ limit: '100' });
            setTenders(data.items);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to load tenders');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        loadTenders();
    }, [loadTenders]);

    const handleCreate = async () => {
        if (!form.title.trim()) return;
        try {
            setCreating(true);
            const payload: TenderCreate = { title: form.title };
            if (form.client) payload.client = form.client;
            if (form.description) payload.description = form.description;
            if (form.deadline) payload.deadline = new Date(form.deadline).toISOString();
            if (form.category) payload.category = form.category;
            await tenderApi.create(payload);
            setForm({ ...EMPTY_FORM });
            setShowNewTender(false);
            await loadTenders();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to create tender');
        } finally {
            setCreating(false);
        }
    };

    // Compute real stats
    const activeTenders = tenders.filter(
        (t) => t.status === 'active' || t.status === 'in_progress'
    ).length;
    const wonTenders = tenders.filter((t) => t.status === 'won').length;
    const totalDecided = tenders.filter(
        (t) => t.status === 'won' || t.status === 'lost'
    ).length;
    const winRate = totalDecided > 0 ? Math.round((wonTenders / totalDecided) * 100) : 0;
    const pendingDeadlines = tenders.filter((t) => {
        const days = getDaysUntil(t.deadline);
        return days !== null && days > 0 && days <= 14;
    }).length;

    const stats = [
        { label: 'Active Tenders', value: String(activeTenders), icon: FileText },
        { label: 'Win Rate', value: totalDecided > 0 ? `${winRate}%` : 'N/A', icon: TrendingUp },
        { label: 'Pending Deadlines', value: String(pendingDeadlines), icon: Clock },
        { label: 'Proposals Won', value: String(wonTenders), icon: CheckCircle },
    ];

    return (
        <div className="animate-in">
            {/* Header */}
            <div className="page-header">
                <div>
                    <h1 className="page-title">Dashboard</h1>
                    <p className="page-subtitle">Manage your tender pipeline and track deadlines</p>
                </div>
                <button
                    className="btn btn-primary"
                    onClick={() => setShowNewTender(!showNewTender)}
                >
                    <Plus size={18} />
                    New Tender
                </button>
            </div>

            {/* Error */}
            {error && (
                <div className="card" style={{ borderColor: '#ef4444', marginBottom: '1.5rem', display: 'flex', alignItems: 'center', gap: '0.75rem', color: '#ef4444' }}>
                    <AlertCircle size={18} />
                    <span>{error}</span>
                    <button className="btn btn-ghost btn-sm" onClick={loadTenders} style={{ marginLeft: 'auto' }}>Retry</button>
                </div>
            )}

            {/* Stats */}
            <div className="stats-grid">
                {stats.map((stat, i) => (
                    <motion.div
                        key={stat.label}
                        className="stat-card"
                        initial={{ opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: i * 0.08 }}
                    >
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                            <div>
                                <div className="stat-label">{stat.label}</div>
                                <div className="stat-value">
                                    {loading ? '—' : stat.value}
                                </div>
                            </div>
                            <stat.icon size={20} color="#64748b" />
                        </div>
                    </motion.div>
                ))}
            </div>

            {/* New Tender Form */}
            {showNewTender && (
                <motion.div
                    className="card"
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: 'auto' }}
                    style={{ marginBottom: '1.5rem' }}
                >
                    <h3 style={{ marginBottom: '1rem' }}>Create New Tender</h3>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                        <div className="form-group">
                            <label className="form-label">Tender Title *</label>
                            <input
                                className="form-input"
                                placeholder="e.g., Highway Bridge Rehabilitation"
                                value={form.title}
                                onChange={(e) => setForm({ ...form, title: e.target.value })}
                            />
                        </div>
                        <div className="form-group">
                            <label className="form-label">Client</label>
                            <input
                                className="form-input"
                                placeholder="e.g., State DOT"
                                value={form.client || ''}
                                onChange={(e) => setForm({ ...form, client: e.target.value })}
                            />
                        </div>
                        <div className="form-group">
                            <label className="form-label">Category</label>
                            <select
                                className="form-select"
                                value={form.category || ''}
                                onChange={(e) => setForm({ ...form, category: e.target.value })}
                            >
                                <option value="">Select category</option>
                                <option>Infrastructure</option>
                                <option>IT & Technology</option>
                                <option>Water & Environment</option>
                                <option>Energy</option>
                                <option>Healthcare</option>
                                <option>Education</option>
                            </select>
                        </div>
                        <div className="form-group">
                            <label className="form-label">Deadline</label>
                            <input
                                className="form-input"
                                type="date"
                                value={form.deadline || ''}
                                onChange={(e) => setForm({ ...form, deadline: e.target.value })}
                            />
                        </div>
                    </div>
                    <div style={{ display: 'flex', gap: '0.75rem', marginTop: '0.5rem' }}>
                        <button
                            className="btn btn-primary"
                            onClick={handleCreate}
                            disabled={creating || !form.title.trim()}
                        >
                            {creating ? <Loader2 size={16} className="spin" /> : <Plus size={16} />}
                            {creating ? 'Creating...' : 'Create Tender'}
                        </button>
                        <button className="btn btn-ghost" onClick={() => setShowNewTender(false)}>
                            Cancel
                        </button>
                    </div>
                </motion.div>
            )}

            {/* Loading */}
            {loading && (
                <div className="loading-spinner" style={{ padding: '3rem 0' }}>
                    <div className="spinner" />
                    <p style={{ color: 'var(--text-muted)', marginTop: '0.75rem' }}>Loading tenders...</p>
                </div>
            )}

            {/* Pipeline Kanban */}
            {!loading && (
                <div className="pipeline">
                    {PIPELINE_COLUMNS.map((col) => {
                        const colTenders = tenders.filter((t) => t.status === col.key);
                        return (
                            <div className="pipeline-column" key={col.key}>
                                <div className="pipeline-header">
                                    <h3 style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                        <span
                                            style={{
                                                width: 8,
                                                height: 8,
                                                borderRadius: '50%',
                                                background: col.color,
                                                display: 'inline-block',
                                            }}
                                        />
                                        {col.label}
                                    </h3>
                                    <span className="pipeline-count">{colTenders.length}</span>
                                </div>

                                {colTenders.length === 0 ? (
                                    <div className="empty-state" style={{ padding: '2rem 1rem' }}>
                                        <p style={{ fontSize: '0.8rem' }}>No tenders</p>
                                    </div>
                                ) : (
                                    colTenders.map((tender, i) => (
                                        <TenderCard key={tender.id} tender={tender} index={i} />
                                    ))
                                )}
                            </div>
                        );
                    })}
                </div>
            )}

            {/* Empty state */}
            {!loading && tenders.length === 0 && !error && (
                <div className="empty-state" style={{ padding: '3rem 0' }}>
                    <FileText size={48} />
                    <h3>No tenders yet</h3>
                    <p>Create your first tender to get started</p>
                </div>
            )}
        </div>
    );
}
