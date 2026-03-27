import type { KpiTransitions } from '../../api/client';

type Anchor = 'top' | 'right' | 'bottom' | 'left';
type NodeTone = 'normal' | 'positive' | 'terminal';
type EdgeTone = 'default' | 'feedback' | 'terminal';
export type MarkovGraphVisualMode = 'analytical' | 'presentation';

interface GraphNode {
    id: string;
    x: number;
    y: number;
    width: number;
    height: number;
    label: string;
    tone: NodeTone;
}

interface GraphEdge {
    from: string;
    to: string;
    labels: string[];
    fromAnchor: Anchor;
    toAnchor: Anchor;
    tone?: EdgeTone;
    dashed?: boolean;
    curveX?: number;
    curveY?: number;
    labelDx?: number;
    labelDy?: number;
    loopAnchor?: Anchor;
    loopSize?: number;
}

interface GraphBand {
    label: string;
    x: number;
    y: number;
    width: number;
}

interface Point {
    x: number;
    y: number;
}

interface RectBounds {
    x: number;
    y: number;
    width: number;
    height: number;
}

type LabelVariant = 'visited' | 'latest';

interface EdgeRenderData {
    edge: GraphEdge;
    edgeId: string;
    geometry: {
        path: string;
        label: Point;
    };
    colors: {
        stroke: string;
        width: number;
        opacity: number;
    };
    variant: LabelVariant;
    visibleLabels: string[];
    shouldRender: boolean;
}

interface LabelPlacement {
    edgeId: string;
    x: number;
    y: number;
    width: number;
    height: number;
    lines: string[];
    variant: LabelVariant;
}

interface EdgeVisibility {
    shouldRender: boolean;
    isObserved: boolean;
    isLatest: boolean;
}

interface MarkovStateGraphProps {
    currentState: string | null;
    transitions: KpiTransitions | null;
    visualMode?: MarkovGraphVisualMode;
}

const SVG_WIDTH = 1704;
const SVG_HEIGHT = 1056;
const GRAPH_TRANSLATE_X = 24;
const GRAPH_TRANSLATE_Y = 28;
const NODE_WIDTH = 176;
const NODE_HEIGHT = 60;
const GRAPH_WIDTH = SVG_WIDTH - (GRAPH_TRANSLATE_X * 2);
const GRAPH_HEIGHT = SVG_HEIGHT - (GRAPH_TRANSLATE_Y * 2);
const LABEL_MARGIN = 18;
const LABEL_NODE_CLEARANCE = 20;
const LABEL_LABEL_CLEARANCE = 14;

const GRAPH_BANDS: GraphBand[] = [
    { label: 'Governance corridor', x: 44, y: 56, width: 1128 },
    { label: 'Execution loop', x: 740, y: 234, width: 676 },
    { label: 'Submission corridor', x: 1186, y: 584, width: 286 },
    { label: 'Terminal outcomes', x: 1462, y: 506, width: 178 },
];

const GRAPH_NODES: GraphNode[] = [
    { id: 'S0', x: 40, y: 96, width: NODE_WIDTH, height: NODE_HEIGHT, label: 'Intake Opportunity', tone: 'normal' },
    { id: 'S1', x: 272, y: 96, width: NODE_WIDTH, height: NODE_HEIGHT, label: 'Go / No-Go', tone: 'normal' },
    { id: 'S2', x: 504, y: 96, width: NODE_WIDTH, height: NODE_HEIGHT, label: 'Bid Planning', tone: 'normal' },
    { id: 'S3', x: 736, y: 96, width: NODE_WIDTH, height: NODE_HEIGHT, label: 'Request Contributions', tone: 'normal' },
    { id: 'S4', x: 968, y: 96, width: NODE_WIDTH, height: NODE_HEIGHT, label: 'Coordination & Collection', tone: 'normal' },
    { id: 'S5', x: 972, y: 272, width: NODE_WIDTH, height: NODE_HEIGHT, label: 'Review / QA', tone: 'normal' },
    { id: 'S6', x: 728, y: 444, width: NODE_WIDTH, height: NODE_HEIGHT, label: 'Rework / Coordination Exception', tone: 'normal' },
    { id: 'S7', x: 1212, y: 272, width: NODE_WIDTH, height: NODE_HEIGHT, label: 'Integrated Draft', tone: 'normal' },
    { id: 'S8', x: 1212, y: 444, width: NODE_WIDTH, height: NODE_HEIGHT, label: 'Compliance Gate', tone: 'normal' },
    { id: 'S9', x: 1212, y: 618, width: NODE_WIDTH, height: NODE_HEIGHT, label: 'Submission', tone: 'normal' },
    { id: 'S10', x: 1212, y: 784, width: NODE_WIDTH, height: NODE_HEIGHT, label: 'Post-Submission Clarifications', tone: 'normal' },
    { id: 'S11', x: 1460, y: 566, width: NODE_WIDTH, height: NODE_HEIGHT, label: 'Win', tone: 'positive' },
    { id: 'S12', x: 1460, y: 712, width: NODE_WIDTH, height: NODE_HEIGHT, label: 'Loss', tone: 'positive' },
    { id: 'S13', x: 1460, y: 858, width: NODE_WIDTH, height: NODE_HEIGHT, label: 'Excluded / Withdrawn / Stopped', tone: 'terminal' },
];

