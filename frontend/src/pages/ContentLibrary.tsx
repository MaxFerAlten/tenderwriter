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
} from 'lucide-react';
import { contentApi, type ContentBlock, type ContentBlockCreate } from '../api/client';

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

    // New block form state
    const [formTitle, setFormTitle] = useState('');
    const [formContent, setFormContent] = useState('');
    const [formCategory, setFormCategory] = useState('');
    const [formTags, setFormTags] = useState('');

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
        if (!formTitle.trim() || !formContent.trim()) return;
        try {
            setCreating(true);
            const data: ContentBlockCreate = {
                title: formTitle,
                content: formContent,
            };
            if (formCategory) data.category = formCategory;
            if (formTags.trim()) {
                data.tags = formTags.split(',').map((t) => t.trim()).filter(Boolean);
            }
            await contentApi.create(data);
            // Reset form
            setFormTitle('');
            setFormContent('');
            setFormCategory('');
            setFormTags('');
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
                    <div className="form-group">
                        <label className="form-label">Content *</label>
                        <textarea
                            className="form-textarea"
                            placeholder="Write reusable content..."
                            style={{ minHeight: 120 }}
                            value={formContent}
                            onChange={(e) => setFormContent(e.target.value)}
                        />
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
                            disabled={creating || !formTitle.trim() || !formContent.trim()}
                        >
                            {creating ? <Loader2 size={16} className="spin" /> : <Plus size={16} />}
                            {creating ? 'Creating...' : 'Create'}
                        </button>
                        <button className="btn btn-ghost" onClick={() => setShowNewBlock(false)}>Cancel</button>
                    </div>
                </motion.div>
            )}

            {/* Loading */}
            {loading && (
                <div className="loading-spinner" style={{ padding: '3rem 0' }}>
                    <div className="spinner" />
                    <p style={{ color: 'var(--text-muted)', marginTop: '0.75rem' }}>Loading content blocks...</p>
                </div>
            )}

            {/* Content Grid */}
            {!loading && (
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

            {!loading && blocks.length === 0 && (
                <div className="empty-state">
                    <Filter size={48} />
                    <h3>No content blocks found</h3>
                    <p>{searchQuery || selectedCategory !== 'All'
                        ? 'Try adjusting your search or category filter'
                        : 'Create your first content block to get started'}
                    </p>
                </div>
            )}
        </div>
    );
}
