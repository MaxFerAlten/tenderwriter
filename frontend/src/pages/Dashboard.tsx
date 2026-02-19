import { useState } from 'react';
import { motion } from 'framer-motion';
import {
    Plus,
    Clock,
    TrendingUp,
    FileText,
    CheckCircle,
} from 'lucide-react';

// ── Demo Data ──
const DEMO_TENDERS = [
    {
        id: 1,
        title: 'Highway Bridge Rehabilitation — Route 42',
        client: 'State Department of Transportation',
        deadline: '2026-03-15',
        status: 'active',
        category: 'Infrastructure',
    },
    {
        id: 2,
        title: 'Municipal Water Treatment Plant Upgrade',
        client: 'City of Springfield',
        deadline: '2026-02-28',
        status: 'in_progress',
        category: 'Water & Environment',
    },
    {
        id: 3,
        title: 'Enterprise IT Infrastructure Modernization',
        client: 'Global Corp Inc.',
        deadline: '2026-04-01',
        status: 'draft',
        category: 'IT & Technology',
    },
    {
        id: 4,
        title: 'School District Campus Expansion Phase II',
        client: 'Lincoln County Schools',
        deadline: '2026-03-20',
        status: 'active',
        category: 'Education',
    },
    {
        id: 5,
        title: 'Renewable Energy Feasibility Study',
        client: 'GreenPower Authority',
        deadline: '2026-02-20',
        status: 'submitted',
        category: 'Energy',
    },
    {
        id: 6,
        title: 'Hospital Wing Construction — Phase I',
        client: 'Metropolitan Health System',
        deadline: '2026-01-30',
        status: 'won',
        category: 'Healthcare',
    },
];

const PIPELINE_COLUMNS = [
    { key: 'draft', label: 'Draft', color: '#64748b' },
    { key: 'active', label: 'Active', color: '#3b82f6' },
    { key: 'in_progress', label: 'In Progress', color: '#f59e0b' },
    { key: 'submitted', label: 'Submitted', color: '#8b5cf6' },
    { key: 'won', label: 'Won', color: '#10b981' },
];

function getDaysUntil(dateStr: string): number {
    const target = new Date(dateStr);
    const now = new Date();
    return Math.ceil((target.getTime() - now.getTime()) / (1000 * 60 * 60 * 24));
}

function TenderCard({ tender, index }: { tender: typeof DEMO_TENDERS[0]; index: number }) {
    const days = getDaysUntil(tender.deadline);
    const isUrgent = days <= 7 && days > 0;
    const isPast = days < 0;

    return (
        <motion.div
            className="tender-card"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: index * 0.05 }}
        >
            <div className="tender-card-title">{tender.title}</div>
            <div className="tender-card-client">{tender.client}</div>
            <div className="tender-card-footer">
                <span className={isUrgent ? 'deadline-urgent' : ''}>
                    <Clock size={12} style={{ marginRight: 4, verticalAlign: 'middle' }} />
                    {isPast ? 'Past due' : isUrgent ? `${days}d left!` : `${days} days`}
                </span>
                <span className={`badge badge-${tender.status.replace('_', '-')}`}>
                    {tender.status.replace('_', ' ')}
                </span>
            </div>
        </motion.div>
    );
}

export default function Dashboard() {
    const [showNewTender, setShowNewTender] = useState(false);

    const stats = [
        { label: 'Active Tenders', value: '4', change: '+2 this month', positive: true, icon: FileText },
        { label: 'Win Rate', value: '68%', change: '+5% vs last quarter', positive: true, icon: TrendingUp },
        { label: 'Pending Deadlines', value: '3', change: '2 this week', positive: false, icon: Clock },
        { label: 'Proposals Won', value: '12', change: '+3 this quarter', positive: true, icon: CheckCircle },
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
                                <div className="stat-value">{stat.value}</div>
                                <div className={`stat-change ${stat.positive ? 'positive' : 'negative'}`}>
                                    {stat.change}
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
                            <label className="form-label">Tender Title</label>
                            <input className="form-input" placeholder="e.g., Highway Bridge Rehabilitation" />
                        </div>
                        <div className="form-group">
                            <label className="form-label">Client</label>
                            <input className="form-input" placeholder="e.g., State DOT" />
                        </div>
                        <div className="form-group">
                            <label className="form-label">Category</label>
                            <select className="form-select">
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
                            <input className="form-input" type="date" />
                        </div>
                    </div>
                    <div style={{ display: 'flex', gap: '0.75rem', marginTop: '0.5rem' }}>
                        <button className="btn btn-primary">
                            <Plus size={16} /> Create Tender
                        </button>
                        <button className="btn btn-ghost" onClick={() => setShowNewTender(false)}>
                            Cancel
                        </button>
                    </div>
                </motion.div>
            )}

            {/* Pipeline Kanban */}
            <div className="pipeline">
                {PIPELINE_COLUMNS.map((col) => {
                    const tenders = DEMO_TENDERS.filter((t) => t.status === col.key);
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
                                <span className="pipeline-count">{tenders.length}</span>
                            </div>

                            {tenders.length === 0 ? (
                                <div className="empty-state" style={{ padding: '2rem 1rem' }}>
                                    <p style={{ fontSize: '0.8rem' }}>No tenders</p>
                                </div>
                            ) : (
                                tenders.map((tender, i) => (
                                    <TenderCard key={tender.id} tender={tender} index={i} />
                                ))
                            )}
                        </div>
                    );
                })}
            </div>
        </div>
    );
}