const GRAPH_EDGES: GraphEdge[] = [
    { from: 'S0', to: 'S1', labels: ['tender_document_ingested'], fromAnchor: 'right', toAnchor: 'left', labelDy: -18 },
    { from: 'S1', to: 'S2', labels: ['go_decision_recorded'], fromAnchor: 'right', toAnchor: 'left', labelDy: -18 },
    { from: 'S1', to: 'S13', labels: ['no_bid_decision_recorded'], fromAnchor: 'bottom', toAnchor: 'left', tone: 'terminal', dashed: true, curveX: 168, curveY: 204, labelDx: 132, labelDy: 46 },
    { from: 'S2', to: 'S2', labels: ['bid_plan_created', 'bid_plan_approved'], fromAnchor: 'top', toAnchor: 'top', loopAnchor: 'top', loopSize: 38, labelDy: -30 },
    { from: 'S2', to: 'S3', labels: ['contribution_request_wave_opened'], fromAnchor: 'right', toAnchor: 'left', labelDy: -18 },
    { from: 'S3', to: 'S3', labels: ['contribution_assignment_confirmed'], fromAnchor: 'top', toAnchor: 'top', loopAnchor: 'top', loopSize: 38, labelDy: -30 },
    { from: 'S3', to: 'S4', labels: ['contribution_received'], fromAnchor: 'right', toAnchor: 'left', labelDy: -18 },
    { from: 'S4', to: 'S5', labels: ['contribution_review_started', 'review_cycle_started'], fromAnchor: 'bottom', toAnchor: 'top', labelDx: 84, labelDy: 12 },
    { from: 'S4', to: 'S6', labels: ['coordination_risk_raised'], fromAnchor: 'bottom', toAnchor: 'top', tone: 'feedback', curveX: -148, curveY: 28, labelDx: -86, labelDy: 24 },
    { from: 'S5', to: 'S6', labels: ['review_changes_requested', 'rework_requested'], fromAnchor: 'bottom', toAnchor: 'top', tone: 'feedback', curveX: -40, curveY: 14, labelDx: -18, labelDy: 20 },
    { from: 'S5', to: 'S7', labels: ['review_approved', 'draft_integrated_ready'], fromAnchor: 'right', toAnchor: 'left', labelDy: -18 },
    { from: 'S6', to: 'S5', labels: ['rework_resolved'], fromAnchor: 'top', toAnchor: 'left', curveX: 60, curveY: -88, labelDx: 6, labelDy: -18 },
    { from: 'S6', to: 'S4', labels: ['rework_reescalated_to_coordination'], fromAnchor: 'top', toAnchor: 'bottom', tone: 'feedback', curveX: -144, curveY: -28, labelDx: -96, labelDy: -22 },
    { from: 'S7', to: 'S8', labels: ['compliance_gate_opened'], fromAnchor: 'bottom', toAnchor: 'top', labelDx: 50, labelDy: -4 },
    { from: 'S8', to: 'S8', labels: ['compliance_gate_failed'], fromAnchor: 'right', toAnchor: 'right', loopAnchor: 'right', loopSize: 40, tone: 'feedback', labelDx: 56, labelDy: -8 },
    { from: 'S8', to: 'S7', labels: ['compliance_gate_passed'], fromAnchor: 'top', toAnchor: 'bottom', labelDx: 54, labelDy: 8 },
    { from: 'S8', to: 'S6', labels: ['compliance_gate_rework_requested'], fromAnchor: 'left', toAnchor: 'right', tone: 'feedback', labelDy: -18 },
    { from: 'S8', to: 'S9', labels: ['tender_submitted'], fromAnchor: 'bottom', toAnchor: 'top', labelDx: 36, labelDy: -8 },
    { from: 'S8', to: 'S13', labels: ['tender_stopped_at_gate'], fromAnchor: 'right', toAnchor: 'left', tone: 'terminal', dashed: true, curveX: 124, curveY: 114, labelDx: 104, labelDy: 64 },
    { from: 'S9', to: 'S9', labels: ['submission_acknowledged'], fromAnchor: 'left', toAnchor: 'left', loopAnchor: 'left', loopSize: 40, labelDx: -66, labelDy: -8 },
    { from: 'S9', to: 'S8', labels: ['submission_failed'], fromAnchor: 'top', toAnchor: 'bottom', tone: 'feedback', labelDx: 40, labelDy: 0 },
    { from: 'S9', to: 'S10', labels: ['clarification_requested'], fromAnchor: 'bottom', toAnchor: 'top', labelDx: 44, labelDy: -8 },
    { from: 'S9', to: 'S11', labels: ['award_confirmed'], fromAnchor: 'right', toAnchor: 'left', tone: 'terminal', labelDx: 18, labelDy: -18 },
    { from: 'S9', to: 'S12', labels: ['loss_reason_recorded'], fromAnchor: 'right', toAnchor: 'left', tone: 'terminal', curveY: 16, labelDx: 18, labelDy: 6 },
    { from: 'S9', to: 'S13', labels: ['tender_excluded', 'tender_withdrawn', 'tender_stopped'], fromAnchor: 'right', toAnchor: 'left', tone: 'terminal', dashed: true, curveY: 38, labelDx: 30, labelDy: 32 },
    { from: 'S10', to: 'S10', labels: ['clarification_response_drafted', 'clarification_submitted'], fromAnchor: 'right', toAnchor: 'right', loopAnchor: 'right', loopSize: 40, labelDx: 64, labelDy: -18 },
    { from: 'S10', to: 'S9', labels: ['clarification_closed'], fromAnchor: 'top', toAnchor: 'bottom', labelDx: -52, labelDy: -8 },
    { from: 'S10', to: 'S11', labels: ['award_confirmed'], fromAnchor: 'right', toAnchor: 'left', tone: 'terminal', curveY: -150, labelDx: 18, labelDy: -38 },
    { from: 'S10', to: 'S12', labels: ['loss_reason_recorded'], fromAnchor: 'right', toAnchor: 'left', tone: 'terminal', curveY: -46, labelDx: 22, labelDy: -12 },
    { from: 'S10', to: 'S13', labels: ['tender_excluded', 'tender_withdrawn', 'tender_stopped'], fromAnchor: 'right', toAnchor: 'left', tone: 'terminal', dashed: true, curveY: 28, labelDx: 28, labelDy: 6 },
];

