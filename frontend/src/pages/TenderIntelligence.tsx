import { useCallback, useEffect, useMemo, useState } from 'react';
import {
    AlertCircle,
    Brain,
    Loader2,
    MessageSquare,
    ShieldCheck,
    Target,
    FileSearch,
    Send,
    GitBranch,
    Scale,
} from 'lucide-react';
import { motion } from 'framer-motion';
import {
    intelligenceApi,
    tenderApi,
    type CompliancePanoramaResult,
    type ContradictionFinderResult,
    type CoverageAnalyzerResult,
    type EvidenceAuditorResult,
    type GraphPathExplainerResult,
    type IntelligenceAgentQueryResult,
    type IntelligenceToolDescriptor,
    type RehearsalMode,
    type RehearsalRun,
    type Tender,
} from '../api/client';
import { RehearsalPanel } from '../features/intelligence/RehearsalPanel';
import { HEALTH_COLOR, StatusBadge } from '../features/intelligence/shared';

type ToolKey = 'coverage' | 'evidence' | 'compliance' | 'contradiction';

type ToolResult =
    | { kind: 'coverage'; data: CoverageAnalyzerResult }
    | { kind: 'evidence'; data: EvidenceAuditorResult }
    | { kind: 'compliance'; data: CompliancePanoramaResult }
    | { kind: 'contradiction'; data: ContradictionFinderResult };

interface ToolButtonConfig {
    key: ToolKey;
    label: string;
    description: string;
    icon: typeof Target;
}

const TOOL_BUTTONS: ToolButtonConfig[] = [
    {
        key: 'coverage',
        label: 'Coverage Analyzer',
        description: 'Maps requirements onto proposal sections and surfaces unresolved gaps.',
        icon: Target,
    },
    {
        key: 'evidence',
        label: 'Evidence Auditor',
        description: 'Classifies each requirement as strong / weak / missing evidence.',
        icon: FileSearch,
    },
    {
        key: 'compliance',
        label: 'Compliance Panorama',
        description: 'Reads the KPI snapshot and local gates to produce a health panorama.',
        icon: ShieldCheck,
    },
    {
        key: 'contradiction',
        label: 'Contradiction Finder',
        description: 'Surfaces candidate contradictions across requirements, proposal sections and evidence.',
        icon: Scale,
    },
];

function formatInt(n: number): string {
    return Number.isFinite(n) ? n.toLocaleString() : '0';
}

