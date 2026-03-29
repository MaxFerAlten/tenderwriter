import { useEffect, useId, useMemo, useRef, useState } from 'react';

import type { KpiTransitions } from '../../api/client';

type NodeTone = 'normal' | 'positive' | 'terminal';
type EdgeTone = 'default' | 'feedback' | 'terminal' | 'structural';

export type MarkovGraphVisualMode = 'analytical' | 'presentation';

interface CanonicalNode {
    id: string;
    label: string;
    tone: NodeTone;
}

interface CanonicalEdge {
    from: string;
    to: string;
    event?: string;
    tone?: EdgeTone;
}

interface MarkovStateGraphProps {
    currentState: string | null;
    transitions: KpiTransitions | null;
    visualMode?: MarkovGraphVisualMode;
}

interface ObservedGraphState {
    visitedNodes: Set<string>;
    observedPairs: Set<string>;
    observedEdges: Set<string>;
    latestPair: string | null;
    latestEdge: string | null;
}

const EDGE_LINE_PATTERN = /^(\s*)([A-Z0-9]+)(?:\(\(.*?\)\)|\[.*?\]|\{.*?\})?\s*-->(?:\|([^|]+)\|)?\s*([A-Z0-9]+)(?:\(\(.*?\)\)|\[.*?\]|\{.*?\})?\s*$/;

const CANONICAL_NODES: CanonicalNode[] = [
    { id: 'S0', label: 'Intake Opportunity', tone: 'normal' },
    { id: 'S1', label: 'Go / No-Go', tone: 'normal' },
    { id: 'S2', label: 'Bid Planning', tone: 'normal' },
    { id: 'S3', label: 'Request Contributions', tone: 'normal' },
    { id: 'S4', label: 'Coordination & Collection', tone: 'normal' },
    { id: 'S5', label: 'Review / QA', tone: 'normal' },
    { id: 'S6', label: 'Rework / Coordination Exception', tone: 'normal' },
    { id: 'S7', label: 'Integrated Draft', tone: 'normal' },
    { id: 'S8', label: 'Compliance Gate', tone: 'normal' },
    { id: 'S9', label: 'Submission', tone: 'normal' },
    { id: 'S10', label: 'Post-Submission Clarifications', tone: 'normal' },
    { id: 'S11', label: 'Win', tone: 'positive' },
    { id: 'S12', label: 'Loss', tone: 'positive' },
    { id: 'S13', label: 'Excluded / Withdrawn / Stopped', tone: 'terminal' },
];

