import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';

import { DashboardModalStack, TenderUploadAlertModal, type TenderUploadAlert } from './Dashboard';

describe('TenderUploadAlertModal', () => {
    it('does not render a dialog when there is no import warning to show', () => {
        const html = renderToStaticMarkup(
            <TenderUploadAlertModal alert={null} />
        );

        expect(html).toBe('');
    });

    it('renders the LLM warning message and fallback guidance for import warnings', () => {
        const alert: TenderUploadAlert = {
            title: 'Import completed with warnings',
            tenderTitle: 'Toscana',
            filename: 'documento.pdf',
            extractionMethod: 'heuristic_v1',
            warnings: [
                {
                    code: 'llm_extraction_failed',
                    title: 'LLM requirement extraction warning',
                    message: 'OpenAI-compatible completion generation failed with status 403: upstream denied access',
                    source: 'requirement_extraction_llm_v2',
                    status_code: 403,
                    fallback_applied: true,
                    fallback_method: 'heuristic_v1',
                    fallback_message: 'The import continued with the heuristic_v1 fallback extractor.',
                },
            ],
        };

        const html = renderToStaticMarkup(
            <TenderUploadAlertModal alert={alert} />
        );

        expect(html).toContain('Import completed with warnings');
        expect(html).toContain('Toscana');
        expect(html).toContain('documento.pdf');
        expect(html).toContain('HTTP 403');
        expect(html).toContain('OpenAI-compatible completion generation failed with status 403: upstream denied access');
        expect(html).toContain('The import continued with the heuristic_v1 fallback extractor.');
        expect(html).toContain('Final extraction method used for this import: <strong>heuristic_v1</strong>');
    });

    it('keeps unique AnimatePresence child keys when multiple dashboard modals are active', () => {
        const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
        const alert: TenderUploadAlert = {
            title: 'Import completed with warnings',
            tenderTitle: 'Toscana',
            filename: 'documento.pdf',
            extractionMethod: 'heuristic_v1',
            warnings: [
                {
                    code: 'llm_extraction_failed',
                    message: 'Upstream denied access.',
                    fallback_applied: true,
                    fallback_method: 'heuristic_v1',
                },
            ],
        };

        renderToStaticMarkup(
            <DashboardModalStack
                uploadAlert={alert}
                onCloseUploadAlert={() => {}}
                showNewProposal={12}
                onCloseProposal={() => {}}
                proposalTitle="Proposal draft"
                onProposalTitleChange={() => {}}
                creatingProposal={false}
                onCreateProposal={() => {}}
                showNewTender={true}
                onCloseNewTender={() => {}}
                form={{
                    title: 'Tender title',
                    client: 'Client',
                    description: '',
                    deadline: '',
                    category: '',
                    tags: [],
                    budget_estimate: undefined,
                }}
                setForm={() => {}}
                duplicateTitleError={null}
                newTenderError={null}
                setNewTenderError={() => {}}
                normalizedFormTitle="Tender title"
                creating={false}
                onCreate={() => {}}
            />
        );

        expect(consoleErrorSpy).not.toHaveBeenCalledWith(
            expect.stringContaining('Encountered two children with the same key')
        );
        consoleErrorSpy.mockRestore();
    });
});
