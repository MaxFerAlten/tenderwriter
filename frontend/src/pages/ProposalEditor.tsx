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
} from 'lucide-react';
import {
    proposalApi,
    ragApi,
    type Proposal,
    type ProposalDetail,
    type Section,
    type RAGResponse,
} from '../api/client';

function EditorToolbar({ onAiWrite, generating }: { onAiWrite: () => void; generating: boolean }) {
    const tools = [
        { label: 'B', title: 'Bold', style: { fontWeight: 700 } as React.CSSProperties },
        { label: 'I', title: 'Italic', style: { fontStyle: 'italic' } as React.CSSProperties },
        { label: 'H1', title: 'Heading 1', style: { fontWeight: 700, fontSize: '0.7rem' } as React.CSSProperties },
        { label: 'H2', title: 'Heading 2', style: { fontWeight: 600, fontSize: '0.7rem' } as React.CSSProperties },
        { label: '•', title: 'Bullet List', style: { fontSize: '1.1rem' } as React.CSSProperties },
        { label: '1.', title: 'Numbered List', style: { fontSize: '0.8rem' } as React.CSSProperties },
        { label: '"', title: 'Blockquote', style: { fontSize: '1rem' } as React.CSSProperties },
    ];

    return (
        <div style={{
            display: 'flex',
            gap: '2px',
            padding: '0.5rem 0',
            borderBottom: '1px solid var(--border-default)',
            marginBottom: '1rem',
        }}>
            {tools.map((tool) => (
                <button
                    key={tool.title}
                    className="btn btn-ghost btn-sm btn-icon"
                    title={tool.title}
                    style={{ ...tool.style, minWidth: 32, minHeight: 32 }}
                >
                    {tool.label}
                </button>
            ))}
            <div style={{ flex: 1 }} />
            <button
                className="btn btn-sm"
                style={{
                    background: 'linear-gradient(135deg, var(--accent-blue), var(--accent-purple))',
                    color: 'white',
                    border: 'none',
                    gap: '0.35rem',
                }}
                onClick={onAiWrite}
                disabled={generating}
            >
                {generating ? <Loader2 size={14} className="spin" /> : <Wand2 size={14} />}
                {generating ? 'Writing...' : 'AI Write'}
            </button>
        </div>
    );
}

export default function ProposalEditor() {
    // Proposal list state
    const [proposals, setProposals] = useState<Proposal[]>([]);
    const [loadingList, setLoadingList] = useState(true);
    const [selectedProposalId, setSelectedProposalId] = useState<number | null>(null);

    // Proposal detail state
    const [proposal, setProposal] = useState<ProposalDetail | null>(null);
    const [loadingDetail, setLoadingDetail] = useState(false);
    const [activeSection, setActiveSection] = useState(0);

    // Editor state
    const [editorContent, setEditorContent] = useState('');
    const [saving, setSaving] = useState(false);
    const [saved, setSaved] = useState(false);

    // AI state
    const [aiQuery, setAiQuery] = useState('');
    const [aiGenerating, setAiGenerating] = useState(false);
    const [aiResult, setAiResult] = useState<RAGResponse | null>(null);
    const [aiError, setAiError] = useState<string | null>(null);

    // General
    const [error, setError] = useState<string | null>(null);

    // Load proposals list
    useEffect(() => {
        (async () => {
            try {
                setLoadingList(true);
                const data = await proposalApi.list({ limit: '50' });
                setProposals(data.items);
                if (data.items.length > 0 && !selectedProposalId) {
                    setSelectedProposalId(data.items[0].id);
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
            // Load first section content
            if (data.sections.length > 0) {
                setEditorContent(sectionToText(data.sections[0]));
            } else {
                setEditorContent('');
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

    // When section changes, load its content
    useEffect(() => {
        if (proposal && proposal.sections[activeSection]) {
            setEditorContent(sectionToText(proposal.sections[activeSection]));
            setSaved(false);
            setAiResult(null);
        }
    }, [activeSection, proposal]);

    const sectionToText = (section: Section): string => {
        // Content is stored as TipTap JSON, but we render plain text for now
        const content = section.content;
        if (!content || Object.keys(content).length === 0) return '';
        // Try to extract text from TipTap JSON structure
        if (content.type === 'doc' && Array.isArray(content.content)) {
            return (content.content as Array<{ content?: Array<{ text?: string }> }>)
                .map((node) =>
                    (node.content || []).map((c) => c.text || '').join('')
                )
                .join('\n\n');
        }
        // Fallback: if it's a simple text field
        if (typeof content.text === 'string') return content.text;
        return JSON.stringify(content);
    };

    const textToContent = (text: string): Record<string, unknown> => {
        // Store as simple TipTap-compatible JSON
        return {
            type: 'doc',
            content: text.split('\n\n').filter(Boolean).map((paragraph) => ({
                type: 'paragraph',
                content: [{ type: 'text', text: paragraph }],
            })),
        };
    };

    const handleSave = async () => {
        if (!proposal || !proposal.sections[activeSection]) return;
        const section = proposal.sections[activeSection];
        try {
            setSaving(true);
            await proposalApi.updateSection(proposal.id, section.id, {
                content: textToContent(editorContent),
            });
            setSaved(true);
            setTimeout(() => setSaved(false), 3000);
            // Refresh
            await loadProposal(proposal.id);
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
                    section_content: editorContent,
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
                    query: `Improve the following proposal text for "${section.title}": ${editorContent.slice(0, 500)}`,
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

    const insertAiContent = () => {
        if (aiResult?.answer) {
            setEditorContent((prev) => (prev ? prev + '\n\n' + aiResult.answer : aiResult.answer));
            setAiResult(null);
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
                    <button className="btn btn-primary" onClick={handleSave} disabled={saving || !proposal}>
                        {saving ? <Loader2 size={16} className="spin" /> : saved ? <Check size={16} /> : <Check size={16} />}
                        {saving ? 'Saving...' : saved ? 'Saved!' : 'Save'}
                    </button>
                </div>
            </div>

            {/* Error */}
            {error && (
                <div className="card" style={{ borderColor: '#ef4444', marginBottom: '1.5rem', display: 'flex', alignItems: 'center', gap: '0.75rem', color: '#ef4444' }}>
                    <AlertCircle size={18} />
                    <span>{error}</span>
                    <button className="btn btn-ghost btn-sm" onClick={() => setError(null)} style={{ marginLeft: 'auto' }}>
                        <X size={14} />
                    </button>
                </div>
            )}

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
                        <h2 style={{ marginBottom: '0.25rem' }}>
                            {currentSection?.title || 'Select a section'}
                        </h2>
                        <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '1rem' }}>
                            Section {activeSection + 1} of {proposal.sections.length}
                            {currentSection && <> — Status: <strong>{currentSection.status.replace('_', ' ')}</strong></>}
                        </p>

                        <EditorToolbar
                            onAiWrite={() => handleAiAssist('ai-write')}
                            generating={aiGenerating}
                        />

                        {/* Editor Area */}
                        <textarea
                            style={{
                                minHeight: 400,
                                width: '100%',
                                outline: 'none',
                                fontSize: '1rem',
                                lineHeight: 1.75,
                                color: 'var(--text-primary)',
                                background: 'transparent',
                                border: 'none',
                                resize: 'vertical',
                                fontFamily: 'inherit',
                            }}
                            value={editorContent}
                            onChange={(e) => {
                                setEditorContent(e.target.value);
                                setSaved(false);
                            }}
                            placeholder="Start writing your proposal section here, or use AI Write to generate content..."
                        />
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
        </div>
    );
}