const CANONICAL_EDGES: CanonicalEdge[] = [
    { from: 'START', to: 'S0', tone: 'structural' },
    { from: 'S0', to: 'S1', event: 'tender_document_ingested' },
    { from: 'S1', to: 'S2', event: 'go_decision_recorded' },
    { from: 'S1', to: 'S13', event: 'no_bid_decision_recorded', tone: 'terminal' },
    { from: 'S2', to: 'S2', event: 'bid_plan_created' },
    { from: 'S2', to: 'S2', event: 'bid_plan_approved' },
    { from: 'S2', to: 'S3', event: 'contribution_request_wave_opened' },
    { from: 'S3', to: 'S3', event: 'contribution_assignment_confirmed' },
    { from: 'S3', to: 'S4', event: 'contribution_received' },
    { from: 'S4', to: 'S5', event: 'contribution_review_started' },
    { from: 'S4', to: 'S5', event: 'review_cycle_started' },
    { from: 'S4', to: 'S6', event: 'coordination_risk_raised', tone: 'feedback' },
    { from: 'S5', to: 'S6', event: 'review_changes_requested', tone: 'feedback' },
    { from: 'S5', to: 'S6', event: 'rework_requested', tone: 'feedback' },
    { from: 'S5', to: 'S7', event: 'review_approved' },
    { from: 'S5', to: 'S7', event: 'draft_integrated_ready' },
    { from: 'S6', to: 'S5', event: 'rework_resolved', tone: 'feedback' },
    { from: 'S6', to: 'S4', event: 'rework_reescalated_to_coordination', tone: 'feedback' },
    { from: 'S7', to: 'S8', event: 'compliance_gate_opened' },
    { from: 'S8', to: 'S8', event: 'compliance_gate_failed', tone: 'feedback' },
    { from: 'S8', to: 'S7', event: 'compliance_gate_passed', tone: 'feedback' },
    { from: 'S8', to: 'S6', event: 'compliance_gate_rework_requested', tone: 'feedback' },
    { from: 'S8', to: 'S9', event: 'tender_submitted' },
    { from: 'S8', to: 'S13', event: 'tender_stopped_at_gate', tone: 'terminal' },
    { from: 'S9', to: 'S9', event: 'submission_acknowledged' },
    { from: 'S9', to: 'S8', event: 'submission_failed', tone: 'feedback' },
    { from: 'S9', to: 'S10', event: 'clarification_requested' },
    { from: 'S9', to: 'S11', event: 'award_confirmed', tone: 'terminal' },
    { from: 'S9', to: 'S12', event: 'loss_reason_recorded', tone: 'terminal' },
    { from: 'S9', to: 'S13', event: 'tender_excluded', tone: 'terminal' },
    { from: 'S9', to: 'S13', event: 'tender_withdrawn', tone: 'terminal' },
    { from: 'S9', to: 'S13', event: 'tender_stopped', tone: 'terminal' },
    { from: 'S10', to: 'S10', event: 'clarification_response_drafted' },
    { from: 'S10', to: 'S10', event: 'clarification_submitted' },
    { from: 'S10', to: 'S9', event: 'clarification_closed', tone: 'feedback' },
    { from: 'S10', to: 'S11', event: 'award_confirmed', tone: 'terminal' },
    { from: 'S10', to: 'S12', event: 'loss_reason_recorded', tone: 'terminal' },
    { from: 'S10', to: 'S13', event: 'tender_excluded', tone: 'terminal' },
    { from: 'S10', to: 'S13', event: 'tender_withdrawn', tone: 'terminal' },
    { from: 'S10', to: 'S13', event: 'tender_stopped', tone: 'terminal' },
    { from: 'S11', to: 'FIN', tone: 'structural' },
    { from: 'S12', to: 'FIN', tone: 'structural' },
    { from: 'S13', to: 'FIN', tone: 'structural' },
];

let mermaidLoader: Promise<typeof import('mermaid').default> | null = null;
let diagramTemplateLoader: Promise<string> | null = null;

function loadMermaid() {
    if (!mermaidLoader) {
        mermaidLoader = import('mermaid').then(({ default: mermaid }) => {
            mermaid.initialize({
                startOnLoad: false,
                securityLevel: 'loose',
                theme: 'base',
                fontFamily: 'Inter, Segoe UI, sans-serif',
            });

            return mermaid;
        });
    }

    return mermaidLoader;
}

function loadDiagramTemplate() {
    if (!diagramTemplateLoader) {
        const templateUrl = `${import.meta.env.BASE_URL}markov-diagram.mmd`;
        diagramTemplateLoader = fetch(templateUrl).then(async (response) => {
            if (!response.ok) {
                throw new Error(`Unable to load diagram template (${response.status}).`);
            }

            return response.text();
        });
    }

    return diagramTemplateLoader;
}