const NODE_MAP = new Map(GRAPH_NODES.map((node) => [node.id, node]));

const LABEL_RADII = [0, 40, 76, 112, 148] as const;

function anchorPoint(node: GraphNode, anchor: Anchor): Point {
    switch (anchor) {
        case 'top':
            return { x: node.x + node.width / 2, y: node.y };
        case 'right':
            return { x: node.x + node.width, y: node.y + node.height / 2 };
        case 'bottom':
            return { x: node.x + node.width / 2, y: node.y + node.height };
        case 'left':
            return { x: node.x, y: node.y + node.height / 2 };
        default:
            return { x: node.x, y: node.y };
    }
}

function anchorVector(anchor: Anchor): Point {
    switch (anchor) {
        case 'top':
            return { x: 0, y: -1 };
        case 'right':
            return { x: 1, y: 0 };
        case 'bottom':
            return { x: 0, y: 1 };
        case 'left':
            return { x: -1, y: 0 };
        default:
            return { x: 0, y: 0 };
    }
}

function cubicPoint(start: Point, control1: Point, control2: Point, end: Point, t: number): Point {
    const mt = 1 - t;
    return {
        x: (mt ** 3 * start.x) + (3 * mt ** 2 * t * control1.x) + (3 * mt * t ** 2 * control2.x) + (t ** 3 * end.x),
        y: (mt ** 3 * start.y) + (3 * mt ** 2 * t * control1.y) + (3 * mt * t ** 2 * control2.y) + (t ** 3 * end.y),
    };
}

function buildLoopGeometry(node: GraphNode, edge: GraphEdge): { path: string; label: Point } {
    const loopAnchor = edge.loopAnchor || 'top';
    const size = edge.loopSize || 38;
    const center = anchorPoint(node, loopAnchor);

    switch (loopAnchor) {
        case 'right': {
            const path = [
                `M ${node.x + node.width} ${node.y + node.height * 0.28}`,
                `C ${node.x + node.width + size} ${node.y + node.height * 0.12}, ${node.x + node.width + size} ${node.y + node.height * 0.88}, ${node.x + node.width} ${node.y + node.height * 0.72}`,
            ].join(' ');
            return { path, label: { x: center.x + size + 22 + (edge.labelDx || 0), y: center.y + (edge.labelDy || 0) } };
        }
        case 'left': {
            const path = [
                `M ${node.x} ${node.y + node.height * 0.28}`,
                `C ${node.x - size} ${node.y + node.height * 0.12}, ${node.x - size} ${node.y + node.height * 0.88}, ${node.x} ${node.y + node.height * 0.72}`,
            ].join(' ');
            return { path, label: { x: center.x - size - 22 + (edge.labelDx || 0), y: center.y + (edge.labelDy || 0) } };
        }
        case 'bottom': {
            const path = [
                `M ${node.x + node.width * 0.28} ${node.y + node.height}`,
                `C ${node.x + node.width * 0.12} ${node.y + node.height + size}, ${node.x + node.width * 0.88} ${node.y + node.height + size}, ${node.x + node.width * 0.72} ${node.y + node.height}`,
            ].join(' ');
            return { path, label: { x: center.x + (edge.labelDx || 0), y: center.y + size + 22 + (edge.labelDy || 0) } };
        }
        case 'top':
        default: {
            const path = [
                `M ${node.x + node.width * 0.28} ${node.y}`,
                `C ${node.x + node.width * 0.12} ${node.y - size}, ${node.x + node.width * 0.88} ${node.y - size}, ${node.x + node.width * 0.72} ${node.y}`,
            ].join(' ');
            return { path, label: { x: center.x + (edge.labelDx || 0), y: center.y - size - 18 + (edge.labelDy || 0) } };
        }
    }
}

