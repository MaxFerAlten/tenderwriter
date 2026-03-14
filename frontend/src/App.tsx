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
import Dashboard from './pages/Dashboard';
import ProposalEditor from './pages/ProposalEditor';
import ContentLibrary from './pages/ContentLibrary';
import RAGSearch from './pages/Search';
import SettingsPage from './pages/Settings';
import SystemMonitor from './pages/SystemMonitor';
import TenderPermissions from './pages/TenderPermissions';
import TaskManager from './pages/TaskManager';
import Components from './pages/Components';
import Developments from './pages/Developments';
import ObservabilityKPI from './pages/ObservabilityKPI';
import Login from './pages/Login';
import Register from './pages/Register';
import TenderChat from './pages/TenderChat';
import { useAuth } from './contexts/AuthContext';

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

function App() {
    const location = useLocation();
    const { user, isLoading, logout } = useAuth();

    if (isLoading) {
        return <div style={{ height: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-secondary)' }}>Loading...</div>;
    }

    if (!user) {
        return (
            <AnimatePresence mode="wait">
                <Routes location={location} key={location.pathname}>
                    <Route path="/login" element={<Login />} />
                    <Route path="/register" element={<Register />} />
                    <Route path="*" element={<Navigate to="/login" replace />} />
                </Routes>
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
                    </motion.div>
                </AnimatePresence>
            </main>
        </div>
    );
}

export default App;
