import { useEffect, useRef, useState } from 'react';
import { motion } from 'framer-motion';
import {
    Search as SearchIcon,
    Sparkles,
    Send,
    Square,
    FileText,
    Database,
    Network,
    AlertCircle,
    History,
    Clock
} from 'lucide-react';
import { ragApi, type RAGResponse } from '../api/client';
import {
    createSearchResultRevealState,
    finalizeSearchResults,
    noteInitialAnswerPainted,
    revealStagedSearchResults,
    stageSearchResults,
    type SearchResultRevealTransition,
} from './searchResultReveal';

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

function normalizeMatchScore(score: number): number {
    if (!Number.isFinite(score)) return 0;

    let normalized = score;
    if (score < 0 || score > 1) {
        // Cross-encoder scores are often raw logits and can be negative.
        normalized = 1 / (1 + Math.exp(-score));
    }

    return Math.max(0, Math.min(1, normalized));
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
    const streamControllerRef = useRef<AbortController | null>(null);
    const pendingTokensRef = useRef<string[]>([]);
    const answerFlushTimerRef = useRef<number | null>(null);
    const streamCompletedRef = useRef(false);
    const drainWaitersRef = useRef<Array<() => void>>([]);
    const resultsRevealFrameRef = useRef<number | null>(null);
    const resultsRevealStateRef = useRef(createSearchResultRevealState<DisplayResult>());

    useEffect(() => {
        loadHistory();
        return () => {
            streamControllerRef.current?.abort();
            cancelAnswerFlush();
            cancelSourcesReveal();
        };
    }, []);

    useEffect(() => {
        if (!answer) {
            return;
        }

        applyResultRevealTransition(noteInitialAnswerPainted(resultsRevealStateRef.current));
    }, [answer]);

    const loadHistory = async () => {
        try {
            const data = await ragApi.getHistory();
            setHistory(data);
        } catch (e) {
            console.error('Failed to load history', e);
        }
    };

    const loadHistoricalItem = (item: HistoryItem) => {
        streamControllerRef.current?.abort();
        cancelAnswerFlush();
        cancelSourcesReveal();
        setQuery(item.query);
        setAnswer(item.response);
        setResults([]);
        setHasSearched(true);
        setError(null);
        setIsSearching(false);
    };

    const resolveDrainWaiters = () => {
        if (drainWaitersRef.current.length === 0) return;
        const waiters = [...drainWaitersRef.current];
        drainWaitersRef.current = [];
        waiters.forEach((resolve) => resolve());
    };

    const applyResultRevealTransition = (
        transition: SearchResultRevealTransition<DisplayResult>
    ) => {
        resultsRevealStateRef.current = transition.nextState;

        if (transition.revealedResults !== null) {
            setResults(transition.revealedResults);
        }

        if (transition.shouldScheduleReveal) {
            scheduleSourcesReveal();
        }
    };

    const flushPendingResults = () => {
        applyResultRevealTransition(
            revealStagedSearchResults(resultsRevealStateRef.current)
        );
    };

    const scheduleSourcesReveal = () => {
        if (
            !resultsRevealStateRef.current.pendingResults
            || resultsRevealFrameRef.current !== null
        ) {
            return;
        }

        resultsRevealFrameRef.current = window.requestAnimationFrame(() => {
            resultsRevealFrameRef.current = null;
            flushPendingResults();
        });
    };

    const stageRetrievedSources = (nextResults: DisplayResult[]) => {
        applyResultRevealTransition(
            stageSearchResults(resultsRevealStateRef.current, nextResults)
        );
    };

    const cancelSourcesReveal = () => {
        if (resultsRevealFrameRef.current !== null) {
            window.cancelAnimationFrame(resultsRevealFrameRef.current);
            resultsRevealFrameRef.current = null;
        }

        resultsRevealStateRef.current = createSearchResultRevealState<DisplayResult>();
    };

    const scheduleAnswerFlush = () => {
        if (answerFlushTimerRef.current !== null) return;
        answerFlushTimerRef.current = window.setTimeout(() => {
            answerFlushTimerRef.current = null;

            if (pendingTokensRef.current.length === 0) {
                if (streamCompletedRef.current) {
                    resolveDrainWaiters();
                }
                return;
            }

            let chunkCharCount = 0;
            let chunkTokenCount = 0;
            while (pendingTokensRef.current.length > 0 && chunkTokenCount < 8 && chunkCharCount < 48) {
                chunkCharCount += pendingTokensRef.current[0].length;
                chunkTokenCount += 1;
            }

            const nextChunk = pendingTokensRef.current.splice(0, chunkTokenCount).join('');
            if (nextChunk) {
                setAnswer((current) => current + nextChunk);
            }

            if (pendingTokensRef.current.length > 0 || !streamCompletedRef.current) {
                scheduleAnswerFlush();
                return;
            }

            resolveDrainWaiters();
        }, 24);
    };

    const queueAnswerToken = (token: string) => {
        pendingTokensRef.current.push(token);
        scheduleAnswerFlush();
    };

    const markAnswerStreamCompleted = () => {
        streamCompletedRef.current = true;
        if (pendingTokensRef.current.length === 0 && answerFlushTimerRef.current === null) {
            resolveDrainWaiters();
        }
    };

    const waitForAnswerDrain = () => {
        if (streamCompletedRef.current && pendingTokensRef.current.length === 0 && answerFlushTimerRef.current === null) {
            return Promise.resolve();
        }

        return new Promise<void>((resolve) => {
            drainWaitersRef.current.push(resolve);
        });
    };

    const cancelAnswerFlush = () => {
        if (answerFlushTimerRef.current !== null) {
            window.clearTimeout(answerFlushTimerRef.current);
            answerFlushTimerRef.current = null;
        }
        pendingTokensRef.current = [];
        streamCompletedRef.current = false;
        resolveDrainWaiters();
    };

    const stopStreaming = () => {
        streamControllerRef.current?.abort();
        streamControllerRef.current = null;
        cancelAnswerFlush();
        cancelSourcesReveal();
        setIsSearching(false);
    };

    const handleSearch = async () => {
        if (!query.trim()) return;
        streamControllerRef.current?.abort();
        cancelAnswerFlush();
        cancelSourcesReveal();
        const controller = new AbortController();
        streamControllerRef.current = controller;

        setIsSearching(true);
        setHasSearched(true);
        setError(null);
        setResults([]);
        setAnswer('');

        try {
            const sourcePromise: Promise<DisplayResult[]> = ragApi.query({
                query,
                mode: 'search',
                temperature: 0.3,
            }).then((sourceData: RAGResponse) =>
                sourceData.sources.map((s) => ({
                    text: s.text,
                    score: normalizeMatchScore(s.score),
                    sources: inferSources(s.metadata),
                    metadata: s.metadata,
                }))
            );
            void sourcePromise.then((sourceData) => {
                if (!controller.signal.aborted) {
                    stageRetrievedSources(sourceData);
                }
            }).catch(() => undefined);
            void sourcePromise.catch(() => undefined);

            const streamPromise = ragApi.streamQuery({
                query,
                mode: 'qa',
                temperature: 0.3,
            }, {
                signal: controller.signal,
                onToken: (token) => {
                    queueAnswerToken(token);
                },
            });

            await streamPromise;
            markAnswerStreamCompleted();
            await waitForAnswerDrain();
            const sourceData = await sourcePromise;
            if (!controller.signal.aborted) {
                applyResultRevealTransition(
                    finalizeSearchResults(resultsRevealStateRef.current, sourceData)
                );
            }
            await loadHistory();
        } catch (err) {
            if (err instanceof DOMException && err.name === 'AbortError') {
                cancelAnswerFlush();
                cancelSourcesReveal();
                return;
            }
            cancelAnswerFlush();
            cancelSourcesReveal();
            controller.abort();
            const msg = err instanceof Error ? err.message : 'Search failed';
            setError(msg);
            // Show a helpful message if the backend is likely offline
            if (msg.includes('fetch') || msg.includes('network') || msg.includes('Failed')) {
                setError('Could not reach the backend. Make sure the API server is running on port 8000.');
            }
        } finally {
            if (streamControllerRef.current === controller) {
                streamControllerRef.current = null;
            }
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
                        No recent searches.
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
                        onClick={isSearching ? stopStreaming : handleSearch}
                        disabled={!isSearching && !query.trim()}
                        style={{
                            position: 'absolute',
                            right: '0.5rem',
                            top: '50%',
                            transform: 'translateY(-50%)',
                        }}
                    >
                        {isSearching ? (
                            <>
                                <Square size={12} /> Stop
                            </>
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
                {hasSearched && !error && (isSearching || answer || results.length > 0) && (
                    <div style={{ display: 'grid', gap: '1.5rem' }}>
                        {/* AI Answer */}
                        {(answer || isSearching) && (
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
                                    {isSearching && (
                                        <span style={{
                                            fontSize: '0.72rem',
                                            fontWeight: 700,
                                            color: 'var(--accent-blue)',
                                            padding: '0.18rem 0.5rem',
                                            borderRadius: 999,
                                            background: 'color-mix(in srgb, var(--accent-blue) 14%, transparent)',
                                        }}>
                                            Streaming...
                                        </span>
                                    )}
                                </div>
                                <div
                                    style={{ fontSize: '0.9rem', lineHeight: 1.8, color: 'var(--text-secondary)', whiteSpace: 'pre-line' }}
                                    dangerouslySetInnerHTML={{
                                        __html: answer
                                            .replace(/\*\*(.*?)\*\*/g, '<strong style="color: var(--text-primary)">$1</strong>')
                                    }}
                                />
                                {isSearching && (
                                    <div style={{ marginTop: '0.75rem', color: 'var(--text-muted)', fontSize: '0.8rem' }}>
                                        Sto scrivendo la risposta in tempo reale...
                                    </div>
                                )}
                            </motion.div>
                        )}

                        {/* No answer and no results */}
                        {!isSearching && !answer && results.length === 0 && (
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
                {isSearching && !answer && results.length === 0 && (
                    <div className="loading-spinner" style={{ flexDirection: 'column', gap: '1rem' }}>
                        <div className="spinner" />
                        <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                            Recupero le fonti e avvio la generazione streaming...
                        </p>
                    </div>
                )}
            </div>
        </div>
    );
}
