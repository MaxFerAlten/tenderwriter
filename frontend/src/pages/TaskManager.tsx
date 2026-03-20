import { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
    Play,
    RefreshCw,
    FileDown,
    Clock,
    CheckCircle,
    XCircle,
    AlertCircle,
    Loader2,
    FileText,
    X,
    List,
    Sparkles,
} from 'lucide-react';

interface TaskInfo {
    task_id: string;
    status: string;
    result?: any;
    error?: string;
}

const STATUS_COLORS: Record<string, string> = {
    PENDING: '#f59e0b',
    STARTED: '#3b82f6',
    SUCCESS: '#10b981',
    FAILURE: '#ef4444',
    RETRY: '#8b5cf6',
};

const STATUS_ICONS: Record<string, any> = {
    PENDING: Clock,
    STARTED: Loader2,
    SUCCESS: CheckCircle,
    FAILURE: XCircle,
    RETRY: RefreshCw,
};

export default function TaskManager() {
    const [tasks, setTasks] = useState<TaskInfo[]>([]);
    const [loading, setLoading] = useState(false);
    const [pollingTask, setPollingTask] = useState<string | null>(null);

    const [showIdsModal, setShowIdsModal] = useState(false);

    const [error, setError] = useState<string | null>(null);
    const [availableProposals, setAvailableProposals] = useState<any[]>([]);
    const [availableDocuments, setAvailableDocuments] = useState<any[]>([]);
    const [availableSections, setAvailableSections] = useState<any[]>([]);

    const [showFormModal, setShowFormModal] = useState(false);
    const [formType, setFormType] = useState<'index' | 'generate' | 'export'>('index');
    const [formData, setFormData] = useState({
        documentId: '',
        proposalId: '',
        sectionId: '',
        prompt: '',
        exportProposalId: '',
    });

    const startTask = async (endpoint: string, body: any) => {
        setLoading(true);
        setError(null);
        setShowFormModal(false);
        try {
            const token = localStorage.getItem('token');
            const res = await fetch(endpoint, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${token}`,
                },
                body: JSON.stringify(body),
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Task failed');
            setTasks(prev => [...prev, { task_id: data.task_id, status: 'PENDING' }]);
            setPollingTask(data.task_id);
            return data.task_id;
        } catch (err: any) {
            setError(err.message);
            return null;
        } finally {
            setLoading(false);
        }
    };

    const checkTaskStatus = useCallback(async (taskId: string) => {
        try {
            const token = localStorage.getItem('token');
            const res = await fetch(`/api/tasks/status/${taskId}`, {
                headers: { 'Authorization': `Bearer ${token}` },
            });
            const data = await res.json();
            setTasks(prev => prev.map(t => 
                t.task_id === taskId ? { ...t, status: data.status, result: data.result, error: data.error } : t
            ));
            if (data.status === 'SUCCESS' || data.status === 'FAILURE') {
                setPollingTask(null);
            }
        } catch (err) {
            console.error('Failed to check task status:', err);
        }
    }, []);

    useEffect(() => {
        if (!pollingTask) return;
        const interval = setInterval(() => checkTaskStatus(pollingTask), 2000);
        return () => clearInterval(interval);
    }, [pollingTask, checkTaskStatus]);

    const handleSubmit = () => {
        if (formType === 'index' && formData.documentId) {
            startTask('/api/tasks/index-document', { document_id: Number(formData.documentId) });
        } else if (formType === 'generate' && formData.proposalId && formData.sectionId) {
            startTask('/api/tasks/generate-section', {
                proposal_id: Number(formData.proposalId),
                section_id: Number(formData.sectionId),
                prompt: formData.prompt || undefined,
            });
        } else if (formType === 'export' && formData.exportProposalId) {
            startTask('/api/tasks/export-pdf', { proposal_id: Number(formData.exportProposalId) });
        }
    };

    const handleCancelTask = async (taskId: string) => {
        try {
            const token = localStorage.getItem('token');
            await fetch(`/api/tasks/cancel/${taskId}`, {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${token}` },
            });
            setTasks(prev => prev.map(t => 
                t.task_id === taskId ? { ...t, status: 'FAILURE', error: 'Cancelled by user' } : t
            ));
        } catch (err) {
            console.error('Failed to cancel task:', err);
        }
    };

    const handleRemoveTask = (taskId: string) => {
        setTasks(prev => prev.filter(t => t.task_id !== taskId));
    };

    const loadAvailableIds = async () => {
        try {
            const token = localStorage.getItem('token');
            const [proposalsRes, docsRes] = await Promise.all([
                fetch('/api/proposals', { headers: { 'Authorization': `Bearer ${token}` } }),
                fetch('/api/content-blocks', { headers: { 'Authorization': `Bearer ${token}` } }),
            ]);
            const proposals = await proposalsRes.json();
            const docs = await docsRes.json();
            
            const proposalsData = proposals.items || proposals.data || [];
            setAvailableProposals(proposalsData);
            setAvailableDocuments(docs.items || docs.data || []);
            
            const allSections: any[] = [];
            for (const p of proposalsData) {
                try {
                    const sectionsRes = await fetch(`/api/proposals/${p.id}/sections`, {
                        headers: { 'Authorization': `Bearer ${token}` }
                    });
                    const sections = await sectionsRes.json();
                    const sectionsList = Array.isArray(sections) ? sections : sections.items || [];
                    for (const s of sectionsList) {
                        allSections.push({ ...s, proposalTitle: p.title });
                    }
                } catch (sectionError) {
                    console.warn(`Failed to load sections for proposal ${p.id}`, sectionError);
                }
            }
            setAvailableSections(allSections);
            setShowIdsModal(true);
        } catch (err) {
            console.error('Failed to load IDs:', err);
        }
    };

    const openForm = (type: 'index' | 'generate' | 'export') => {
        setFormType(type);
        setFormData({ documentId: '', proposalId: '', sectionId: '', prompt: '', exportProposalId: '' });
        setShowFormModal(true);
    };

    return (
        <div style={{
            minHeight: '100vh',
            padding: '2rem',
            background: 'radial-gradient(circle at 10% 10%, rgba(59, 130, 246, 0.1) 0%, transparent 40%), radial-gradient(circle at 90% 90%, rgba(139, 92, 246, 0.1) 0%, transparent 40%)',
        }}>
            <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                style={{ maxWidth: '800px', margin: '0 auto' }}
            >
                {/* Header */}
                <div style={{ textAlign: 'center', marginBottom: '2rem' }}>
                    <Sparkles size={40} color="#60a5fa" style={{ marginBottom: '1rem', filter: 'drop-shadow(0 0 10px rgba(96, 165, 250, 0.5))' }} />
                    <h1 style={{ fontSize: '1.75rem', marginBottom: '0.5rem', background: 'linear-gradient(135deg, #fff 0%, #94a3b8 100%)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
                        Task Manager
                    </h1>
                    <p style={{ color: '#9ca3af' }}>Gestisci operazioni asincrone</p>
                </div>

                {error && (
                    <div style={{ padding: '1rem', background: 'rgba(239, 68, 68, 0.1)', border: '1px solid rgba(239, 68, 68, 0.3)', borderRadius: '0.75rem', marginBottom: '1.5rem', display: 'flex', alignItems: 'center', gap: '0.5rem', color: '#f87171' }}>
                        <AlertCircle size={18} />
                        <span>{error}</span>
                    </div>
                )}

                {/* Action Cards */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem', marginBottom: '2rem' }}>
                    {[
                        { type: 'index' as const, icon: FileText, label: 'Index Document', desc: 'Indicizza documento nel RAG', color: '#3b82f6' },
                        { type: 'generate' as const, icon: Play, label: 'Generate Section', desc: 'Genera sezione con LLM', color: '#8b5cf6' },
                        { type: 'export' as const, icon: FileDown, label: 'Export PDF', desc: 'Esporta proposta in PDF', color: '#10b981' },
                    ].map(item => (
                        <motion.button
                            key={item.type}
                            whileHover={{ scale: 1.02 }}
                            whileTap={{ scale: 0.98 }}
                            onClick={() => openForm(item.type)}
                            style={{ padding: '1.5rem', background: 'rgba(17, 24, 39, 0.8)', backdropFilter: 'blur(24px)', border: '1px solid rgba(255, 255, 255, 0.1)', borderRadius: '0.75rem', cursor: 'pointer', textAlign: 'left' }}
                        >
                            <item.icon size={28} color={item.color} style={{ marginBottom: '0.75rem' }} />
                            <h3 style={{ color: 'white', fontWeight: 500, marginBottom: '0.25rem' }}>{item.label}</h3>
                            <p style={{ color: '#9ca3af', fontSize: '0.875rem' }}>{item.desc}</p>
                        </motion.button>
                    ))}
                </div>

                {/* IDs Button */}
                <button onClick={loadAvailableIds} style={{ width: '100%', padding: '0.75rem', background: 'rgba(17, 24, 39, 0.8)', border: '1px solid rgba(255, 255, 255, 0.1)', borderRadius: '0.75rem', color: '#9ca3af', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem', marginBottom: '2rem' }}>
                    <List size={18} />
                    Mostra ID disponibili
                </button>

                {/* Task History */}
                <div style={{ background: 'rgba(17, 24, 39, 0.8)', backdropFilter: 'blur(24px)', border: '1px solid rgba(255, 255, 255, 0.1)', borderRadius: '0.75rem', overflow: 'hidden' }}>
                    <div style={{ padding: '1rem', borderBottom: '1px solid rgba(255, 255, 255, 0.1)' }}>
                        <h2 style={{ color: 'white', fontSize: '1rem', fontWeight: 500 }}>Task History</h2>
                    </div>
                    <div>
                        {tasks.length === 0 ? (
                            <div style={{ padding: '2rem', textAlign: 'center', color: '#6b7280' }}>No tasks executed</div>
                        ) : (
                            tasks.slice().reverse().map(task => {
                                const Icon = STATUS_ICONS[task.status] || Clock;
                                const color = STATUS_COLORS[task.status] || '#64748b';
                                return (
                                    <div key={task.task_id} style={{ padding: '1rem', display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid rgba(255, 255, 255, 0.05)' }}>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                                            <div style={{ width: 40, height: 40, borderRadius: '50%', background: `${color}20`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                                                <Icon size={20} color={color} />
                                            </div>
                                            <div>
                                                <p style={{ color: 'white', fontFamily: 'monospace', fontSize: '0.875rem' }}>{task.task_id.slice(0, 8)}...</p>
                                                <p style={{ color, fontSize: '0.875rem' }}>Status: {task.status}</p>
                                                {task.error && <p style={{ color: '#f87171', fontSize: '0.75rem' }}>{task.error}</p>}
                                            </div>
                                        </div>
                                        <div style={{ display: 'flex', gap: '0.5rem' }}>
                                            {task.status === 'STARTED' && (
                                                <button onClick={() => handleCancelTask(task.task_id)} style={{ padding: '0.5rem', background: 'transparent', border: 'none', color: '#9ca3af', cursor: 'pointer' }}><X size={18} /></button>
                                            )}
                                            {(task.status === 'SUCCESS' || task.status === 'FAILURE') && (
                                                <button onClick={() => handleRemoveTask(task.task_id)} style={{ padding: '0.5rem', background: 'transparent', border: 'none', color: '#9ca3af', cursor: 'pointer' }}><X size={18} /></button>
                                            )}
                                        </div>
                                    </div>
                                );
                            })
                        )}
                    </div>
                </div>
            </motion.div>

            {/* Form Modal */}
            <AnimatePresence>
                {showFormModal && (
                    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 50 }} onClick={() => setShowFormModal(false)}>
                        <motion.div initial={{ scale: 0.95 }} animate={{ scale: 1 }} exit={{ scale: 0.95 }} onClick={e => e.stopPropagation()} style={{ background: 'rgba(17, 24, 39, 0.95)', border: '1px solid rgba(255, 255, 255, 0.1)', borderRadius: '0.75rem', padding: '1.5rem', width: '100%', maxWidth: '400px' }}>
                            <h3 style={{ color: 'white', fontSize: '1.1rem', fontWeight: 600, marginBottom: '1rem' }}>
                                {formType === 'index' ? 'Index Document' : formType === 'generate' ? 'Generate Section' : 'Export PDF'}
                            </h3>
                            {formType === 'index' && <input type="number" placeholder="Document ID" value={formData.documentId} onChange={e => setFormData({ ...formData, documentId: e.target.value })} style={inputStyle} />}
                            {formType === 'generate' && (
                                <>
                                    <input type="number" placeholder="Proposal ID" value={formData.proposalId} onChange={e => setFormData({ ...formData, proposalId: e.target.value })} style={inputStyle} />
                                    <input type="number" placeholder="Section ID" value={formData.sectionId} onChange={e => setFormData({ ...formData, sectionId: e.target.value })} style={inputStyle} />
                                    <textarea placeholder="Prompt (opzionale)" value={formData.prompt} onChange={e => setFormData({ ...formData, prompt: e.target.value })} rows={3} style={{ ...inputStyle, resize: 'none' }} />
                                </>
                            )}
                            {formType === 'export' && <input type="number" placeholder="Proposal ID" value={formData.exportProposalId} onChange={e => setFormData({ ...formData, exportProposalId: e.target.value })} style={inputStyle} />}
                            <div style={{ display: 'flex', gap: '0.5rem', marginTop: '1rem', justifyContent: 'flex-end' }}>
                                <button onClick={() => setShowFormModal(false)} style={cancelBtnStyle}>Cancel</button>
                                <button onClick={handleSubmit} disabled={loading} style={submitBtnStyle}>{loading ? 'Loading...' : 'Start'}</button>
                            </div>
                        </motion.div>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* IDs Modal */}
            <AnimatePresence>
                {showIdsModal && (
                    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 50 }} onClick={() => setShowIdsModal(false)}>
                        <motion.div initial={{ scale: 0.95 }} animate={{ scale: 1 }} exit={{ scale: 0.95 }} onClick={e => e.stopPropagation()} style={{ background: 'rgba(17, 24, 39, 0.95)', border: '1px solid rgba(255, 255, 255, 0.1)', borderRadius: '0.75rem', padding: '1.5rem', width: '100%', maxWidth: '500px', maxHeight: '80vh', overflow: 'auto' }}>
                            <h3 style={{ color: 'white', fontSize: '1.1rem', fontWeight: 600, marginBottom: '1rem' }}>Available IDs</h3>
                            <div style={{ marginBottom: '1.5rem' }}>
                                <h4 style={{ color: '#a78bfa', fontWeight: 500, marginBottom: '0.5rem' }}>Proposals</h4>
                                {availableProposals.length === 0 ? <p style={{ color: '#6b7280', fontSize: '0.875rem' }}>No proposals available</p> : (
                                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                                        {availableProposals.map(p => (
                                            <div key={p.id} style={{ background: 'rgba(31, 41, 55, 0.5)', padding: '0.5rem', borderRadius: '0.375rem', display: 'flex', justifyContent: 'space-between' }}>
                                                <span style={{ color: 'white' }}>ID: <strong>{p.id}</strong></span>
                                                <span style={{ color: '#9ca3af', fontSize: '0.875rem', maxWidth: '200px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{p.title}</span>
                                            </div>
                                        ))}
                                    </div>
                                )}
                            </div>
                            <div style={{ marginBottom: '1.5rem' }}>
                                <h4 style={{ color: '#fb923c', fontWeight: 500, marginBottom: '0.5rem' }}>Sections</h4>
                                {availableSections.length === 0 ? <p style={{ color: '#6b7280', fontSize: '0.875rem' }}>No sections available</p> : (
                                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                                        {availableSections.map(s => (
                                            <div key={s.id} style={{ background: 'rgba(31, 41, 55, 0.5)', padding: '0.5rem', borderRadius: '0.375rem', display: 'flex', justifyContent: 'space-between' }}>
                                                <span style={{ color: 'white' }}>ID: <strong>{s.id}</strong></span>
                                                <span style={{ color: '#9ca3af', fontSize: '0.875rem', maxWidth: '200px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{s.title}</span>
                                            </div>
                                        ))}
                                    </div>
                                )}
                            </div>
                            <div style={{ marginBottom: '1rem' }}>
                                <h4 style={{ color: '#60a5fa', fontWeight: 500, marginBottom: '0.5rem' }}>Documents</h4>
                                {availableDocuments.length === 0 ? <p style={{ color: '#6b7280', fontSize: '0.875rem' }}>No documents available</p> : (
                                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                                        {availableDocuments.map(d => (
                                            <div key={d.id} style={{ background: 'rgba(31, 41, 55, 0.5)', padding: '0.5rem', borderRadius: '0.375rem', display: 'flex', justifyContent: 'space-between' }}>
                                                <span style={{ color: 'white' }}>ID: <strong>{d.id}</strong></span>
                                                <span style={{ color: '#9ca3af', fontSize: '0.875rem', maxWidth: '200px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{d.title}</span>
                                            </div>
                                        ))}
                                    </div>
                                )}
                            </div>
                            <button onClick={() => setShowIdsModal(false)} style={{ width: '100%', padding: '0.5rem', background: 'rgba(31, 41, 55, 0.8)', border: '1px solid rgba(255, 255, 255, 0.1)', borderRadius: '0.375rem', color: '#d1d5db', cursor: 'pointer' }}>Chiudi</button>
                        </motion.div>
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    );
}

const inputStyle = { width: '100%', padding: '0.75rem', background: 'rgba(31, 41, 55, 0.8)', border: '1px solid rgba(255, 255, 255, 0.1)', borderRadius: '0.5rem', color: 'white', fontSize: '0.9rem', marginBottom: '0.75rem', outline: 'none' } as const;
const cancelBtnStyle = { padding: '0.5rem 1rem', background: 'rgba(31, 41, 55, 0.8)', border: '1px solid rgba(255, 255, 255, 0.1)', borderRadius: '0.5rem', color: '#9ca3af', cursor: 'pointer' } as const;
const submitBtnStyle = { padding: '0.5rem 1rem', background: '#3b82f6', border: 'none', borderRadius: '0.5rem', color: 'white', cursor: 'pointer' } as const;
