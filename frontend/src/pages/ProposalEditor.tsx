import { useState, useEffect, useCallback, useRef } from 'react';
import {
    Sparkles,
    Send,
    Check,
    Copy,
    FileText,
    Wand2,
    AlertCircle,
    Loader2,
    X,
    Maximize2,
    Plus,
    Trash2,
} from 'lucide-react';
import { useLocation, useNavigate } from 'react-router-dom';
import {
    proposalApi,
    ragApi,
    type Proposal,
    type ProposalDetail,
    type RAGResponse,
} from '../api/client';
import LazyOnlyOfficeEditor, { prefetchOnlyOfficeEditor } from '../components/LazyOnlyOfficeEditor';
import { ProposalWriterPanel } from '../components/ProposalWriterPanel';
import { ONLYOFFICE_URL } from '../config/runtime';

const DEFAULT_SECTIONS = [
    'Executive Summary',
    'Company Overview',
    'Technical Approach',
    'Team & Key Personnel',
    'Past Performance & References',
    'Project Timeline',
    'Pricing & Budget',
    'Compliance Matrix',
];

export default function ProposalEditor() {
    const location = useLocation();
    const navigatedProposalId = location.state?.proposalId as number | undefined;

    // Proposal list state
    const [proposals, setProposals] = useState<Proposal[]>([]);
    const [loadingList, setLoadingList] = useState(true);
    const [selectedProposalId, setSelectedProposalId] = useState<number | null>(navigatedProposalId || null);

    // Proposal detail state
    const [proposal, setProposal] = useState<ProposalDetail | null>(null);
    const [loadingDetail, setLoadingDetail] = useState(false);
    const [activeSection, setActiveSection] = useState(0);

    // Editor state
    const [saving, setSaving] = useState(false);
    const [saved, setSaved] = useState(false);
    const [isDirty, setIsDirty] = useState(false);

    // Modal state
    const [showAddSectionModal, setShowAddSectionModal] = useState(false);
    const [newSectionTitle, setNewSectionTitle] = useState('');

    // Section setup modal (first-time landing)
    const [showSectionSetup, setShowSectionSetup] = useState(false);
    const [setupSections, setSetupSections] = useState<string[]>([]);
    const [setupNewTitle, setSetupNewTitle] = useState('');
    const [creatingSections, setCreatingSections] = useState(false);

    // Unsaved changes modal
    const [showUnsavedModal, setShowUnsavedModal] = useState(false);
    const pendingNavigationRef = useRef<(() => void) | null>(null);
    const isDirtyRef = useRef(false);

    // AI state
    const [aiQuery, setAiQuery] = useState('');
    const [aiGenerating, setAiGenerating] = useState(false);
    const [aiResult, setAiResult] = useState<RAGResponse | null>(null);
    const [aiError, setAiError] = useState<string | null>(null);
    const [isFullEdit, setIsFullEdit] = useState(false);

    // General
    const [error, setError] = useState<string | null>(null);

    const navigate = useNavigate();

    // Keep ref in sync for event handlers
    useEffect(() => {
        isDirtyRef.current = isDirty;
    }, [isDirty]);

    // Browser tab close / refresh guard
    useEffect(() => {
        const handleBeforeUnload = (e: BeforeUnloadEvent) => {
            if (isDirtyRef.current) {
                e.preventDefault();
            }
        };
        window.addEventListener('beforeunload', handleBeforeUnload);
        return () => window.removeEventListener('beforeunload', handleBeforeUnload);
    }, []);

    // Intercept browser back/forward when dirty
    useEffect(() => {
        const handlePopState = () => {
            if (isDirtyRef.current) {
                // Push state back to prevent navigation
                window.history.pushState(null, '', window.location.href);
                pendingNavigationRef.current = () => navigate(-1);
                setShowUnsavedModal(true);
            }
        };
        // Push an extra history entry so we can intercept back
        window.history.pushState(null, '', window.location.href);
        window.addEventListener('popstate', handlePopState);
        return () => window.removeEventListener('popstate', handlePopState);
    }, [navigate]);

    // Guard for in-app navigation (sidebar clicks, etc.)
    const guardedNavigate = useCallback((action: () => void) => {
        if (isDirtyRef.current) {
            pendingNavigationRef.current = action;
            setShowUnsavedModal(true);
        } else {
            action();
        }
    }, []);

    const handleUnsavedSave = async () => {
        await handleSave();
        setShowUnsavedModal(false);
        setIsDirty(false);
        isDirtyRef.current = false;
        if (pendingNavigationRef.current) {
            pendingNavigationRef.current();
        }
        pendingNavigationRef.current = null;
    };

    const handleUnsavedDiscard = () => {
        setShowUnsavedModal(false);
        setIsDirty(false);
        isDirtyRef.current = false;
        if (pendingNavigationRef.current) {
            pendingNavigationRef.current();
        }
        pendingNavigationRef.current = null;
    };

    const handleUnsavedCancel = () => {
        setShowUnsavedModal(false);
        pendingNavigationRef.current = null;
    };

    // ── OnlyOffice dirty state callback ──
    const handleDocumentStateChange = useCallback((dirty: boolean) => {
        setIsDirty(dirty);
    }, []);

    // ── Add section handler (sidebar) ──
    const handleAddSection = async () => {
        if (!newSectionTitle || !proposal) return;
        try {
            const newSection = await proposalApi.addSection(proposal.id, {
                title: newSectionTitle,
                content: {},
                order: proposal.sections.length,
            });
            setProposal({ ...proposal, sections: [...proposal.sections, newSection] });
            setActiveSection(proposal.sections.length);
            setShowAddSectionModal(false);
            setNewSectionTitle('');
        } catch (err) {
            console.error('Failed to add section:', err);
        }
    };

    // ── Section setup modal handlers ──
    const handleAddSetupSection = () => {
        if (!setupNewTitle.trim()) return;
        setSetupSections([...setupSections, setupNewTitle.trim()]);
        setSetupNewTitle('');
    };

    const handleRemoveSetupSection = (idx: number) => {
        setSetupSections(setupSections.filter((_, i) => i !== idx));
    };

    const handleUseDefaults = () => {
        setSetupSections([...DEFAULT_SECTIONS]);
    };

    const handleCreateSections = async () => {
        if (!proposal || setupSections.length === 0) return;
        try {
            setCreatingSections(true);
            const created = await proposalApi.bulkCreateSections(proposal.id, setupSections);
            setProposal({ ...proposal, sections: created });
            setActiveSection(0);
            setShowSectionSetup(false);
            setSetupSections([]);
        } catch (err) {
            console.error('Failed to create sections:', err);
        } finally {
            setCreatingSections(false);
        }
    };

    // ── Load proposals list ──
    useEffect(() => {
        (async () => {
            try {
                setLoadingList(true);
                const data = await proposalApi.list({ limit: '50' });
                const activeProposals = data.items.filter(p => p.status !== 'submitted');
                setProposals(activeProposals);

                if (navigatedProposalId && activeProposals.some(p => p.id === navigatedProposalId)) {
                    setSelectedProposalId(navigatedProposalId);
                } else if (activeProposals.length > 0 && !selectedProposalId && !navigatedProposalId) {
                    setSelectedProposalId(activeProposals[0].id);
                }
            } catch (err) {
                setError(err instanceof Error ? err.message : 'Failed to load proposals');
            } finally {
                setLoadingList(false);
            }
        })();
    }, []);

    // ── Load proposal detail ──
    const loadProposal = useCallback(async (id: number) => {
        try {
            setLoadingDetail(true);
            setError(null);
            const data = await proposalApi.get(id);
            setProposal(data);
            setActiveSection(0);
            // If proposal has no sections, show setup modal
            if (data.sections.length === 0) {
                setSetupSections([]);
                setShowSectionSetup(true);
            }
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to load proposal');
        } finally {
            setLoadingDetail(false);
        }
    }, []);

    useEffect(() => {
        if (selectedProposalId) {
            loadProposal(selectedProposalId);
        }
    }, [selectedProposalId, loadProposal]);

    useEffect(() => {
        if (proposal && proposal.sections[activeSection]) {
            setSaved(false);
            setAiResult(null);
        }
    }, [activeSection, proposal]);

    useEffect(() => {
        if (!proposal?.sections?.[activeSection]) {
            return;
        }

        const timer = window.setTimeout(() => {
            void prefetchOnlyOfficeEditor();
        }, 120);

        return () => window.clearTimeout(timer);
    }, [activeSection, proposal]);


    const handleSave = async () => {
        if (!proposal || !proposal.sections[activeSection]) return;
        const section = proposal.sections[activeSection];
        try {
            setSaving(true);
            // Trigger force save via OnlyOffice
            const token = localStorage.getItem('token');
            await fetch(`/api/onlyoffice/forcesave/proposal/${proposal.id}/${section.id}`, {
                method: 'POST',
                headers: token ? { Authorization: `Bearer ${token}` } : {},
            });
            setSaved(true);
            setIsDirty(false);
            setTimeout(() => setSaved(false), 3000);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to save');
        } finally {
            setSaving(false);
        }
    };

    const handleAiAssist = async (action: string) => {
        if (!proposal || !proposal.sections[activeSection]) return;
        const section = proposal.sections[activeSection];

        setAiGenerating(true);
        setAiError(null);
        setAiResult(null);

        try {
            let result: RAGResponse;

            if (action === 'Write this section' || action === 'ai-write') {
                result = await ragApi.generateSection({
                    query: `Write the "${section.title}" section for the proposal "${proposal.title}"`,
                    section_title: section.title,
                    instructions: aiQuery || `Write a professional ${section.title} section`,
                });
            } else if (action === 'Check compliance') {
                const compResult = await ragApi.complianceCheck({
                    requirement: `Requirements for ${section.title}`,
                    section_content: section.title,
                });
                result = {
                    answer: JSON.stringify(compResult.assessment, null, 2),
                    sources: [],
                    mode: 'compliance',
                };
            } else if (action === 'Find relevant content') {
                result = await ragApi.query({
                    query: section.title,
                    mode: 'search',
                });
            } else if (action === 'Improve current text') {
                result = await ragApi.query({
                    query: `Improve the proposal text for "${section.title}"`,
                    mode: 'qa',
                });
            } else {
                result = await ragApi.query({
                    query: aiQuery || section.title,
                    mode: 'qa',
                });
            }

            setAiResult(result);
        } catch (err) {
            setAiError(err instanceof Error ? err.message : 'AI request failed');
        } finally {
            setAiGenerating(false);
        }
    };

    const insertAiContent = async () => {
        if (!aiResult?.answer || !proposal || !proposal.sections[activeSection]) return;
        try {
            const token = localStorage.getItem('token');
            const section = proposal.sections[activeSection];

            // Update section content in database
            await fetch(`/api/proposals/${proposal.id}/sections/${section.id}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
                body: JSON.stringify({ title: section.title, content: aiResult.answer, order: section.order })
            });

            // Update local state
            const updatedSections = [...proposal.sections];
            updatedSections[activeSection] = { ...section, content: aiResult.answer as any };
            setProposal({ ...proposal, sections: updatedSections });

            // Trigger OnlyOffice force save
            await fetch(`/api/onlyoffice/forcesave/proposal/${proposal.id}/${section.id}`, {
                method: 'POST',
                headers: token ? { Authorization: `Bearer ${token}` } : {},
            });

            setAiResult(null);
        } catch (err) {
            console.error('Failed to insert AI content:', err);
        }
    };

    // Loading state
    if (loadingList) {
        return (
            <div className="animate-in">
                <div className="loading-spinner" style={{ padding: '4rem 0' }}>
                    <div className="spinner" />
                    <p style={{ color: 'var(--text-muted)', marginTop: '0.75rem' }}>Loading proposals...</p>
                </div>
            </div>
        );
    }

    // No proposals
    if (proposals.length === 0) {
        return (
            <div className="animate-in">
                <div className="page-header">
                    <div>
                        <h1 className="page-title">Proposal Editor</h1>
                        <p className="page-subtitle">Create proposals for your tenders</p>
                    </div>
                </div>
                <div className="empty-state" style={{ padding: '4rem 0' }}>
                    <FileText size={48} />
                    <h3>No proposals yet</h3>
                    <p>Create a tender first, then create a proposal for it from the Dashboard</p>
                </div>
            </div>
        );
    }

    const currentSection = proposal?.sections?.[activeSection];

    return (
        <div className="animate-in">
            <div className="page-header">
                <div>
                    <h1 className="page-title">Proposal Editor</h1>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                        <select
                            className="form-select"
                            style={{ maxWidth: 400, fontSize: '0.85rem' }}
                            value={selectedProposalId || ''}
                            onChange={(e) => {
                                const newId = Number(e.target.value);
                                guardedNavigate(() => setSelectedProposalId(newId));
                            }}
                        >
                            {proposals.map((p) => (
                                <option key={p.id} value={p.id}>
                                    {p.title} (v{p.version})
                                </option>
                            ))}
                        </select>
                    </div>
                </div>
                <div style={{ display: 'flex', gap: '0.75rem' }}>
                    <button
                        className="btn btn-primary"
                        onClick={handleSave}
                        disabled={saving || !proposal || proposal.status === 'submitted'}
                    >
                        {saving ? <Loader2 size={16} className="spin" /> : saved ? <Check size={16} /> : <Check size={16} />}
                        {saving ? 'Saving...' : saved ? 'Saved!' : proposal?.status === 'submitted' ? 'Submitted' : 'Save'}
                    </button>
                </div>
            </div>

            {/* Error or Read-only Banner */}
            {error ? (
                <div className="card" style={{ borderColor: '#ef4444', marginBottom: '1.5rem', display: 'flex', alignItems: 'center', gap: '0.75rem', color: '#ef4444' }}>
                    <AlertCircle size={18} />
                    <span>{error}</span>
                    <button className="btn btn-ghost btn-sm" onClick={() => setError(null)} style={{ marginLeft: 'auto' }}>
                        <X size={14} />
                    </button>
                </div>
            ) : proposal?.status === 'submitted' ? (
                <div className="card" style={{ borderColor: 'var(--accent-purple)', marginBottom: '1.5rem', display: 'flex', alignItems: 'center', gap: '0.75rem', color: 'var(--accent-purple)', background: 'rgba(139, 92, 246, 0.05)' }}>
                    <Send size={18} />
                    <span>This proposal has been <strong>Submitted</strong> and is now in read-only mode.</span>
                </div>
            ) : null}

            {loadingDetail ? (
                <div className="loading-spinner" style={{ padding: '4rem 0' }}>
                    <div className="spinner" />
                    <p style={{ color: 'var(--text-muted)', marginTop: '0.75rem' }}>Loading proposal...</p>
                </div>
            ) : proposal ? (
                <div className="editor-layout">
                    {/* Sections Sidebar */}
                    <div className="editor-sidebar">
                        <h4 style={{ marginBottom: '0.75rem', color: 'var(--text-secondary)', fontSize: '0.8rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                            Sections ({proposal.sections.length})
                        </h4>
                        {proposal.sections.map((section, idx) => (
                            <div
                                key={section.id}
                                className={`section-list-item ${idx === activeSection ? 'active' : ''}`}
                                onClick={() => guardedNavigate(() => setActiveSection(idx))}
                            >
                                <span className={`section-status-dot ${section.status.replace('_', '-')}`} />
                                <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                    {section.title}
                                </span>
                            </div>
                        ))}

                        <button
                            onClick={() => setShowAddSectionModal(true)}
                            style={{
                                width: '100%',
                                marginTop: '0.5rem',
                                padding: '0.5rem',
                                background: 'var(--accent-blue)',
                                color: 'white',
                                border: 'none',
                                borderRadius: 'var(--radius-sm)',
                                cursor: 'pointer',
                                fontSize: '0.8rem'
                            }}
                        >
                            + Add Section
                        </button>

                        {/* Add Section Modal */}
                        {showAddSectionModal && (
                            <div style={{
                                position: 'fixed',
                                inset: 0,
                                background: 'rgba(0,0,0,0.5)',
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                zIndex: 50
                            }}>
                                <div style={{
                                    background: 'var(--bg-card)',
                                    border: '1px solid var(--border-default)',
                                    borderRadius: 'var(--radius-lg)',
                                    padding: '1.5rem',
                                    width: '100%',
                                    maxWidth: '400px'
                                }}>
                                    <h3 style={{ color: 'var(--text-primary)', marginBottom: '1rem', fontSize: '1.1rem', fontWeight: 600 }}>
                                        New Section
                                    </h3>
                                    <input
                                        type="text"
                                        placeholder="Section title"
                                        value={newSectionTitle}
                                        onChange={e => setNewSectionTitle(e.target.value)}
                                        onKeyDown={e => e.key === 'Enter' && newSectionTitle && handleAddSection()}
                                        style={{
                                            width: '100%',
                                            padding: '0.75rem',
                                            background: 'var(--bg-input)',
                                            border: '1px solid var(--border-default)',
                                            borderRadius: 'var(--radius-sm)',
                                            color: 'var(--text-primary)',
                                            fontSize: '0.9rem',
                                            marginBottom: '1rem'
                                        }}
                                        autoFocus
                                    />
                                    <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
                                        <button
                                            onClick={() => { setShowAddSectionModal(false); setNewSectionTitle(''); }}
                                            style={{
                                                padding: '0.5rem 1rem',
                                                background: 'var(--bg-input)',
                                                border: '1px solid var(--border-default)',
                                                borderRadius: 'var(--radius-sm)',
                                                color: 'var(--text-secondary)',
                                                cursor: 'pointer'
                                            }}
                                        >
                                            Cancel
                                        </button>
                                        <button
                                            onClick={handleAddSection}
                                            disabled={!newSectionTitle}
                                            style={{
                                                padding: '0.5rem 1rem',
                                                background: newSectionTitle ? 'var(--accent-blue)' : 'var(--bg-input)',
                                                border: 'none',
                                                borderRadius: 'var(--radius-sm)',
                                                color: 'white',
                                                cursor: newSectionTitle ? 'pointer' : 'not-allowed',
                                                opacity: newSectionTitle ? 1 : 0.5
                                            }}
                                        >
                                            Add
                                        </button>
                                    </div>
                                </div>
                            </div>
                        )}

                        {/* Compliance Summary */}
                        <div style={{ marginTop: '1.5rem', padding: '0.75rem', background: 'var(--bg-glass)', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-default)' }}>
                            <h4 style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginBottom: '0.5rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                                Progress
                            </h4>
                            {['todo', 'in_progress', 'in_review', 'approved'].map((status) => {
                                const count = proposal.sections.filter((s) => s.status === status).length;
                                const label = status.replace('_', ' ');
                                const color =
                                    status === 'approved' ? 'var(--accent-green)' :
                                        status === 'in_review' ? 'var(--accent-purple)' :
                                            status === 'in_progress' ? 'var(--accent-amber)' :
                                                'var(--text-muted)';
                                return count > 0 ? (
                                    <div key={status} style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', marginBottom: '0.25rem' }}>
                                        <span style={{ color, textTransform: 'capitalize' }}>{label}</span>
                                        <span>{count}/{proposal.sections.length}</span>
                                    </div>
                                ) : null;
                            })}
                            <div style={{ marginTop: '0.5rem', height: 4, borderRadius: 2, background: 'var(--bg-input)', overflow: 'hidden' }}>
                                <div style={{
                                    height: '100%',
                                    width: `${(proposal.sections.filter(s => s.status === 'approved' || s.status === 'in_review').length / Math.max(proposal.sections.length, 1)) * 100}%`,
                                    background: 'linear-gradient(90deg, var(--accent-green), var(--accent-amber))',
                                    borderRadius: 2,
                                }} />
                            </div>
                        </div>
                    </div>

                    {/* Main Editor */}
                    <div className="editor-main">
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
                            <div>
                                <h2 style={{ margin: 0 }}>
                                    {currentSection?.title || 'Select a section'}
                                </h2>
                                <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', margin: 0 }}>
                                    Section {activeSection + 1} of {proposal.sections.length}
                                    {currentSection && <> — Status: <strong>{currentSection.status.replace('_', ' ')}</strong></>}
                                </p>
                            </div>
                            <button
                                className="btn btn-secondary btn-sm"
                                onClick={() => setIsFullEdit(true)}
                                onMouseEnter={() => void prefetchOnlyOfficeEditor()}
                                onFocus={() => void prefetchOnlyOfficeEditor()}
                                onTouchStart={() => void prefetchOnlyOfficeEditor()}
                                style={{ gap: '0.4rem' }}
                            >
                                <Maximize2 size={14} />
                                Full Edit
                            </button>
                        </div>

                        {/* OnlyOffice Editor Area */}
                        {currentSection && (
                            <div style={{ flex: 1, minHeight: 0 }}>
                                <LazyOnlyOfficeEditor
                                    key={`${proposal.id}-${currentSection.id}`}
                                    proposalId={proposal.id}
                                    sectionId={currentSection.id}
                                    title={currentSection.title}
                                    onlyofficeApiUrl={ONLYOFFICE_URL}
                                    minHeight="520px"
                                    onDocumentStateChange={handleDocumentStateChange}
                                />
                            </div>
                        )}

                        {/* Empty state when no sections exist */}
                        {proposal.sections.length === 0 && (
                            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '4rem 0', color: 'var(--text-muted)' }}>
                                <FileText size={48} />
                                <h3 style={{ marginTop: '1rem' }}>No sections yet</h3>
                                <p>Set up the sections for this proposal to get started.</p>
                                <button
                                    className="btn btn-primary"
                                    style={{ marginTop: '1rem' }}
                                    onClick={() => { setSetupSections([]); setShowSectionSetup(true); }}
                                >
                                    Set Up Sections
                                </button>
                            </div>
                        )}
                    </div>

                    {/* AI Assist Panel */}
                    <div className="editor-assist">
                        <div className="ai-panel-header">
                            <Sparkles size={18} color="#60a5fa" />
                            <h4 style={{ flex: 1 }}>AI Assistant</h4>
                            <span className="ai-badge">RAG</span>
                        </div>

                        {/* AI Input */}
                        <div style={{ position: 'relative', marginBottom: '1rem' }}>
                            <textarea
                                className="form-textarea"
                                placeholder="Ask AI to help write this section..."
                                value={aiQuery}
                                onChange={(e) => setAiQuery(e.target.value)}
                                onKeyDown={(e) => {
                                    if (e.key === 'Enter' && !e.shiftKey) {
                                        e.preventDefault();
                                        handleAiAssist('custom');
                                    }
                                }}
                                style={{ minHeight: 80, fontSize: '0.85rem', paddingRight: '2.5rem' }}
                            />
                            <button
                                className="btn btn-icon"
                                style={{
                                    position: 'absolute',
                                    right: 8,
                                    bottom: 8,
                                    background: 'linear-gradient(135deg, var(--accent-blue), var(--accent-purple))',
                                    color: 'white',
                                    border: 'none',
                                    borderRadius: 'var(--radius-sm)',
                                }}
                                onClick={() => handleAiAssist('custom')}
                                disabled={aiGenerating}
                            >
                                {aiGenerating ? <Loader2 size={14} className="spin" /> : <Send size={14} />}
                            </button>
                        </div>

                        {/* Quick Actions */}
                        <div style={{ marginBottom: '1rem' }}>
                            <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '0.5rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                                Quick Actions
                            </p>
                            {[
                                'Write this section',
                                'Improve current text',
                                'Check compliance',
                                'Find relevant content',
                            ].map((action) => (
                                <button
                                    key={action}
                                    className="btn btn-ghost btn-sm"
                                    style={{ width: '100%', justifyContent: 'flex-start', marginBottom: '2px', fontSize: '0.82rem' }}
                                    onClick={() => handleAiAssist(action)}
                                    disabled={aiGenerating}
                                >
                                    <Wand2 size={13} /> {action}
                                </button>
                            ))}
                        </div>

                        {/* ProposalWriterAgent — preview/apply with rehearsal awareness */}
                        {proposal && proposal.sections[activeSection] && (
                            <ProposalWriterPanel
                                tenderId={proposal.tender_id}
                                proposalId={proposal.id}
                                sectionId={proposal.sections[activeSection].id}
                                sectionTitle={proposal.sections[activeSection].title}
                                onApplied={(result) => {
                                    if (!proposal) return;
                                    const updated = [...proposal.sections];
                                    updated[activeSection] = {
                                        ...updated[activeSection],
                                        content: { type: 'doc', content: [
                                            { type: 'paragraph', content: [{ type: 'text', text: result.draft_text }] },
                                        ] },
                                    };
                                    setProposal({ ...proposal, sections: updated });
                                }}
                            />
                        )}

                        {/* AI Error */}
                        {aiError && (
                            <div style={{ padding: '0.75rem', borderRadius: 'var(--radius-sm)', background: 'rgba(239, 68, 68, 0.1)', color: '#ef4444', fontSize: '0.8rem', marginBottom: '1rem' }}>
                                {aiError}
                            </div>
                        )}

                        {/* AI Loading */}
                        {aiGenerating && (
                            <div style={{ textAlign: 'center', padding: '1.5rem 0' }}>
                                <div className="spinner" style={{ margin: '0 auto 0.5rem' }} />
                                <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Generating with RAG...</p>
                            </div>
                        )}

                        {/* AI Result */}
                        {aiResult && (
                            <div>
                                <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '0.5rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                                    AI Generated Content
                                </p>
                                <div className="ai-suggestion">
                                    <p style={{ fontSize: '0.85rem', lineHeight: 1.6, whiteSpace: 'pre-wrap' }}>
                                        {aiResult.answer.slice(0, 500)}{aiResult.answer.length > 500 ? '...' : ''}
                                    </p>
                                    <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.5rem' }}>
                                        <button className="btn btn-ghost btn-sm" onClick={insertAiContent}>
                                            <Copy size={12} /> Insert into editor
                                        </button>
                                    </div>
                                </div>

                                {/* Sources */}
                                {aiResult.sources.length > 0 && (
                                    <div style={{ marginTop: '0.75rem' }}>
                                        <p style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginBottom: '0.35rem' }}>
                                            Sources ({aiResult.sources.length})
                                        </p>
                                        {aiResult.sources.slice(0, 3).map((s, i) => (
                                            <div key={i} className="ai-suggestion" style={{ padding: '0.5rem', marginBottom: '0.35rem' }}>
                                                <p style={{ fontSize: '0.75rem', lineHeight: 1.5 }}>
                                                    {s.text.slice(0, 150)}...
                                                </p>
                                            </div>
                                        ))}
                                    </div>
                                )}
                            </div>
                        )}
                    </div>
                </div>
            ) : null}

            {/* Full Screen Editor Modal */}
            {proposal && currentSection && isFullEdit && (
                <div
                    className="modal-backdrop"
                    style={{ zIndex: 1000, padding: '1rem' }}
                >
                    <div
                        className="modal"
                        style={{ width: '100%', height: '95vh', display: 'flex', flexDirection: 'column' }}
                    >
                        <div className="modal-header" style={{ padding: '1rem 1.5rem', borderBottom: '1px solid var(--border-default)' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                                <Sparkles size={20} color="var(--accent-blue)" />
                                <h2 style={{ margin: 0 }}>Full Edit: {currentSection.title}</h2>
                            </div>
                            <div style={{ display: 'flex', gap: '0.75rem' }}>
                                <button className="btn btn-primary btn-sm" onClick={handleSave} disabled={saving}>
                                    {saving ? <Loader2 size={16} className="spin" /> : <Check size={16} />}
                                    {saving ? 'Saving...' : 'Save'}
                                </button>
                                <button
                                    className="btn btn-secondary btn-sm"
                                    onClick={() => setIsFullEdit(false)}
                                >
                                    Exit Full Screen
                                </button>
                            </div>
                        </div>
                        <div className="modal-body" style={{ flex: 1, padding: 0, overflow: 'hidden' }}>
                            <LazyOnlyOfficeEditor
                                proposalId={proposal.id}
                                sectionId={currentSection.id}
                                title={currentSection.title}
                                onlyofficeApiUrl={ONLYOFFICE_URL}
                                minHeight="720px"
                                onDocumentStateChange={handleDocumentStateChange}
                            />
                        </div>
                    </div>
                </div>
            )}

            {/* ── Section Setup Modal (first-time landing) ── */}
            {showSectionSetup && (
                <div style={{
                    position: 'fixed',
                    inset: 0,
                    background: 'rgba(0,0,0,0.75)',
                    backdropFilter: 'blur(4px)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    zIndex: 1100
                }}>
                    <div style={{
                        background: 'var(--bg-card)',
                        border: '1px solid var(--border-default)',
                        borderRadius: 'var(--radius-lg)',
                        padding: '2rem',
                        width: '100%',
                        maxWidth: '540px',
                        maxHeight: '80vh',
                        display: 'flex',
                        flexDirection: 'column',
                    }}>
                        <h2 style={{ color: 'var(--text-primary)', marginBottom: '0.25rem', fontSize: '1.25rem', fontWeight: 600 }}>
                            Set Up Proposal Sections
                        </h2>
                        <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem', marginBottom: '1.25rem' }}>
                            List the sections you want to create for this proposal, or use the default template.
                        </p>

                        {/* Section list */}
                        <div style={{ flex: 1, overflowY: 'auto', marginBottom: '1rem', minHeight: 0 }}>
                            {setupSections.length === 0 ? (
                                <div style={{
                                    padding: '2rem',
                                    textAlign: 'center',
                                    color: 'var(--text-muted)',
                                    fontSize: '0.85rem',
                                    border: '1px dashed var(--border-default)',
                                    borderRadius: 'var(--radius-md)',
                                }}>
                                    No sections added yet. Add sections manually or use the defaults.
                                </div>
                            ) : (
                                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
                                    {setupSections.map((title, idx) => (
                                        <div key={idx} style={{
                                            display: 'flex',
                                            alignItems: 'center',
                                            gap: '0.75rem',
                                            padding: '0.5rem 0.75rem',
                                            background: 'var(--bg-glass)',
                                            borderRadius: 'var(--radius-sm)',
                                            border: '1px solid var(--border-default)',
                                        }}>
                                            <span style={{
                                                width: 22,
                                                height: 22,
                                                borderRadius: '50%',
                                                background: 'var(--accent-blue)',
                                                color: 'white',
                                                display: 'flex',
                                                alignItems: 'center',
                                                justifyContent: 'center',
                                                fontSize: '0.7rem',
                                                fontWeight: 600,
                                                flexShrink: 0,
                                            }}>
                                                {idx + 1}
                                            </span>
                                            <span style={{ flex: 1, fontSize: '0.9rem', color: 'var(--text-primary)' }}>
                                                {title}
                                            </span>
                                            <button
                                                onClick={() => handleRemoveSetupSection(idx)}
                                                style={{
                                                    background: 'none',
                                                    border: 'none',
                                                    color: 'var(--text-muted)',
                                                    cursor: 'pointer',
                                                    padding: '0.25rem',
                                                    display: 'flex',
                                                    alignItems: 'center',
                                                }}
                                                title="Remove section"
                                            >
                                                <Trash2 size={14} />
                                            </button>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>

                        {/* Add section input */}
                        <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem' }}>
                            <input
                                type="text"
                                placeholder="Enter section title..."
                                value={setupNewTitle}
                                onChange={e => setSetupNewTitle(e.target.value)}
                                onKeyDown={e => e.key === 'Enter' && setupNewTitle.trim() && handleAddSetupSection()}
                                style={{
                                    flex: 1,
                                    padding: '0.6rem 0.75rem',
                                    background: 'var(--bg-input)',
                                    border: '1px solid var(--border-default)',
                                    borderRadius: 'var(--radius-sm)',
                                    color: 'var(--text-primary)',
                                    fontSize: '0.85rem',
                                }}
                                autoFocus
                            />
                            <button
                                onClick={handleAddSetupSection}
                                disabled={!setupNewTitle.trim()}
                                style={{
                                    padding: '0.6rem 0.75rem',
                                    background: setupNewTitle.trim() ? 'var(--accent-blue)' : 'var(--bg-input)',
                                    border: 'none',
                                    borderRadius: 'var(--radius-sm)',
                                    color: 'white',
                                    cursor: setupNewTitle.trim() ? 'pointer' : 'not-allowed',
                                    opacity: setupNewTitle.trim() ? 1 : 0.5,
                                    display: 'flex',
                                    alignItems: 'center',
                                    gap: '0.35rem',
                                    fontSize: '0.85rem',
                                }}
                            >
                                <Plus size={14} />
                                Add Section
                            </button>
                        </div>

                        {/* Action buttons */}
                        <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'space-between' }}>
                            <button
                                onClick={handleUseDefaults}
                                style={{
                                    padding: '0.6rem 1rem',
                                    background: 'var(--bg-input)',
                                    border: '1px solid var(--border-default)',
                                    borderRadius: 'var(--radius-sm)',
                                    color: 'var(--text-secondary)',
                                    cursor: 'pointer',
                                    fontSize: '0.85rem',
                                }}
                            >
                                Use Default Sections
                            </button>
                            <button
                                onClick={handleCreateSections}
                                disabled={setupSections.length === 0 || creatingSections}
                                style={{
                                    padding: '0.6rem 1.25rem',
                                    background: setupSections.length > 0 ? 'var(--accent-blue)' : 'var(--bg-input)',
                                    border: 'none',
                                    borderRadius: 'var(--radius-sm)',
                                    color: 'white',
                                    cursor: setupSections.length > 0 && !creatingSections ? 'pointer' : 'not-allowed',
                                    opacity: setupSections.length > 0 ? 1 : 0.5,
                                    fontSize: '0.85rem',
                                    display: 'flex',
                                    alignItems: 'center',
                                    gap: '0.5rem',
                                }}
                            >
                                {creatingSections ? <Loader2 size={14} className="spin" /> : <Check size={14} />}
                                Create Sections
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* ── Unsaved Changes Modal ── */}
            {showUnsavedModal && (
                <div style={{
                    position: 'fixed',
                    inset: 0,
                    background: 'rgba(0,0,0,0.6)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    zIndex: 1200
                }}>
                    <div style={{
                        background: 'var(--bg-card)',
                        border: '1px solid var(--border-default)',
                        borderRadius: 'var(--radius-lg)',
                        padding: '1.5rem',
                        width: '100%',
                        maxWidth: '420px',
                    }}>
                        <h3 style={{ color: 'var(--text-primary)', marginBottom: '0.5rem', fontSize: '1.1rem', fontWeight: 600 }}>
                            Unsaved Changes
                        </h3>
                        <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem', marginBottom: '1.25rem' }}>
                            You have unsaved changes in the current section. What would you like to do?
                        </p>
                        <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
                            <button
                                onClick={handleUnsavedCancel}
                                style={{
                                    padding: '0.5rem 1rem',
                                    background: 'var(--bg-input)',
                                    border: '1px solid var(--border-default)',
                                    borderRadius: 'var(--radius-sm)',
                                    color: 'var(--text-secondary)',
                                    cursor: 'pointer',
                                    fontSize: '0.85rem',
                                }}
                            >
                                Cancel
                            </button>
                            <button
                                onClick={handleUnsavedDiscard}
                                style={{
                                    padding: '0.5rem 1rem',
                                    background: 'rgba(239, 68, 68, 0.1)',
                                    border: '1px solid rgba(239, 68, 68, 0.3)',
                                    borderRadius: 'var(--radius-sm)',
                                    color: '#ef4444',
                                    cursor: 'pointer',
                                    fontSize: '0.85rem',
                                }}
                            >
                                Discard
                            </button>
                            <button
                                onClick={handleUnsavedSave}
                                disabled={saving}
                                style={{
                                    padding: '0.5rem 1rem',
                                    background: 'var(--accent-blue)',
                                    border: 'none',
                                    borderRadius: 'var(--radius-sm)',
                                    color: 'white',
                                    cursor: 'pointer',
                                    fontSize: '0.85rem',
                                    display: 'flex',
                                    alignItems: 'center',
                                    gap: '0.35rem',
                                }}
                            >
                                {saving ? <Loader2 size={14} className="spin" /> : <Check size={14} />}
                                Save
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
