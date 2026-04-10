import { useState, useEffect, useCallback, useRef } from 'react';
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
    Video,
    ChevronDown,
    X,
    Settings,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import {
    prefetchTenderChatContext,
    prefetchTenderChatRetrospective,
    tenderApi,
    proposalApi,
    type Tender,
    type TenderCreate,
    type TenderImportWarning,
} from '../api/client';
import { preloadRoute } from '../router/lazyRoutes';

const PIPELINE_COLUMNS = [
    { key: 'draft', label: 'Draft', color: '#64748b' },
    { key: 'active', label: 'Active', color: '#3b82f6' },
    { key: 'in_progress', label: 'In Progress', color: '#f59e0b' },
    { key: 'submitted', label: 'Submitted', color: '#8b5cf6' },
    { key: 'won', label: 'Won', color: '#10b981' },
];

interface IngestionLiveStatus {
    status: string;
    progress: number;
    error?: string;
    tenderId: number;
    documentId: number;
}

function getDaysUntil(dateStr: string | null): number | null {
    if (!dateStr) return null;
    const target = new Date(dateStr);
    const now = new Date();
    return Math.ceil((target.getTime() - now.getTime()) / (1000 * 60 * 60 * 24));
}

function cleanTenderTitle(title: string): string {
    return title.trim().replace(/\s+/g, ' ');
}

function tenderTitleLookupKey(title: string): string {
    return cleanTenderTitle(title).toLowerCase();
}

export interface TenderUploadAlert {
    title: string;
    tenderTitle: string;
    filename: string;
    warnings: TenderImportWarning[];
    extractionMethod?: string | null;
}

export function TenderUploadAlertModal({
    alert,
    onClose,
}: {
    alert: TenderUploadAlert | null;
    onClose?: () => void;
}) {
    if (!alert) {
        return null;
    }

    const fallbackWarnings = alert.warnings.filter((warning) => warning.fallback_applied);

    return (
        <motion.div
            className="modal-overlay"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            role="dialog"
            aria-modal="true"
            aria-labelledby="tender-upload-alert-title"
        >
            <motion.div
                className="modal-content"
                style={{ maxWidth: '620px' }}
                initial={{ scale: 0.95, opacity: 0, y: 20 }}
                animate={{ scale: 1, opacity: 1, y: 0 }}
                exit={{ scale: 0.95, opacity: 0, y: 20 }}
            >
                <div className="modal-header">
                    <h3 id="tender-upload-alert-title" style={{ margin: 0 }}>{alert.title}</h3>
                    <button className="btn btn-icon btn-ghost" onClick={onClose}>
                        <X size={20} />
                    </button>
                </div>

                <div className="modal-body">
                    <div
                        style={{
                            display: 'flex',
                            alignItems: 'flex-start',
                            gap: '0.75rem',
                            padding: '0.85rem 1rem',
                            borderRadius: '12px',
                            background: 'rgba(127, 29, 29, 0.14)',
                            border: '1px solid rgba(248, 113, 113, 0.25)',
                            color: '#fecaca',
                            marginBottom: '1rem',
                        }}
                    >
                        <AlertCircle size={18} style={{ marginTop: '0.1rem', flexShrink: 0 }} />
                        <div>
                            <div style={{ fontWeight: 700, marginBottom: '0.25rem' }}>
                                {alert.tenderTitle} · {alert.filename}
                            </div>
                            <div style={{ fontSize: '0.92rem', color: '#fde68a' }}>
                                The document import completed, but the LLM step reported at least one warning.
                            </div>
                        </div>
                    </div>

                    <div style={{ display: 'grid', gap: '0.9rem' }}>
                        {alert.warnings.map((warning, index) => (
                            <div
                                key={`${warning.code}-${index}`}
                                style={{
                                    padding: '0.9rem 1rem',
                                    borderRadius: '12px',
                                    border: '1px solid rgba(148, 163, 184, 0.18)',
                                    background: 'rgba(15, 23, 42, 0.45)',
                                }}
                            >
                                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.75rem' }}>
                                    <strong>{warning.title || 'Import warning'}</strong>
                                    {warning.status_code !== undefined && warning.status_code !== null && (
                                        <span className="badge badge-pending">HTTP {warning.status_code}</span>
                                    )}
                                </div>
                                <p style={{ margin: '0.65rem 0 0', color: 'var(--text-secondary)' }}>{warning.message}</p>
                                {warning.fallback_applied && (
                                    <div
                                        style={{
                                            marginTop: '0.75rem',
                                            padding: '0.65rem 0.8rem',
                                            borderRadius: '10px',
                                            background: 'rgba(16, 185, 129, 0.12)',
                                            border: '1px solid rgba(16, 185, 129, 0.22)',
                                            color: '#a7f3d0',
                                        }}
                                    >
                                        {warning.fallback_message || 'Fallback applied.'}
                                    </div>
                                )}
                            </div>
                        ))}
                    </div>

                    {fallbackWarnings.length > 0 && alert.extractionMethod && (
                        <div style={{ marginTop: '1rem', color: 'var(--text-muted)', fontSize: '0.9rem' }}>
                            Final extraction method used for this import: <strong>{alert.extractionMethod}</strong>
                        </div>
                    )}
                </div>

                <div className="modal-footer">
                    <button className="btn btn-primary" onClick={onClose}>
                        Understood
                    </button>
                </div>
            </motion.div>
        </motion.div>
    );
}

