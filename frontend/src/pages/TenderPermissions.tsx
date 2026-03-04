import { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
    Shield,
    Users,
    Search,
    X,
    Loader2,
    AlertCircle,
    CheckCircle,
    UserPlus,
    Trash2,
    FileText,
    ChevronDown,
    ChevronUp,
} from 'lucide-react';
import {
    adminApi,
    type AdminUser,
    type TenderPermissionOverview,
} from '../api/client';

export default function TenderPermissions() {
    const [tenders, setTenders] = useState<TenderPermissionOverview[]>([]);
    const [users, setUsers] = useState<AdminUser[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [success, setSuccess] = useState<string | null>(null);
    const [searchTerm, setSearchTerm] = useState('');
    const [expandedTender, setExpandedTender] = useState<number | null>(null);

    // Grant form state
    const [grantTenderId, setGrantTenderId] = useState<number | null>(null);
    const [grantUserId, setGrantUserId] = useState<number | ''>('');
    const [grantPermission, setGrantPermission] = useState('viewer');
    const [granting, setGranting] = useState(false);

    const loadData = useCallback(async () => {
        try {
            setLoading(true);
            setError(null);
            const [tendersData, usersData] = await Promise.all([
                adminApi.getAllTenderPermissions(),
                adminApi.listUsers(),
            ]);
            setTenders(tendersData);
            setUsers(usersData);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Errore nel caricamento dei dati');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        loadData();
    }, [loadData]);

    const handleGrant = async (tenderId: number) => {
        if (!grantUserId) return;
        try {
            setGranting(true);
            setError(null);
            await adminApi.grantPermission(tenderId, {
                user_id: Number(grantUserId),
                permission: grantPermission,
            });
            setSuccess('Permesso concesso con successo');
            setGrantTenderId(null);
            setGrantUserId('');
            setGrantPermission('viewer');
            await loadData();
            setTimeout(() => setSuccess(null), 3000);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Errore nella concessione del permesso');
        } finally {
            setGranting(false);
        }
    };

    const handleRevoke = async (tenderId: number, userId: number, userName: string) => {
        if (!confirm(`Revocare l'accesso di ${userName} a questo tender?`)) return;
        try {
            setError(null);
            await adminApi.revokePermission(tenderId, userId);
            setSuccess('Permesso revocato con successo');
            await loadData();
            setTimeout(() => setSuccess(null), 3000);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Errore nella revoca del permesso');
        }
    };

    const filteredTenders = tenders.filter((t) =>
        t.tender_title.toLowerCase().includes(searchTerm.toLowerCase()) ||
        (t.owner_name && t.owner_name.toLowerCase().includes(searchTerm.toLowerCase()))
    );

    const nonAdminUsers = users.filter((u) => u.role !== 'admin');

    return (
        <div className="animate-in">
            {/* Header */}
            <div className="page-header">
                <div>
                    <h1 className="page-title" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                        <Shield size={28} color="#60a5fa" />
                        Gestione Permessi Tender
                    </h1>
                    <p className="page-subtitle">
                        Controlla l'accesso granulare ai tender per ogni utente
                    </p>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                    <Users size={18} color="#64748b" />
                    <span style={{ color: 'var(--text-secondary)', fontSize: '0.875rem' }}>
                        {nonAdminUsers.length} utenti · {tenders.length} tender
                    </span>
                </div>
            </div>

            {/* Notifications */}
            <AnimatePresence>
                {error && (
                    <motion.div
                        initial={{ opacity: 0, y: -10 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -10 }}
                        className="card"
                        style={{
                            borderColor: '#ef4444',
                            marginBottom: '1.5rem',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '0.75rem',
                            color: '#ef4444',
                        }}
                    >
                        <AlertCircle size={18} />
                        <span>{error}</span>
                        <button
                            className="btn btn-ghost btn-sm"
                            onClick={() => setError(null)}
                            style={{ marginLeft: 'auto' }}
                        >
                            <X size={14} />
                        </button>
                    </motion.div>
                )}

                {success && (
                    <motion.div
                        initial={{ opacity: 0, y: -10 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -10 }}
                        className="card"
                        style={{
                            borderColor: '#10b981',
                            marginBottom: '1.5rem',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '0.75rem',
                            color: '#10b981',
                        }}
                    >
                        <CheckCircle size={18} />
                        <span>{success}</span>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* Search */}
            <div className="card" style={{ marginBottom: '1.5rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                    <Search size={18} color="#64748b" />
                    <input
                        className="form-input"
                        placeholder="Cerca per nome tender o proprietario..."
                        value={searchTerm}
                        onChange={(e) => setSearchTerm(e.target.value)}
                        style={{ flex: 1, border: 'none', background: 'transparent' }}
                    />
                </div>
            </div>

            {/* Loading */}
            {loading && (
                <div className="loading-spinner" style={{ padding: '3rem 0' }}>
                    <div className="spinner" />
                    <p style={{ color: 'var(--text-muted)', marginTop: '0.75rem' }}>
                        Caricamento permessi...
                    </p>
                </div>
            )}

            {/* Tender List with Permissions */}
            {!loading && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                    {filteredTenders.length === 0 ? (
                        <div className="empty-state" style={{ padding: '3rem 0' }}>
                            <FileText size={48} />
                            <h3>Nessun tender trovato</h3>
                            <p>Non ci sono tender corrispondenti alla ricerca</p>
                        </div>
                    ) : (
                        filteredTenders.map((tender, idx) => {
                            const isExpanded = expandedTender === tender.tender_id;
                            const isGranting = grantTenderId === tender.tender_id;

                            // Users that already have permission (exclude from dropdown)
                            const permittedUserIds = new Set(
                                tender.permissions.map((p) => p.user_id)
                            );
                            // Also exclude the owner
                            if (tender.owner_id) permittedUserIds.add(tender.owner_id);

                            const availableUsers = nonAdminUsers.filter(
                                (u) => !permittedUserIds.has(u.id)
                            );

                            return (
                                <motion.div
                                    key={tender.tender_id}
                                    className="card"
                                    initial={{ opacity: 0, y: 10 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    transition={{ delay: idx * 0.03 }}
                                    style={{ overflow: 'hidden' }}
                                >
                                    {/* Tender Header */}
                                    <div
                                        style={{
                                            display: 'flex',
                                            alignItems: 'center',
                                            justifyContent: 'space-between',
                                            cursor: 'pointer',
                                        }}
                                        onClick={() =>
                                            setExpandedTender(isExpanded ? null : tender.tender_id)
                                        }
                                    >
                                        <div style={{ flex: 1 }}>
                                            <div
                                                style={{
                                                    display: 'flex',
                                                    alignItems: 'center',
                                                    gap: '0.75rem',
                                                }}
                                            >
                                                <FileText size={18} color="#60a5fa" />
                                                <h3 style={{ margin: 0, fontSize: '1rem' }}>
                                                    {tender.tender_title}
                                                </h3>
                                            </div>
                                            <div
                                                style={{
                                                    fontSize: '0.8rem',
                                                    color: 'var(--text-muted)',
                                                    marginTop: '0.25rem',
                                                    marginLeft: '2.25rem',
                                                }}
                                            >
                                                Proprietario:{' '}
                                                <span style={{ color: 'var(--text-secondary)' }}>
                                                    {tender.owner_name || 'N/A'}
                                                </span>
                                                {' · '}
                                                {tender.permissions.length} permess
                                                {tender.permissions.length === 1 ? 'o' : 'i'} attiv
                                                {tender.permissions.length === 1 ? 'o' : 'i'}
                                            </div>
                                        </div>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                            <span
                                                className="badge"
                                                style={{
                                                    background:
                                                        tender.permissions.length > 0
                                                            ? 'rgba(96, 165, 250, 0.15)'
                                                            : 'rgba(100, 116, 139, 0.15)',
                                                    color:
                                                        tender.permissions.length > 0
                                                            ? '#60a5fa'
                                                            : '#64748b',
                                                    padding: '0.25rem 0.5rem',
                                                    borderRadius: '0.375rem',
                                                    fontSize: '0.75rem',
                                                }}
                                            >
                                                {tender.permissions.length} condivisioni
                                            </span>
                                            {isExpanded ? (
                                                <ChevronUp size={18} color="#64748b" />
                                            ) : (
                                                <ChevronDown size={18} color="#64748b" />
                                            )}
                                        </div>
                                    </div>

                                    {/* Expanded Content */}
                                    <AnimatePresence>
                                        {isExpanded && (
                                            <motion.div
                                                initial={{ height: 0, opacity: 0 }}
                                                animate={{ height: 'auto', opacity: 1 }}
                                                exit={{ height: 0, opacity: 0 }}
                                                transition={{ duration: 0.2 }}
                                                style={{ overflow: 'hidden' }}
                                            >
                                                <div
                                                    style={{
                                                        borderTop: '1px solid var(--border)',
                                                        marginTop: '1rem',
                                                        paddingTop: '1rem',
                                                    }}
                                                >
                                                    {/* Permission List */}
                                                    {tender.permissions.length === 0 ? (
                                                        <p
                                                            style={{
                                                                color: 'var(--text-muted)',
                                                                fontSize: '0.875rem',
                                                                textAlign: 'center',
                                                                padding: '1rem 0',
                                                            }}
                                                        >
                                                            Nessun permesso aggiuntivo. Solo il proprietario ha accesso.
                                                        </p>
                                                    ) : (
                                                        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                                                            {tender.permissions.map((perm) => (
                                                                <div
                                                                    key={perm.id}
                                                                    style={{
                                                                        display: 'flex',
                                                                        alignItems: 'center',
                                                                        justifyContent: 'space-between',
                                                                        padding: '0.625rem 0.75rem',
                                                                        borderRadius: '0.5rem',
                                                                        background: 'var(--bg-secondary)',
                                                                    }}
                                                                >
                                                                    <div>
                                                                        <div
                                                                            style={{
                                                                                fontWeight: 500,
                                                                                fontSize: '0.875rem',
                                                                            }}
                                                                        >
                                                                            {perm.user_name}
                                                                        </div>
                                                                        <div
                                                                            style={{
                                                                                fontSize: '0.75rem',
                                                                                color: 'var(--text-muted)',
                                                                            }}
                                                                        >
                                                                            {perm.user_email}
                                                                        </div>
                                                                    </div>
                                                                    <div
                                                                        style={{
                                                                            display: 'flex',
                                                                            alignItems: 'center',
                                                                            gap: '0.75rem',
                                                                        }}
                                                                    >
                                                                        <span
                                                                            className="badge"
                                                                            style={{
                                                                                background:
                                                                                    perm.permission === 'editor'
                                                                                        ? 'rgba(245, 158, 11, 0.15)'
                                                                                        : 'rgba(96, 165, 250, 0.15)',
                                                                                color:
                                                                                    perm.permission === 'editor'
                                                                                        ? '#f59e0b'
                                                                                        : '#60a5fa',
                                                                                padding: '0.2rem 0.5rem',
                                                                                borderRadius: '0.375rem',
                                                                                fontSize: '0.7rem',
                                                                                textTransform: 'uppercase',
                                                                                fontWeight: 600,
                                                                            }}
                                                                        >
                                                                            {perm.permission}
                                                                        </span>
                                                                        <button
                                                                            className="btn btn-ghost btn-sm"
                                                                            onClick={(e) => {
                                                                                e.stopPropagation();
                                                                                handleRevoke(
                                                                                    tender.tender_id,
                                                                                    perm.user_id,
                                                                                    perm.user_name
                                                                                );
                                                                            }}
                                                                            title="Revoca accesso"
                                                                            style={{
                                                                                color: '#ef4444',
                                                                                padding: '0.25rem',
                                                                            }}
                                                                        >
                                                                            <Trash2 size={14} />
                                                                        </button>
                                                                    </div>
                                                                </div>
                                                            ))}
                                                        </div>
                                                    )}

                                                    {/* Grant Form */}
                                                    {isGranting ? (
                                                        <motion.div
                                                            initial={{ opacity: 0, y: -5 }}
                                                            animate={{ opacity: 1, y: 0 }}
                                                            style={{
                                                                marginTop: '0.75rem',
                                                                padding: '0.75rem',
                                                                borderRadius: '0.5rem',
                                                                background: 'var(--bg-tertiary)',
                                                                border: '1px solid var(--border)',
                                                            }}
                                                        >
                                                            <div
                                                                style={{
                                                                    display: 'grid',
                                                                    gridTemplateColumns: '1fr auto auto auto',
                                                                    gap: '0.5rem',
                                                                    alignItems: 'end',
                                                                }}
                                                            >
                                                                <div className="form-group" style={{ margin: 0 }}>
                                                                    <label
                                                                        className="form-label"
                                                                        style={{ fontSize: '0.75rem' }}
                                                                    >
                                                                        Utente
                                                                    </label>
                                                                    <select
                                                                        className="form-select"
                                                                        value={grantUserId}
                                                                        onChange={(e) =>
                                                                            setGrantUserId(
                                                                                e.target.value ? Number(e.target.value) : ''
                                                                            )
                                                                        }
                                                                        style={{ fontSize: '0.8rem' }}
                                                                    >
                                                                        <option value="">Seleziona utente...</option>
                                                                        {availableUsers.map((u) => (
                                                                            <option key={u.id} value={u.id}>
                                                                                {u.name} ({u.email})
                                                                            </option>
                                                                        ))}
                                                                    </select>
                                                                </div>
                                                                <div className="form-group" style={{ margin: 0 }}>
                                                                    <label
                                                                        className="form-label"
                                                                        style={{ fontSize: '0.75rem' }}
                                                                    >
                                                                        Permesso
                                                                    </label>
                                                                    <select
                                                                        className="form-select"
                                                                        value={grantPermission}
                                                                        onChange={(e) =>
                                                                            setGrantPermission(e.target.value)
                                                                        }
                                                                        style={{ fontSize: '0.8rem' }}
                                                                    >
                                                                        <option value="viewer">Viewer</option>
                                                                        <option value="editor">Editor</option>
                                                                    </select>
                                                                </div>
                                                                <button
                                                                    className="btn btn-primary btn-sm"
                                                                    onClick={() => handleGrant(tender.tender_id)}
                                                                    disabled={granting || !grantUserId}
                                                                    style={{ fontSize: '0.8rem' }}
                                                                >
                                                                    {granting ? (
                                                                        <Loader2 size={14} className="spin" />
                                                                    ) : (
                                                                        <CheckCircle size={14} />
                                                                    )}
                                                                    Conferma
                                                                </button>
                                                                <button
                                                                    className="btn btn-ghost btn-sm"
                                                                    onClick={() => setGrantTenderId(null)}
                                                                    style={{ fontSize: '0.8rem' }}
                                                                >
                                                                    <X size={14} />
                                                                </button>
                                                            </div>
                                                        </motion.div>
                                                    ) : (
                                                        <button
                                                            className="btn btn-secondary btn-sm"
                                                            onClick={(e) => {
                                                                e.stopPropagation();
                                                                setGrantTenderId(tender.tender_id);
                                                                setGrantUserId('');
                                                                setGrantPermission('viewer');
                                                            }}
                                                            style={{
                                                                marginTop: '0.75rem',
                                                                fontSize: '0.8rem',
                                                            }}
                                                        >
                                                            <UserPlus size={14} />
                                                            Aggiungi Accesso
                                                        </button>
                                                    )}
                                                </div>
                                            </motion.div>
                                        )}
                                    </AnimatePresence>
                                </motion.div>
                            );
                        })
                    )}
                </div>
            )}
        </div>
    );
}