export default function TenderIntelligence() {
    const [tenders, setTenders] = useState<Tender[]>([]);
    const [descriptors, setDescriptors] = useState<IntelligenceToolDescriptor[]>([]);
    const [selectedTenderId, setSelectedTenderId] = useState<number | null>(null);
    const [loadingTool, setLoadingTool] = useState<ToolKey | null>(null);
    const [result, setResult] = useState<ToolResult | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [onlyHighPriority, setOnlyHighPriority] = useState<boolean>(false);
    const [bootstrapError, setBootstrapError] = useState<string | null>(null);
    const [agentQuestion, setAgentQuestion] = useState<string>('Why is this tender amber?');
    const [agentLoading, setAgentLoading] = useState<boolean>(false);
    const [agentResult, setAgentResult] = useState<IntelligenceAgentQueryResult | null>(null);
    const [agentError, setAgentError] = useState<string | null>(null);
    const [graphRequirementId, setGraphRequirementId] = useState<string>('');
    const [graphLoading, setGraphLoading] = useState<boolean>(false);
    const [graphResult, setGraphResult] = useState<GraphPathExplainerResult | null>(null);
    const [graphError, setGraphError] = useState<string | null>(null);
    const [rehearsalRuns, setRehearsalRuns] = useState<RehearsalRun[]>([]);
    const [rehearsalLoading, setRehearsalLoading] = useState<boolean>(false);
    const [rehearsalError, setRehearsalError] = useState<string | null>(null);
    const [rehearsalProposalId, setRehearsalProposalId] = useState<string>('');
    const [rehearsalMode, setRehearsalMode] = useState<RehearsalMode>('full');
    const [rehearsalCreating, setRehearsalCreating] = useState<boolean>(false);
    const [selectedRunId, setSelectedRunId] = useState<number | null>(null);
    const [recommendationBusyId, setRecommendationBusyId] = useState<number | null>(null);

    useEffect(() => {
        let cancelled = false;
        async function bootstrap() {
            try {
                const [tenderList, toolList] = await Promise.all([
                    tenderApi.list(),
                    intelligenceApi.listTools(),
                ]);
                if (cancelled) {
                    return;
                }
                setTenders(tenderList.items);
                setDescriptors(toolList.tools);
                if (tenderList.items.length > 0) {
                    setSelectedTenderId(tenderList.items[0].id);
                }
            } catch (err) {
                if (!cancelled) {
                    setBootstrapError(err instanceof Error ? err.message : String(err));
                }
            }
        }
        void bootstrap();
        return () => {
            cancelled = true;
        };
    }, []);

    const descriptorByName = useMemo(() => {
        const map: Record<string, IntelligenceToolDescriptor> = {};
        for (const tool of descriptors) {
            map[tool.name] = tool;
        }
        return map;
    }, [descriptors]);

    async function runAgentQuery() {
        if (selectedTenderId === null) {
            setAgentError('Select a tender first.');
            return;
        }
        const question = agentQuestion.trim();
        if (!question) {
            setAgentError('Type a question.');
            return;
        }
        setAgentLoading(true);
        setAgentError(null);
        try {
            const data = await intelligenceApi.query(selectedTenderId, question, onlyHighPriority);
            setAgentResult(data);
        } catch (err) {
            setAgentError(err instanceof Error ? err.message : String(err));
            setAgentResult(null);
        } finally {
            setAgentLoading(false);
        }
    }

    async function runTool(key: ToolKey) {
        if (selectedTenderId === null) {
            setError('Select a tender first.');
            return;
        }
        setLoadingTool(key);
        setError(null);
        try {
            if (key === 'coverage') {
                const envelope = await intelligenceApi.runCoverageAnalyzer(selectedTenderId);
                setResult({ kind: 'coverage', data: envelope.result });
            } else if (key === 'evidence') {
                const envelope = await intelligenceApi.runEvidenceAuditor(
                    selectedTenderId,
                    onlyHighPriority,
                );
                setResult({ kind: 'evidence', data: envelope.result });
            } else if (key === 'compliance') {
                const envelope = await intelligenceApi.runCompliancePanorama(selectedTenderId);
                setResult({ kind: 'compliance', data: envelope.result });
            } else {
                const envelope = await intelligenceApi.runContradictionFinder(selectedTenderId);
                setResult({ kind: 'contradiction', data: envelope.result });
            }
        } catch (err) {
            setError(err instanceof Error ? err.message : String(err));
            setResult(null);
        } finally {
            setLoadingTool(null);
        }
    }

    const refreshRehearsalRuns = useCallback(
        async (tenderId: number) => {
            setRehearsalLoading(true);
            setRehearsalError(null);
            try {
                const runs = await intelligenceApi.listRehearsals(tenderId, { limit: 25 });
                setRehearsalRuns(runs);
                if (runs.length > 0) {
                    setSelectedRunId((current) =>
                        current !== null && runs.some((r) => r.id === current) ? current : runs[0].id,
                    );
                } else {
                    setSelectedRunId(null);
                }
            } catch (err) {
                setRehearsalError(err instanceof Error ? err.message : String(err));
                setRehearsalRuns([]);
                setSelectedRunId(null);
            } finally {
                setRehearsalLoading(false);
            }
        },
        [],
    );

    useEffect(() => {
        if (selectedTenderId === null) {
            setRehearsalRuns([]);
            setSelectedRunId(null);
            return;
        }
        void refreshRehearsalRuns(selectedTenderId);
    }, [selectedTenderId, refreshRehearsalRuns]);

    async function createRehearsal() {
        if (selectedTenderId === null) {
            setRehearsalError('Select a tender first.');
            return;
        }
        const trimmed = rehearsalProposalId.trim();
        const proposalId = Number(trimmed);
        if (!trimmed || !Number.isInteger(proposalId) || proposalId <= 0) {
            setRehearsalError('Enter a positive integer proposal id.');
            return;
        }
        setRehearsalCreating(true);
        setRehearsalError(null);
        try {
            await intelligenceApi.createRehearsal({
                tender_id: selectedTenderId,
                proposal_id: proposalId,
                mode: rehearsalMode,
                include_forecast_context: true,
            });
            await refreshRehearsalRuns(selectedTenderId);
        } catch (err) {
            setRehearsalError(err instanceof Error ? err.message : String(err));
        } finally {
            setRehearsalCreating(false);
        }
    }

    async function acceptRehearsalRecommendation(runId: number, recommendationId: number) {
        setRecommendationBusyId(recommendationId);
        setRehearsalError(null);
        try {
            const response = await intelligenceApi.acceptRecommendation(runId, recommendationId);
            setRehearsalRuns((runs) =>
                runs.map((run) =>
                    run.id === runId
                        ? {
                            ...run,
                            recommendations: run.recommendations.map((r) =>
                                r.id === recommendationId ? response.recommendation : r,
                            ),
                        }
                        : run,
                ),
            );
        } catch (err) {
            setRehearsalError(err instanceof Error ? err.message : String(err));
        } finally {
            setRecommendationBusyId(null);
        }
    }

    async function dismissRehearsalRecommendation(runId: number, recommendationId: number) {
        setRecommendationBusyId(recommendationId);
        setRehearsalError(null);
        try {
            const response = await intelligenceApi.dismissRecommendation(runId, recommendationId);
            setRehearsalRuns((runs) =>
                runs.map((run) =>
                    run.id === runId
                        ? {
                            ...run,
                            recommendations: run.recommendations.map((r) =>
                                r.id === recommendationId ? response.recommendation : r,
                            ),
                        }
                        : run,
                ),
            );
        } catch (err) {
            setRehearsalError(err instanceof Error ? err.message : String(err));
        } finally {
            setRecommendationBusyId(null);
        }
    }

    async function runGraphPathExplainer() {
        if (selectedTenderId === null) {
            setGraphError('Select a tender first.');
            return;
        }
        const trimmed = graphRequirementId.trim();
        const requirementId = Number(trimmed);
        if (!trimmed || !Number.isInteger(requirementId) || requirementId <= 0) {
            setGraphError('Enter a positive integer requirement id.');
            return;
        }
        setGraphLoading(true);
        setGraphError(null);
        try {
            const envelope = await intelligenceApi.runGraphPathExplainer(
                selectedTenderId,
                requirementId,
            );
            setGraphResult(envelope.result);
        } catch (err) {
            setGraphError(err instanceof Error ? err.message : String(err));
            setGraphResult(null);
        } finally {
            setGraphLoading(false);
        }
    }

    return (
        <div
            style={{
                minHeight: '100vh',
                padding: '2rem',
                background:
                    'radial-gradient(circle at 10% 10%, rgba(96, 165, 250, 0.08) 0%, transparent 45%), radial-gradient(circle at 90% 90%, rgba(139, 92, 246, 0.08) 0%, transparent 45%)',
            }}
        >
            <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                style={{ maxWidth: '1100px', margin: '0 auto' }}
            >
                <header style={{ marginBottom: '1.5rem' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                        <Brain size={28} color="#60a5fa" />
                        <h1
                            style={{
                                fontSize: '1.6rem',
                                background: 'linear-gradient(135deg, #fff 0%, #94a3b8 100%)',
                                WebkitBackgroundClip: 'text',
                                WebkitTextFillColor: 'transparent',
                            }}
                        >
                            Tender Intelligence
                        </h1>
                    </div>
                    <p style={{ color: '#9ca3af', marginTop: '0.25rem' }}>
                        Read-only tools that summarise coverage, evidence and compliance panorama for a tender.
                    </p>
                </header>

                {bootstrapError && (
                    <div
                        style={{
                            padding: '1rem',
                            borderRadius: '0.75rem',
                            background: 'rgba(239, 68, 68, 0.12)',
                            border: '1px solid rgba(239, 68, 68, 0.4)',
                            color: '#fca5a5',
                            marginBottom: '1rem',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '0.5rem',
                        }}
                    >
                        <AlertCircle size={16} />
                        <span>{bootstrapError}</span>
                    </div>
                )}

                <section
                    style={{
                        padding: '1.25rem',
                        background: 'rgba(17, 24, 39, 0.85)',
                        border: '1px solid rgba(255, 255, 255, 0.08)',
                        borderRadius: '0.75rem',
                        marginBottom: '1rem',
                        display: 'grid',
                        gridTemplateColumns: 'minmax(220px, 320px) 1fr',
                        gap: '1rem',
                        alignItems: 'center',
                    }}
                >
                    <label style={{ display: 'grid', gap: '0.35rem' }}>
                        <span style={{ color: '#9ca3af', fontSize: '0.8rem' }}>Tender</span>
                        <select
                            value={selectedTenderId ?? ''}
                            onChange={(e) => setSelectedTenderId(e.target.value ? Number(e.target.value) : null)}
                            style={{
                                padding: '0.55rem 0.75rem',
                                background: 'rgba(15, 23, 42, 0.8)',
                                color: 'white',
                                border: '1px solid rgba(255, 255, 255, 0.1)',
                                borderRadius: '0.5rem',
                            }}
                        >
                            {tenders.length === 0 && <option value="">No tenders available</option>}
                            {tenders.map((t) => (
                                <option key={t.id} value={t.id}>
                                    {t.title}
                                </option>
                            ))}
                        </select>
                    </label>

                    <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: '#9ca3af' }}>
                        <input
                            type="checkbox"
                            checked={onlyHighPriority}
                            onChange={(e) => setOnlyHighPriority(e.target.checked)}
                        />
                        <span>Evidence auditor: only high-priority requirements</span>
                    </label>
                </section>

                <AgentPanel
                    question={agentQuestion}
                    onQuestionChange={setAgentQuestion}
                    onSubmit={runAgentQuery}
                    loading={agentLoading}
                    disabled={selectedTenderId === null}
                    error={agentError}
                    result={agentResult}
                />

                <GraphPathPanel
                    requirementId={graphRequirementId}
                    onRequirementIdChange={setGraphRequirementId}
                    onSubmit={runGraphPathExplainer}
                    loading={graphLoading}
                    disabled={selectedTenderId === null}
                    error={graphError}
                    result={graphResult}
                />

                <RehearsalPanel
                    runs={rehearsalRuns}
                    loading={rehearsalLoading}
                    error={rehearsalError}
                    proposalId={rehearsalProposalId}
                    onProposalIdChange={setRehearsalProposalId}
                    mode={rehearsalMode}
                    onModeChange={setRehearsalMode}
                    creating={rehearsalCreating}
                    onCreate={createRehearsal}
                    selectedRunId={selectedRunId}
                    onSelectRun={setSelectedRunId}
                    recommendationBusyId={recommendationBusyId}
                    onAccept={acceptRehearsalRecommendation}
                    onDismiss={dismissRehearsalRecommendation}
                    disabled={selectedTenderId === null}
                />

                <section
                    style={{
                        display: 'grid',
                        gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))',
                        gap: '0.75rem',
                        marginBottom: '1.25rem',
                    }}
                >
                    {TOOL_BUTTONS.map((tool) => {
                        const isLoading = loadingTool === tool.key;
                        const Icon = tool.icon;
                        const descriptorName =
                            tool.key === 'coverage'
                                ? 'coverage_analyzer'
                                : tool.key === 'evidence'
                                    ? 'evidence_auditor'
                                    : tool.key === 'compliance'
                                        ? 'compliance_panorama'
                                        : 'contradiction_finder';
                        const descriptor = descriptorByName[descriptorName];
                        return (
                            <button
                                key={tool.key}
                                onClick={() => runTool(tool.key)}
                                disabled={isLoading || selectedTenderId === null}
                                style={{
                                    textAlign: 'left',
                                    padding: '1rem',
                                    borderRadius: '0.75rem',
                                    background: 'rgba(30, 41, 59, 0.8)',
                                    border: '1px solid rgba(148, 163, 184, 0.2)',
                                    color: 'white',
                                    cursor: isLoading || selectedTenderId === null ? 'not-allowed' : 'pointer',
                                    opacity: selectedTenderId === null ? 0.5 : 1,
                                    display: 'grid',
                                    gap: '0.5rem',
                                }}
                            >
                                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                    {isLoading ? <Loader2 size={18} className="spin" /> : <Icon size={18} color="#60a5fa" />}
                                    <strong>{tool.label}</strong>
                                </div>
                                <p style={{ color: '#9ca3af', fontSize: '0.85rem', margin: 0 }}>
                                    {descriptor?.description || tool.description}
                                </p>
                            </button>
                        );
                    })}
                </section>

                {error && (
                    <div
                        style={{
                            padding: '0.75rem 1rem',
                            borderRadius: '0.5rem',
                            background: 'rgba(239, 68, 68, 0.12)',
                            border: '1px solid rgba(239, 68, 68, 0.4)',
                            color: '#fca5a5',
                            marginBottom: '1rem',
                        }}
                    >
                        {error}
                    </div>
                )}

                {result && <ResultPanel result={result} />}
            </motion.div>
        </div>
    );
}

