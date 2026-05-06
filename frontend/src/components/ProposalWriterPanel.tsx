import { useState } from 'react';
import {
    intelligenceApi,
    type ProposalWriterMode,
    type ProposalWriterRequest,
    type ProposalWriterResult,
} from '../api/client';

const MODE_LABELS: Record<ProposalWriterMode, string> = {
    draft: 'Draft from scratch',
    rewrite: 'Rewrite formally',
    improve: 'Improve with coverage gaps',
    address_rehearsal_findings: 'Address rehearsal findings',
};

export interface ProposalWriterPanelProps {
    tenderId: number;
    proposalId: number;
    sectionId: number;
    sectionTitle: string;
    onApplied?: (result: ProposalWriterResult) => void;
}

export function ProposalWriterPanel({
    tenderId,
    proposalId,
    sectionId,
    sectionTitle,
    onApplied,
}: ProposalWriterPanelProps) {
    const [mode, setMode] = useState<ProposalWriterMode>('improve');
    const [instruction, setInstruction] = useState<string>('');
    const [preview, setPreview] = useState<ProposalWriterResult | null>(null);
    const [loading, setLoading] = useState<'preview' | 'apply' | null>(null);
    const [error, setError] = useState<string | null>(null);

    const baseRequest: ProposalWriterRequest = {
        tender_id: tenderId,
        proposal_id: proposalId,
        section_id: sectionId,
        mode,
        instruction: instruction || null,
    };

    const generatePreview = async () => {
        setLoading('preview');
        setError(null);
        try {
            const result = await intelligenceApi.runProposalWriter({
                ...baseRequest,
                apply: false,
            });
            setPreview(result);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Preview failed');
        } finally {
            setLoading(null);
        }
    };

    const applyPreview = async () => {
        if (!preview) return;
        setLoading('apply');
        setError(null);
        try {
            const result = await intelligenceApi.runProposalWriter({
                ...baseRequest,
                apply: true,
            });
            setPreview(result);
            if (result.applied) onApplied?.(result);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Apply failed');
        } finally {
            setLoading(null);
        }
    };

    return (
        <div
            data-testid="proposal-writer-panel"
            style={{
                marginTop: '1rem',
                padding: '0.75rem',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-sm)',
            }}
        >
            <p
                style={{
                    fontSize: '0.75rem',
                    color: 'var(--text-muted)',
                    marginBottom: '0.5rem',
                    textTransform: 'uppercase',
                    letterSpacing: '0.05em',
                }}
            >
                AI Improve Section — {sectionTitle}
            </p>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px', marginBottom: '0.5rem' }}>
                {(Object.keys(MODE_LABELS) as ProposalWriterMode[]).map((option) => (
                    <button
                        key={option}
                        type="button"
                        className={`btn btn-sm ${mode === option ? 'btn-primary' : 'btn-ghost'}`}
                        onClick={() => setMode(option)}
                        disabled={loading !== null}
                        style={{ fontSize: '0.75rem' }}
                    >
                        {MODE_LABELS[option]}
                    </button>
                ))}
            </div>
            <textarea
                placeholder="Optional instruction (e.g. Strengthen SLA and compliance)"
                value={instruction}
                onChange={(e) => setInstruction(e.target.value)}
                disabled={loading !== null}
                style={{ width: '100%', minHeight: 60, fontSize: '0.8rem', marginBottom: '0.5rem' }}
                data-testid="proposal-writer-instruction"
            />
            <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.5rem' }}>
                <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    onClick={generatePreview}
                    disabled={loading !== null}
                    data-testid="proposal-writer-preview-btn"
                >
                    {loading === 'preview' ? 'Generating…' : 'Generate preview'}
                </button>
                <button
                    type="button"
                    className="btn btn-primary btn-sm"
                    onClick={applyPreview}
                    disabled={loading !== null || preview === null}
                    data-testid="proposal-writer-apply-btn"
                >
                    {loading === 'apply' ? 'Applying…' : 'Apply to section'}
                </button>
            </div>

            {error && (
                <div
                    role="alert"
                    style={{
                        padding: '0.5rem',
                        borderRadius: 'var(--radius-sm)',
                        background: 'rgba(239, 68, 68, 0.1)',
                        color: '#ef4444',
                        fontSize: '0.8rem',
                        marginBottom: '0.5rem',
                    }}
                >
                    {error}
                </div>
            )}

            {preview && (
                <div data-testid="proposal-writer-preview">
                    <div
                        className="ai-suggestion"
                        style={{ whiteSpace: 'pre-wrap', fontSize: '0.85rem', lineHeight: 1.5 }}
                    >
                        {preview.draft_text.slice(0, 2000)}
                        {preview.draft_text.length > 2000 ? '…' : ''}
                    </div>

                    {preview.applied && (
                        <p
                            data-testid="proposal-writer-applied-marker"
                            style={{ fontSize: '0.75rem', color: 'var(--accent-blue)', marginTop: '0.4rem' }}
                        >
                            Applied to section.
                        </p>
                    )}

                    {preview.warnings.length > 0 && (
                        <div style={{ marginTop: '0.5rem' }}>
                            <p style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Warnings</p>
                            <ul style={{ margin: 0, paddingLeft: '1rem', fontSize: '0.75rem' }}>
                                {preview.warnings.map((w, i) => (
                                    <li key={i}>{w}</li>
                                ))}
                            </ul>
                        </div>
                    )}

                    {preview.contradictions.length > 0 && (
                        <p style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: '0.4rem' }}>
                            {preview.contradictions.length} contradiction(s) flagged.
                        </p>
                    )}
                </div>
            )}
        </div>
    );
}

export default ProposalWriterPanel;