function buildEdgeGeometry(edge: GraphEdge): { path: string; label: Point } {
    const fromNode = NODE_MAP.get(edge.from);
    const toNode = NODE_MAP.get(edge.to);
    if (!fromNode || !toNode) {
        return { path: '', label: { x: 0, y: 0 } };
    }

    if (edge.from === edge.to) {
        return buildLoopGeometry(fromNode, edge);
    }

    const start = anchorPoint(fromNode, edge.fromAnchor);
    const end = anchorPoint(toNode, edge.toAnchor);
    const startVector = anchorVector(edge.fromAnchor);
    const endVector = anchorVector(edge.toAnchor);
    const distance = Math.max(Math.abs(end.x - start.x), Math.abs(end.y - start.y));
    const strength = Math.max(52, distance * 0.26);
    const control1 = {
        x: start.x + startVector.x * strength + (edge.curveX || 0),
        y: start.y + startVector.y * strength + (edge.curveY || 0),
    };
    const control2 = {
        x: end.x + endVector.x * strength + (edge.curveX || 0),
        y: end.y + endVector.y * strength + (edge.curveY || 0),
    };
    const midpoint = cubicPoint(start, control1, control2, end, 0.5);

    return {
        path: `M ${start.x} ${start.y} C ${control1.x} ${control1.y}, ${control2.x} ${control2.y}, ${end.x} ${end.y}`,
        label: {
            x: midpoint.x + (edge.labelDx || 0),
            y: midpoint.y + (edge.labelDy || 0),
        },
    };
}

function wrapEdgeLabel(label: string): string[] {
    if (label.length <= 24) {
        return [label];
    }

    const midpoint = Math.floor(label.length / 2);
    const splitIndex = label.indexOf('_', midpoint);
    if (splitIndex > 0) {
        return [label.slice(0, splitIndex + 1), label.slice(splitIndex + 1)];
    }

    return [label.slice(0, midpoint), label.slice(midpoint)];
}

function splitNodeLabel(label: string): string[] {
    const separators = [' / ', ' & '];
    for (const separator of separators) {
        if (label.includes(separator)) {
            return label.split(separator);
        }
    }

    if (label.length > 24) {
        const midpoint = Math.floor(label.length / 2);
        const splitIndex = label.lastIndexOf(' ', midpoint);
        if (splitIndex > 0) {
            return [label.slice(0, splitIndex), label.slice(splitIndex + 1)];
        }
    }

    return [label];
}

function edgeKey(edge: Pick<GraphEdge, 'from' | 'to'>): string {
    return `${edge.from}->${edge.to}`;
}

function expandRect(rect: RectBounds, padding: number): RectBounds {
    return {
        x: rect.x - padding,
        y: rect.y - padding,
        width: rect.width + (padding * 2),
        height: rect.height + (padding * 2),
    };
}

function rectsOverlap(a: RectBounds, b: RectBounds): boolean {
    return a.x < (b.x + b.width)
        && (a.x + a.width) > b.x
        && a.y < (b.y + b.height)
        && (a.y + a.height) > b.y;
}

function clamp(value: number, min: number, max: number): number {
    return Math.min(Math.max(value, min), max);
}

function labelRect(x: number, y: number, width: number, height: number): RectBounds {
    return {
        x: x - (width / 2),
        y: y - (height / 2),
        width,
        height,
    };
}

function labelAxis(edge: GraphEdge): 'horizontal' | 'vertical' | 'diagonal' | 'loop' {
    if (edge.from === edge.to) {
        return 'loop';
    }

    const horizontalAnchors = new Set<Anchor>(['left', 'right']);
    const verticalAnchors = new Set<Anchor>(['top', 'bottom']);

    if (horizontalAnchors.has(edge.fromAnchor) && horizontalAnchors.has(edge.toAnchor)) {
        return 'horizontal';
    }

    if (verticalAnchors.has(edge.fromAnchor) && verticalAnchors.has(edge.toAnchor)) {
        return 'vertical';
    }

    return 'diagonal';
}

function labelCandidates(base: Point, edge: GraphEdge): Point[] {
    const axis = labelAxis(edge);
    const candidates: Point[] = [];
    const seen = new Set<string>();

    function push(dx: number, dy: number) {
        const roundedDx = Math.round(dx);
        const roundedDy = Math.round(dy);
        const key = `${roundedDx}:${roundedDy}`;
        if (seen.has(key)) {
            return;
        }
        seen.add(key);
        candidates.push({
            x: base.x + roundedDx,
            y: base.y + roundedDy,
        });
    }

    for (const radius of LABEL_RADII) {
        if (radius === 0) {
            push(0, 0);
            continue;
        }

        if (axis === 'horizontal') {
            push(0, -radius);
            push(0, radius);
            push(radius * 0.55, -radius * 0.45);
            push(-radius * 0.55, -radius * 0.45);
            push(radius * 0.55, radius * 0.45);
            push(-radius * 0.55, radius * 0.45);
            push(radius, 0);
            push(-radius, 0);
            continue;
        }

        if (axis === 'vertical') {
            push(radius, 0);
            push(-radius, 0);
            push(radius * 0.78, -radius * 0.3);
            push(-radius * 0.78, -radius * 0.3);
            push(radius * 0.78, radius * 0.3);
            push(-radius * 0.78, radius * 0.3);
            push(0, -radius);
            push(0, radius);
            continue;
        }

        if (axis === 'diagonal') {
            push(radius * 0.72, -radius * 0.6);
            push(-radius * 0.72, -radius * 0.6);
            push(radius * 0.72, radius * 0.6);
            push(-radius * 0.72, radius * 0.6);
            push(0, -radius);
            push(0, radius);
            push(radius, 0);
            push(-radius, 0);
            continue;
        }

        switch (edge.loopAnchor || 'top') {
            case 'right':
                push(radius, 0);
                push(radius * 0.78, -radius * 0.32);
                push(radius * 0.78, radius * 0.32);
                push(0, -radius);
                push(0, radius);
                break;
            case 'left':
                push(-radius, 0);
                push(-radius * 0.78, -radius * 0.32);
                push(-radius * 0.78, radius * 0.32);
                push(0, -radius);
                push(0, radius);
                break;
            case 'bottom':
                push(0, radius);
                push(radius * 0.52, radius * 0.4);
                push(-radius * 0.52, radius * 0.4);
                push(radius, 0);
                push(-radius, 0);
                break;
            case 'top':
            default:
                push(0, -radius);
                push(radius * 0.52, -radius * 0.4);
                push(-radius * 0.52, -radius * 0.4);
                push(radius, 0);
                push(-radius, 0);
                break;
        }
    }

    return candidates;
}