function escapeHtml(value: string): string {
    return value
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function wrapMermaidLabel(label: string): string {
    const separator = label.includes('_') ? '_' : ' ';
    const parts = separator === '_' ? label.split('_') : label.split(' ');
    const lines: string[] = [];
    let current = '';

    for (const part of parts) {
        const candidate = current ? `${current}${separator}${part}` : part;
        if (candidate.length <= 18) {
            current = candidate;
            continue;
        }

        if (current) {
            lines.push(current);
        }
        current = part;
    }

    if (current) {
        lines.push(current);
    }

    return lines.map(escapeHtml).join('<br/>');
}

function edgePair(edge: Pick<CanonicalEdge, 'from' | 'to'>): string {
    return `${edge.from}->${edge.to}`;
}

function edgeKey(edge: Pick<CanonicalEdge, 'from' | 'to' | 'event'>): string {
    return `${edgePair(edge)}|${edge.event || ''}`;
}

function collectObservedGraphState(currentState: string | null, transitions: KpiTransitions | null): ObservedGraphState {
    const visitedNodes = new Set<string>();
    const observedPairs = new Set<string>();
    const observedEdges = new Set<string>();

    if (currentState) {
        visitedNodes.add(currentState);
    }

    for (const item of transitions?.items || []) {
        if (item.from_state) {
            visitedNodes.add(item.from_state);
        }
        if (item.to_state) {
            visitedNodes.add(item.to_state);
        }
        if (!item.from_state || !item.to_state) {
            continue;
        }

        const pair = `${item.from_state}->${item.to_state}`;
        observedPairs.add(pair);

        if (item.source_event_type) {
            observedEdges.add(`${pair}|${item.source_event_type}`);
        }
    }

    const latestItem = transitions?.items?.[0];
    const latestPair = latestItem?.from_state && latestItem?.to_state
        ? `${latestItem.from_state}->${latestItem.to_state}`
        : null;
    const latestEdge = latestPair && latestItem?.source_event_type
        ? `${latestPair}|${latestItem.source_event_type}`
        : null;

    return {
        visitedNodes,
        observedPairs,
        observedEdges,
        latestPair,
        latestEdge,
    };
}

function isObservedEdge(edge: CanonicalEdge, state: ObservedGraphState): boolean {
    return state.observedEdges.has(edgeKey(edge)) || state.observedPairs.has(edgePair(edge));
}

function isLatestEdge(edge: CanonicalEdge, state: ObservedGraphState): boolean {
    return state.latestEdge === edgeKey(edge) || state.latestPair === edgePair(edge);
}

function resolveNodeClass(node: CanonicalNode, currentState: string | null, state: ObservedGraphState, visualMode: MarkovGraphVisualMode): string {
    if (node.id === currentState) {
        return 'current';
    }

    if (state.visitedNodes.has(node.id)) {
        return `${node.tone}Visited`;
    }

    return visualMode === 'presentation' ? `${node.tone}Muted` : node.tone;
}

function edgeStyle(edge: CanonicalEdge, state: ObservedGraphState, visualMode: MarkovGraphVisualMode): string {
    const observed = isObservedEdge(edge, state);
    const latest = isLatestEdge(edge, state);

    if (latest) {
        return 'stroke:#f59e0b,stroke-width:3.2px,opacity:1,color:#fde68a,fill:none';
    }

    if (observed) {
        return visualMode === 'presentation'
            ? 'stroke:#7dd3fc,stroke-width:2.6px,opacity:0.98,color:#e0f2fe,fill:none'
            : 'stroke:#93c5fd,stroke-width:2.6px,opacity:0.95,color:#e0f2fe,fill:none';
    }

    if (visualMode === 'presentation') {
        switch (edge.tone || 'default') {
            case 'terminal':
                return 'stroke:#7f1d1d,stroke-width:1.2px,opacity:0.12,color:transparent,fill:none';
            case 'feedback':
                return 'stroke:#78350f,stroke-width:1.15px,opacity:0.11,color:transparent,fill:none';
            case 'structural':
                return 'stroke:#334155,stroke-width:1.1px,opacity:0.1,color:transparent,fill:none';
            default:
                return 'stroke:#334155,stroke-width:1.1px,opacity:0.08,color:transparent,fill:none';
        }
    }

    switch (edge.tone || 'default') {
        case 'terminal':
            return 'stroke:#7f1d1d,stroke-width:1.35px,opacity:0.34,color:#fecaca,fill:none';
        case 'feedback':
            return 'stroke:#78350f,stroke-width:1.3px,opacity:0.32,color:#fef3c7,fill:none';
        case 'structural':
            return 'stroke:#475569,stroke-width:1.2px,opacity:0.28,color:#cbd5e1,fill:none';
        default:
            return 'stroke:#475569,stroke-width:1.2px,opacity:0.24,color:#dbeafe,fill:none';
    }
}

function buildMermaidDiagram(
    diagramTemplate: string,
    currentState: string | null,
    transitions: KpiTransitions | null,
    visualMode: MarkovGraphVisualMode,
): string {
    const state = collectObservedGraphState(currentState, transitions);
    const lines: string[] = [];
    const templateLines = diagramTemplate.replace(/\r\n/g, '\n').split('\n');
    let edgeIndex = 0;

    for (const line of templateLines) {
        const trimmed = line.trim();
        if (trimmed.startsWith('classDef ') || trimmed.startsWith('class ') || trimmed.startsWith('linkStyle ')) {
            continue;
        }

        const edgeMatch = line.match(EDGE_LINE_PATTERN);
        if (!edgeMatch) {
            lines.push(line);
            continue;
        }

        const [, indent = '    ', from, templateLabel, to] = edgeMatch;
        const edge = CANONICAL_EDGES[edgeIndex];
        if (!edge) {
            throw new Error('Diagram template contains more edges than the canonical Markov graph.');
        }
        if (edge.from !== from || edge.to !== to) {
            throw new Error(`Diagram template edge mismatch at index ${edgeIndex}: expected ${edge.from} -> ${edge.to}, got ${from} -> ${to}.`);
        }

        const showLabel = Boolean(edge.event) && (visualMode === 'analytical' || isObservedEdge(edge, state) || isLatestEdge(edge, state));
        if (showLabel) {
            const label = wrapMermaidLabel(templateLabel || edge.event || '');
            lines.push(`${indent}${from} -->|${label}| ${to}`);
        } else {
            lines.push(`${indent}${from} --> ${to}`);
        }

        edgeIndex += 1;
    }

    if (edgeIndex !== CANONICAL_EDGES.length) {
        throw new Error(`Diagram template edge mismatch: expected ${CANONICAL_EDGES.length} edges, found ${edgeIndex}.`);
    }

    lines.push('');
    lines.push('    classDef normal fill:#18263f,stroke:#93c5fd,stroke-width:1.35px,color:#f8fafc;');
    lines.push('    classDef positive fill:#173627,stroke:#6ee7b7,stroke-width:1.4px,color:#ecfdf5;');
    lines.push('    classDef terminal fill:#4a2026,stroke:#fca5a5,stroke-width:1.4px,color:#fff1f2;');
    lines.push('    classDef normalVisited fill:#1c3557,stroke:#bfdbfe,stroke-width:1.8px,color:#eff6ff;');
    lines.push('    classDef positiveVisited fill:#1b4332,stroke:#86efac,stroke-width:1.8px,color:#f0fdf4;');
    lines.push('    classDef terminalVisited fill:#5a2630,stroke:#fda4af,stroke-width:1.8px,color:#fff1f2;');
    lines.push('    classDef normalMuted fill:#0f172a,stroke:#334155,stroke-width:1px,color:#94a3b8;');
    lines.push('    classDef positiveMuted fill:#0d1f19,stroke:#14532d,stroke-width:1px,color:#86efac;');
    lines.push('    classDef terminalMuted fill:#261217,stroke:#7f1d1d,stroke-width:1px,color:#fca5a5;');
    lines.push('    classDef current fill:#0f3a4a,stroke:#67e8f9,stroke-width:2.4px,color:#ecfeff;');
    lines.push('    classDef endcap fill:#0f172a,stroke:#94a3b8,stroke-width:1.2px,color:#ffffff;');

    for (const node of CANONICAL_NODES) {
        lines.push(`    class ${node.id} ${resolveNodeClass(node, currentState, state, visualMode)};`);
    }

    lines.push('    class START,FIN endcap;');

    for (const [index, edge] of CANONICAL_EDGES.entries()) {
        lines.push(`    linkStyle ${index} ${edgeStyle(edge, state, visualMode)};`);
    }

    return lines.join('\n');
}

export default function MarkovStateGraph({
    currentState,
    transitions,
    visualMode = 'analytical',
}: MarkovStateGraphProps) {
    const hostRef = useRef<HTMLDivElement | null>(null);
    const renderSequenceRef = useRef(0);
    const baseId = useId().replace(/:/g, '-');
    const [diagramTemplate, setDiagramTemplate] = useState<string | null>(null);
    const [templateError, setTemplateError] = useState<string | null>(null);
    const [renderError, setRenderError] = useState<string | null>(null);

    useEffect(() => {
        let disposed = false;

        void loadDiagramTemplate()
            .then((template) => {
                if (!disposed) {
                    setDiagramTemplate(template);
                    setTemplateError(null);
                }
            })
            .catch((error) => {
                if (!disposed) {
                    const message = error instanceof Error ? error.message : 'Unable to load diagram template.';
                    setTemplateError(message);
                }
            });

        return () => {
            disposed = true;
        };
    }, []);

    const diagram = useMemo(
        () => (diagramTemplate
            ? buildMermaidDiagram(diagramTemplate, currentState, transitions, visualMode)
            : null),
        [currentState, diagramTemplate, transitions, visualMode],
    );

    useEffect(() => {
        const activeDiagram = diagram;
        if (!activeDiagram) {
            return;
        }
        const mermaidSource: string = activeDiagram;

        renderSequenceRef.current += 1;
        const renderId = `markov-${baseId}-${renderSequenceRef.current}`;
        let disposed = false;

        async function renderDiagram() {
            if (!hostRef.current) {
                return;
            }

            setRenderError(null);
            hostRef.current.innerHTML = '';

            try {
                const mermaid = await loadMermaid();
                const { svg, bindFunctions } = await mermaid.render(renderId, mermaidSource);
                if (disposed || !hostRef.current) {
                    return;
                }

                hostRef.current.innerHTML = svg;
                hostRef.current.dataset.mode = visualMode;
                const svgElement = hostRef.current.querySelector('svg');
                if (svgElement) {
                    svgElement.removeAttribute('width');
                    svgElement.removeAttribute('height');
                    svgElement.style.width = '100%';
                    svgElement.style.maxWidth = '100%';
                    svgElement.style.height = 'auto';
                    svgElement.style.display = 'block';
                }

                bindFunctions?.(hostRef.current);
            } catch (error) {
                if (!disposed) {
                    const message = error instanceof Error ? error.message : 'Unable to render Mermaid graph.';
                    setRenderError(message);
                }
            }
        }

        void renderDiagram();

        return () => {
            disposed = true;
        };
    }, [baseId, diagram, visualMode]);

    const errorMessage = templateError || renderError;

    if (errorMessage) {
        return (
            <div
                style={{
                    borderRadius: '18px',
                    border: '1px solid rgba(248, 113, 113, 0.35)',
                    background: 'rgba(127, 29, 29, 0.18)',
                    padding: '1rem',
                    color: '#fecaca',
                }}
            >
                Mermaid render failed: {errorMessage}
            </div>
        );
    }

    if (!diagramTemplate) {
        return (
            <div
                style={{
                    borderRadius: '18px',
                    border: '1px solid rgba(148, 163, 184, 0.18)',
                    background: 'rgba(15, 23, 42, 0.72)',
                    padding: '1rem',
                    color: '#cbd5e1',
                }}
            >
                Loading Mermaid diagram template...
            </div>
        );
    }

    return (
        <div style={{ overflow: 'hidden' }}>
            <div ref={hostRef} />
        </div>
    );
}