function ResultPanel({ result }: { result: ToolResult }) {
    if (result.kind === 'coverage') {
        return <CoverageResult data={result.data} />;
    }
    if (result.kind === 'evidence') {
        return <EvidenceResult data={result.data} />;
    }
    if (result.kind === 'compliance') {
        return <PanoramaResult data={result.data} />;
    }
    return <ContradictionResult data={result.data} />;
}

function SectionShell({ title, children }: { title: string; children: React.ReactNode }) {
    return (
        <section
            style={{
                padding: '1.25rem',
                background: 'rgba(17, 24, 39, 0.85)',
                border: '1px solid rgba(255, 255, 255, 0.08)',
                borderRadius: '0.75rem',
                marginBottom: '1rem',
            }}
        >
            <h2 style={{ fontSize: '1.1rem', color: 'white', marginBottom: '0.75rem' }}>{title}</h2>
            {children}
        </section>
    );
}

function SummaryGrid({ entries }: { entries: Array<{ label: string; value: number | string }> }) {
    return (
        <div
            style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
                gap: '0.5rem',
            }}
        >
            {entries.map((entry) => (
                <div
                    key={entry.label}
                    style={{
                        padding: '0.75rem',
                        background: 'rgba(15, 23, 42, 0.6)',
                        border: '1px solid rgba(148, 163, 184, 0.15)',
                        borderRadius: '0.5rem',
                    }}
                >
                    <div style={{ color: '#9ca3af', fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: 0.5 }}>
                        {entry.label}
                    </div>
                    <div style={{ color: 'white', fontSize: '1.25rem', marginTop: '0.25rem' }}>{entry.value}</div>
                </div>
            ))}
        </div>
    );
}