export function DashboardModalStack({
    uploadAlert,
    onCloseUploadAlert,
    showNewProposal,
    onCloseProposal,
    proposalTitle,
    onProposalTitleChange,
    creatingProposal,
    onCreateProposal,
    showNewTender,
    onCloseNewTender,
    form,
    setForm,
    duplicateTitleError,
    newTenderError,
    setNewTenderError,
    normalizedFormTitle,
    creating,
    onCreate,
}: {
    uploadAlert: TenderUploadAlert | null;
    onCloseUploadAlert: () => void;
    showNewProposal: number | null;
    onCloseProposal: () => void;
    proposalTitle: string;
    onProposalTitleChange: (value: string) => void;
    creatingProposal: boolean;
    onCreateProposal: () => void;
    showNewTender: boolean;
    onCloseNewTender: () => void;
    form: TenderCreate;
    setForm: (value: TenderCreate) => void;
    duplicateTitleError: string | null;
    newTenderError: string | null;
    setNewTenderError: (value: string | null) => void;
    normalizedFormTitle: string;
    creating: boolean;
    onCreate: () => void;
}) {
    return (
        <AnimatePresence>
            {uploadAlert && (
                <TenderUploadAlertModal
                    key="upload-alert-modal"
                    alert={uploadAlert}
                    onClose={onCloseUploadAlert}
                />
            )}
            {showNewProposal !== null && (
                <motion.div
                    key="new-proposal-modal"
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
                                onClick={onCloseProposal}
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
                                    onChange={(e) => onProposalTitleChange(e.target.value)}
                                    autoFocus
                                />
                            </div>
                        </div>

                        <div className="modal-footer">
                            <button
                                className="btn btn-ghost"
                                onClick={onCloseProposal}
                            >
                                Cancel
                            </button>
                            <button
                                className="btn btn-primary"
                                disabled={!proposalTitle.trim() || creatingProposal}
                                onClick={onCreateProposal}
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
                    key="new-tender-modal"
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
                                onClick={onCloseNewTender}
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
                                        onChange={(e) => {
                                            setForm({ ...form, title: e.target.value });
                                            setNewTenderError(null);
                                        }}
                                        autoFocus
                                    />
                                    {(duplicateTitleError || newTenderError) && (
                                        <div style={{ marginTop: '0.45rem', fontSize: '0.82rem', color: '#f87171' }}>
                                            {duplicateTitleError || newTenderError}
                                        </div>
                                    )}
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
                            <button className="btn btn-ghost" onClick={onCloseNewTender}>
                                Cancel
                            </button>
                            <button
                                className="btn btn-primary"
                                onClick={onCreate}
                                disabled={creating || !normalizedFormTitle || Boolean(duplicateTitleError)}
                            >
                                {creating ? <Loader2 size={16} className="spin" /> : <Plus size={16} />}
                                {creating ? 'Creating...' : 'Create Tender'}
                            </button>
                        </div>
                    </motion.div>
                </motion.div>
            )}
        </AnimatePresence>
    );
}