function nodeColors(
    node: GraphNode,
    currentState: string | null,
    visitedStates: Set<string>,
    visualMode: MarkovGraphVisualMode,
): { fill: string; stroke: string; text: string; idFill: string } {
    const isCurrent = currentState === node.id;
    const wasVisited = visitedStates.has(node.id);
    const isPresentation = visualMode === 'presentation';

    if (isCurrent) {
        return {
            fill: isPresentation ? 'rgba(56, 189, 248, 0.2)' : 'rgba(34, 211, 238, 0.18)',
            stroke: isPresentation ? '#7dd3fc' : '#67e8f9',
            text: '#ecfeff',
            idFill: isPresentation ? '#dbeafe' : '#a5f3fc',
        };
    }

    if (node.tone === 'positive') {
        return {
            fill: wasVisited
                ? (isPresentation ? 'rgba(34, 197, 94, 0.16)' : 'rgba(16, 185, 129, 0.18)')
                : (isPresentation ? 'rgba(21, 128, 61, 0.13)' : 'rgba(20, 83, 45, 0.16)'),
            stroke: wasVisited
                ? (isPresentation ? '#86efac' : '#6ee7b7')
                : (isPresentation ? 'rgba(134, 239, 172, 0.28)' : 'rgba(110, 231, 183, 0.38)'),
            text: '#ecfdf5',
            idFill: isPresentation ? '#dcfce7' : '#bbf7d0',
        };
    }

    if (node.tone === 'terminal') {
        return {
            fill: wasVisited
                ? (isPresentation ? 'rgba(244, 63, 94, 0.16)' : 'rgba(239, 68, 68, 0.2)')
                : (isPresentation ? 'rgba(127, 29, 29, 0.14)' : 'rgba(127, 29, 29, 0.16)'),
            stroke: wasVisited
                ? (isPresentation ? '#fda4af' : '#fca5a5')
                : (isPresentation ? 'rgba(251, 113, 133, 0.26)' : 'rgba(252, 165, 165, 0.4)'),
            text: '#fff5f5',
            idFill: isPresentation ? '#ffe4e6' : '#fecaca',
        };
    }

    if (wasVisited) {
        return {
            fill: isPresentation ? 'rgba(59, 130, 246, 0.14)' : 'rgba(59, 130, 246, 0.16)',
            stroke: isPresentation ? '#bfdbfe' : '#93c5fd',
            text: '#eff6ff',
            idFill: isPresentation ? '#dbeafe' : '#bfdbfe',
        };
    }

    return {
        fill: isPresentation ? 'rgba(15, 23, 42, 0.9)' : 'rgba(17, 24, 39, 0.82)',
        stroke: isPresentation ? 'rgba(191, 219, 254, 0.18)' : 'rgba(148, 163, 184, 0.34)',
        text: isPresentation ? '#f8fafc' : '#e5eef8',
        idFill: isPresentation ? '#cbd5e1' : '#94a3b8',
    };
}

function edgeColors(
    edge: GraphEdge,
    visitedEdgeKeys: Set<string>,
    latestEdgeKey: string | null,
    visualMode: MarkovGraphVisualMode,
): { stroke: string; width: number; opacity: number } {
    const key = edgeKey(edge);
    const isPresentation = visualMode === 'presentation';

    if (latestEdgeKey === key) {
        return { stroke: isPresentation ? '#fbbf24' : '#f59e0b', width: isPresentation ? 2.9 : 3.1, opacity: 1 };
    }
    if (visitedEdgeKeys.has(key)) {
        return { stroke: isPresentation ? '#93c5fd' : '#7dd3fc', width: isPresentation ? 2.35 : 2.6, opacity: isPresentation ? 0.92 : 0.96 };
    }
    if (edge.tone === 'terminal') {
        return { stroke: isPresentation ? 'rgba(251, 113, 133, 0.22)' : 'rgba(248, 113, 113, 0.28)', width: isPresentation ? 1.2 : 1.4, opacity: isPresentation ? 0.48 : 0.58 };
    }
    if (edge.tone === 'feedback') {
        return { stroke: isPresentation ? 'rgba(250, 204, 21, 0.18)' : 'rgba(251, 191, 36, 0.24)', width: isPresentation ? 1.2 : 1.4, opacity: isPresentation ? 0.44 : 0.54 };
    }
    return { stroke: isPresentation ? 'rgba(148, 163, 184, 0.15)' : 'rgba(148, 163, 184, 0.22)', width: isPresentation ? 1.1 : 1.25, opacity: isPresentation ? 0.34 : 0.46 };
}