function CoverageResult({ data }: { data: CoverageAnalyzerResult }) {
    return (
        <>
            <SectionShell title={`Coverage summary — tender #${data.tender_id}`}>
                <SummaryGrid
                    entries={[
                        { label: 'Total', value: formatInt(data.summary.total_requirements) },
                        { label: 'Fully covered', value: formatInt(data.summary.fully_covered) },
                        { label: 'Partial', value: formatInt(data.summary.partially_covered) },
                        { label: 'Uncovered', value: formatInt(data.summary.uncovered) },
                        { label: 'High-prio uncovered', value: formatInt(data.summary.high_priority_uncovered) },
                    ]}
                />
            </SectionShell>

            <SectionShell title="By domain">
                {data.by_domain.length === 0 ? (
                    <p style={{ color: '#9ca3af' }}>No ontology-tagged requirements.</p>
                ) : (
                    <table style={{ width: '100%', color: 'white', borderCollapse: 'collapse' }}>
                        <thead>
                            <tr style={{ color: '#9ca3af', textAlign: 'left' }}>
                                <th style={{ padding: '0.4rem 0' }}>Domain</th>
                                <th>Total</th>
                                <th>Covered</th>
                                <th>Partial</th>
                                <th>Uncovered</th>
                            </tr>
                        </thead>
                        <tbody>
                            {data.by_domain.map((row) => (
                                <tr key={row.domain} style={{ borderTop: '1px solid rgba(148, 163, 184, 0.1)' }}>
                                    <td style={{ padding: '0.4rem 0' }}>{row.domain}</td>
                                    <td>{formatInt(row.total)}</td>
                                    <td>{formatInt(row.covered)}</td>
                                    <td>{formatInt(row.partial)}</td>
                                    <td>{formatInt(row.uncovered)}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
            </SectionShell>

            <SectionShell title={`Gaps (${data.gaps.length})`}>
                {data.gaps.length === 0 ? (
                    <p style={{ color: '#9ca3af' }}>No gaps.</p>
                ) : (
                    <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'grid', gap: '0.5rem' }}>
                        {data.gaps.map((gap) => (
                            <li
                                key={gap.requirement_id}
                                style={{
                                    padding: '0.75rem',
                                    background: 'rgba(15, 23, 42, 0.6)',
                                    border: '1px solid rgba(148, 163, 184, 0.15)',
                                    borderRadius: '0.5rem',
                                }}
                            >
                                <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', marginBottom: '0.25rem' }}>
                                    <StatusBadge label={gap.coverage_status} color="#fbbf24" />
                                    <StatusBadge label={gap.priority} color="#60a5fa" />
                                    <span style={{ color: '#9ca3af', fontSize: '0.8rem' }}>
                                        {gap.ontology_domain} / {gap.ontology_subdomain}
                                    </span>
                                </div>
                                <div style={{ color: 'white' }}>{gap.summary}</div>
                                {gap.mapped_section_title && (
                                    <div style={{ color: '#9ca3af', fontSize: '0.8rem', marginTop: '0.25rem' }}>
                                        Mapped section: {gap.mapped_section_title}
                                    </div>
                                )}
                            </li>
                        ))}
                    </ul>
                )}
            </SectionShell>
        </>
    );
}

function EvidenceResult({ data }: { data: EvidenceAuditorResult }) {
    const color: Record<string, string> = {
        strong: '#10b981',
        weak: '#f59e0b',
        missing: '#ef4444',
    };
    return (
        <>
            <SectionShell title={`Evidence summary — tender #${data.tender_id}`}>
                <SummaryGrid
                    entries={[
                        { label: 'Checked', value: formatInt(data.summary.requirements_checked) },
                        { label: 'Strong', value: formatInt(data.summary.strong_evidence) },
                        { label: 'Weak', value: formatInt(data.summary.weak_evidence) },
                        { label: 'Missing', value: formatInt(data.summary.missing_evidence) },
                        { label: 'Only high-prio?', value: data.only_high_priority ? 'yes' : 'no' },
                    ]}
                />
            </SectionShell>
            <SectionShell title={`Findings (${data.findings.length})`}>
                {data.findings.length === 0 ? (
                    <p style={{ color: '#9ca3af' }}>No findings.</p>
                ) : (
                    <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'grid', gap: '0.5rem' }}>
                        {data.findings.map((finding) => (
                            <li
                                key={finding.requirement_id}
                                style={{
                                    padding: '0.75rem',
                                    background: 'rgba(15, 23, 42, 0.6)',
                                    border: '1px solid rgba(148, 163, 184, 0.15)',
                                    borderRadius: '0.5rem',
                                }}
                            >
                                <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', marginBottom: '0.25rem', flexWrap: 'wrap' }}>
                                    <StatusBadge label={finding.evidence_status} color={color[finding.evidence_status] ?? '#60a5fa'} />
                                    <StatusBadge label={finding.priority} color="#60a5fa" />
                                    <span style={{ color: '#9ca3af', fontSize: '0.8rem' }}>
                                        {finding.expected_evidence_type} · owner {finding.owner_role}
                                    </span>
                                </div>
                                <div style={{ color: 'white' }}>{finding.summary}</div>
                                <div style={{ color: '#9ca3af', fontSize: '0.8rem', marginTop: '0.25rem' }}>
                                    Section: {finding.mapped_section_title ?? '—'}
                                </div>
                            </li>
                        ))}
                    </ul>
                )}
            </SectionShell>
        </>
    );
}

function PanoramaResult({ data }: { data: CompliancePanoramaResult }) {
    const health = HEALTH_COLOR[data.health] ?? '#60a5fa';
    return (
        <>
            <SectionShell title={`Compliance panorama — tender #${data.tender_id}`}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.75rem' }}>
                    <StatusBadge label={`health: ${data.health}`} color={health} />
                    {data.analytical_phase && <StatusBadge label={data.analytical_phase} color="#60a5fa" />}
                    {data.auto_gate_status && <StatusBadge label={`gate: ${data.auto_gate_status}`} color="#a78bfa" />}
                    <StatusBadge
                        label={data.kpi_snapshot_delivered ? 'kpi: delivered' : 'kpi: unavailable'}
                        color={data.kpi_snapshot_delivered ? '#10b981' : '#6b7280'}
                    />
                </div>
                <SummaryGrid
                    entries={[
                        { label: 'Failed gates', value: formatInt(data.summary.failed_gates) },
                        { label: 'Open gates', value: formatInt(data.summary.open_gates) },
                        { label: 'Blocking reworks', value: formatInt(data.summary.blocking_reworks) },
                        { label: 'Unresolved reqs', value: formatInt(data.summary.unresolved_requirements) },
                        { label: 'High-prio unresolved', value: formatInt(data.summary.high_priority_unresolved) },
                    ]}
                />
            </SectionShell>
            <SectionShell title={`Top risks (${data.top_risks.length})`}>
                {data.top_risks.length === 0 ? (
                    <p style={{ color: '#9ca3af' }}>No top risks reported.</p>
                ) : (
                    <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'grid', gap: '0.5rem' }}>
                        {data.top_risks.map((risk) => (
                            <li
                                key={risk.code}
                                style={{
                                    padding: '0.75rem',
                                    background: 'rgba(15, 23, 42, 0.6)',
                                    border: '1px solid rgba(148, 163, 184, 0.15)',
                                    borderRadius: '0.5rem',
                                    display: 'grid',
                                    gap: '0.25rem',
                                }}
                            >
                                <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                                    <StatusBadge label={risk.severity} color="#ef4444" />
                                    <span style={{ color: '#9ca3af', fontSize: '0.8rem' }}>{risk.code}</span>
                                </div>
                                <div style={{ color: 'white' }}>{risk.summary}</div>
                            </li>
                        ))}
                    </ul>
                )}
            </SectionShell>
        </>
    );
}

