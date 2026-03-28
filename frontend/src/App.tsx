import { Suspense, useEffect } from 'react';
import { Routes, Route, NavLink, useLocation, Navigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
    Activity,
    BarChart3,
    Code,
    FileText,
    GitBranch,
    LayoutDashboard,
    Library,
    LogOut,
    Play,
    Search,
    Server,
    Settings,
    Shield,
    Sparkles,
} from 'lucide-react';
import { useAuth } from './contexts/AuthContext';
import {
    ComponentsPage,
    ContentLibraryPage,
    DashboardPage,
    DevelopmentsPage,
    LoginPage,
    MarkovStateProcessPage,
    ObservabilityKpiPage,
    preloadLikelyRoutes,
    preloadRoute,
    ProposalEditorPage,
    RegisterPage,
    SearchPage,
    SettingsPage,
    SystemMonitorPage,
    TaskManagerPage,
    TenderChatPage,
    TenderPermissionsPage,
    OperationalWorkspacePage,
} from './router/lazyRoutes';

const navItems = [
    { path: '/', label: 'Dashboard', icon: LayoutDashboard },
    { path: '/proposals', label: 'Proposals', icon: FileText },
    { path: '/library', label: 'Content Library', icon: Library },
    { path: '/search', label: 'AI Search', icon: Search },
    { path: '/tasks', label: 'Task Manager', icon: Play },
    { path: '/tender-access', label: 'Tender Access', icon: Shield, adminOnly: true },
    { path: '/observability-kpi', label: 'Observability KPI', icon: BarChart3, adminOnly: true },
    { path: '/markov-state-process', label: 'Markov State Process', icon: GitBranch, adminOnly: true },
    { path: '/components', label: 'Components', icon: Server, adminOnly: true },
    { path: '/settings', label: 'Settings', icon: Settings, adminOnly: true },
    { path: '/monitor', label: 'System Monitor', icon: Activity, adminOnly: true },
    { path: '/developments', label: 'Developments', icon: Code, adminOnly: true },
];

function FullscreenLoader({ message }: { message: string }) {
    return (
        <div style={{ height: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-secondary)' }}>
            {message}
        </div>
    );
}

function RouteLoader() {
    return (
        <div className="card" style={{ minHeight: '220px', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-secondary)' }}>
            Loading page...
        </div>
    );
}

function App() {
    const location = useLocation();
    const { user, isLoading, logout } = useAuth();

    useEffect(() => {
        if (!user) {
            return undefined;
        }

        const timer = window.setTimeout(() => {
            void preloadLikelyRoutes(user.role);
        }, 900);

        return () => window.clearTimeout(timer);
    }, [user]);

    const warmRoute = (path: string) => {
        void preloadRoute(path);
    };

    if (isLoading) {
        return <FullscreenLoader message="Loading..." />;
    }

    if (!user) {
        return (
            <AnimatePresence mode="wait">
                <Suspense fallback={<FullscreenLoader message="Loading authentication..." />}>
                    <Routes location={location} key={location.pathname}>
                        <Route path="/login" element={<LoginPage />} />
                        <Route path="/register" element={<RegisterPage />} />
                        <Route path="*" element={<Navigate to="/login" replace />} />
                    </Routes>
                </Suspense>
            </AnimatePresence>
        );
    }

    return (
        <div className="app-layout">
            <aside className="sidebar">
                <div className="sidebar-logo">
                    <Sparkles size={24} color="#60a5fa" />
                    <h1>TenderWriter</h1>
                </div>

                <nav className="sidebar-nav">
                    {navItems.map((item) => {
                        if (item.adminOnly && user.role !== 'admin') return null;
                        return (
                            <NavLink
                                key={item.path}
                                to={item.path}
                                className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
                                end={item.path === '/'}
                                onMouseEnter={() => warmRoute(item.path)}
                                onFocus={() => warmRoute(item.path)}
                                onTouchStart={() => warmRoute(item.path)}
                            >
                                <item.icon size={20} />
                                <span>{item.label}</span>
                            </NavLink>
                        );
                    })}
                </nav>

                <div className="sidebar-footer">
                    <button
                        className="nav-item"
                        onClick={logout}
                        style={{
                            background: 'transparent',
                            border: 'none',
                            width: '100%',
                            textAlign: 'left',
                            cursor: 'pointer',
                            fontFamily: 'inherit',
                            fontSize: 'inherit',
                            color: 'var(--text-secondary)',
                        }}
                    >
                        <LogOut />
                        <span>Logout</span>
                    </button>
                </div>
            </aside>

            <main className="main-content">
                <AnimatePresence mode="wait">
                    <motion.div
                        key={location.pathname}
                        initial={{ opacity: 0, y: 8 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -8 }}
                        transition={{ duration: 0.2 }}
                        style={{ width: '100%' }}
                    >
                        <Suspense fallback={<RouteLoader />}>
                            <Routes location={location}>
                                <Route path="/" element={<DashboardPage />} />
                                <Route path="/proposals" element={<ProposalEditorPage />} />
                                <Route path="/proposals/:id" element={<ProposalEditorPage />} />
                                <Route path="/library" element={<ContentLibraryPage />} />
                                <Route path="/search" element={<SearchPage />} />
                                <Route path="/tasks" element={<TaskManagerPage />} />
                                <Route path="/observability-kpi" element={user.role === 'admin' ? <ObservabilityKpiPage /> : <Navigate to="/" />} />
                                <Route path="/observability-kpi/:tenderId" element={user.role === 'admin' ? <ObservabilityKpiPage /> : <Navigate to="/" />} />
                                <Route path="/observability-kpi/:tenderId/:section" element={user.role === 'admin' ? <ObservabilityKpiPage /> : <Navigate to="/" />} />
                                <Route path="/observability-kpi/:tenderId/operational-workspace" element={user.role === 'admin' ? <OperationalWorkspacePage /> : <Navigate to="/" />} />
                                <Route path="/markov-state-process" element={user.role === 'admin' ? <MarkovStateProcessPage /> : <Navigate to="/" />} />
                                <Route path="/markov-state-process/:tenderId" element={user.role === 'admin' ? <Navigate to="/markov-state-process" replace /> : <Navigate to="/" />} />
                                <Route path="/components" element={user.role === 'admin' ? <ComponentsPage /> : <Navigate to="/" />} />
                                <Route path="/settings" element={user.role === 'admin' ? <SettingsPage /> : <Navigate to="/" />} />
                                <Route path="/monitor" element={user.role === 'admin' ? <SystemMonitorPage /> : <Navigate to="/" />} />
                                <Route path="/developments" element={user.role === 'admin' ? <DevelopmentsPage /> : <Navigate to="/" />} />
                                <Route path="/permissions" element={user.role === 'admin' ? <Navigate to="/tender-access" replace /> : <Navigate to="/" />} />
                                <Route path="/tender-access" element={user.role === 'admin' ? <TenderPermissionsPage /> : <Navigate to="/" />} />
                                <Route path="/tenders/:id/chat" element={<TenderChatPage />} />
                            </Routes>
                        </Suspense>
                    </motion.div>
                </AnimatePresence>
            </main>
        </div>
    );
}

export default App;