function edgeVisibility(
    edgeId: string,
    visitedEdgeKeys: Set<string>,
    latestEdgeKey: string | null,
    visualMode: MarkovGraphVisualMode,
): EdgeVisibility {
    const isLatest = latestEdgeKey === edgeId;
    const isObserved = visitedEdgeKeys.has(edgeId);

    if (visualMode === 'presentation') {
        return {
            shouldRender: isObserved || isLatest,
            isObserved,
            isLatest,
        };
    }

    return {
        shouldRender: true,
        isObserved,
        isLatest,
    };
}

function collectObservedLabels(transitions: KpiTransitions | null): Map<string, string[]> {
    const labelsByEdge = new Map<string, string[]>();

    for (const item of transitions?.items || []) {
        if (!item.from_state || !item.to_state || !item.source_event_type) {
            continue;
        }

        const key = `${item.from_state}->${item.to_state}`;
        const current = labelsByEdge.get(key) || [];
        if (!current.includes(item.source_event_type)) {
            current.push(item.source_event_type);
            labelsByEdge.set(key, current);
        }
    }

    return labelsByEdge;
}

function labelBoxSize(lines: string[]): { width: number; height: number } {
    const maxLength = lines.reduce((max, line) => Math.max(max, line.length), 0);
    const width = Math.max(92, Math.min(252, maxLength * 6.7 + 22));
    const height = Math.max(30, lines.length * 13 + 16);
    return { width, height };
}

function renderLabelBox(lines: string[], x: number, y: number, variant: LabelVariant, visualMode: MarkovGraphVisualMode) {
    const { width, height } = labelBoxSize(lines);
    const isPresentation = visualMode === 'presentation';
    const fill = variant === 'latest'
        ? (isPresentation ? 'rgba(251, 191, 36, 0.12)' : 'rgba(245, 158, 11, 0.14)')
        : (isPresentation ? 'rgba(15, 23, 42, 0.76)' : 'rgba(15, 23, 42, 0.88)');
    const stroke = variant === 'latest'
        ? (isPresentation ? 'rgba(251, 191, 36, 0.42)' : 'rgba(245, 158, 11, 0.55)')
        : (isPresentation ? 'rgba(191, 219, 254, 0.22)' : 'rgba(125, 211, 252, 0.32)');
    const text = variant === 'latest'
        ? (isPresentation ? '#fef3c7' : '#fde68a')
        : (isPresentation ? '#eff6ff' : '#e2f3ff');
    const baseY = y - (height / 2) + 14;

    return (
        <g transform={`translate(${x}, ${y})`}>
            <rect
                x={-width / 2}
                y={-height / 2}
                width={width}
                height={height}
                rx={isPresentation ? '14' : '12'}
                fill={fill}
                stroke={stroke}
                strokeWidth={isPresentation ? '1' : '1.2'}
            />
            <text
                x="0"
                y={baseY - y}
                textAnchor="middle"
                fontSize={isPresentation ? '10.2' : '10.5'}
                fontWeight="700"
                fill={text}
            >
                {lines.map((line, index) => (
                    <tspan key={`${line}-${index}`} x="0" dy={index === 0 ? 0 : 12}>
                        {line}
                    </tspan>
                ))}
            </text>
        </g>
    );
}