function TenderCard({ tender, index, ingestionStatuses, onUpload, onActivate, onCreateProposal, onEditProposal, onSubmit, onOpenChat, onWarmChat, onOpenFullChat }: { tender: Tender; index: number; ingestionStatuses: Record<number, IngestionLiveStatus>; onUpload: (id: number, file: File) => Promise<void>; onActivate: (id: number) => Promise<void>; onCreateProposal: (tenderId: number | null) => void; onEditProposal: (proposalId: number) => void; onSubmit: (id: number) => Promise<void>; onOpenChat: (id: number) => void; onWarmChat: (id: number) => void; onOpenFullChat: (id: number) => void }) {
    const days = getDaysUntil(tender.deadline);
    const isUrgent = days !== null && days <= 7 && days > 0;
    const isPast = days !== null && days < 0;

    const [uploading, setUploading] = useState(false);
    const [chatMenuOpen, setChatMenuOpen] = useState(false);

    // Get all statuses related to this tender's documents
    const activeIngestions = Object.values(ingestionStatuses).filter(s => 
        s.tenderId === tender.id && (s.status === 'processing' || s.status === 'pending')
    );

    const hasProcessing = activeIngestions.length > 0;
    const isCompleted = tender.ingestion_status === 'completed' || Object.values(ingestionStatuses).some(s => s.tenderId === tender.id && s.status === 'completed');

    const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file) return;

        try {
            setUploading(true);
            await onUpload(tender.id, file);
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
                {tender.status === 'draft' && (
                    <label 
                        className="btn btn-secondary btn-sm" 
                        style={{ cursor: uploading ? 'not-allowed' : 'pointer', fontSize: '0.75rem', padding: '0.25rem 0.5rem' }}
                    >
                        {uploading ? <Loader2 size={12} className="spin" /> : <Upload size={12} />}
                        {uploading ? 'Uploading...' : 'Upload PDF'}
                        <input
                            type="file"
                            accept=".pdf,.docx,.txt"
                            style={{ display: 'none' }}
                            onChange={handleFileChange}
                            disabled={uploading}
                        />
                    </label>
                )}

                {activeIngestions.map((ing) => (
                    <div key={ing.documentId} className="badge badge-draft" style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: '4px', minWidth: '120px', padding: '0.5rem' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '0.7rem' }}>
                            <Loader2 size={10} className="spin" /> 
                            {ing.status === 'processing' ? `Parsing... ${Math.round(ing.progress)}%` : 'In coda...'}
                        </div>
                        <div style={{ width: '100%', height: '4px', background: 'rgba(255,255,255,0.1)', borderRadius: '2px', overflow: 'hidden' }}>
                            <div style={{ width: `${ing.progress}%`, height: '100%', background: 'var(--accent-blue)', transition: 'width 0.3s ease' }} />
                        </div>
                    </div>
                ))}
                
                {isCompleted && tender.status === 'draft' && (
                    <button
                        className="btn btn-primary btn-sm"
                        style={{ 
                            fontSize: '0.75rem', 
                            padding: '0.25rem 0.5rem', 
                            gap: '0.25rem',
                            opacity: hasProcessing ? 0.6 : 1,
                            cursor: hasProcessing ? 'not-allowed' : 'pointer'
                        }}
                        onClick={() => onActivate(tender.id)}
                        disabled={hasProcessing}
                    >
                        <Check size={12} />
                        Activate Tender
                    </button>
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

                {/* Chat mode split-button: Internal Chat (default) + Mattermost dropdown */}
                <div style={{ position: 'relative', display: 'inline-flex' }}>
                    <button
                        className="btn btn-ghost btn-sm"
                        style={{ fontSize: '0.75rem', padding: '0.25rem 0.6rem', gap: '0.25rem', borderTopRightRadius: 0, borderBottomRightRadius: 0 }}
                        onClick={() => onOpenChat(tender.id)}
                        onMouseEnter={() => onWarmChat(tender.id)}
                        onFocus={() => onWarmChat(tender.id)}
                        onTouchStart={() => onWarmChat(tender.id)}
                    >
                        <MessageSquare size={12} />
                        Chat
                    </button>
                    <button
                        className="btn btn-ghost btn-sm"
                        style={{
                            padding: '0.25rem 0.35rem',
                            borderTopLeftRadius: 0,
                            borderBottomLeftRadius: 0,
                            borderLeft: '1px solid var(--border-default)',
                            minWidth: 'unset',
                        }}
                        onClick={(e) => {
                            e.stopPropagation();
                            setChatMenuOpen(!chatMenuOpen);
                        }}
                        onBlur={() => setTimeout(() => setChatMenuOpen(false), 150)}
                        aria-label="Chat options"
                        aria-haspopup="menu"
                        aria-expanded={chatMenuOpen}
                    >
                        <ChevronDown size={14} />
                    </button>
                    {chatMenuOpen && (
                        <div style={{
                            position: 'absolute',
                            top: '100%',
                            right: 0,
                            marginTop: '0.25rem',
                            background: 'var(--bg-card, #1e293b)',
                            border: '1px solid var(--border-default)',
                            borderRadius: '8px',
                            boxShadow: 'var(--shadow-lg)',
                            zIndex: 50,
                            minWidth: '180px',
                            overflow: 'hidden',
                        }}>
                            <button
                                className="btn btn-ghost"
                                style={{ width: '100%', fontSize: '0.78rem', padding: '0.6rem 0.75rem', gap: '0.4rem', justifyContent: 'flex-start', borderRadius: 0 }}
                                onMouseDown={(e) => { e.preventDefault(); onOpenChat(tender.id); setChatMenuOpen(false); }}
                            >
                                <MessageSquare size={14} />
                                Simple Chat
                            </button>
                            <div style={{ borderTop: '1px solid var(--border-default)' }} />
                            <button
                                className="btn btn-ghost"
                                style={{ width: '100%', fontSize: '0.78rem', padding: '0.6rem 0.75rem', gap: '0.4rem', justifyContent: 'flex-start', borderRadius: 0 }}
                                onMouseDown={(e) => { e.preventDefault(); onOpenFullChat(tender.id); setChatMenuOpen(false); }}
                            >
                                <Video size={14} />
                                Full Chat
                            </button>
                        </div>
                    )}
                </div>
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
    const [newTenderError, setNewTenderError] = useState<string | null>(null);
    const [uploadAlert, setUploadAlert] = useState<TenderUploadAlert | null>(null);

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

    const closeNewTenderModal = useCallback(() => {
        setShowNewTender(false);
        setForm({ ...EMPTY_FORM });
        setNewTenderError(null);
    }, []);

    const openNewTenderModal = useCallback(() => {
        setShowNewTender(true);
        setForm({ ...EMPTY_FORM });
        setNewTenderError(null);
    }, []);

    const normalizedFormTitle = cleanTenderTitle(form.title);
    const duplicateTitleError = normalizedFormTitle
        && tenders.some((tender) => tenderTitleLookupKey(tender.title) === tenderTitleLookupKey(normalizedFormTitle))
        ? 'A tender with this title already exists.'
        : null;

    const handleCreate = async () => {
        if (!normalizedFormTitle) return;
        if (duplicateTitleError) {
            setNewTenderError(duplicateTitleError);
            return;
        }

        try {
            setCreating(true);
            setNewTenderError(null);
            const payload: TenderCreate = { title: normalizedFormTitle };
            if (form.client) payload.client = form.client;
            if (form.description) payload.description = form.description;
            if (form.deadline) payload.deadline = new Date(form.deadline).toISOString();
            if (form.category) payload.category = form.category;
            await tenderApi.create(payload);
            closeNewTenderModal();
            await loadTenders();
        } catch (err) {
            setNewTenderError(err instanceof Error ? err.message : 'Failed to create tender');
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

    const [ingestionStatuses, setIngestionStatuses] = useState<Record<number, IngestionLiveStatus>>({});
    const hadActiveIngestionRef = useRef(false);

    const hasActiveIngestions = Object.values(ingestionStatuses).some(
        (ing) => ing.status === 'processing' || ing.status === 'pending'
    ) || tenders.some(
        (tender) => tender.ingestion_status === 'processing' || tender.ingestion_status === 'pending'
    );

    const handleUpload = async (id: number, file: File) => {
        try {
            setError(null);
            setUploadAlert(null);
            const response = await tenderApi.uploadDocument(id, file);
            const docId = response.document_id;
            
            // Start SSE listener
            setIngestionStatuses(prev => ({
                ...prev,
                [docId]: { status: 'pending', progress: 0, tenderId: id, documentId: docId },
            }));
            
            const eventSource = new EventSource(tenderApi.streamDocumentStatusUrl(id, docId));
            
            eventSource.onmessage = (event) => {
                const data = JSON.parse(event.data);
                if (data.error) {
                    setIngestionStatuses(prev => ({ ...prev, [docId]: { ...prev[docId], status: 'failed', error: data.error } }));
                    eventSource.close();
                    return;
                }
                
                setIngestionStatuses(prev => {
                    const previous = prev[docId] || {
                        status: 'pending',
                        progress: 0,
                        tenderId: id,
                        documentId: docId,
                    };

                    const rawProgress = Number(data.progress);
                    const incomingProgress = Number.isFinite(rawProgress) ? rawProgress : previous.progress;
                    let nextProgress = Math.max(previous.progress, incomingProgress);

                    // The backend emits milestone updates; this keeps the bar moving between milestones.
                    if (data.status === 'processing') {
                        nextProgress = Math.min(Math.max(nextProgress, previous.progress + 3), 95);
                    } else if (data.status === 'pending') {
                        nextProgress = Math.min(nextProgress, 10);
                    } else if (data.status === 'completed') {
                        nextProgress = 100;
                    }

                    return {
                        ...prev,
                        [docId]: {
                            ...previous,
                            status: data.status,
                            progress: nextProgress,
                            error: data.error_message,
                        },
                    };
                });
                
                if (data.status === 'completed' || data.status === 'failed') {
                    eventSource.close();
                    if (data.status === 'completed') {
                        warmChatExperience(id);
                    } else {
                        setError(`Ingestion failed: ${data.error_message || 'Unknown error'}`);
                    }
                    loadTenders();
                }
            };
            
            eventSource.onerror = () => {
                setIngestionStatuses(prev => {
                    const previous = prev[docId];
                    return {
                        ...prev,
                        [docId]: {
                            status: 'failed',
                            progress: previous?.progress ?? 0,
                            error: 'EventSource error',
                            tenderId: previous?.tenderId ?? id,
                            documentId: docId,
                        },
                    };
                });
                eventSource.close();
            };
            
        } catch (err) {
            const message = err instanceof Error ? err.message : 'Failed to upload document';
            setError(message);
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

    const handleOpenFullChat = async (id: number) => {
        try {
            const session = await tenderApi.fullchat(id);
            if (session.auth_mode === 'sso') {
                // SSO mode: Keycloak handles auth via browser redirect — no cookie needed.
                // Mattermost will redirect to Keycloak, which already has an active session.
                window.open(session.mm_url, '_blank', 'noopener');
            } else {
                // Legacy mode: set the Mattermost browser session cookies before opening the channel.
                document.cookie = `MMAUTHTOKEN=${session.mm_token}; path=/mm; SameSite=Lax`;
                document.cookie = `MMUSERID=${session.mm_user_id}; path=/mm; SameSite=Lax`;
                window.open(session.mm_url, '_blank', 'noopener');
            }
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to open Full Chat');
        }
    };

    const handleActivateTender = async (id: number) => {
        try {
            setLoading(true);
            await tenderApi.activate(id);
            await loadTenders();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to activate tender');
        } finally {
            setLoading(false);
        }
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

    useEffect(() => {
        if (!hasActiveIngestions) {
            return;
        }

        const intervalId = window.setInterval(() => {
            void loadTenders();
        }, 5000);

        return () => window.clearInterval(intervalId);
    }, [hasActiveIngestions, loadTenders]);

    useEffect(() => {
        if (hadActiveIngestionRef.current && !hasActiveIngestions) {
            void loadTenders();
        }
        hadActiveIngestionRef.current = hasActiveIngestions;
    }, [hasActiveIngestions, loadTenders]);

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
                <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
                    <button
                        className="btn btn-secondary"
                        onClick={async () => {
                            try {
                                const token = localStorage.getItem('token');
                                const res = await fetch('/api/system/rebuild-bm25', {
                                    method: 'POST',
                                    headers: token ? { Authorization: `Bearer ${token}` } : {},
                                });
                                if (res.ok) {
                                    alert('BM25 rebuild successful!');
                                } else {
                                    const err = await res.json().catch(() => ({}));
                                    alert(`Failed to rebuild: ${err.detail || res.statusText}`);
                                }
                            } catch (e) {
                                alert(`Failed to rebuild: ${e}`);
                            }
                        }}
                    >
                        <Settings size={18} />
                        Rebuild BM25
                    </button>
                    <button
                        className="btn btn-primary"
                        onClick={() => {
                            if (showNewTender) {
                                closeNewTenderModal();
                                return;
                            }
                            openNewTenderModal();
                        }}
                    >
                        <Plus size={18} />
                        New Tender
                    </button>
                </div>
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
                                        <TenderCard key={tender.id} tender={tender} index={i} ingestionStatuses={ingestionStatuses} onActivate={handleActivateTender} onUpload={handleUpload} onCreateProposal={setShowNewProposal} onEditProposal={handleEditProposal} onSubmit={handleSubmitTender} onOpenChat={handleOpenChat} onWarmChat={handleWarmChat} onOpenFullChat={handleOpenFullChat} />
                                    ))
                                )}
                            </div>
                        );
                    })}
                </div>
            )}

            <DashboardModalStack
                uploadAlert={uploadAlert}
                onCloseUploadAlert={() => setUploadAlert(null)}
                showNewProposal={showNewProposal}
                onCloseProposal={() => {
                    setShowNewProposal(null);
                    setProposalTitle('');
                }}
                proposalTitle={proposalTitle}
                onProposalTitleChange={setProposalTitle}
                creatingProposal={creatingProposal}
                onCreateProposal={handleCreateProposal}
                showNewTender={showNewTender}
                onCloseNewTender={closeNewTenderModal}
                form={form}
                setForm={setForm}
                duplicateTitleError={duplicateTitleError}
                newTenderError={newTenderError}
                setNewTenderError={setNewTenderError}
                normalizedFormTitle={normalizedFormTitle}
                creating={creating}
                onCreate={handleCreate}
            />

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
