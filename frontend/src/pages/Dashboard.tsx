import { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
    Plus,
    Clock,
    TrendingUp,
    FileText,
    CheckCircle,
    AlertCircle,
    Loader2,
    Upload,
    Check,
    FileEdit,
    MessageSquare,
    X,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { prefetchTenderChatContext, prefetchTenderChatRetrospective, tenderApi, proposalApi, type Tender, type TenderCreate } from '../api/client';
import { preloadRoute } from '../router/lazyRoutes';

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

function TenderCard({ tender, index, onUpload, onCreateProposal, onEditProposal, onSubmit, onOpenChat, onWarmChat }: { tender: Tender; index: number; onUpload: (id: number, file: File) => Promise<void>; onCreateProposal: (tenderId: number | null) => void; onEditProposal: (proposalId: number) => void; onSubmit: (id: number) => Promise<void>; onOpenChat: (id: number) => void; onWarmChat: (id: number) => void }) {
    const days = getDaysUntil(tender.deadline);
    const isUrgent = days !== null && days <= 7 && days > 0;
    const isPast = days !== null && days < 0;

    const [uploading, setUploading] = useState(false);
    const [success, setSuccess] = useState(false);

    const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file) return;

        try {
            setUploading(true);
            await onUpload(tender.id, file);
            setSuccess(true);
            setTimeout(() => setSuccess(false), 3000);
        } catch (err) {
            console.error(err);
        } finally {
            setUploading(false);
            // Reset input
            e.target.value = '';
        }
    };

    return (
        <motion.div
            className="tender-card"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            whileHover={{ y: -4, boxShadow: 'var(--shadow-lg)', borderColor: 'var(--accent-blue)' }}
            transition={{ delay: index * 0.05, duration: 0.2 }}
            style={{
                background: 'rgba(255, 255, 255, 0.02)',
                backdropFilter: 'blur(10px)',
                cursor: 'default'
            }}
        >
            <div className="tender-card-title">{tender.title}</div>
            <div className="tender-card-client">{tender.client || 'No client'}</div>

            <div style={{ marginTop: '0.75rem', marginBottom: '0.75rem', display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                {!['submitted', 'won', 'lost', 'cancelled'].includes(tender.status) && (
                    <label className="btn btn-secondary btn-sm" style={{ cursor: uploading ? 'not-allowed' : 'pointer', fontSize: '0.75rem', padding: '0.25rem 0.5rem' }}>
                        {uploading ? <Loader2 size={12} className="spin" /> : success ? <Check size={12} color="#10b981" /> : <Upload size={12} />}
                        {uploading ? 'Uploading...' : success ? 'Uploaded' : 'Upload PDF'}
                        <input
                            type="file"
                            accept=".pdf,.docx,.txt"
                            style={{ display: 'none' }}
                            onChange={handleFileChange}
                            disabled={uploading}
                        />
                    </label>
                )}

                {tender.status === 'active' && (
                    <button
                        className="btn btn-primary btn-sm"
                        style={{ fontSize: '0.75rem', padding: '0.25rem 0.5rem', gap: '0.25rem' }}
                        onClick={() => onCreateProposal(tender.id)}
                    >
                        <FileEdit size={12} />
                        Create Proposal
                    </button>
                )}

                {tender.status === 'in_progress' && (
                    <>
                        <button
                            className="btn btn-primary btn-sm"
                            style={{ fontSize: '0.75rem', padding: '0.25rem 0.5rem', gap: '0.25rem' }}
                            onClick={() => {
                                if (tender.proposal_id) {
                                    onEditProposal(tender.proposal_id);
                                } else {
                                    onCreateProposal(tender.id);
                                }
                            }}
                        >
                            <FileEdit size={12} />
                            Edit Proposal
                        </button>
                        <button
                            className="btn btn-secondary btn-sm"
                            style={{ fontSize: '0.75rem', padding: '0.25rem 0.6rem', gap: '0.25rem', background: 'var(--accent-purple)', color: 'white', border: 'none' }}
                            onClick={() => onSubmit(tender.id)}
                        >
                            <CheckCircle size={12} />
                            Submit
                        </button>
                    </>
                )}

                <button
                    className="btn btn-ghost btn-sm"
                    style={{ fontSize: '0.75rem', padding: '0.25rem 0.6rem', gap: '0.25rem' }}
                    onClick={() => onOpenChat(tender.id)}
                    onMouseEnter={() => onWarmChat(tender.id)}
                    onFocus={() => onWarmChat(tender.id)}
                    onTouchStart={() => onWarmChat(tender.id)}
                >
                    <MessageSquare size={12} />
                    Open Chat
                </button>
            </div>

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

    // Proposal creation state
    const [showNewProposal, setShowNewProposal] = useState<number | null>(null);
    const [proposalTitle, setProposalTitle] = useState('');
    const [creatingProposal, setCreatingProposal] = useState(false);

    const navigate = useNavigate();

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

    const handleCreateProposal = async () => {
        if (!proposalTitle.trim() || showNewProposal === null) return;
        try {
            setCreatingProposal(true);
            const proposal = await proposalApi.create({
                tender_id: showNewProposal,
                title: proposalTitle,
            });
            setShowNewProposal(null);
            setProposalTitle('');
            // Navigate to proposals page and select the new proposal
            navigate('/proposals', { state: { proposalId: proposal.id } });
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to create proposal');
        } finally {
            setCreatingProposal(false);
        }
    };

    const handleUpload = async (id: number, file: File) => {
        try {
            setError(null);
            await tenderApi.uploadDocument(id, file);
            warmChatExperience(id);
            // Refresh to see status change from DRAFT -> ACTIVE
            await loadTenders();
            navigate(`/tenders/${id}/chat`);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to upload document');
            throw err;
        }
    };

    const handleEditProposal = (proposalId: number) => {
        navigate('/proposals', { state: { proposalId } });
    };

    const warmChatExperience = useCallback((id: number) => {
        void preloadRoute(`/tenders/${id}/chat`);
        void prefetchTenderChatContext(id);
        void prefetchTenderChatRetrospective(id);
    }, []);

    const handleWarmChat = (id: number) => {
        warmChatExperience(id);
    };

    const handleOpenChat = (id: number) => {
        warmChatExperience(id);
        navigate(`/tenders/${id}/chat`);
    };

    const handleSubmitTender = async (id: number) => {
        try {
            setLoading(true);
            await tenderApi.update(id, { status: 'submitted' });
            await loadTenders();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to submit tender');
        } finally {
            setLoading(false);
        }
    };

    // Compute real stats
    const activeTenders = tenders.filter(
        (t) => t.status === 'active' || t.status === 'in_progress' || t.status === 'submitted'
    ).length;
    const wonTenders = tenders.filter((t) => t.status === 'won').length;
    const totalDecided = tenders.filter(
        (t) => t.status === 'won' || t.status === 'lost'
    ).length;
    const winRate = totalDecided > 0 ? Math.round((wonTenders / totalDecided) * 100) : 0;
    const pendingDeadlines = tenders.filter((t) => {
        const days = getDaysUntil(t.deadline);
        // exclude won, lost, cancelled from pending deadlines
        const isPending = !['won', 'lost', 'cancelled'].includes(t.status);
        return isPending && days !== null && days > 0 && days <= 14;
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
                        whileHover={{ y: -4, boxShadow: 'var(--shadow-glow)', borderColor: 'var(--accent-blue)' }}
                        transition={{ delay: i * 0.08, duration: 0.2 }}
                        style={{
                            background: 'rgba(255, 255, 255, 0.03)',
                            backdropFilter: 'blur(10px)',
                            border: '1px solid var(--border-default)',
                        }}
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

            {/* Tenders list logic remains below */}

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
                                        <TenderCard key={tender.id} tender={tender} index={i} onUpload={handleUpload} onCreateProposal={setShowNewProposal} onEditProposal={handleEditProposal} onSubmit={handleSubmitTender} onOpenChat={handleOpenChat} onWarmChat={handleWarmChat} />
                                    ))
                                )}
                            </div>
                        );
                    })}
                </div>
            )}

            {/* New Proposal Modal */}
            <AnimatePresence>
                {showNewProposal !== null && (
                    <motion.div
                        className="modal-overlay"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                    >
                        <motion.div
                            className="modal-content"
                            initial={{ scale: 0.95, opacity: 0, y: 20 }}
                            animate={{ scale: 1, opacity: 1, y: 0 }}
                            exit={{ scale: 0.95, opacity: 0, y: 20 }}
                        >
                            <div className="modal-header">
                                <h3 style={{ margin: 0 }}>Create New Proposal</h3>
                                <button
                                    className="btn btn-icon btn-ghost"
                                    onClick={() => {
                                        setShowNewProposal(null);
                                        setProposalTitle('');
                                    }}
                                >
                                    <X size={20} />
                                </button>
                            </div>

                            <div className="modal-body">
                                <p className="page-subtitle" style={{ marginBottom: '1.5rem', marginTop: 0 }}>
                                    Define the title for your new technical proposal. You can change this later.
                                </p>
                                <div className="form-group">
                                    <label className="form-label">Proposal Title *</label>
                                    <input
                                        type="text"
                                        className="form-input"
                                        placeholder="e.g., Technical Proposal - Phase 1"
                                        value={proposalTitle}
                                        onChange={(e) => setProposalTitle(e.target.value)}
                                        autoFocus
                                    />
                                </div>
                            </div>

                            <div className="modal-footer">
                                <button
                                    className="btn btn-ghost"
                                    onClick={() => {
                                        setShowNewProposal(null);
                                        setProposalTitle('');
                                    }}
                                >
                                    Cancel
                                </button>
                                <button
                                    className="btn btn-primary"
                                    disabled={!proposalTitle.trim() || creatingProposal}
                                    onClick={handleCreateProposal}
                                >
                                    {creatingProposal ? (
                                        <>
                                            <Loader2 size={16} className="spin" />
                                            Creating...
                                        </>
                                    ) : (
                                        'Create Proposal'
                                    )}
                                </button>
                            </div>
                        </motion.div>
                    </motion.div>
                )}
                {showNewTender && (
                    <motion.div
                        className="modal-overlay"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                    >
                        <motion.div
                            className="modal-content"
                            style={{ maxWidth: '650px' }}
                            initial={{ scale: 0.95, opacity: 0, y: 20 }}
                            animate={{ scale: 1, opacity: 1, y: 0 }}
                            exit={{ scale: 0.95, opacity: 0, y: 20 }}
                        >
                            <div className="modal-header">
                                <h3 style={{ margin: 0 }}>Create New Tender</h3>
                                <button
                                    className="btn btn-icon btn-ghost"
                                    onClick={() => setShowNewTender(false)}
                                >
                                    <X size={20} />
                                </button>
                            </div>

                            <div className="modal-body">
                                <p className="page-subtitle" style={{ marginBottom: '1.5rem', marginTop: 0 }}>
                                    Add a new opportunity to the pipeline. You can import documents immediately after creation.
                                </p>
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.25rem' }}>
                                    <div className="form-group">
                                        <label className="form-label">Tender Title *</label>
                                        <input
                                            className="form-input"
                                            placeholder="e.g., Highway Bridge Rehabilitation"
                                            value={form.title}
                                            onChange={(e) => setForm({ ...form, title: e.target.value })}
                                            autoFocus
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
                                <div className="form-group" style={{ marginTop: '0.25rem' }}>
                                    <label className="form-label">Description (Optional)</label>
                                    <textarea
                                        className="form-textarea"
                                        placeholder="Briefly describe the tender requirements or context..."
                                        value={form.description || ''}
                                        onChange={(e) => setForm({ ...form, description: e.target.value })}
                                        rows={3}
                                    />
                                </div>
                            </div>

                            <div className="modal-footer">
                                <button className="btn btn-ghost" onClick={() => setShowNewTender(false)}>
                                    Cancel
                                </button>
                                <button
                                    className="btn btn-primary"
                                    onClick={handleCreate}
                                    disabled={creating || !form.title.trim()}
                                >
                                    {creating ? <Loader2 size={16} className="spin" /> : <Plus size={16} />}
                                    {creating ? 'Creating...' : 'Create Tender'}
                                </button>
                            </div>
                        </motion.div>
                    </motion.div>
                )}
            </AnimatePresence>

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