const SEVERITY_COLOR: Record<string, string> = {
    critical: '#ef4444',
    high: '#f97316',
    medium: '#f59e0b',
    low: '#60a5fa',
};

const RECOMMENDED_ACTION_LABEL: Record<string, string> = {
    review_uncovered_requirement: 'Review uncovered requirement',
    strengthen_evidence: 'Strengthen evidence',
    address_failed_gate: 'Address failed gate',
    resolve_blocking_rework: 'Resolve blocking rework',
    inspect_panorama: 'Inspect panorama',
    review_contradiction: 'Review contradiction',
    follow_up_question: 'Ask follow-up question',
};

const CONTRADICTION_KIND_LABEL: Record<string, string> = {
    requirement_vs_proposal: 'Requirement ↔ Proposal',
    proposal_vs_evidence: 'Proposal ↔ Evidence',
    requirement_vs_requirement: 'Requirement ↔ Requirement',
};

const GRAPH_STEP_COLOR: Record<string, string> = {
    requirement: '#a78bfa',
    section: '#60a5fa',
    contribution: '#22d3ee',
    review: '#facc15',
    rework: '#fb923c',
    gate: '#ef4444',
};

interface AgentPanelProps {
    question: string;
    onQuestionChange: (value: string) => void;
    onSubmit: () => void;
    loading: boolean;
    disabled: boolean;
    error: string | null;
    result: IntelligenceAgentQueryResult | null;
}

