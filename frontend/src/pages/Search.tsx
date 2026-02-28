import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import {
    Search as SearchIcon,
    Sparkles,
    Send,
    FileText,
    Database,
    Network,
    AlertCircle,
    History,
    Clock
} from 'lucide-react';
import { ragApi, type RAGResponse } from '../api/client';

interface DisplayResult {
    text: string;
    score: number;
    sources: string[];
    metadata: Record<string, unknown>;
}

interface HistoryItem {
    id: number;
    query: string;
    response: string;
    created_at: string;
}

function SourceBadge({ source }: { source: string }) {
    const config: Record<string, { icon: typeof FileText; label: string; color: string }> = {
        dense: { icon: Database, label: 'Vector', color: 'var(--accent-blue)' },
        sparse: { icon: FileText, label: 'BM25', color: 'var(--accent-amber)' },
        graph: { icon: Network, label: 'Graph', color: 'var(--accent-purple)' },
    };
    const c = config[source] || config.dense;

    return (
        <span style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '0.25rem',
            padding: '0.15rem 0.45rem',
            borderRadius: 100,
            fontSize: '0.68rem',
            fontWeight: 600,
            background: `color-mix(in srgb, ${c.color} 15%, transparent)`,
            color: c.color,
        }}>
            <c.icon size={10} />
            {c.label}
        </span>
    );
}

