import { useState } from 'react';
import {
    Sparkles,
    Send,
    Check,
    Copy,
    FileText,
    Wand2,
} from 'lucide-react';

// ── Demo sections ──
const DEMO_SECTIONS = [
    { id: 1, title: 'Executive Summary', status: 'approved', content: 'Our team brings over 20 years of combined experience...' },
    { id: 2, title: 'Company Overview', status: 'in-progress', content: '' },
    { id: 3, title: 'Technical Approach', status: 'todo', content: '' },
    { id: 4, title: 'Team & Key Personnel', status: 'todo', content: '' },
    { id: 5, title: 'Past Performance & References', status: 'todo', content: '' },
    { id: 6, title: 'Project Timeline', status: 'todo', content: '' },
    { id: 7, title: 'Pricing & Budget', status: 'todo', content: '' },
    { id: 8, title: 'Compliance Matrix', status: 'in-review', content: '' },
];

function EditorToolbar() {
    const tools = [
        { label: 'B', title: 'Bold', style: { fontWeight: 700 } },
        { label: 'I', title: 'Italic', style: { fontStyle: 'italic' } },
        { label: 'H1', title: 'Heading 1', style: { fontWeight: 700, fontSize: '0.7rem' } },
        { label: 'H2', title: 'Heading 2', style: { fontWeight: 600, fontSize: '0.7rem' } },
        { label: '•', title: 'Bullet List', style: { fontSize: '1.1rem' } },
        { label: '1.', title: 'Numbered List', style: { fontSize: '0.8rem' } },
        { label: '"', title: 'Blockquote', style: { fontSize: '1rem' } },
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
            <button className="btn btn-sm" style={{
                background: 'linear-gradient(135deg, var(--accent-blue), var(--accent-purple))',
                color: 'white',
                border: 'none',
                gap: '0.35rem',
            }}>
                <Wand2 size={14} />
                AI Write
            </button>
        </div>
    );
}

export default function ProposalEditor() {
    const [activeSection, setActiveSection] = useState(0);
    const [aiQuery, setAiQuery] = useState('');
    const [editorContent] = useState(
        'Our team brings over 20 years of combined experience in bridge rehabilitation and structural engineering projects. We have successfully delivered 15+ similar projects for state and federal transportation agencies across the region.\n\nOur approach emphasizes minimal traffic disruption, innovative materials, and rigorous quality control to ensure long-term structural integrity.'
    );

    return (
        <div className="animate-in">
            <div className="page-header">
                <div>
                    <h1 className="page-title">Proposal Editor</h1>
                    <p className="page-subtitle">
                        Highway Bridge Rehabilitation — Route 42
                    </p>
                </div>
                <div style={{ display: 'flex', gap: '0.75rem' }}>
                    <button className="btn btn-secondary">
                        <FileText size={16} /> Export PDF
                    </button>
                    <button className="btn btn-primary">
                        <Check size={16} /> Save
                    </button>
                </div>
            </div>

            <div className="editor-layout">
                {/* Sections Sidebar */}
                <div className="editor-sidebar">
                    <h4 style={{ marginBottom: '0.75rem', color: 'var(--text-secondary)', fontSize: '0.8rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                        Sections
                    </h4>
                    {DEMO_SECTIONS.map((section, idx) => (
                        <div
                            key={section.id}
                            className={`section-list-item ${idx === activeSection ? 'active' : ''}`}
                            onClick={() => setActiveSection(idx)}
                        >
                            <span className={`section-status-dot ${section.status}`} />
                            <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                {section.title}
                            </span>
                        </div>
                    ))}

                    <button className="btn btn-ghost btn-sm" style={{ marginTop: '0.75rem', width: '100%', justifyContent: 'flex-start' }}>
                        + Add Section
                    </button>

                    {/* Compliance Summary */}
                    <div style={{ marginTop: '1.5rem', padding: '0.75rem', background: 'var(--bg-glass)', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-default)' }}>
                        <h4 style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginBottom: '0.5rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                            Compliance
                        </h4>
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', marginBottom: '0.25rem' }}>
                            <span style={{ color: 'var(--accent-green)' }}>Addressed</span>
                            <span>3/8</span>
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', marginBottom: '0.25rem' }}>
                            <span style={{ color: 'var(--accent-amber)' }}>Partial</span>
                            <span>2/8</span>
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem' }}>
                            <span style={{ color: 'var(--text-muted)' }}>Missing</span>
                            <span>3/8</span>
                        </div>
                        <div style={{ marginTop: '0.5rem', height: 4, borderRadius: 2, background: 'var(--bg-input)', overflow: 'hidden' }}>
                            <div style={{ height: '100%', width: '62.5%', background: 'linear-gradient(90deg, var(--accent-green), var(--accent-amber))', borderRadius: 2 }} />
                        </div>
                    </div>
                </div>

                {/* Main Editor */}
                <div className="editor-main">
                    <h2 style={{ marginBottom: '0.25rem' }}>
                        {DEMO_SECTIONS[activeSection].title}
                    </h2>
                    <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '1rem' }}>
                        Section {activeSection + 1} of {DEMO_SECTIONS.length}
                    </p>

                    <EditorToolbar />

                    {/* Editor Area */}
                    <div
                        contentEditable
                        suppressContentEditableWarning
                        style={{
                            minHeight: 400,
                            outline: 'none',
                            fontSize: '1rem',
                            lineHeight: 1.75,
                            color: 'var(--text-primary)',
                        }}
                    >
                        {editorContent}
                    </div>
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
                        >
                            <Send size={14} />
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
                            'Generate from template',
                        ].map((action) => (
                            <button
                                key={action}
                                className="btn btn-ghost btn-sm"
                                style={{ width: '100%', justifyContent: 'flex-start', marginBottom: '2px', fontSize: '0.82rem' }}
                            >
                                <Wand2 size={13} /> {action}
                            </button>
                        ))}
                    </div>

                    {/* Suggested Content */}
                    <div>
                        <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '0.5rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                            Suggested Content
                        </p>

                        <div className="ai-suggestion">
                            <p style={{ fontWeight: 600, fontSize: '0.8rem', marginBottom: '0.3rem', color: 'var(--text-primary)' }}>
                                Bridge Rehabilitation Experience
                            </p>
                            <p>Successfully completed the I-95 bridge rehabilitation project for PennDOT in 2024, delivering 2 weeks ahead of schedule...</p>
                            <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.5rem' }}>
                                <button className="btn btn-ghost btn-sm">
                                    <Copy size={12} /> Insert
                                </button>
                            </div>
                        </div>

                        <div className="ai-suggestion">
                            <p style={{ fontWeight: 600, fontSize: '0.8rem', marginBottom: '0.3rem', color: 'var(--text-primary)' }}>
                                Team Qualifications
                            </p>
                            <p>Lead Engineer John Smith, PE, holds 15 years of structural engineering experience with PMP and LEED certifications...</p>
                            <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.5rem' }}>
                                <button className="btn btn-ghost btn-sm">
                                    <Copy size={12} /> Insert
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}
