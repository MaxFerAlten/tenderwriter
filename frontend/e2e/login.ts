import { Page, Route } from '@playwright/test';

interface LoginOptions {
    userId?: number;
    role?: 'admin' | 'user';
    name?: string;
    email?: string;
}

export async function login(page: Page, options: LoginOptions = {}): Promise<void> {
    const user = {
        id: options.userId ?? 1,
        name: options.name ?? 'Test User',
        email: options.email ?? 'test@example.com',
        role: options.role ?? 'user',
    };

    await page.addInitScript((u) => {
        window.localStorage.setItem('token', 'test-token');
        window.localStorage.setItem('auth_session_kind', 'legacy');
        (window as unknown as { __TW_TEST_USER?: typeof u }).__TW_TEST_USER = u;
    }, user);

    await page.route('**/api/auth/me', async (route: Route) => {
        await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify(user),
        });
    });

    await page.route('**/api/auth/auth-mode', async (route: Route) => {
        await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({ provider: 'legacy' }),
        });
    });
}

export const SAMPLE_TENDER = {
    id: 1,
    title: 'Capitolato Acme',
    client: 'Acme Corp',
    description: null,
    deadline: null,
    status: 'open',
    category: null,
    tags: [],
    budget_estimate: null,
    proposal_id: null,
    created_at: new Date().toISOString(),
    created_by: 1,
    created_by_name: 'Test User',
    requirement_count: 0,
};
