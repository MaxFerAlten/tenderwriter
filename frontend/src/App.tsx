import { Suspense, lazy } from 'react';
import { Routes, Route, NavLink, useLocation, Navigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
    Activity,
    BarChart3,
    Code,
    FileText,
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

const Dashboard = lazy(() => import('./pages/Dashboard'));
const ProposalEditor = lazy(() => import('./pages/ProposalEditor'));
const ContentLibrary = lazy(() => import('./pages/ContentLibrary'));
const RAGSearch = lazy(() => import('./pages/Search'));
const SettingsPage = lazy(() => import('./pages/Settings'));
const SystemMonitor = lazy(() => import('./pages/SystemMonitor'));
const TenderPermissions = lazy(() => import('./pages/TenderPermissions'));
const TaskManager = lazy(() => import('./pages/TaskManager'));
const Components = lazy(() => import('./pages/Components'));
const Developments = lazy(() => import('./pages/Developments'));
const ObservabilityKPI = lazy(() => import('./pages/ObservabilityKPI'));
const Login = lazy(() => import('./pages/Login'));
const Register = lazy(() => import('./pages/Register'));
const TenderChat = lazy(() => import('./pages/TenderChat'));

const navItems = [
    { path: '/', label: 'Dashboard', icon: LayoutDashboard },
    { path: '/proposals', label: 'Proposals', icon: FileText },
    { path: '/library', label: 'Content Library', icon: Library },
    { path: '/search', label: 'AI Search', icon: Search },
    { path: '/tasks', label: 'Task Manager', icon: Play },
    { path: '/observability-kpi', label: 'Observability KPI', icon: BarChart3, adminOnly: true },
    { path: '/components', label: 'Components', icon: Server, adminOnly: true },
    { path: '/settings', label: 'Settings', icon: Settings, adminOnly: true },
    { path: '/monitor', label: 'System Monitor', icon: Activity, adminOnly: true },
    { path: '/developments', label: 'Developments', icon: Code, adminOnly: true },
    { path: '/permissions', label: 'Permissions', icon: Shield, adminOnly: true },
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

    if (isLoading) {
        return <FullscreenLoader message="Loading..." />;
    }

    if (!user) {
        return (
            <AnimatePresence mode="wait">
                <Suspense fallback={<FullscreenLoader message="Loading authentication..." />}>
                    <Routes location={location} key={location.pathname}>
                        <Route path="/login" element={<Login />} />
                        <Route path="/register" element={<Register />} />
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
                        if (item.adminOnly && user?.role !== 'admin') return null;
                        return (
                            <NavLink
                                key={item.path}
                                to={item.path}
                                className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
                                end={item.path === '/'}
                            >
                                <item.icon size={20} />
                                <span>{item.label}</span>
                            </NavLink>
                        );
                    })}
                </nav>

                <div className="sidebar-nav" style={{ marginTop: 'auto' }}>
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
                                <Route path="/" element={<Dashboard />} />
                                <Route path="/proposals" element={<ProposalEditor />} />
                                <Route path="/proposals/:id" element={<ProposalEditor />} />
                                <Route path="/library" element={<ContentLibrary />} />
                                <Route path="/search" element={<RAGSearch />} />
                                <Route path="/tasks" element={<TaskManager />} />
                                <Route path="/observability-kpi" element={user?.role === 'admin' ? <ObservabilityKPI /> : <Navigate to="/" />} />
                                <Route path="/components" element={user?.role === 'admin' ? <Components /> : <Navigate to="/" />} />
                                <Route path="/settings" element={user?.role === 'admin' ? <SettingsPage /> : <Navigate to="/" />} />
                                <Route path="/monitor" element={user?.role === 'admin' ? <SystemMonitor /> : <Navigate to="/" />} />
                                <Route path="/developments" element={user?.role === 'admin' ? <Developments /> : <Navigate to="/" />} />
                                <Route path="/permissions" element={user?.role === 'admin' ? <TenderPermissions /> : <Navigate to="/" />} />
                                <Route path="/tenders/:id/chat" element={<TenderChat />} />
                            </Routes>
                        </Suspense>
                    </motion.div>
                </AnimatePresence>
            </main>
        </div>
    );
}

export default App;
