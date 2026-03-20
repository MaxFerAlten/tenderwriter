import { useState, useEffect, useCallback } from 'react';
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
} from 'lucide-react';
import { useLocation } from 'react-router-dom';
import {
    proposalApi,
    ragApi,
    type Proposal,
    type ProposalDetail,
    type RAGResponse,
} from '../api/client';
import LazyOnlyOfficeEditor, { prefetchOnlyOfficeEditor } from '../components/LazyOnlyOfficeEditor';
import { ONLYOFFICE_URL } from '../config/runtime';

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

    // Modal state
    const [showAddSectionModal, setShowAddSectionModal] = useState(false);
    const [newSectionTitle, setNewSectionTitle] = useState('');

    // AI state
    const [aiQuery, setAiQuery] = useState('');
    const [aiGenerating, setAiGenerating] = useState(false);
    const [aiResult, setAiResult] = useState<RAGResponse | null>(null);
    const [aiError, setAiError] = useState<string | null>(null);
    const [isFullEdit, setIsFullEdit] = useState(false);

    // General
    const [error, setError] = useState<string | null>(null);

    // Add section handler
    const handleAddSection = async () => {
        if (!newSectionTitle || !proposal) return;
        try {
            const token = localStorage.getItem('token');
            const res = await fetch(`/api/proposals/${proposal.id}/sections`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
                body: JSON.stringify({ title: newSectionTitle, content: {}, order: proposal.sections.length })
            });
            if (res.ok) {
                const newSection = await res.json();
                setProposal({ ...proposal, sections: [...proposal.sections, newSection] });
                setActiveSection(proposal.sections.length);
                setShowAddSectionModal(false);
                setNewSectionTitle('');
            }
        } catch (err) {
            console.error('Failed to add section:', err);
        }
    };

    // Load proposals list
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

    // Load proposal detail
    const loadProposal = useCallback(async (id: number) => {
        try {
            setLoadingDetail(true);
            setError(null);
            const data = await proposalApi.get(id);
            setProposal(data);
            setActiveSection(0);
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
                            onChange={(e) => setSelectedProposalId(Number(e.target.value))}
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
                                onClick={() => setActiveSection(idx)}
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
                            + Aggiungi Sezione
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
                                        Nuova Sezione
                                    </h3>
                                    <input
                                        type="text"
                                        placeholder="Titolo della sezione"
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
                                            Annulla
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
                                            Aggiungi
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
                                />
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
                            />
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
