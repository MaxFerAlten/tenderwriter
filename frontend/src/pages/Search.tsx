import { useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
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
    Clock,
    Trash2,
    Loader2,
    SlidersHorizontal,
    RotateCcw,
    X,
} from 'lucide-react';
import { ragApi, tenderApi, type RAGResponse, type Tender } from '../api/client';
import {
    createSearchResultRevealState,
    finalizeSearchResults,
    noteInitialAnswerPainted,
    revealStagedSearchResults,
    stageSearchResults,
    type SearchResultRevealTransition,
} from './searchResultReveal';
import { sanitizeSearchAnswer } from './searchAnswerSanitizer';
import { collapseDuplicateSearchHistory } from './searchHistoryUtils';
import {
    buildRagSearchPayload,
    cloneSearchSettings,
    DEFAULT_SEARCH_SETTINGS,
    getSearchPresetConfig,
    getSearchSettingsSummary,
    GLOBAL_SEARCH_SCOPE,
    normalizeSearchSettings,
    toggleRetriever,
    type RetrieverKey,
    type SearchPreset,
    type SearchScope,
    type SearchSettingsState,
} from './searchSettings';

const SCOPE_STORAGE_KEY = 'tw.search.scope';

function loadStoredScope(): SearchScope {
    if (typeof window === 'undefined') {
        return GLOBAL_SEARCH_SCOPE;
    }
    try {
        const raw = window.localStorage.getItem(SCOPE_STORAGE_KEY);
        if (!raw) return GLOBAL_SEARCH_SCOPE;
        const parsed = JSON.parse(raw) as Partial<SearchScope>;
        if (parsed.route_key === 'tender' && typeof parsed.tender_id === 'number') {
            return { route_key: 'tender', tender_id: parsed.tender_id };
        }
        return GLOBAL_SEARCH_SCOPE;
    } catch {
        return GLOBAL_SEARCH_SCOPE;
    }
}

function persistScope(scope: SearchScope): void {
    if (typeof window === 'undefined') return;
    try {
        window.localStorage.setItem(SCOPE_STORAGE_KEY, JSON.stringify(scope));
    } catch {
        // ignore quota errors
    }
}

interface DisplayResult {
    text: string;
    score: number;
    sources: string[];
    source_scores: Record<string, number>;
    metadata: Record<string, unknown>;
}

interface HistoryItem {
    id: number;
    query: string;
    response: string;
    created_at: string;
}

interface SearchResultsVisibilityInput {
    hasSearched: boolean;
    isSearching: boolean;
    visibleAnswer: string;
    resultsLength: number;
}

interface SearchEmptyStateInput {
    isSearching: boolean;
    visibleAnswer: string;
    resultsLength: number;
    error: string | null;
}

const TRANSPORT_ERROR_PATTERNS: RegExp[] = [
    /TypeError:\s*Failed to fetch/i,
    /TypeError:\s*Load failed/i,
    /NetworkError\b/i,
    /ERR_CONNECTION_REFUSED/i,
    /ERR_NETWORK/i,
    /^Failed to fetch$/i,
    /^Load failed$/i,
];

export function normalizeSearchErrorMessage(message: string): string {
    if (TRANSPORT_ERROR_PATTERNS.some((pattern) => pattern.test(message))) {
        return 'Could not reach the backend. Make sure the API server is running on port 8000.';
    }
    return message;
}

export function shouldShowSearchResults(input: SearchResultsVisibilityInput): boolean {
    return (
        input.hasSearched
        && (input.isSearching || Boolean(input.visibleAnswer) || input.resultsLength > 0)
    );
}

export function shouldShowEmptySearchState(input: SearchEmptyStateInput): boolean {
    return !input.isSearching && !input.visibleAnswer && input.resultsLength === 0 && !input.error;
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

function SourceBadge({ source, pct }: { source: string; pct?: number }) {
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
            {c.label}{pct !== undefined ? ` ${pct}%` : ''}
        </span>
    );
}