function AgentPanel({ question, onQuestionChange, onSubmit, loading, disabled, error, result }: AgentPanelProps) {
    return (
        <section
            style={{
                padding: '1.25rem',
                background: 'rgba(17, 24, 39, 0.85)',
                border: '1px solid rgba(255, 255, 255, 0.08)',
                borderRadius: '0.75rem',
                marginBottom: '1rem',
                display: 'grid',
                gap: '0.75rem',
            }}
        >
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <MessageSquare size={18} color="#a78bfa" />
                <h2 style={{ fontSize: '1.05rem', color: 'white', margin: 0 }}>Ask the Tender Intelligence Agent</h2>
            </div>
            <p style={{ color: '#9ca3af', margin: 0, fontSize: '0.85rem' }}>
                Routed to up to 3 read-only tools. The agent never mutates workflow, gate or rework state.
            </p>
            <form
                onSubmit={(e) => {
                    e.preventDefault();
                    onSubmit();
                }}
                style={{ display: 'flex', gap: '0.5rem' }}
            >
                <input
                    value={question}
                    onChange={(e) => onQuestionChange(e.target.value)}
                    placeholder="es. perché siamo amber? quali requisiti high-priority sono scoperti?"
                    style={{
                        flex: 1,
                        padding: '0.55rem 0.75rem',
                        background: 'rgba(15, 23, 42, 0.8)',
                        color: 'white',
                        border: '1px solid rgba(255, 255, 255, 0.1)',
                        borderRadius: '0.5rem',
                    }}
                />
                <button
                    type="submit"
                    disabled={loading || disabled}
                    style={{
                        padding: '0.55rem 1rem',
                        background: 'rgba(96, 165, 250, 0.2)',
                        color: 'white',
                        border: '1px solid rgba(96, 165, 250, 0.4)',
                        borderRadius: '0.5rem',
                        cursor: loading || disabled ? 'not-allowed' : 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '0.4rem',
                    }}
                >
                    {loading ? <Loader2 size={16} className="spin" /> : <Send size={16} />}
                    <span>Ask</span>
                </button>
            </form>
            {error && (
                <div style={{ color: '#fca5a5', fontSize: '0.85rem' }}>{error}</div>
            )}
            {result && <AgentResult data={result} />}
        </section>
    );
}