function buildLabelPlacements(edgeRenderData: EdgeRenderData[]): LabelPlacement[] {
    const placed: LabelPlacement[] = [];
    const blockedNodeRects = GRAPH_NODES.map((node) => expandRect({
        x: node.x,
        y: node.y,
        width: node.width,
        height: node.height,
    }, LABEL_NODE_CLEARANCE));
    const blockedBandRects = GRAPH_BANDS.map((band) => expandRect({
        x: band.x - 10,
        y: band.y - 18,
        width: band.width + 20,
        height: 32,
    }, 4));
    const obstacleRects = [...blockedNodeRects, ...blockedBandRects];

    const sortable = edgeRenderData
        .filter((item) => item.visibleLabels.length > 0)
        .sort((left, right) => {
            if (left.variant !== right.variant) {
                return left.variant === 'latest' ? -1 : 1;
            }
            const leftArea = labelBoxSize(left.visibleLabels).width * labelBoxSize(left.visibleLabels).height;
            const rightArea = labelBoxSize(right.visibleLabels).width * labelBoxSize(right.visibleLabels).height;
            return rightArea - leftArea;
        });

    for (const item of sortable) {
        const { width, height } = labelBoxSize(item.visibleLabels);
        const candidates = labelCandidates(item.geometry.label, item.edge);
        let bestPlacement: LabelPlacement | null = null;
        let bestScore = Number.POSITIVE_INFINITY;

        for (const candidate of candidates) {
            const clampedX = clamp(candidate.x, LABEL_MARGIN + (width / 2), GRAPH_WIDTH - LABEL_MARGIN - (width / 2));
            const clampedY = clamp(candidate.y, LABEL_MARGIN + (height / 2), GRAPH_HEIGHT - LABEL_MARGIN - (height / 2));
            const rect = labelRect(clampedX, clampedY, width, height);
            const expandedRect = expandRect(rect, LABEL_LABEL_CLEARANCE);

            const nodeHits = obstacleRects.reduce((count, obstacleRect) => (
                rectsOverlap(expandedRect, obstacleRect) ? count + 1 : count
            ), 0);

            const labelHits = placed.reduce((count, other) => {
                const otherRect = expandRect(labelRect(other.x, other.y, other.width, other.height), LABEL_LABEL_CLEARANCE);
                return rectsOverlap(expandedRect, otherRect) ? count + 1 : count;
            }, 0);

            const distancePenalty = Math.abs(clampedX - item.geometry.label.x) + Math.abs(clampedY - item.geometry.label.y);
            const score = (nodeHits * 1000) + (labelHits * 100) + distancePenalty;

            if (score < bestScore) {
                bestScore = score;
                bestPlacement = {
                    edgeId: item.edgeId,
                    x: clampedX,
                    y: clampedY,
                    width,
                    height,
                    lines: item.visibleLabels,
                    variant: item.variant,
                };
            }

            if (score === 0) {
                break;
            }
        }

        if (bestPlacement) {
            placed.push(bestPlacement);
        }
    }

    return placed;
}

