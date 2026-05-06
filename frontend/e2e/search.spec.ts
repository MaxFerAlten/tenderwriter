import { expect, test, type Route } from '@playwright/test';

import { login, SAMPLE_TENDER } from './login';

interface RagCall {
    mode: string;
    save_history: boolean;
    route_key?: string;
    tender_id?: number | null;
    [key: string]: unknown;
}

async function mockBaseline(page: import('@playwright/test').Page, ragCalls: RagCall[]): Promise<void> {
    await page.route('**/api/tenders*', async (route: Route) => {
        await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({ items: [SAMPLE_TENDER], total: 1 }),
        });
    });
    await page.route('**/api/rag/history', async (route: Route) => {
        await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify([]),
        });
    });
    await page.route('**/api/rag/query', async (route: Route) => {
        const body = (route.request().postDataJSON() ?? {}) as RagCall;
        ragCalls.push(body);
        const payload = body.mode === 'search'
            ? {
                answer: '',
                mode: 'search',
                sources: [{
                    text: 'Fonte di test sulla gara',
                    score: 0.91,
                    metadata: { tender_id: 1, filename: 'capitolato.pdf' },
                    retriever_sources: ['dense', 'sparse'],
                    source_scores: { dense: 0.6, sparse: 0.4 },
                }],
            }
            : {
                answer: 'Risposta RAG di test',
                mode: 'qa',
                sources: [{
                    text: 'Fonte di test sulla gara',
                    score: 0.91,
                    metadata: { tender_id: 1, filename: 'capitolato.pdf' },
                    retriever_sources: ['dense', 'sparse'],
                    source_scores: { dense: 0.6, sparse: 0.4 },
                }],
            };
        await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify(payload),
        });
    });
}

test.describe('/search RAG flow', () => {
    test('search-then-QA triggers two backend calls with correct save_history flags', async ({ page }) => {
        const ragCalls: RagCall[] = [];
        await login(page);
        await mockBaseline(page, ragCalls);

        await page.goto('/search');
        await page.getByPlaceholder(/Ask anything/i).fill('descrivi la gara');
        await page.getByRole('button', { name: /Search/i }).click();

        await expect(page.getByTestId('search-answer')).toContainText('Risposta RAG di test');
        await expect(page.getByText('Fonte di test sulla gara').first()).toBeVisible();

        const modes = ragCalls.map((c) => c.mode);
        expect(modes).toEqual(['search', 'qa']);
        expect(ragCalls[0].save_history).toBe(false);
        expect(ragCalls[0].route_key).toBe('global');
        expect(ragCalls[0].tender_id).toBeUndefined();
    });

    test('tender-scoped search sends route_key=tender and tender_id', async ({ page }) => {
        const ragCalls: RagCall[] = [];
        await login(page);
        await mockBaseline(page, ragCalls);

        await page.goto('/search');
        await page.getByTestId('search-scope-select').selectOption(String(SAMPLE_TENDER.id));
        await page.getByPlaceholder(/Ask anything/i).fill('requisiti tecnici');
        await page.getByRole('button', { name: /Search/i }).click();

        await expect(page.getByTestId('search-answer')).toContainText('Risposta RAG di test');
        expect(ragCalls.length).toBeGreaterThan(0);
        for (const call of ragCalls) {
            expect(call.route_key).toBe('tender');
            expect(call.tender_id).toBe(SAMPLE_TENDER.id);
        }
    });

    test('malicious HTML in answer is rendered as text and not executed', async ({ page }) => {
        const ragCalls: RagCall[] = [];
        await login(page);
        await mockBaseline(page, ragCalls);

        await page.unroute('**/api/rag/query');
        const malicious = '<img src=x onerror="window.__xss=true">payload';
        await page.route('**/api/rag/query', async (route: Route) => {
            const body = (route.request().postDataJSON() ?? {}) as RagCall;
            ragCalls.push(body);
            const isSearch = body.mode === 'search';
            await route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify({
                    answer: isSearch ? '' : malicious,
                    mode: isSearch ? 'search' : 'qa',
                    sources: [],
                }),
            });
        });

        await page.goto('/search');
        await page.getByPlaceholder(/Ask anything/i).fill('payload');
        await page.getByRole('button', { name: /Search/i }).click();

        const answerLocator = page.getByTestId('search-answer');
        await expect(answerLocator).toContainText('payload');
        const xssExecuted = await page.evaluate(() => (window as unknown as { __xss?: boolean }).__xss === true);
        expect(xssExecuted).toBe(false);
        const innerHtml = await answerLocator.innerHTML();
        expect(innerHtml).not.toContain('<img');
    });
});
