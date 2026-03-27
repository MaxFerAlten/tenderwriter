import { lazy, type ComponentType, type LazyExoticComponent } from 'react';

type PageComponent = ComponentType<any>;
type PageModule = { default: PageComponent };
type RouteLoader = () => Promise<PageModule>;

function loadPage<T extends PageComponent>(loader: () => Promise<{ default: T }>): RouteLoader {
    return loader as RouteLoader;
}

const routeLoaders = {
    '/': loadPage(() => import('../pages/Dashboard')),
    '/proposals': loadPage(() => import('../pages/ProposalEditor')),
    '/library': loadPage(() => import('../pages/ContentLibrary')),
    '/search': loadPage(() => import('../pages/Search')),
    '/tasks': loadPage(() => import('../pages/TaskManager')),
    '/observability-kpi': loadPage(() => import('../pages/ObservabilityKPI')),
    '/markov-state-process': loadPage(() => import('../pages/MarkovStateProcess')),
    '/components': loadPage(() => import('../pages/Components')),
    '/settings': loadPage(() => import('../pages/Settings')),
    '/monitor': loadPage(() => import('../pages/SystemMonitor')),
    '/developments': loadPage(() => import('../pages/Developments')),
    '/permissions': loadPage(() => import('../pages/TenderPermissions')),
    '/login': loadPage(() => import('../pages/Login')),
    '/register': loadPage(() => import('../pages/Register')),
    '/observability-kpi/:tenderId/operational-workspace': loadPage(() => import('../pages/OperationalWorkspacePage')),
    '/tenders/:id/chat': loadPage(() => import('../pages/TenderChat')),
} satisfies Record<string, RouteLoader>;

const warmedRoutes = new Set<string>();

function lazyPage(path: keyof typeof routeLoaders): LazyExoticComponent<PageComponent> {
    return lazy(routeLoaders[path]);
}

export function normalizeRoutePath(path: string): keyof typeof routeLoaders | null {
    if (!path) {
        return null;
    }

    if (path === '/') {
        return '/';
    }

    if (path.startsWith('/proposals/')) {
        return '/proposals';
    }

    if (/^\/observability-kpi\/[^/]+\/operational-workspace$/i.test(path)) {
        return '/observability-kpi/:tenderId/operational-workspace';
    }

    if (/^\/observability-kpi\/[^/]+(?:\/[^/]+)?$/i.test(path)) {
        return '/observability-kpi';
    }

    if (/^\/markov-state-process\/[^/]+$/i.test(path)) {
        return '/markov-state-process';
    }

    if (/^\/tenders\/[^/]+\/chat$/i.test(path)) {
        return '/tenders/:id/chat';
    }

    return (path in routeLoaders ? path : null) as keyof typeof routeLoaders | null;
}

export function getLikelyRoutePaths(role?: string | null): Array<keyof typeof routeLoaders> {
    const common: Array<keyof typeof routeLoaders> = ['/proposals', '/library', '/tasks'];
    if (role === 'admin') {
        return [...common, '/observability-kpi', '/markov-state-process', '/monitor'];
    }
    return common;
}

export async function preloadRoute(path: string): Promise<void> {
    const normalizedPath = normalizeRoutePath(path);
    if (!normalizedPath || warmedRoutes.has(normalizedPath)) {
        return;
    }

    warmedRoutes.add(normalizedPath);
    try {
        await routeLoaders[normalizedPath]();
    } catch (error) {
        warmedRoutes.delete(normalizedPath);
        throw error;
    }
}

export async function preloadLikelyRoutes(role?: string | null): Promise<void> {
    await Promise.allSettled(getLikelyRoutePaths(role).map((path) => preloadRoute(path)));
}

export function resetWarmedRoutesForTest(): void {
    warmedRoutes.clear();
}

export const DashboardPage = lazyPage('/');
export const ProposalEditorPage = lazyPage('/proposals');
export const ContentLibraryPage = lazyPage('/library');
export const SearchPage = lazyPage('/search');
export const TaskManagerPage = lazyPage('/tasks');
export const ObservabilityKpiPage = lazyPage('/observability-kpi');
export const MarkovStateProcessPage = lazyPage('/markov-state-process');
export const ComponentsPage = lazyPage('/components');
export const SettingsPage = lazyPage('/settings');
export const SystemMonitorPage = lazyPage('/monitor');
export const DevelopmentsPage = lazyPage('/developments');
export const TenderPermissionsPage = lazyPage('/permissions');
export const LoginPage = lazyPage('/login');
export const RegisterPage = lazyPage('/register');
export const OperationalWorkspacePage = lazyPage('/observability-kpi/:tenderId/operational-workspace');
export const TenderChatPage = lazyPage('/tenders/:id/chat');
