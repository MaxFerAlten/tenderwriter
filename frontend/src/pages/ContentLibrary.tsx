import { useState, useEffect, useCallback } from 'react';
import { motion } from 'framer-motion';
import {
    Plus,
    Search,
    Star,
    Copy,
    Trash2,
    Filter,
    AlertCircle,
    Loader2,
    Check,
    X,
    FileEdit,
    Sparkles,
} from 'lucide-react';
import { contentApi, type ContentBlock } from '../api/client';
import OnlyOfficeEditor from './OnlyOfficeEditor';

const CATEGORIES = [
    'All',
    'Boilerplate',
    'Team & Personnel',
    'Technical Approach',
    'Quality & Compliance',
    'Past Performance',
];

function StarRating({ rating }: { rating: number }) {
    return (
        <div style={{ display: 'flex', gap: '2px' }}>
            {[1, 2, 3, 4, 5].map((star) => (
                <Star
                    key={star}
                    size={12}
                    fill={star <= Math.round(rating) ? '#f59e0b' : 'transparent'}
                    color={star <= Math.round(rating) ? '#f59e0b' : '#64748b'}
                />
            ))}
            <span style={{ marginLeft: '0.25rem', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                {rating.toFixed(1)}
            </span>
        </div>
    );
}

export default function ContentLibrary() {
    const [blocks, setBlocks] = useState<ContentBlock[]>([]);
    const [total, setTotal] = useState(0);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [searchQuery, setSearchQuery] = useState('');
    const [selectedCategory, setSelectedCategory] = useState('All');
    const [showNewBlock, setShowNewBlock] = useState(false);
    const [creating, setCreating] = useState(false);
    const [copiedId, setCopiedId] = useState<number | null>(null);
    const [deletingId, setDeletingId] = useState<number | null>(null);
    const [editingBlock, setEditingBlock] = useState<ContentBlock | null>(null);
    const [isFullEdit, setIsFullEdit] = useState(false);

    // New block form state
    const [formTitle, setFormTitle] = useState('');
    const [formCategory, setFormCategory] = useState('');
    const [formTags, setFormTags] = useState('');
    const [createDocKey, setCreateDocKey] = useState<string | null>(null);

    const loadBlocks = useCallback(async () => {
        try {
            setLoading(true);
            setError(null);
            const params: Record<string, string> = { limit: '50' };
            if (searchQuery) params.search = searchQuery;
            if (selectedCategory !== 'All') params.category = selectedCategory;
            const data = await contentApi.list(params);
            setBlocks(data.items);
            setTotal(data.total);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to load content blocks');
        } finally {
            setLoading(false);
        }
    }, [searchQuery, selectedCategory]);

    useEffect(() => {
        loadBlocks();
    }, [loadBlocks]);

    const handleCreate = async () => {
        if (!formTitle.trim()) return;
        try {
            setCreating(true);
            const data: any = {
                title: formTitle,
                content: ' ', // Satisfy backend if not using ONLYOFFICE
                onlyoffice_key: createDocKey,
            };
            if (formCategory) data.category = formCategory;
            if (formTags.trim()) {
                data.tags = formTags.split(',').map((t) => t.trim()).filter(Boolean);
            }
            await contentApi.create(data);

            // Reset form
            setFormTitle('');
            setFormCategory('');
            setFormTags('');
            setCreateDocKey(null);
            setShowNewBlock(false);

            await loadBlocks();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to create content block');
        } finally {
            setCreating(false);
        }
    };

    const handleCopy = (block: ContentBlock) => {
        navigator.clipboard.writeText(block.content).then(() => {
            setCopiedId(block.id);
            setTimeout(() => setCopiedId(null), 2000);
        });
    };

    const handleDelete = async (blockId: number) => {
        try {
            setDeletingId(blockId);
            await contentApi.delete(blockId);
            await loadBlocks();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to delete block');
        } finally {
            setDeletingId(null);
        }
    };

    // Debounced search
    const [searchTimer, setSearchTimer] = useState<ReturnType<typeof setTimeout> | null>(null);
    const handleSearchChange = (value: string) => {
        setSearchQuery(value);
        if (searchTimer) clearTimeout(searchTimer);
        setSearchTimer(
            setTimeout(() => {
                // loadBlocks will fire via useEffect dep on searchQuery
            }, 300)
        );
    };

    return (
        <div className="animate-in">
            <div className="page-header">
                <div>
                    <h1 className="page-title">Content Library</h1>
                    <p className="page-subtitle">
                        Reusable content blocks for rapid proposal assembly
                        {!loading && <> — {total} blocks</>}
                    </p>
                </div>
                <button className="btn btn-primary" onClick={() => setShowNewBlock(!showNewBlock)}>
                    <Plus size={18} />
                    New Block
                </button>
            </div>

            {/* Error */}
            {error && (
                <div className="card" style={{ borderColor: '#ef4444', marginBottom: '1.5rem', display: 'flex', alignItems: 'center', gap: '0.75rem', color: '#ef4444' }}>
                    <AlertCircle size={18} />
                    <span>{error}</span>
                    <button className="btn btn-ghost btn-sm" onClick={() => setError(null)} style={{ marginLeft: 'auto' }}>
                        <X size={14} />
                    </button>
                </div>
            )}

            {/* Search */}
            <div className="search-container">
                <Search size={18} className="search-icon" />
                <input
                    className="search-input"
                    placeholder="Search content blocks by title, content, or tags..."
                    value={searchQuery}
                    onChange={(e) => handleSearchChange(e.target.value)}
                />
            </div>

            {/* Category Filters */}
            <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1.5rem', flexWrap: 'wrap' }}>
                {CATEGORIES.map((cat) => (
                    <button
                        key={cat}
                        className={`btn btn-sm ${selectedCategory === cat ? 'btn-primary' : 'btn-secondary'}`}
                        onClick={() => setSelectedCategory(cat)}
                        style={{ fontSize: '0.8rem' }}
                    >
                        {cat}
                    </button>
                ))}
            </div>

            {/* New Block Form */}
            {showNewBlock && (
                <motion.div
                    className="card"
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: 'auto' }}
                    style={{ marginBottom: '1.5rem' }}
                >
                    <h3 style={{ marginBottom: '1rem' }}>New Content Block</h3>
                    <div className="form-group">
                        <label className="form-label">Title *</label>
                        <input
                            className="form-input"
                            placeholder="e.g., Bridge Engineering Experience"
                            value={formTitle}
                            onChange={(e) => setFormTitle(e.target.value)}
                        />
                    </div>
                    <div className="form-group" style={{ display: 'flex', flexDirection: 'column' }}>
                        <label className="form-label">Content *</label>
                        <div style={{ minHeight: '600px', height: '600px', marginBottom: '1.5rem', background: 'var(--bg-secondary)', borderRadius: 'var(--radius-md)', overflow: 'hidden' }}>
                            <OnlyOfficeEditor
                                mode="create"
                                title={formTitle || 'Nuovo Blocco'}
                                onlyofficeApiUrl={(import.meta as any).env?.VITE_ONLYOFFICE_URL || 'http://localhost:8443'}
                                onConfigLoaded={(cfg) => setCreateDocKey(cfg.config.document.key)}
                            />
                        </div>
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                        <div className="form-group">
                            <label className="form-label">Category</label>
                            <select
                                className="form-select"
                                value={formCategory}
                                onChange={(e) => setFormCategory(e.target.value)}
                            >
                                <option value="">Select...</option>
                                {CATEGORIES.filter((c) => c !== 'All').map((cat) => (
                                    <option key={cat}>{cat}</option>
                                ))}
                            </select>
                        </div>
                        <div className="form-group">
                            <label className="form-label">Tags (comma-separated)</label>
                            <input
                                className="form-input"
                                placeholder="bridge, engineering, cv"
                                value={formTags}
                                onChange={(e) => setFormTags(e.target.value)}
                            />
                        </div>
                    </div>
                    <div style={{ display: 'flex', gap: '0.75rem' }}>
                        <button
                            className="btn btn-primary"
                            onClick={handleCreate}
                            disabled={creating || !formTitle.trim()}
                        >
                            {creating ? <Loader2 size={16} className="spin" /> : <Plus size={16} />}
                            {creating ? 'Creating...' : 'Create Block'}
                        </button>
                        <button className="btn btn-ghost" onClick={() => {
                            setShowNewBlock(false);
                            setFormTitle('');
                            setCreateDocKey(null);
                        }}>Cancel</button>
                    </div>
                </motion.div>
            )}

            {/* Loading */}
            {loading && !searchQuery && (
                <div className="loading-spinner" style={{ padding: '3rem 0' }}>
                    <div className="spinner" />
                    <p style={{ color: 'var(--text-muted)', marginTop: '0.75rem' }}>Loading content blocks...</p>
                </div>
            )}

            {/* Inline Editor for Existing Block */}
            {editingBlock && !isFullEdit && (
                <motion.div
                    className="card"
                    initial={{ opacity: 0, scale: 0.98 }}
                    animate={{ opacity: 1, scale: 1 }}
                    style={{ marginBottom: '1.5rem', borderLeft: '4px solid var(--accent-blue)' }}
                >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
                        <div>
                            <h3 style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                <FileEdit size={20} color="var(--accent-blue)" />
                                Editing: {editingBlock.title}
                            </h3>
                            <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                                {editingBlock.category || 'Uncategorized'}
                            </p>
                        </div>
                        <div style={{ display: 'flex', gap: '0.5rem' }}>
                            <button
                                className="btn btn-secondary btn-sm"
                                onClick={() => setIsFullEdit(true)}
                                title="Open in Full Screen Modal"
                            >
                                <Sparkles size={14} />
                                Full Edit
                            </button>
                            <button
                                className="btn btn-ghost btn-sm btn-icon"
                                onClick={() => {
                                    setEditingBlock(null);
                                    loadBlocks();
                                }}
                            >
                                <X size={18} />
                            </button>
                        </div>
                    </div>

                    <div style={{ minHeight: '600px', height: '600px', marginBottom: '1rem', background: 'var(--bg-secondary)', borderRadius: 'var(--radius-md)', overflow: 'hidden' }}>
                        <OnlyOfficeEditor
                            mode="library"
                            libraryBlockId={editingBlock.id}
                            title={editingBlock.title}
                            onlyofficeApiUrl={(import.meta as any).env?.VITE_ONLYOFFICE_URL || 'http://localhost:8443'}
                        />
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                        <button
                            className="btn btn-secondary"
                            onClick={() => {
                                setEditingBlock(null);
                                loadBlocks();
                            }}
                        >
                            Done Editing
                        </button>
                    </div>
                </motion.div>
            )}

            {/* Content Grid - Hidden when editing inline */}
            {!loading && !editingBlock && (
                <div className="content-grid">
                    {blocks.map((block, i) => (
                        <motion.div
                            key={block.id}
                            className="content-card"
                            initial={{ opacity: 0, y: 10 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ delay: i * 0.05 }}
                        >
                            <div className="card-header">
                                <div>
                                    <div className="card-title">{block.title}</div>
                                    <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                                        {block.category || 'Uncategorized'}
                                    </span>
                                </div>
                                <div style={{ display: 'flex', gap: '0.25rem' }}>
                                    <button
                                        className="btn btn-ghost btn-icon btn-sm"
                                        title="Edit in OnlyOffice"
                                        onClick={() => setEditingBlock(block)}
                                    >
                                        <FileEdit size={14} />
                                    </button>
                                    <button
                                        className="btn btn-ghost btn-icon btn-sm"
                                        title="Copy to clipboard"
                                        onClick={() => handleCopy(block)}
                                    >
                                        {copiedId === block.id ? <Check size={14} color="#10b981" /> : <Copy size={14} />}
                                    </button>
                                    <button
                                        className="btn btn-ghost btn-icon btn-sm"
                                        title="Delete"
                                        onClick={() => handleDelete(block.id)}
                                        disabled={deletingId === block.id}
                                    >
                                        {deletingId === block.id ? <Loader2 size={14} className="spin" /> : <Trash2 size={14} />}
                                    </button>
                                </div>
                            </div>

                            <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', lineHeight: 1.6, marginBottom: '0.75rem' }}>
                                {block.content.length > 180 ? block.content.slice(0, 180) + '...' : block.content}
                            </p>

                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                <StarRating rating={block.quality_rating} />
                                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                                    Used {block.usage_count}×
                                </span>
                            </div>

                            {block.tags && block.tags.length > 0 && (
                                <div className="content-card-tags">
                                    {block.tags.map((tag) => (
                                        <span key={tag} className="tag">{tag}</span>
                                    ))}
                                </div>
                            )}
                        </motion.div>
                    ))}
                </div>
            )}

            {!loading && blocks.length === 0 && !editingBlock && (
                <div className="empty-state">
                    <Filter size={48} />
                    <h3>No content blocks found</h3>
                    <p>{searchQuery || selectedCategory !== 'All'
                        ? 'Try adjusting your search or category filter'
                        : 'Create your first content block to get started'}
                    </p>
                </div>
            )}

            {/* OnlyOffice Editor Modal - Now triggered only by isFullEdit */}
            {editingBlock && isFullEdit && (
                <motion.div
                    className="modal-backdrop"
                    style={{ zIndex: 100, padding: '1rem' }}
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                >
                    <motion.div
                        className="modal"
                        style={{ width: '100%', height: '95vh', display: 'flex', flexDirection: 'column' }}
                        initial={{ scale: 0.95, opacity: 0 }}
                        animate={{ scale: 1, opacity: 1 }}
                    >
                        <div className="modal-header" style={{ padding: '1rem 1.5rem', borderBottom: '1px solid var(--border-default)' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                                <Sparkles size={20} color="var(--accent-blue)" />
                                <h2 style={{ margin: 0 }}>Full Edit: {editingBlock.title}</h2>
                            </div>
                            <button
                                className="btn btn-primary btn-sm"
                                onClick={() => setIsFullEdit(false)}
                            >
                                Exit Full Screen
                            </button>
                        </div>
                        <div className="modal-body" style={{ flex: 1, padding: 0, overflow: 'hidden' }}>
                            <OnlyOfficeEditor
                                mode="library"
                                libraryBlockId={editingBlock.id}
                                title={editingBlock.title}
                                onlyofficeApiUrl={(import.meta as any).env?.VITE_ONLYOFFICE_URL || 'http://localhost:8443'}
                            />
                        </div>
                    </motion.div>
                </motion.div>
            )}
        </div>
    );
}