const SEARCH_PRESET_DETAILS: Array<{
    key: Exclude<SearchPreset, 'custom'>;
    title: string;
    description: string;
}> = [
    {
        key: 'balanced',
        title: 'Balanced',
        description: 'Matches the current HybridRAG behavior with an even mix of precision and coverage.',
    },
    {
        key: 'precise',
        title: 'Precise',
        description: 'Lowers temperature and favors tighter, more stable vector/BM25 matches.',
    },
    {
        key: 'exploratory',
        title: 'Exploratory',
        description: 'Broadens retrieved context and gives more influence to the knowledge graph.',
    },
];

export default function RAGSearch() {
    const [query, setQuery] = useState('');
    const [results, setResults] = useState<DisplayResult[]>([]);
    const [answer, setAnswer] = useState('');
    const [isSearching, setIsSearching] = useState(false);
    const [hasSearched, setHasSearched] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [history, setHistory] = useState<HistoryItem[]>([]);
    const [isClearingHistory, setIsClearingHistory] = useState(false);
    const [searchSettings, setSearchSettings] = useState<SearchSettingsState>(() => cloneSearchSettings(DEFAULT_SEARCH_SETTINGS));
    const [draftSearchSettings, setDraftSearchSettings] = useState<SearchSettingsState>(() => cloneSearchSettings(DEFAULT_SEARCH_SETTINGS));
    const [showSettingsModal, setShowSettingsModal] = useState(false);
    const [scope, setScope] = useState<SearchScope>(() => loadStoredScope());
    const [accessibleTenders, setAccessibleTenders] = useState<Tender[]>([]);
    const streamControllerRef = useRef<AbortController | null>(null);
    const rawAnswerRef = useRef('');
    const pendingTokensRef = useRef<string[]>([]);
    const answerFlushTimerRef = useRef<number | null>(null);
    const streamCompletedRef = useRef(false);
    const drainWaitersRef = useRef<Array<() => void>>([]);
    const resultsRevealFrameRef = useRef<number | null>(null);
    const resultsRevealStateRef = useRef(createSearchResultRevealState<DisplayResult>());

    useEffect(() => {
        loadHistory();
        loadAccessibleTenders();
        return () => {
            streamControllerRef.current?.abort();
            cancelAnswerFlush();
            cancelSourcesReveal();
        };
    }, []);

    useEffect(() => {
        const visibleAnswer = sanitizeSearchAnswer(answer);
        if (!visibleAnswer) {
            return;
        }

        applyResultRevealTransition(noteInitialAnswerPainted(resultsRevealStateRef.current));
    }, [answer]);

    const loadHistory = async () => {
        try {
            const data = await ragApi.getHistory();
            setHistory(collapseDuplicateSearchHistory(data));
        } catch (e) {
            console.error('Failed to load history', e);
        }
    };

    const loadAccessibleTenders = async () => {
        try {
            const data = await tenderApi.list();
            setAccessibleTenders(data.items);
            setScope((current) => {
                if (current.route_key !== 'tender') return current;
                if (data.items.some((t) => t.id === current.tender_id)) return current;
                const fallback = GLOBAL_SEARCH_SCOPE;
                persistScope(fallback);
                return fallback;
            });
        } catch (e) {
            console.error('Failed to load tenders', e);
        }
    };

    const handleScopeChange = (value: string) => {
        const next: SearchScope = value === 'global'
            ? GLOBAL_SEARCH_SCOPE
            : { route_key: 'tender', tender_id: Number(value) };
        setScope(next);
        persistScope(next);
    };

    const loadHistoricalItem = (item: HistoryItem) => {
        streamControllerRef.current?.abort();
        cancelAnswerFlush();
        cancelSourcesReveal();
        setQuery(item.query);
        rawAnswerRef.current = item.response;
        setAnswer(sanitizeSearchAnswer(item.response));
        setResults([]);
        setHasSearched(true);
        setError(null);
        setIsSearching(false);
    };

    const handleClearHistory = async () => {
        if (history.length === 0 || isClearingHistory) {
            return;
        }

        if (!window.confirm('Azzerare tutta la cronologia delle ricerche?')) {
            return;
        }

        try {
            setIsClearingHistory(true);
            setError(null);
            await ragApi.clearHistory();
            setHistory([]);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to clear search history');
        } finally {
            setIsClearingHistory(false);
        }
    };

    const openSettingsModal = () => {
        setDraftSearchSettings(cloneSearchSettings(searchSettings));
        setShowSettingsModal(true);
    };

    const closeSettingsModal = () => {
        setShowSettingsModal(false);
    };

    const applySettings = () => {
        setSearchSettings(normalizeSearchSettings(draftSearchSettings));
        setShowSettingsModal(false);
    };

    const applyPresetToDraft = (preset: Exclude<SearchPreset, 'custom'>) => {
        setDraftSearchSettings((current) => ({
            ...getSearchPresetConfig(preset),
            saveHistory: current.saveHistory,
            streamingEnabled: current.streamingEnabled,
        }));
    };

    const updateDraftRetriever = (key: RetrieverKey) => {
        setDraftSearchSettings((current) => ({
            ...toggleRetriever(current, key),
            preset: 'custom',
        }));
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

    const resolveDrainWaiters = () => {
        if (drainWaitersRef.current.length === 0) return;
        const waiters = [...drainWaitersRef.current];
        drainWaitersRef.current = [];
        waiters.forEach((resolve) => resolve());
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
                rawAnswerRef.current += nextChunk;
                setAnswer(sanitizeSearchAnswer(rawAnswerRef.current));
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
        const effectiveSettings = normalizeSearchSettings(searchSettings);
        const controller = new AbortController();
        let sourcePromise: Promise<DisplayResult[]> | null = null;
        streamControllerRef.current = controller;

        setIsSearching(true);
        setHasSearched(true);
        setError(null);
        setResults([]);
        rawAnswerRef.current = '';
        setAnswer('');

        try {
            const sourceRequest = buildRagSearchPayload(
                query,
                'search',
                effectiveSettings,
                scope,
                { save_history: false }
            );
            sourcePromise = ragApi.query({
                ...sourceRequest,
            }, {
                signal: controller.signal,
            }).then((sourceData: RAGResponse) =>
                sourceData.sources.map((s) => ({
                    text: s.text,
                    score: normalizeMatchScore(s.score),
                    sources: s.retriever_sources?.length ? s.retriever_sources : inferSources(s.metadata),
                    source_scores: s.source_scores ?? {},
                    metadata: s.metadata,
                }))
            );
            void sourcePromise.then((sourceData) => {
                if (!controller.signal.aborted) {
                    stageRetrievedSources(sourceData);
                }
            }).catch(() => undefined);
            void sourcePromise.catch(() => undefined);

            if (effectiveSettings.streamingEnabled) {
                const streamPromise = ragApi.streamQuery(
                    buildRagSearchPayload(query, 'qa', effectiveSettings, scope),
                    {
                        signal: controller.signal,
                        onToken: (token) => {
                            queueAnswerToken(token);
                        },
                    }
                );

                await streamPromise;
                markAnswerStreamCompleted();
                await waitForAnswerDrain();
                const sourceData = await sourcePromise;
                if (!controller.signal.aborted) {
                    applyResultRevealTransition(
                        finalizeSearchResults(resultsRevealStateRef.current, sourceData)
                    );
                }
            } else {
                const response = await ragApi.query(
                    buildRagSearchPayload(query, 'qa', effectiveSettings, scope),
                    { signal: controller.signal }
                );
                const sourceData = response.sources.map((s) => ({
                    text: s.text,
                    score: normalizeMatchScore(s.score),
                    sources: s.retriever_sources?.length ? s.retriever_sources : inferSources(s.metadata),
                    source_scores: s.source_scores ?? {},
                    metadata: s.metadata,
                }));
                rawAnswerRef.current = response.answer;
                setAnswer(sanitizeSearchAnswer(response.answer));
                if (!controller.signal.aborted) {
                    stageRetrievedSources(sourceData);
                    applyResultRevealTransition(
                        finalizeSearchResults(resultsRevealStateRef.current, sourceData)
                    );
                }
            }
            await loadHistory();
        } catch (err) {
            if (err instanceof DOMException && err.name === 'AbortError') {
                cancelAnswerFlush();
                cancelSourcesReveal();
                return;
            }
            cancelAnswerFlush();
            if (sourcePromise) {
                try {
                    const sourceData = await sourcePromise;
                    if (!controller.signal.aborted) {
                        applyResultRevealTransition(
                            finalizeSearchResults(resultsRevealStateRef.current, sourceData)
                        );
                    }
                } catch {
                    // Retrieval failed too; the error banner already explains the visible failure.
                }
            }
            const msg = err instanceof Error ? err.message : 'Search failed';
            setError(normalizeSearchErrorMessage(msg));
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

    const visibleAnswer = sanitizeSearchAnswer(answer);
    const searchSettingsSummary = getSearchSettingsSummary(searchSettings);

    return (
        <div className="animate-in" style={{ display: 'grid', gridTemplateColumns: '300px 1fr', gap: '2rem', height: '100%' }}>
            {/* Sidebar History */}
            <div style={{ borderRight: '1px solid var(--border-color)', paddingRight: '1rem', display: 'flex', flexDirection: 'column', height: '100%', overflowY: 'auto' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.75rem', marginBottom: '1.5rem', color: 'var(--text-primary)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                        <History size={18} />
                        <h3 style={{ fontSize: '1.1rem', margin: 0 }}>Cronologia</h3>
                    </div>
                    <button
                        className="btn btn-ghost btn-sm"
                        onClick={handleClearHistory}
                        disabled={history.length === 0 || isClearingHistory}
                        title="Azzera cronologia"
                        style={{ gap: '0.35rem', opacity: history.length === 0 ? 0.55 : 1 }}
                    >
                        {isClearingHistory ? <Loader2 size={14} className="spin" /> : <Trash2 size={14} />}
                        {isClearingHistory ? 'Pulisco...' : 'Azzera'}
                    </button>
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
                <div style={{ marginBottom: '2rem' }}>
                    <div style={{ marginBottom: '0.6rem' }}>
                        <label
                            htmlFor="search-scope"
                            style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)', marginRight: '0.5rem' }}
                        >
                            Scope
                        </label>
                        <select
                            id="search-scope"
                            data-testid="search-scope-select"
                            value={scope.route_key === 'tender' && scope.tender_id != null ? String(scope.tender_id) : 'global'}
                            onChange={(e) => handleScopeChange(e.target.value)}
                            style={{
                                padding: '0.4rem 0.7rem',
                                borderRadius: 8,
                                border: '1px solid var(--border-color)',
                                background: 'var(--bg-elevated, transparent)',
                                color: 'var(--text-primary)',
                                fontSize: '0.85rem',
                            }}
                        >
                            <option value="global">Global library</option>
                            {accessibleTenders.map((t) => (
                                <option key={t.id} value={String(t.id)}>{t.title}</option>
                            ))}
                        </select>
                    </div>
                    <div style={{ display: 'flex', gap: '0.9rem', alignItems: 'stretch', flexWrap: 'wrap' }}>
                        <div style={{ position: 'relative', flex: '1 1 560px', minWidth: '320px' }}>
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
                                style={{ paddingLeft: '3.25rem' }}
                            />
                        </div>

                        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.55rem', minWidth: '168px' }}>
                            <button
                                className="btn btn-primary"
                                onClick={isSearching ? stopStreaming : handleSearch}
                                disabled={!isSearching && !query.trim()}
                                style={{ justifyContent: 'center' }}
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
                            <button
                                className="btn btn-secondary btn-sm"
                                onClick={openSettingsModal}
                                style={{ justifyContent: 'center' }}
                            >
                                <SlidersHorizontal size={14} /> Customize
                            </button>
                        </div>
                    </div>

                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.55rem', marginTop: '0.85rem' }}>
                        {searchSettingsSummary.map((item) => (
                            <span
                                key={item}
                                style={{
                                    padding: '0.4rem 0.7rem',
                                    borderRadius: 999,
                                    border: '1px solid var(--border-color)',
                                    background: 'color-mix(in srgb, var(--bg-secondary) 88%, transparent)',
                                    color: 'var(--text-secondary)',
                                    fontSize: '0.78rem',
                                    fontWeight: 600,
                                }}
                            >
                                {item}
                            </span>
                        ))}
                    </div>
                </div>

                {/* Error */}
                {error && (
                    <div className="card" style={{ borderColor: '#ef4444', marginBottom: '1.5rem', display: 'flex', alignItems: 'center', gap: '0.75rem', color: '#ef4444' }}>
                        <AlertCircle size={18} />
                        <span>{error}</span>
                    </div>
                )}

                <AnimatePresence>
                    {showSettingsModal && (
                        <motion.div
                            className="modal-overlay"
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            exit={{ opacity: 0 }}
                            onClick={closeSettingsModal}
                        >
                            <motion.div
                                className="modal-content search-settings-modal"
                                style={{ maxWidth: '860px' }}
                                initial={{ scale: 0.96, opacity: 0, y: 18 }}
                                animate={{ scale: 1, opacity: 1, y: 0 }}
                                exit={{ scale: 0.96, opacity: 0, y: 18 }}
                                onClick={(event) => event.stopPropagation()}
                            >
                                <div className="modal-header">
                                    <div>
                                        <h3 style={{ margin: 0 }}>Customize LLM/RAG Search</h3>
                                        <p className="page-subtitle" style={{ margin: '0.45rem 0 0 0' }}>
                                            Tune retrieval, ranking, and model behavior for the next search.
                                        </p>
                                    </div>
                                    <button
                                        className="btn btn-icon btn-ghost"
                                        onClick={closeSettingsModal}
                                    >
                                        <X size={18} />
                                    </button>
                                </div>

                                <div className="modal-body search-settings-modal-body" style={{ display: 'grid', gap: '1.25rem' }}>
                                    <div className="card" style={{ padding: '1rem' }}>
                                        <div style={{ marginBottom: '0.9rem' }}>
                                            <h4 style={{ margin: 0, fontSize: '0.98rem' }}>Quick presets</h4>
                                            <p style={{ margin: '0.35rem 0 0 0', color: 'var(--text-muted)', fontSize: '0.82rem' }}>
                                                Start from a safe baseline, then fine-tune the individual controls.
                                            </p>
                                        </div>
                                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: '0.8rem' }}>
                                            {SEARCH_PRESET_DETAILS.map((preset) => (
                                                <button
                                                    key={preset.key}
                                                    type="button"
                                                    onClick={() => applyPresetToDraft(preset.key)}
                                                    style={{
                                                        textAlign: 'left',
                                                        padding: '0.95rem',
                                                        borderRadius: '14px',
                                                        border: draftSearchSettings.preset === preset.key
                                                            ? '1px solid var(--accent-blue)'
                                                            : '1px solid var(--border-color)',
                                                        background: draftSearchSettings.preset === preset.key
                                                            ? 'color-mix(in srgb, var(--accent-blue) 14%, var(--bg-secondary))'
                                                            : 'var(--bg-secondary)',
                                                        cursor: 'pointer',
                                                    }}
                                                >
                                                    <div style={{ color: 'var(--text-primary)', fontWeight: 700, marginBottom: '0.35rem' }}>
                                                        {preset.title}
                                                    </div>
                                                    <div style={{ color: 'var(--text-muted)', fontSize: '0.8rem', lineHeight: 1.55 }}>
                                                        {preset.description}
                                                    </div>
                                                </button>
                                            ))}
                                        </div>
                                    </div>

                                    <div style={{ display: 'grid', gridTemplateColumns: '1.1fr 0.9fr', gap: '1rem' }}>
                                        <div className="card" style={{ padding: '1rem' }}>
                                            <div style={{ display: 'flex', justifyContent: 'space-between', gap: '1rem', alignItems: 'baseline' }}>
                                                <div>
                                                    <h4 style={{ margin: 0, fontSize: '0.98rem' }}>Recall retrieval</h4>
                                                    <p style={{ margin: '0.35rem 0 0 0', color: 'var(--text-muted)', fontSize: '0.82rem' }}>
                                                        How many candidates to pull from dense, BM25, and graph retrieval before fusion and reranking.
                                                    </p>
                                                </div>
                                                <strong style={{ color: 'var(--text-primary)' }}>{draftSearchSettings.retrievalTopK}</strong>
                                            </div>
                                            <input
                                                type="range"
                                                min={8}
                                                max={40}
                                                step={1}
                                                value={draftSearchSettings.retrievalTopK}
                                                onChange={(event) => setDraftSearchSettings((current) => ({
                                                    ...current,
                                                    preset: 'custom',
                                                    retrievalTopK: Number(event.target.value),
                                                }))}
                                                style={{ width: '100%', marginTop: '1rem' }}
                                            />
                                            <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--text-muted)', fontSize: '0.75rem', marginTop: '0.4rem' }}>
                                                <span>Narrow recall</span>
                                                <span>Wide recall</span>
                                            </div>
                                        </div>

                                        <div className="card" style={{ padding: '1rem' }}>
                                            <div style={{ display: 'flex', justifyContent: 'space-between', gap: '1rem', alignItems: 'baseline' }}>
                                                <div>
                                                    <h4 style={{ margin: 0, fontSize: '0.98rem' }}>LLM temperature</h4>
                                                    <p style={{ margin: '0.35rem 0 0 0', color: 'var(--text-muted)', fontSize: '0.82rem' }}>
                                                        Lower for source-grounded answers, higher for exploratory rephrasing.
                                                    </p>
                                                </div>
                                                <strong style={{ color: 'var(--text-primary)' }}>{draftSearchSettings.temperature.toFixed(2)}</strong>
                                            </div>
                                            <input
                                                type="range"
                                                min={0}
                                                max={1}
                                                step={0.05}
                                                value={draftSearchSettings.temperature}
                                                onChange={(event) => setDraftSearchSettings((current) => ({
                                                    ...current,
                                                    preset: 'custom',
                                                    temperature: Number(event.target.value),
                                                }))}
                                                style={{ width: '100%', marginTop: '1rem' }}
                                            />
                                            <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--text-muted)', fontSize: '0.75rem', marginTop: '0.4rem' }}>
                                                <span>Grounded</span>
                                                <span>Creative</span>
                                            </div>
                                        </div>
                                    </div>

                                    <div className="card" style={{ padding: '1rem' }}>
                                        <div style={{ display: 'flex', justifyContent: 'space-between', gap: '1rem', alignItems: 'baseline' }}>
                                            <div>
                                                <h4 style={{ margin: 0, fontSize: '0.98rem' }}>Final sources in context</h4>
                                                <p style={{ margin: '0.35rem 0 0 0', color: 'var(--text-muted)', fontSize: '0.82rem' }}>
                                                    How many sources to keep after fusion and reranking for the answer and the on-page source list.
                                                </p>
                                            </div>
                                            <strong style={{ color: 'var(--text-primary)' }}>{draftSearchSettings.topK}</strong>
                                        </div>
                                        <input
                                            type="range"
                                            min={3}
                                            max={12}
                                            step={1}
                                            value={draftSearchSettings.topK}
                                            onChange={(event) => setDraftSearchSettings((current) => ({
                                                ...current,
                                                preset: 'custom',
                                                topK: Number(event.target.value),
                                            }))}
                                            style={{ width: '100%', marginTop: '1rem' }}
                                        />
                                        <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--text-muted)', fontSize: '0.75rem', marginTop: '0.4rem' }}>
                                            <span>Lean</span>
                                            <span>More sources</span>
                                        </div>
                                    </div>

                                    <div className="card" style={{ padding: '1rem' }}>
                                        <div style={{ marginBottom: '1rem' }}>
                                            <h4 style={{ margin: 0, fontSize: '0.98rem' }}>Active retrievers and fusion weights</h4>
                                            <p style={{ margin: '0.35rem 0 0 0', color: 'var(--text-muted)', fontSize: '0.82rem' }}>
                                                Choose which channels to use and how much each one should influence the final fusion rank. At least one retriever always stays enabled.
                                            </p>
                                        </div>

                                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: '0.85rem' }}>
                                            {([
                                                {
                                                    key: 'dense',
                                                    title: 'Vector',
                                                    description: 'Semantic retrieval over embeddings based on meaning similarity.',
                                                    accent: 'var(--accent-blue)',
                                                },
                                                {
                                                    key: 'sparse',
                                                    title: 'BM25',
                                                    description: 'Lexical and exact matching, useful for technical keywords and specific terms.',
                                                    accent: 'var(--accent-amber)',
                                                },
                                                {
                                                    key: 'graph',
                                                    title: 'Knowledge Graph',
                                                    description: 'Structured relationships across entities, projects, team members, and requirements.',
                                                    accent: 'var(--accent-purple)',
                                                },
                                            ] as Array<{ key: RetrieverKey; title: string; description: string; accent: string }>).map((retriever) => (
                                                <div
                                                    key={retriever.key}
                                                    style={{
                                                        border: '1px solid var(--border-color)',
                                                        borderRadius: '14px',
                                                        padding: '0.95rem',
                                                        background: 'var(--bg-secondary)',
                                                    }}
                                                >
                                                    <label style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.75rem', marginBottom: '0.7rem' }}>
                                                        <div>
                                                            <div style={{ color: 'var(--text-primary)', fontWeight: 700 }}>
                                                                {retriever.title}
                                                            </div>
                                                            <div style={{ color: 'var(--text-muted)', fontSize: '0.78rem', lineHeight: 1.45, marginTop: '0.25rem' }}>
                                                                {retriever.description}
                                                            </div>
                                                        </div>
                                                        <input
                                                            type="checkbox"
                                                            checked={draftSearchSettings.retrievers[retriever.key]}
                                                            onChange={() => updateDraftRetriever(retriever.key)}
                                                        />
                                                    </label>

                                                    <div style={{ opacity: draftSearchSettings.retrievers[retriever.key] ? 1 : 0.5 }}>
                                                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.35rem' }}>
                                                            <span style={{ fontSize: '0.76rem', fontWeight: 700, color: retriever.accent }}>
                                                                Fusion weight
                                                            </span>
                                                            <span style={{ fontSize: '0.76rem', color: 'var(--text-secondary)' }}>
                                                                {draftSearchSettings.fusionWeights[retriever.key].toFixed(2)}
                                                            </span>
                                                        </div>
                                                        <input
                                                            type="range"
                                                            min={0.05}
                                                            max={1.5}
                                                            step={0.05}
                                                            disabled={!draftSearchSettings.retrievers[retriever.key]}
                                                            value={draftSearchSettings.fusionWeights[retriever.key]}
                                                            onChange={(event) => setDraftSearchSettings((current) => ({
                                                                ...current,
                                                                preset: 'custom',
                                                                fusionWeights: {
                                                                    ...current.fusionWeights,
                                                                    [retriever.key]: Number(event.target.value),
                                                                },
                                                            }))}
                                                            style={{ width: '100%' }}
                                                        />
                                                    </div>
                                                </div>
                                            ))}
                                        </div>
                                    </div>

                                    <div className="card" style={{ padding: '1rem' }}>
                                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: '1rem' }}>
                                            <label style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.9rem' }}>
                                                <div>
                                                    <div style={{ color: 'var(--text-primary)', fontWeight: 700 }}>Save to history</div>
                                                    <div style={{ color: 'var(--text-muted)', fontSize: '0.8rem', marginTop: '0.25rem' }}>
                                                        When disabled, the current search is not stored in the sidebar history.
                                                    </div>
                                                </div>
                                                <input
                                                    type="checkbox"
                                                    checked={draftSearchSettings.saveHistory}
                                                    onChange={(event) => setDraftSearchSettings((current) => ({
                                                        ...current,
                                                        preset: 'custom',
                                                        saveHistory: event.target.checked,
                                                    }))}
                                                />
                                            </label>

                                            <label style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.9rem' }}>
                                                <div>
                                                    <div style={{ color: 'var(--text-primary)', fontWeight: 700 }}>Streaming</div>
                                                    <div style={{ color: 'var(--text-muted)', fontSize: '0.8rem', marginTop: '0.25rem' }}>
                                                        Token-by-token answer output.
                                                    </div>
                                                </div>
                                                <input
                                                    type="checkbox"
                                                    checked={draftSearchSettings.streamingEnabled}
                                                    onChange={(event) => setDraftSearchSettings((current) => ({
                                                        ...current,
                                                        preset: 'custom',
                                                        streamingEnabled: event.target.checked,
                                                    }))}
                                                />
                                            </label>
                                        </div>
                                    </div>
                                </div>

                                <div className="modal-footer">
                                    <button
                                        className="btn btn-ghost"
                                        onClick={() => setDraftSearchSettings(cloneSearchSettings(DEFAULT_SEARCH_SETTINGS))}
                                    >
                                        <RotateCcw size={15} /> Reset default
                                    </button>
                                    <div style={{ display: 'flex', gap: '0.75rem' }}>
                                        <button
                                            className="btn btn-ghost"
                                            onClick={closeSettingsModal}
                                        >
                                            Cancel
                                        </button>
                                        <button
                                            className="btn btn-primary"
                                            onClick={applySettings}
                                        >
                                            Applica impostazioni
                                        </button>
                                    </div>
                                </div>
                            </motion.div>
                        </motion.div>
                    )}
                </AnimatePresence>

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
                {shouldShowSearchResults({
                    hasSearched,
                    isSearching,
                    visibleAnswer,
                    resultsLength: results.length,
                }) && (
                    <div style={{ display: 'grid', gap: '1.5rem' }}>
                        {/* AI Answer */}
                        {(visibleAnswer || isSearching) && (
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
                                    data-testid="search-answer"
                                    style={{ fontSize: '0.9rem', lineHeight: 1.8, color: 'var(--text-secondary)', whiteSpace: 'pre-line' }}
                                >
                                    {visibleAnswer}
                                </div>
                                {isSearching && (
                                    <div style={{ marginTop: '0.75rem', color: 'var(--text-muted)', fontSize: '0.8rem' }}>
                                        Sto scrivendo la risposta in tempo reale...
                                    </div>
                                )}
                            </motion.div>
                        )}

                        {/* No answer and no results */}
                        {shouldShowEmptySearchState({
                            isSearching,
                            visibleAnswer,
                            resultsLength: results.length,
                            error,
                        }) && (
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
                                                {(() => {
                                                    const total = Object.values(result.source_scores).reduce((a, b) => a + b, 0);
                                                    return result.sources.map((s) => {
                                                        const pct = total > 0 && result.source_scores[s]
                                                            ? Math.round((result.source_scores[s] / total) * 100)
                                                            : undefined;
                                                        return <SourceBadge key={s} source={s} pct={pct} />;
                                                    });
                                                })()}
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
                            {normalizeSearchSettings(searchSettings).streamingEnabled
                                ? 'Recupero le fonti e avvio la generazione streaming...'
                                : 'Recupero le fonti e genero la risposta...'}
                        </p>
                    </div>
                )}
            </div>
        </div>
    );
}
