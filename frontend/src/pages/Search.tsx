import { useState } from 'react';
import { motion } from 'framer-motion';
import {
    Search as SearchIcon,
    Sparkles,
    Send,
    FileText,
    Database,
    Network,
} from 'lucide-react';

interface SearchResult {
    text: string;
    score: number;
    sources: string[];
    metadata: Record<string, string>;
}

const DEMO_RESULTS: SearchResult[] = [
    {
        text: 'Successfully completed the Route 42 Highway Bridge Rehabilitation project for PennDOT in 2024. The $12.5M project involved full deck replacement, seismic retrofitting, and bearing replacement on a 6-span steel girder bridge, delivered 2 weeks ahead of schedule with zero safety incidents.',
        score: 0.94,
        sources: ['dense', 'sparse', 'graph'],
        metadata: { source: 'Past Proposals', doc: 'PennDOT_Bridge_Proposal_2024.pdf' },
    },
    {
        text: 'Team Member: Dr. Sarah Chen, PE, SE — 22 years structural engineering experience. Certifications: PE (PA, NJ, NY), SE (PA), PMP. Led 40+ bridge projects valued at $500M+. Expertise: seismic retrofit design, load rating analysis, accelerated bridge construction.',
        score: 0.89,
        sources: ['graph', 'dense'],
        metadata: { source: 'Knowledge Graph', entity: 'TeamMember' },
    },
    {
        text: 'Our accelerated bridge construction methodology reduces traffic disruption by 60%. We utilize prefabricated bridge elements and systems (PBES) along with ultra-high performance concrete (UHPC) to minimize construction timelines while maintaining structural integrity.',
        score: 0.82,
        sources: ['dense', 'sparse'],
        metadata: { source: 'Content Library', category: 'Technical Approach' },
    },
    {
        text: 'Project: I-95 Viaduct Rehabilitation — Client: NJDOT — Year: 2023 — Value: $28M — Category: Bridge Rehabilitation. Team delivered comprehensive structural rehabilitation including post-tensioning repairs, joint replacements, and Advanced Protective Coating systems.',
        score: 0.78,
        sources: ['graph'],
        metadata: { source: 'Knowledge Graph', entity: 'Project' },
    },
];

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
    const [results, setResults] = useState<SearchResult[]>([]);
    const [answer, setAnswer] = useState('');
    const [isSearching, setIsSearching] = useState(false);
    const [hasSearched, setHasSearched] = useState(false);

    const handleSearch = () => {
        if (!query.trim()) return;

        setIsSearching(true);
        setHasSearched(true);

        // Simulate search with demo data
        setTimeout(() => {
            setResults(DEMO_RESULTS);
            setAnswer(
                'Based on your knowledge base, your team has extensive bridge rehabilitation experience. Key highlights:\n\n' +
                '• **Route 42 Bridge** (2024, PennDOT) — $12.5M, full deck replacement, delivered early\n' +
                '• **I-95 Viaduct** (2023, NJDOT) — $28M comprehensive structural rehabilitation\n' +
                '• **Lead Engineer**: Dr. Sarah Chen, PE, SE with 22 years and 40+ bridge projects\n\n' +
                'Your team holds PE licenses in PA, NJ, NY and uses accelerated bridge construction methods (PBES, UHPC) that reduce traffic disruption by 60%.'
            );
            setIsSearching(false);
        }, 1500);
    };

    return (
        <div className="animate-in">
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
                    disabled={isSearching}
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
                                onClick={() => {
                                    setQuery(example);
                                }}
                                style={{ fontSize: '0.82rem' }}
                            >
                                {example}
                            </button>
                        ))}
                    </div>
                </div>
            )}

            {/* Results */}
            {hasSearched && !isSearching && (
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
                            <div style={{ fontSize: '0.9rem', lineHeight: 1.8, color: 'var(--text-secondary)', whiteSpace: 'pre-line' }}
                                dangerouslySetInnerHTML={{
                                    __html: answer
                                        .replace(/\*\*(.*?)\*\*/g, '<strong style="color: var(--text-primary)">$1</strong>')
                                }}
                            />
                        </motion.div>
                    )}

                    {/* Source Documents */}
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

                            <div style={{ display: 'flex', gap: '0.75rem', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                                {Object.entries(result.metadata).map(([key, value]) => (
                                    <span key={key}>
                                        <strong>{key}:</strong> {value}
                                    </span>
                                ))}
                            </div>
                        </motion.div>
                    ))}
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
    );
}
