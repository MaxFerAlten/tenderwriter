import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { ProposalWriterPanel } from './ProposalWriterPanel';

describe('ProposalWriterPanel initial render', () => {
    it('renders all four modes and the instruction textarea on a section', () => {
        const html = renderToStaticMarkup(
            <ProposalWriterPanel
                tenderId={42}
                proposalId={601}
                sectionId={701}
                sectionTitle="Architettura tecnica"
            />,
        );
        expect(html).toContain('AI Improve Section');
        expect(html).toContain('Architettura tecnica');
        expect(html).toContain('Draft from scratch');
        expect(html).toContain('Rewrite formally');
        expect(html).toContain('Improve with coverage gaps');
        expect(html).toContain('Address rehearsal findings');
        expect(html).toContain('proposal-writer-instruction');
        expect(html).toContain('proposal-writer-preview-btn');
        expect(html).toContain('proposal-writer-apply-btn');
        // Apply must be disabled before any preview is generated.
        expect(html).toContain('Apply to section');
        expect(html).toMatch(
            /<button[^>]*disabled[^>]*data-testid="proposal-writer-apply-btn"/,
        );
    });

    it('does not render the preview block before any generation', () => {
        const html = renderToStaticMarkup(
            <ProposalWriterPanel
                tenderId={1}
                proposalId={2}
                sectionId={3}
                sectionTitle="Sez."
            />,
        );
        expect(html).not.toContain('proposal-writer-preview"');
        expect(html).not.toContain('proposal-writer-applied-marker');
    });
});