export default function RAGSearch() {
    const [query, setQuery] = useState('');
    const [results, setResults] = useState<DisplayResult[]>([]);
    const [answer, setAnswer] = useState('');
    const [isSearching, setIsSearching] = useState(false);
    const [hasSearched, setHasSearched] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [history, setHistory] = useState<HistoryItem[]>([]);

    useEffect(() => {
        loadHistory();
    }, []);

    const loadHistory = async () => {
        try {
            const data = await ragApi.getHistory();
            setHistory(data);
        } catch (e) {
            console.error('Failed to load history', e);
        }
    };

    const loadHistoricalItem = (item: HistoryItem) => {
        setQuery(item.query);
        setAnswer(item.response);
        setResults([]);
        setHasSearched(true);
        setError(null);
    };

    const handleSearch = async () => {
        if (!query.trim()) return;

        setIsSearching(true);
        setHasSearched(true);
        setError(null);
        setResults([]);
        setAnswer('');

        try {
            const data: RAGResponse = await ragApi.query({
                query: query,
                mode: 'qa',
                temperature: 0.3,
            });

            setAnswer(data.answer || '');
            setResults(
                data.sources.map((s) => ({
                    text: s.text,
                    score: s.score,
                    sources: inferSources(s.metadata),
                    metadata: s.metadata,
                }))
            );
            loadHistory(); // refresh history after a new search
        } catch (err) {
            const msg = err instanceof Error ? err.message : 'Search failed';
            setError(msg);
            // Show a helpful message if the backend is likely offline
            if (msg.includes('fetch') || msg.includes('network') || msg.includes('Failed')) {
                setError('Could not reach the backend. Make sure the API server is running on port 8000.');
            }
        } finally {
            setIsSearching(false);
        }
    };

    // Infer which retriever contributed based on metadata
    const inferSources = (metadata: Record<string, unknown>): string[] => {
        const sources: string[] = [];
        const src = String(metadata.source || '');
        if (src.includes('knowledge_graph') || src.includes('graph')) sources.push('graph');
        if (src.includes('qdrant') || src.includes('vector') || src.includes('dense')) sources.push('dense');
        if (src.includes('bm25') || src.includes('sparse')) sources.push('sparse');
        // Default: show dense if we can't determine the source
        if (sources.length === 0) sources.push('dense');
        return sources;
    };

    return (
        <div className="animate-in" style={{ display: 'grid', gridTemplateColumns: '300px 1fr', gap: '2rem', height: '100%' }}>
            {/* Sidebar History */}
            <div style={{ borderRight: '1px solid var(--border-color)', paddingRight: '1rem', display: 'flex', flexDirection: 'column', height: '100%', overflowY: 'auto' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1.5rem', color: 'var(--text-primary)' }}>
                    <History size={18} />
                    <h3 style={{ fontSize: '1.1rem', margin: 0 }}>Cronologia</h3>
                </div>

                {history.length === 0 ? (
                    <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', textAlign: 'center', marginTop: '2rem' }}>
                        Nessuna ricerca recente.
                    </p>
                ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                        {history.map(item => (
                            <button
                                key={item.id}
                                onClick={() => loadHistoricalItem(item)}
                                className="history-item-btn"
                                style={{
                                    textAlign: 'left',
                                    background: 'var(--bg-secondary)',
                                    border: '1px solid var(--border-color)',
                                    padding: '0.75rem',
                                    borderRadius: '8px',
                                    cursor: 'pointer',
                                    transition: 'all 0.2s ease',
                                }}
                            >
                                <div style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '0.25rem', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                                    {item.query}
                                </div>
                                <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                                    <Clock size={10} />
                                    {new Date(item.created_at).toLocaleString()}
                                </div>
                            </button>
                        ))}
                    </div>
                )}
            </div>

            {/* Main Search Area */}
            <div style={{ paddingRight: '1rem', overflowY: 'auto', paddingBottom: '3rem' }}>
                <div className="page-header">
                    <div>
                        <h1 className="page-title">
                            <Sparkles size={28} color="#60a5fa" style={{ verticalAlign: 'middle', marginRight: 8 }} />
                            AI Search
                        </h1>
                        <p className="page-subtitle">
                            Search your knowledge base with HybridRAG — vectors + keywords + knowledge graph
                        </p>
                    </div>
                </div>

                {/* Search Bar */}
                <div style={{ position: 'relative', marginBottom: '2rem' }}>
                    <SearchIcon
                        size={20}
                        style={{
                            position: 'absolute',
                            left: '1.25rem',
                            top: '50%',
                            transform: 'translateY(-50%)',
                            color: 'var(--text-muted)',
                        }}
                    />
                    <input
                        className="search-input"
                        placeholder="Ask anything about your proposals, team, projects..."
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                        onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                        style={{ paddingLeft: '3.25rem', paddingRight: '5rem' }}
                    />
                    <button
                        className="btn btn-primary btn-sm"
                        onClick={handleSearch}
                        disabled={isSearching || !query.trim()}
                        style={{
                            position: 'absolute',
                            right: '0.5rem',
                            top: '50%',
                            transform: 'translateY(-50%)',
                        }}
                    >
                        {isSearching ? (
                            <div className="spinner" style={{ width: 16, height: 16, borderWidth: 2 }} />
                        ) : (
                            <>
                                <Send size={14} /> Search
                            </>
                        )}
                    </button>
                </div>

                {/* Error */}
                {error && (
                    <div className="card" style={{ borderColor: '#ef4444', marginBottom: '1.5rem', display: 'flex', alignItems: 'center', gap: '0.75rem', color: '#ef4444' }}>
                        <AlertCircle size={18} />
                        <span>{error}</span>
                    </div>
                )}

                {/* Example Queries */}
                {!hasSearched && (
                    <div style={{ textAlign: 'center', padding: '2rem 0' }}>
                        <p style={{ color: 'var(--text-muted)', marginBottom: '1.5rem' }}>
                            Try searching across your entire knowledge base:
                        </p>
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', justifyContent: 'center' }}>
                            {[
                                'Bridge rehabilitation experience',
                                'Team members with PMP certification',
                                'Past projects for DOT clients',
                                'Environmental compliance methodology',
                                'IT infrastructure proposals',
                            ].map((example) => (
                                <button
                                    key={example}
                                    className="btn btn-secondary btn-sm"
                                    onClick={() => setQuery(example)}
                                    style={{ fontSize: '0.82rem' }}
                                >
                                    {example}
                                </button>
                            ))}
                        </div>
                    </div>
                )}

                {/* Results */}
                {hasSearched && !isSearching && !error && (
                    <div style={{ display: 'grid', gap: '1.5rem' }}>
                        {/* AI Answer */}
                        {answer && (
                            <motion.div
                                className="card"
                                initial={{ opacity: 0, y: 10 }}
                                animate={{ opacity: 1, y: 0 }}
                                style={{ borderColor: 'var(--border-accent)' }}
                            >
                                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem' }}>
                                    <Sparkles size={18} color="#60a5fa" />
                                    <h3 style={{ fontSize: '1rem' }}>AI Answer</h3>
                                    <span className="ai-badge">HybridRAG</span>
                                </div>
                                <div
                                    style={{ fontSize: '0.9rem', lineHeight: 1.8, color: 'var(--text-secondary)', whiteSpace: 'pre-line' }}
                                    dangerouslySetInnerHTML={{
                                        __html: answer
                                            .replace(/\*\*(.*?)\*\*/g, '<strong style="color: var(--text-primary)">$1</strong>')
                                    }}
                                />
                            </motion.div>
                        )}

                        {/* No answer and no results */}
                        {!answer && results.length === 0 && (
                            <div className="empty-state" style={{ padding: '2rem 0' }}>
                                <SearchIcon size={48} />
                                <h3>No results found</h3>
                                <p>Try a different query, or ingest some documents first</p>
                            </div>
                        )}

                        {/* Source Documents */}
                        {results.length > 0 && (
                            <>
                                <h3 style={{ fontSize: '0.85rem', textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text-muted)' }}>
                                    Retrieved Sources ({results.length})
                                </h3>

                                {results.map((result, i) => (
                                    <motion.div
                                        key={i}
                                        className="card"
                                        initial={{ opacity: 0, y: 10 }}
                                        animate={{ opacity: 1, y: 0 }}
                                        transition={{ delay: i * 0.08 }}
                                        style={{ padding: '1.25rem' }}
                                    >
                                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.5rem' }}>
                                            <div style={{ display: 'flex', gap: '0.35rem', flexWrap: 'wrap' }}>
                                                {result.sources.map((s) => (
                                                    <SourceBadge key={s} source={s} />
                                                ))}
                                            </div>
                                            <span style={{
                                                fontSize: '0.75rem',
                                                fontWeight: 700,
                                                color: result.score > 0.85
                                                    ? 'var(--accent-green)'
                                                    : result.score > 0.7
                                                        ? 'var(--accent-amber)'
                                                        : 'var(--text-muted)',
                                            }}>
                                                {(result.score * 100).toFixed(0)}% match
                                            </span>
                                        </div>

                                        <p style={{ fontSize: '0.9rem', lineHeight: 1.7, color: 'var(--text-secondary)', marginBottom: '0.5rem' }}>
                                            {result.text}
                                        </p>

                                        {Object.keys(result.metadata).length > 0 && (
                                            <div style={{ display: 'flex', gap: '0.75rem', fontSize: '0.75rem', color: 'var(--text-muted)', flexWrap: 'wrap' }}>
                                                {Object.entries(result.metadata).map(([key, value]) => (
                                                    <span key={key}>
                                                        <strong>{key}:</strong> {String(value)}
                                                    </span>
                                                ))}
                                            </div>
                                        )}
                                    </motion.div>
                                ))}
                            </>
                        )}
                    </div>
                )}

                {/* Loading */}
                {isSearching && (
                    <div className="loading-spinner" style={{ flexDirection: 'column', gap: '1rem' }}>
                        <div className="spinner" />
                        <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                            Searching vectors, keywords, and knowledge graph...
                        </p>
                    </div>
                )}
            </div>
        </div>
    );
}