function AgentResult({ data }: { data: IntelligenceAgentQueryResult }) {
    return (
        <div style={{ display: 'grid', gap: '0.75rem', marginTop: '0.5rem' }}>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem' }}>
                <StatusBadge label={`intent: ${data.intent}`} color="#a78bfa" />
                {data.tools_used.map((tool) => (
                    <StatusBadge key={tool} label={tool} color="#60a5fa" />
                ))}
            </div>
            <div
                style={{
                    padding: '0.75rem',
                    background: 'rgba(15, 23, 42, 0.6)',
                    border: '1px solid rgba(148, 163, 184, 0.15)',
                    borderRadius: '0.5rem',
                    color: 'white',
                }}
            >
                {data.answer}
            </div>
            {data.findings.length > 0 && (
                <div>
                    <div style={{ color: '#9ca3af', fontSize: '0.8rem', marginBottom: '0.35rem' }}>
                        Findings ({data.findings.length})
                    </div>
                    <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'grid', gap: '0.4rem' }}>
                        {data.findings.slice(0, 8).map((finding, idx) => (
                            <li
                                key={idx}
                                style={{
                                    padding: '0.55rem 0.75rem',
                                    background: 'rgba(15, 23, 42, 0.6)',
                                    border: '1px solid rgba(148, 163, 184, 0.15)',
                                    borderRadius: '0.5rem',
                                }}
                            >
                                <div style={{ display: 'flex', gap: '0.4rem', alignItems: 'center', marginBottom: '0.2rem', flexWrap: 'wrap' }}>
                                    <StatusBadge label={finding.severity} color={SEVERITY_COLOR[finding.severity] ?? '#60a5fa'} />
                                    <span style={{ color: '#9ca3af', fontSize: '0.75rem' }}>
                                        from {finding.source_tool}
                                    </span>
                                </div>
                                <div style={{ color: 'white', fontSize: '0.9rem' }}>{finding.summary}</div>
                            </li>
                        ))}
                    </ul>
                </div>
            )}
            {data.recommended_actions.length > 0 && (
                <div>
                    <div style={{ color: '#9ca3af', fontSize: '0.8rem', marginBottom: '0.35rem' }}>
                        Recommended actions (no automatic write)
                    </div>
                    <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'grid', gap: '0.4rem' }}>
                        {data.recommended_actions.slice(0, 8).map((rec, idx) => (
                            <li
                                key={idx}
                                style={{
                                    padding: '0.55rem 0.75rem',
                                    background: 'rgba(15, 23, 42, 0.6)',
                                    border: '1px solid rgba(148, 163, 184, 0.15)',
                                    borderRadius: '0.5rem',
                                }}
                            >
                                <div style={{ color: '#a78bfa', fontSize: '0.75rem', marginBottom: '0.2rem' }}>
                                    {RECOMMENDED_ACTION_LABEL[rec.kind] ?? rec.kind}
                                </div>
                                <div style={{ color: 'white', fontSize: '0.9rem' }}>{rec.summary}</div>
                            </li>
                        ))}
                    </ul>
                </div>
            )}
        </div>
    );
}

function ContradictionResult({ data }: { data: ContradictionFinderResult }) {
    return (
        <>
            <SectionShell title={`Contradictions — tender #${data.tender_id}`}>
                <SummaryGrid
                    entries={[
                        { label: 'Total', value: formatInt(data.summary.total) },
                        { label: 'Req ↔ Proposal', value: formatInt(data.summary.requirement_vs_proposal) },
                        { label: 'Proposal ↔ Evidence', value: formatInt(data.summary.proposal_vs_evidence) },
                        { label: 'Req ↔ Req', value: formatInt(data.summary.requirement_vs_requirement) },
                    ]}
                />
            </SectionShell>
            <SectionShell title={`Findings (${data.findings.length})`}>
                {data.findings.length === 0 ? (
                    <p style={{ color: '#9ca3af' }}>No candidate contradictions detected.</p>
                ) : (
                    <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'grid', gap: '0.5rem' }}>
                        {data.findings.map((finding, idx) => (
                            <li
                                key={`${finding.kind}-${finding.requirement_id}-${idx}`}
                                style={{
                                    padding: '0.75rem',
                                    background: 'rgba(15, 23, 42, 0.6)',
                                    border: '1px solid rgba(148, 163, 184, 0.15)',
                                    borderRadius: '0.5rem',
                                }}
                            >
                                <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', marginBottom: '0.25rem', flexWrap: 'wrap' }}>
                                    <StatusBadge
                                        label={CONTRADICTION_KIND_LABEL[finding.kind] ?? finding.kind}
                                        color="#fb923c"
                                    />
                                    <StatusBadge
                                        label={finding.severity}
                                        color={SEVERITY_COLOR[finding.severity] ?? '#60a5fa'}
                                    />
                                    <span style={{ color: '#9ca3af', fontSize: '0.8rem' }}>
                                        requirement #{finding.requirement_id}
                                        {finding.related_requirement_id != null
                                            ? ` ↔ #${finding.related_requirement_id}`
                                            : ''}
                                    </span>
                                </div>
                                <div style={{ color: 'white', fontSize: '0.9rem' }}>{finding.summary}</div>
                                {finding.evidence.length > 0 && (
                                    <ul style={{ marginTop: '0.4rem', paddingLeft: '1.1rem', color: '#9ca3af', fontSize: '0.8rem' }}>
                                        {finding.evidence.map((line, eidx) => (
                                            <li key={eidx}>{line}</li>
                                        ))}
                                    </ul>
                                )}
                            </li>
                        ))}
                    </ul>
                )}
            </SectionShell>
        </>
    );
}

