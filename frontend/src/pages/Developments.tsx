import { motion } from 'framer-motion';
import { GitBranch, GitPullRequest, Package, Code2 } from 'lucide-react';

export default function Developments() {
    return (
        <div style={{
            minHeight: '100vh',
            padding: '2rem',
            background: 'radial-gradient(circle at 10% 10%, rgba(59, 130, 246, 0.1) 0%, transparent 40%), radial-gradient(circle at 90% 90%, rgba(139, 92, 246, 0.1) 0%, transparent 40%)',
        }}>
            <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                style={{ maxWidth: '900px', margin: '0 auto' }}
            >
                <div style={{ textAlign: 'center', marginBottom: '2rem' }}>
                    <Code2 size={40} color="#60a5fa" style={{ marginBottom: '1rem', filter: 'drop-shadow(0 0 10px rgba(96, 165, 250, 0.5))' }} />
                    <h1 style={{ fontSize: '1.75rem', marginBottom: '0.5rem', background: 'linear-gradient(135deg, #fff 0%, #94a3b8 100%)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
                        Developments
                    </h1>
                    <p style={{ color: '#9ca3af' }}>Project development status and changelog</p>
                </div>

                <div style={{ display: 'grid', gap: '1rem' }}>
                    {[
                        { icon: GitBranch, title: 'Feature: Celery Integration', desc: 'Background task queue with Redis broker', status: 'completed', date: '2026-03-06' },
                        { icon: GitBranch, title: 'Feature: MinIO Storage', desc: 'Document storage for OnlyOffice', status: 'completed', date: '2026-03-06' },
                        { icon: GitBranch, title: 'Feature: Task Manager UI', desc: 'Frontend page for managing background tasks', status: 'completed', date: '2026-03-06' },
                        { icon: GitBranch, title: 'Feature: Components Dashboard', desc: 'Admin page listing all system components', status: 'completed', date: '2026-03-06' },
                        { icon: GitBranch, title: 'Security: Rate Limiting', desc: 'SlowAPI protection on auth endpoints', status: 'completed', date: '2026-03-06' },
                        { icon: GitBranch, title: 'Security: OTP Hardening', desc: 'Timing-safe comparison and attempt limits', status: 'completed', date: '2026-03-06' },
                        { icon: GitPullRequest, title: 'Feature: Section Management', desc: 'Create and manage proposal sections', status: 'in_progress', date: '2026-03-07' },
                        { icon: Package, title: 'Refactoring: Environment Variables', desc: 'Enforced secure defaults validation', status: 'completed', date: '2026-03-06' },
                    ].map((item, index) => (
                        <motion.div
                            key={item.title}
                            initial={{ opacity: 0, y: 20 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ delay: index * 0.05 }}
                            style={{
                                padding: '1.25rem',
                                background: 'rgba(17, 24, 39, 0.8)',
                                border: '1px solid rgba(255, 255, 255, 0.1)',
                                borderRadius: '0.75rem',
                                display: 'flex',
                                alignItems: 'center',
                                gap: '1rem',
                            }}
                        >
                            <div style={{
                                width: 44,
                                height: 44,
                                borderRadius: '0.5rem',
                                background: item.status === 'completed' ? 'rgba(16, 185, 129, 0.2)' : 'rgba(245, 158, 11, 0.2)',
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                            }}>
                                <item.icon size={22} color={item.status === 'completed' ? '#10b981' : '#f59e0b'} />
                            </div>
                            <div style={{ flex: 1 }}>
                                <h3 style={{ color: 'white', fontWeight: 500, marginBottom: '0.25rem' }}>{item.title}</h3>
                                <p style={{ color: '#9ca3af', fontSize: '0.875rem' }}>{item.desc}</p>
                            </div>
                            <div style={{ textAlign: 'right' }}>
                                <span style={{
                                    padding: '0.25rem 0.75rem',
                                    borderRadius: '1rem',
                                    fontSize: '0.75rem',
                                    background: item.status === 'completed' ? 'rgba(16, 185, 129, 0.2)' : 'rgba(245, 158, 11, 0.2)',
                                    color: item.status === 'completed' ? '#10b981' : '#f59e0b',
                                }}>
                                    {item.status}
                                </span>
                                <p style={{ color: '#6b7280', fontSize: '0.75rem', marginTop: '0.25rem' }}>{item.date}</p>
                            </div>
                        </motion.div>
                    ))}
                </div>
            </motion.div>
        </div>
    );
}
