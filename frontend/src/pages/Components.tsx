import { motion } from 'framer-motion';
import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { buildLocalServiceUrl } from '../config/runtime';
import { 
    Server, 
    Database, 
    Box, 
    Globe, 
    Mail, 
    HardDrive, 
    Cpu, 
    Layers,
    ExternalLink,
    Key
} from 'lucide-react';

function FileText(props: any) {
    return (
        <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}>
            <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/>
            <polyline points="14 2 14 8 20 8"/>
            <line x1="16" x2="8" y1="13" y2="13"/>
            <line x1="16" x2="8" y1="17" y2="17"/>
            <line x1="10" x2="8" y1="9" y2="9"/>
        </svg>
    );
}

export default function Components() {
    const { user } = useAuth();
    const navigate = useNavigate();
    const services = [
        {
            name: 'Frontend',
            description: 'React web application',
            url: buildLocalServiceUrl(3000),
            icon: Globe,
            color: '#3b82f6',
        },
        {
            name: 'Backend API',
            description: 'FastAPI REST endpoints',
            url: buildLocalServiceUrl(8000, '/docs'),
            icon: Server,
            color: '#10b981',
        },
        {
            name: 'PostgreSQL',
            description: 'Relational database',
            url: `${window.location.hostname}:5432`,
            icon: Database,
            color: '#6366f1',
        },
        {
            name: 'Qdrant',
            description: 'Vector database',
            url: buildLocalServiceUrl(6333),
            icon: Database,
            color: '#8b5cf6',
        },
        {
            name: 'Neo4j',
            description: 'Graph database browser',
            url: buildLocalServiceUrl(7474),
            icon: Layers,
            color: '#ec4899',
        },
        {
            name: 'Redis',
            description: 'In-memory data store',
            url: `${window.location.hostname}:6379`,
            icon: HardDrive,
            color: '#ef4444',
        },
        {
            name: 'Redis Commander',
            description: 'Redis GUI interface',
            url: buildLocalServiceUrl(8001),
            icon: Box,
            color: '#f97316',
        },
        {
            name: 'Ollama',
            description: 'Local LLM inference',
            url: buildLocalServiceUrl(11434),
            icon: Cpu,
            color: '#84cc16',
        },
        {
            name: 'MinIO',
            description: 'S3-compatible object storage',
            url: buildLocalServiceUrl(9000),
            icon: HardDrive,
            color: '#14b8a6',
        },
        {
            name: 'OnlyOffice',
            description: 'Document editor',
            url: buildLocalServiceUrl(8443),
            icon: FileText,
            color: '#f43f5e',
        },
        {
            name: 'Mailpit',
            description: 'SMTP testing UI',
            url: buildLocalServiceUrl(8025),
            icon: Mail,
            color: '#a855f7',
        },
    ];
    
    useEffect(() => {
        if (user?.role !== 'admin') {
            navigate('/');
        }
    }, [user, navigate]);
    
    if (user?.role !== 'admin') {
        return null;
    }
    
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
                {/* Header */}
                <div style={{ textAlign: 'center', marginBottom: '2rem' }}>
                    <Server size={40} color="#60a5fa" style={{ marginBottom: '1rem', filter: 'drop-shadow(0 0 10px rgba(96, 165, 250, 0.5))' }} />
                    <h1 style={{ fontSize: '1.75rem', marginBottom: '0.5rem', background: 'linear-gradient(135deg, #fff 0%, #94a3b8 100%)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
                        Componenti
                    </h1>
                    <p style={{ color: '#9ca3af' }}>Elenco dei servizi e componenti del sistema</p>
                </div>

                {/* Services Grid */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(250px, 1fr))', gap: '1rem' }}>
                    {services.map((service, index) => (
                        <motion.a
                            key={service.name}
                            href={service.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            initial={{ opacity: 0, y: 20 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ delay: index * 0.05 }}
                            whileHover={{ scale: 1.02 }}
                            style={{
                                padding: '1.25rem',
                                background: 'rgba(17, 24, 39, 0.8)',
                                backdropFilter: 'blur(24px)',
                                border: '1px solid rgba(255, 255, 255, 0.1)',
                                borderRadius: '0.75rem',
                                textDecoration: 'none',
                                display: 'flex',
                                flexDirection: 'column',
                                gap: '0.75rem',
                            }}
                        >
                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                                <div style={{
                                    width: 40,
                                    height: 40,
                                    borderRadius: '0.5rem',
                                    background: `${service.color}20`,
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'center',
                                }}>
                                    <service.icon size={20} color={service.color} />
                                </div>
                                <div style={{ flex: 1 }}>
                                    <h3 style={{ color: 'white', fontWeight: 500, fontSize: '1rem' }}>{service.name}</h3>
                                    <p style={{ color: '#9ca3af', fontSize: '0.8rem' }}>{service.description}</p>
                                </div>
                                <ExternalLink size={16} color="#6b7280" />
                            </div>
                            <div style={{
                                padding: '0.5rem',
                                background: 'rgba(31, 41, 55, 0.5)',
                                borderRadius: '0.375rem',
                                fontSize: '0.75rem',
                                color: '#60a5fa',
                                fontFamily: 'monospace',
                            }}>
                                {service.url}
                            </div>
                        </motion.a>
                    ))}
                </div>

                {/* Credentials Info */}
                <div style={{
                    marginTop: '2rem',
                    padding: '1.5rem',
                    background: 'rgba(17, 24, 39, 0.8)',
                    border: '1px solid rgba(255, 255, 255, 0.1)',
                    borderRadius: '0.75rem',
                }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem' }}>
                        <Key size={18} color="#f59e0b" />
                        <h3 style={{ color: 'white', fontWeight: 500 }}>Credenziali</h3>
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem' }}>
                        {[
                            { service: 'Neo4j', user: 'neo4j', pass: 'DefaultNEO4J2024Pass' },
                            { service: 'PostgreSQL', user: 'tenderwriter', pass: 'DefaultPg2024Pass' },
                            { service: 'MinIO', user: 'minioadmin', pass: 'DefaultMinIO2024Pass' },
                            { service: 'Admin', user: 'admin@admin.com', pass: 'vN7pQ3wL9xR5tY2uA4bC6dE8fG1hJ0' },
                        ].map(cred => (
                            <div key={cred.service} style={{ padding: '0.75rem', background: 'rgba(31, 41, 55, 0.5)', borderRadius: '0.5rem' }}>
                                <p style={{ color: '#9ca3af', fontSize: '0.75rem', marginBottom: '0.25rem' }}>{cred.service}</p>
                                <p style={{ color: 'white', fontSize: '0.85rem', fontFamily: 'monospace' }}>{cred.user}</p>
                                <p style={{ color: '#60a5fa', fontSize: '0.85rem', fontFamily: 'monospace' }}>{cred.pass}</p>
                            </div>
                        ))}
                    </div>
                </div>
            </motion.div>
        </div>
    );
}