interface GraphPathPanelProps {
    requirementId: string;
    onRequirementIdChange: (value: string) => void;
    onSubmit: () => void;
    loading: boolean;
    disabled: boolean;
    error: string | null;
    result: GraphPathExplainerResult | null;
}

function GraphPathPanel({
    requirementId,
    onRequirementIdChange,
    onSubmit,
    loading,
    disabled,
    error,
    result,
}: GraphPathPanelProps) {
    return (
        <section
            style={{
                padding: '1.25rem',
                background: 'rgba(17, 24, 39, 0.85)',
                border: '1px solid rgba(255, 255, 255, 0.08)',
                borderRadius: '0.75rem',
                marginBottom: '1rem',
                display: 'grid',
                gap: '0.75rem',
            }}
        >
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <GitBranch size={18} color="#22d3ee" />
                <h2 style={{ fontSize: '1.05rem', color: 'white', margin: 0 }}>
                    Graph Path Explainer
                </h2>
            </div>
            <p style={{ color: '#9ca3af', margin: 0, fontSize: '0.85rem' }}>
                Walks the requirement → section → contribution → review/rework/gate chain.
                Read-only, deterministic.
            </p>
            <form
                onSubmit={(e) => {
                    e.preventDefault();
                    onSubmit();
                }}
                style={{ display: 'flex', gap: '0.5rem' }}
            >
                <input
                    value={requirementId}
                    onChange={(e) => onRequirementIdChange(e.target.value)}
                    placeholder="Requirement id (e.g. 1042)"
                    inputMode="numeric"
                    pattern="[0-9]*"
                    style={{
                        width: '220px',
                        padding: '0.55rem 0.75rem',
                        background: 'rgba(15, 23, 42, 0.8)',
                        color: 'white',
                        border: '1px solid rgba(255, 255, 255, 0.1)',
                        borderRadius: '0.5rem',
                    }}
                />
                <button
                    type="submit"
                    disabled={loading || disabled}
                    style={{
                        padding: '0.55rem 1rem',
                        background: 'rgba(34, 211, 238, 0.18)',
                        color: 'white',
                        border: '1px solid rgba(34, 211, 238, 0.4)',
                        borderRadius: '0.5rem',
                        cursor: loading || disabled ? 'not-allowed' : 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '0.4rem',
                    }}
                >
                    {loading ? <Loader2 size={16} className="spin" /> : <GitBranch size={16} />}
                    <span>Explain</span>
                </button>
            </form>
            {error && <div style={{ color: '#fca5a5', fontSize: '0.85rem' }}>{error}</div>}
            {result && <GraphPathResult data={result} />}
        </section>
    );
}

function GraphPathResult({ data }: { data: GraphPathExplainerResult }) {
    if (!data.found) {
        return (
            <div style={{ color: '#fca5a5', fontSize: '0.9rem' }}>{data.narrative}</div>
        );
    }
    return (
        <div style={{ display: 'grid', gap: '0.75rem' }}>
            <div
                style={{
                    padding: '0.75rem',
                    background: 'rgba(15, 23, 42, 0.6)',
                    border: '1px solid rgba(148, 163, 184, 0.15)',
                    borderRadius: '0.5rem',
                    color: 'white',
                    fontSize: '0.9rem',
                }}
            >
                {data.narrative}
            </div>
            <ol style={{ listStyle: 'none', padding: 0, margin: 0, display: 'grid', gap: '0.4rem' }}>
                {data.path.map((step, idx) => {
                    const color = GRAPH_STEP_COLOR[step.kind] ?? '#60a5fa';
                    return (
                        <li
                            key={`${step.kind}-${step.id}-${idx}`}
                            style={{
                                padding: '0.55rem 0.75rem',
                                background: 'rgba(15, 23, 42, 0.6)',
                                border: '1px solid rgba(148, 163, 184, 0.15)',
                                borderRadius: '0.5rem',
                                display: 'grid',
                                gap: '0.2rem',
                            }}
                        >
                            <div style={{ display: 'flex', gap: '0.4rem', alignItems: 'center', flexWrap: 'wrap' }}>
                                <StatusBadge label={step.kind} color={color} />
                                <span style={{ color: '#9ca3af', fontSize: '0.8rem' }}>
                                    #{step.id}
                                </span>
                                {step.status && (
                                    <StatusBadge label={`status: ${step.status}`} color="#94a3b8" />
                                )}
                                {step.priority && (
                                    <StatusBadge label={`priority: ${step.priority}`} color="#94a3b8" />
                                )}
                                {step.is_blocking && (
                                    <StatusBadge label="blocking" color="#ef4444" />
                                )}
                            </div>
                            {step.label && (
                                <div style={{ color: 'white', fontSize: '0.9rem' }}>{step.label}</div>
                            )}
                        </li>
                    );
                })}
            </ol>
        </div>
    );
}