export default function MarkovStateGraph({ currentState, transitions, visualMode = 'analytical' }: MarkovStateGraphProps) {
    const visitedStates = new Set<string>();
    const visitedEdgeKeys = new Set<string>();
    const observedLabelsByEdge = collectObservedLabels(transitions);
    const isPresentation = visualMode === 'presentation';
    const arrowMarkerId = `markov-arrow-${visualMode}`;
    const nodeGlowId = `nodeGlow-${visualMode}`;
    const gridPatternId = `markov-grid-${visualMode}`;
    const presentationSurfaceId = `markov-surface-${visualMode}`;

    if (currentState) {
        visitedStates.add(currentState);
    }

    for (const item of transitions?.items || []) {
        if (item.from_state) {
            visitedStates.add(item.from_state);
        }
        if (item.to_state) {
            visitedStates.add(item.to_state);
        }
        if (item.from_state && item.to_state) {
            visitedEdgeKeys.add(`${item.from_state}->${item.to_state}`);
        }
    }

    const latestTransition = transitions?.items[0] || null;
    const latestEdgeKey = latestTransition ? `${latestTransition.from_state}->${latestTransition.to_state}` : null;
    const edgeRenderData: EdgeRenderData[] = GRAPH_EDGES.map((edge) => {
        const edgeId = edgeKey(edge);
        const observedLabels = observedLabelsByEdge.get(edgeId) || [];
        const visibility = edgeVisibility(edgeId, visitedEdgeKeys, latestEdgeKey, visualMode);

        return {
            edge,
            edgeId,
            geometry: buildEdgeGeometry(edge),
            colors: edgeColors(edge, visitedEdgeKeys, latestEdgeKey, visualMode),
            variant: visibility.isLatest ? ('latest' as const) : ('visited' as const),
            visibleLabels: observedLabels.length > 0 ? observedLabels.flatMap(wrapEdgeLabel) : [],
            shouldRender: visibility.shouldRender,
        };
    }).filter((item) => item.shouldRender);
    const labelPlacements = buildLabelPlacements(edgeRenderData);

    return (
        <div style={{ overflowX: 'auto', overflowY: 'hidden' }}>
            <svg
                viewBox={`0 0 ${SVG_WIDTH} ${SVG_HEIGHT}`}
                style={{ width: '100%', minWidth: isPresentation ? '1240px' : '1120px', height: 'auto', display: 'block' }}
                role="img"
                aria-label="Markov state process graph"
            >
                <defs>
                    <linearGradient id={presentationSurfaceId} x1="0%" y1="0%" x2="100%" y2="100%">
                        <stop offset="0%" stopColor="#020617" stopOpacity="0.98" />
                        <stop offset="52%" stopColor="#0f172a" stopOpacity="0.96" />
                        <stop offset="100%" stopColor="#082f49" stopOpacity="0.92" />
                    </linearGradient>
                    <pattern id={gridPatternId} width="24" height="24" patternUnits="userSpaceOnUse">
                        <circle cx="12" cy="12" r="0.9" fill={isPresentation ? 'rgba(191, 219, 254, 0.04)' : 'rgba(125, 211, 252, 0.08)'} />
                    </pattern>
                    <filter id={nodeGlowId} x="-30%" y="-30%" width="160%" height="160%">
                        <feDropShadow dx="0" dy="0" stdDeviation={isPresentation ? '8' : '9'} floodColor={isPresentation ? 'rgba(125, 211, 252, 0.22)' : 'rgba(34, 211, 238, 0.28)'} />
                    </filter>
                    <marker
                        id={arrowMarkerId}
                        markerUnits="userSpaceOnUse"
                        markerWidth="8"
                        markerHeight="8"
                        refX="6.4"
                        refY="4"
                        orient="auto"
                    >
                        <path d="M 0 0 L 8 4 L 0 8 z" fill={isPresentation ? 'rgba(226, 232, 240, 0.58)' : 'rgba(226, 232, 240, 0.72)'} />
                    </marker>
                </defs>

                <rect
                    x="0"
                    y="0"
                    width={SVG_WIDTH}
                    height={SVG_HEIGHT}
                    rx="28"
                    fill={isPresentation ? `url(#${presentationSurfaceId})` : 'rgba(15, 23, 42, 0.36)'}
                />
                <rect x="0" y="0" width={SVG_WIDTH} height={SVG_HEIGHT} rx="28" fill={`url(#${gridPatternId})`} />
                {isPresentation && (
                    <rect
                        x="0"
                        y="0"
                        width={SVG_WIDTH}
                        height={SVG_HEIGHT}
                        rx="28"
                        fill="rgba(15, 23, 42, 0.14)"
                        stroke="rgba(191, 219, 254, 0.08)"
                    />
                )}

                <g transform={`translate(${GRAPH_TRANSLATE_X} ${GRAPH_TRANSLATE_Y})`}>
                    {GRAPH_BANDS.map((band) => (
                        <g key={band.label}>
                            {isPresentation && (
                                <rect
                                    x={band.x - 12}
                                    y={band.y - 17}
                                    width={Math.max(152, band.label.length * 8.4 + 26)}
                                    height="24"
                                    rx="12"
                                    fill="rgba(15, 23, 42, 0.58)"
                                    stroke="rgba(191, 219, 254, 0.08)"
                                />
                            )}
                            <text
                                x={band.x}
                                y={band.y}
                                fontSize="11"
                                fontWeight="700"
                                letterSpacing="0.12em"
                                fill={isPresentation ? 'rgba(203, 213, 225, 0.68)' : 'rgba(148, 163, 184, 0.55)'}
                            >
                                {band.label.toUpperCase()}
                            </text>
                            <line
                                x1={band.x}
                                y1={band.y + 10}
                                x2={band.x + band.width}
                                y2={band.y + 10}
                                stroke={isPresentation ? 'rgba(148, 163, 184, 0.12)' : 'rgba(148, 163, 184, 0.18)'}
                                strokeDasharray="6 8"
                            />
                        </g>
                    ))}

                    {edgeRenderData.map((item) => {
                        return (
                            <g key={`${item.edgeId}-${item.edge.labels.join('|')}`}>
                                <path
                                    d={item.geometry.path}
                                    fill="none"
                                    stroke={item.colors.stroke}
                                    strokeWidth={item.colors.width}
                                    strokeDasharray={item.edge.dashed ? '8 8' : undefined}
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                    opacity={item.colors.opacity}
                                    markerEnd={`url(#${arrowMarkerId})`}
                                >
                                    <title>{item.edge.labels.join(', ')}</title>
                                </path>
                            </g>
                        );
                    })}

                    {GRAPH_NODES.map((node) => {
                        const wasVisited = visitedStates.has(node.id);
                        const isCurrent = currentState === node.id;
                        const colors = nodeColors(node, currentState, visitedStates, visualMode);
                        const lines = splitNodeLabel(node.label);
                        const groupOpacity = visualMode === 'presentation' && !wasVisited && !isCurrent ? 0.34 : 1;

                        return (
                            <g key={node.id} filter={isCurrent ? `url(#${nodeGlowId})` : undefined} opacity={groupOpacity}>
                                <rect
                                    x={node.x}
                                    y={node.y}
                                    width={node.width}
                                    height={node.height}
                                    rx={isPresentation ? '20' : '18'}
                                    fill={colors.fill}
                                    stroke={colors.stroke}
                                    strokeWidth={isCurrent ? (isPresentation ? 2 : 2.2) : (isPresentation ? 1.1 : 1.25)}
                                />
                                <text
                                    x={node.x + 16}
                                    y={node.y + 19}
                                    fill={colors.idFill}
                                    fontSize={isPresentation ? '11.2' : '11.5'}
                                    fontWeight="800"
                                    letterSpacing="0.08em"
                                >
                                    {node.id}
                                </text>
                                <text
                                    x={node.x + 16}
                                    y={node.y + 37}
                                    fill={colors.text}
                                    fontSize={isPresentation ? '12.2' : '12.5'}
                                    fontWeight="650"
                                >
                                    {lines.map((line, index) => (
                                        <tspan key={`${node.id}-${index}`} x={node.x + 16} dy={index === 0 ? 0 : 13}>
                                            {line}
                                        </tspan>
                                    ))}
                                </text>
                            </g>
                        );
                    })}

                    {labelPlacements.map((placement) => (
                        <g key={`label-${placement.edgeId}`}>
                            {renderLabelBox(placement.lines, placement.x, placement.y, placement.variant, visualMode)}
                        </g>
                    ))}
                </g>
            </svg>
        </div>
    );
}
