import { Routes, Route, NavLink, useLocation, Navigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
    LayoutDashboard,
    FileText,
    Library,
    Search,
    Settings,
    Sparkles,
    LogOut,
    Activity,
} from 'lucide-react';
import Dashboard from './pages/Dashboard';
import ProposalEditor from './pages/ProposalEditor';
import ContentLibrary from './pages/ContentLibrary';
import RAGSearch from './pages/Search';
import SettingsPage from './pages/Settings';
import SystemMonitor from './pages/SystemMonitor';
import Login from './pages/Login';
import Register from './pages/Register';
import { useAuth } from './contexts/AuthContext';

const navItems = [
    { path: '/', label: 'Dashboard', icon: LayoutDashboard },
    { path: '/proposals', label: 'Proposals', icon: FileText },
    { path: '/library', label: 'Content Library', icon: Library },
    { path: '/search', label: 'AI Search', icon: Search },
    { path: '/monitor', label: 'System Monitor', icon: Activity, adminOnly: true },
];

function App() {
    const location = useLocation();
    const { user, isLoading, logout } = useAuth();

    if (isLoading) {
        return <div style={{ height: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-secondary)' }}>Caricamento in corso...</div>;
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
            {/* Sidebar */}
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
                                className={({ isActive }) =>
                                    `nav-item ${isActive ? 'active' : ''}`
                                }
                                end={item.path === '/'}
                            >
                                <item.icon size={20} />
                                <span>{item.label}</span>
                            </NavLink>
                        );
                    })}
                </nav>

                <div className="sidebar-nav" style={{ marginTop: 'auto' }}>
                    <NavLink to="/settings" className="nav-item">
                        <Settings />
                        <span>Impostazioni</span>
                    </NavLink>
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
                            color: 'var(--text-secondary)'
                        }}
                    >
                        <LogOut />
                        <span>Esci</span>
                    </button>
                </div>
            </aside>

            {/* Main Content */}
            <main className="main-content">
                <AnimatePresence mode="wait">
                    <motion.div
                        key={location.pathname}
                        initial={{ opacity: 0, y: 8 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -8 }}
                        transition={{ duration: 0.2 }}
                    >
                        <Routes location={location}>
                            <Route path="/" element={<Dashboard />} />
                            <Route path="/proposals" element={<ProposalEditor />} />
                            <Route path="/proposals/:id" element={<ProposalEditor />} />
                            <Route path="/library" element={<ContentLibrary />} />
                            <Route path="/search" element={<RAGSearch />} />
                            <Route path="/settings" element={<SettingsPage />} />
                            <Route path="/monitor" element={user?.role === 'admin' ? <SystemMonitor /> : <Navigate to="/" />} />
                        </Routes>
                    </motion.div>
                </AnimatePresence>
            </main>
        </div>
    );
}

export default App;
