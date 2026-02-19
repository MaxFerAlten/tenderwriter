import { useState } from 'react';
import { motion } from 'framer-motion';
import {
    Plus,
    Search,
    Star,
    Copy,
    Edit3,
    Filter,
} from 'lucide-react';

const DEMO_BLOCKS = [
    {
        id: 1,
        title: 'Company Overview — Standard',
        content: 'Founded in 2005, our firm has grown to become a leading provider of engineering and consulting services, with a proven track record across infrastructure, environmental, and technology sectors. We employ over 200 professionals across 5 regional offices.',
        category: 'Boilerplate',
        tags: ['company', 'overview', 'about-us'],
        usage_count: 24,
        quality_rating: 4.5,
    },
    {
        id: 2,
        title: 'Bridge Engineering — Team CVs',
        content: 'Our bridge engineering team is led by Dr. Sarah Chen, PE, SE, who has 22 years of experience in structural analysis, seismic retrofit design, and load rating analysis. She has directed over 40 bridge projects valued at $500M+.',
        category: 'Team & Personnel',
        tags: ['team', 'bridge', 'cv', 'engineering'],
        usage_count: 18,
        quality_rating: 4.8,
    },
    {
        id: 3,
        title: 'Quality Assurance Program',
        content: 'Our ISO 9001:2015 certified Quality Management System ensures consistent delivery of high-quality services. We implement a three-tier QA/QC review process with independent verification at each project milestone.',
        category: 'Quality & Compliance',
        tags: ['quality', 'iso-9001', 'compliance'],
        usage_count: 31,
        quality_rating: 4.2,
    },
    {
        id: 4,
        title: 'Environmental Sustainability Approach',
        content: 'We integrate sustainable practices throughout our project lifecycle. Our environmental management approach includes carbon footprint analysis, LEED compliance support, and innovative green infrastructure solutions that minimize environmental impact.',
        category: 'Technical Approach',
        tags: ['sustainability', 'environment', 'leed', 'green'],
        usage_count: 12,
        quality_rating: 3.9,
    },
    {
        id: 5,
        title: 'Safety Record & OSHA Compliance',
        content: 'We maintain an exemplary safety record with an EMR of 0.72 and zero lost-time incidents over the past 3 years. All field personnel hold OSHA 30-hour certifications, and we conduct weekly toolbox talks on every active project.',
        category: 'Quality & Compliance',
        tags: ['safety', 'osha', 'compliance', 'ehs'],
        usage_count: 22,
        quality_rating: 4.6,
    },
    {
        id: 6,
        title: 'IT Infrastructure Modernization Experience',
        content: 'Our IT consulting division has successfully delivered 60+ enterprise modernization projects, including cloud migration, legacy system integration, and cybersecurity enhancement programs for government and Fortune 500 clients.',
        category: 'Past Performance',
        tags: ['it', 'technology', 'modernization', 'cloud'],
        usage_count: 8,
        quality_rating: 4.1,
    },
];

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
    const [searchQuery, setSearchQuery] = useState('');
    const [selectedCategory, setSelectedCategory] = useState('All');
    const [showNewBlock, setShowNewBlock] = useState(false);

    const filtered = DEMO_BLOCKS.filter((block) => {
        const matchesCategory = selectedCategory === 'All' || block.category === selectedCategory;
        const matchesSearch =
            !searchQuery ||
            block.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
            block.content.toLowerCase().includes(searchQuery.toLowerCase()) ||
            block.tags.some((t) => t.includes(searchQuery.toLowerCase()));
        return matchesCategory && matchesSearch;
    });

    return (
        <div className="animate-in">
            <div className="page-header">
                <div>
                    <h1 className="page-title">Content Library</h1>
                    <p className="page-subtitle">
                        Reusable content blocks for rapid proposal assembly
                    </p>
                </div>
                <button className="btn btn-primary" onClick={() => setShowNewBlock(!showNewBlock)}>
                    <Plus size={18} />
                    New Block
                </button>
            </div>

            {/* Search */}
            <div className="search-container">
                <Search size={18} className="search-icon" />
                <input
                    className="search-input"
                    placeholder="Search content blocks by title, content, or tags..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
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
                        <label className="form-label">Title</label>
                        <input className="form-input" placeholder="e.g., Bridge Engineering Experience" />
                    </div>
                    <div className="form-group">
                        <label className="form-label">Content</label>
                        <textarea className="form-textarea" placeholder="Write reusable content..." style={{ minHeight: 120 }} />
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                        <div className="form-group">
                            <label className="form-label">Category</label>
                            <select className="form-select">
                                <option value="">Select...</option>
                                {CATEGORIES.filter((c) => c !== 'All').map((cat) => (
                                    <option key={cat}>{cat}</option>
                                ))}
                            </select>
                        </div>
                        <div className="form-group">
                            <label className="form-label">Tags (comma-separated)</label>
                            <input className="form-input" placeholder="bridge, engineering, cv" />
                        </div>
                    </div>
                    <div style={{ display: 'flex', gap: '0.75rem' }}>
                        <button className="btn btn-primary"><Plus size={16} /> Create</button>
                        <button className="btn btn-ghost" onClick={() => setShowNewBlock(false)}>Cancel</button>
                    </div>
                </motion.div>
            )}

            {/* Content Grid */}
            <div className="content-grid">
                {filtered.map((block, i) => (
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
                                    {block.category}
                                </span>
                            </div>
                            <div style={{ display: 'flex', gap: '0.25rem' }}>
                                <button className="btn btn-ghost btn-icon btn-sm" title="Copy"><Copy size={14} /></button>
                                <button className="btn btn-ghost btn-icon btn-sm" title="Edit"><Edit3 size={14} /></button>
                            </div>
                        </div>

                        <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', lineHeight: 1.6, marginBottom: '0.75rem' }}>
                            {block.content.slice(0, 180)}...
                        </p>

                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <StarRating rating={block.quality_rating} />
                            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                                Used {block.usage_count}×
                            </span>
                        </div>

                        <div className="content-card-tags">
                            {block.tags.map((tag) => (
                                <span key={tag} className="tag">{tag}</span>
                            ))}
                        </div>
                    </motion.div>
                ))}
            </div>

            {filtered.length === 0 && (
                <div className="empty-state">
                    <Filter size={48} />
                    <h3>No matching content blocks</h3>
                    <p>Try adjusting your search or category filter</p>
                </div>
            )}
        </div>
    );
}
