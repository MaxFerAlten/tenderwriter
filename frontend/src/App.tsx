import { Routes, Route, NavLink, useLocation } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
    LayoutDashboard,
    FileText,
    Library,
    Search,
    Settings,
    Sparkles,
} from 'lucide-react';
import Dashboard from './pages/Dashboard';
import ProposalEditor from './pages/ProposalEditor';
import ContentLibrary from './pages/ContentLibrary';
import RAGSearch from './pages/Search';
import SettingsPage from './pages/Settings';

const navItems = [
    { path: '/', label: 'Dashboard', icon: LayoutDashboard },
    { path: '/proposals', label: 'Proposals', icon: FileText },
    { path: '/library', label: 'Content Library', icon: Library },
    { path: '/search', label: 'AI Search', icon: Search },
];

function App() {
    const location = useLocation();

    return (
        <div className="app-layout">
            {/* Sidebar */}
            <aside className="sidebar">
                <div className="sidebar-logo">
                    <Sparkles size={24} color="#60a5fa" />
                    <h1>TenderWriter</h1>
                </div>

                <nav className="sidebar-nav">
                    {navItems.map((item) => (
                        <NavLink
                            key={item.path}
                            to={item.path}
                            className={({ isActive }) =>
                                `nav-item ${isActive ? 'active' : ''}`
                            }
                            end={item.path === '/'}
                        >
                            <item.icon />
                            <span>{item.label}</span>
                        </NavLink>
                    ))}
                </nav>

                <div className="sidebar-nav" style={{ marginTop: 'auto' }}>
                    <NavLink to="/settings" className="nav-item">
                        <Settings />
                        <span>Settings</span>
                    </NavLink>
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
                        </Routes>
                    </motion.div>
                </AnimatePresence>
            </main>
        </div>
    );
}

export default App;
