import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import type {
    ConsolidatedRequirementRecord,
    OperationalWorkspace,
    RequirementExtractionRunRecord,
    RequirementRelationRecord,
    TenderDetail,
} from '../../api/client';
import ComplianceDrilldownPanel from './ComplianceDrilldownPanel';
import { RequirementWorkbenchContent, type RequirementWorkbenchData } from './RequirementWorkbenchPanel';

const tenderDetail: TenderDetail = {
    id: 12,
    title: 'Healthcare tender',
    client: 'Region',
    description: 'Tender detail for observability.',
    deadline: '2026-04-30T10:00:00Z',
    status: 'active',
    category: 'Healthcare',
    tags: [],
    budget_estimate: null,
    created_at: '2026-04-01T10:00:00Z',
    created_by: 1,
    created_by_name: 'Admin',
    requirements: [
        {
            id: 101,
            requirement_text: 'Provide signed annex',
            category: 'legal',
            priority: 'high',
            compliance_status: 'fully_addressed',
            mapped_section_id: 33,
            mapped_section_title: 'Compliance matrix',
            coverage_source: 'consolidated_approved',
        },
        {
            id: 102,
            requirement_text: 'Provide insurance',
            category: 'risk',
            priority: 'medium',
            compliance_status: 'partially_addressed',
            mapped_section_id: null,
            mapped_section_title: null,
            coverage_source: 'legacy',
        },
    ],
};

const workspace: OperationalWorkspace = {
    summary: {
        tender_id: 12,
        contribution_count: 0,
        request_count: 0,
        open_rework_count: 0,
        open_gate_count: 1,
        call_count: 0,
    },
    contributions: [],
    requests: [],
    reviews: [],
    reworks: [],
    gates: [
        {
            id: 401,
            tender_id: 12,
            contribution_unit_id: null,
            owner_user_id: null,
            gate_name: 'Auto compliance readiness',
            due_at: '2026-04-28T10:00:00Z',
            evaluated_at: null,
            decision_notes: 'Waiting for insurance evidence.',
            status: 'open',
        },
    ],
    calls: [],
};

const candidateRuns: RequirementExtractionRunRecord[] = [
    {
        id: 71,
        source_document_ref: 'tenders/12/rfp.pdf',
        filename: 'rfp.pdf',
        extraction_method: 'heuristic_v1',
        candidate_count: 2,
        metadata_json: { staged_candidate_count: 2 },
        created_at: '2026-04-04T10:00:00Z',
        candidates: [
            {
                id: 701,
                candidate_position: 1,
                summary_text: 'Provide signed annex A.',
                normalized_text: 'provide signed annex a',
                category: 'Section 1',
                priority: 'high',
                confidence: 0.91,
                source_document_ref: 'tenders/12/rfp.pdf',
                source_reference: 'Section 1',
                created_at: '2026-04-04T10:00:00Z',
            },
            {
                id: 702,
                candidate_position: 2,
                summary_text: 'Submit insurance certificate.',
                normalized_text: 'submit insurance certificate',
                category: 'Section 7',
                priority: 'high',
                confidence: 0.88,
                source_document_ref: 'tenders/12/rfp.pdf',
                source_reference: 'Section 7',
                created_at: '2026-04-04T10:01:00Z',
            },
        ],
    },
];

const consolidatedRequirements: ConsolidatedRequirementRecord[] = [
    {
        id: 91,
        canonical_text: 'Submit insurance certificate.',
        normalized_text: 'submit insurance certificate',
        category: 'Section 7',
        priority: 'high',
        confidence: 0.83,
        source_count: 1,
        consolidation_method: 'staging_v1',
        review_state: 'pending',
        graph_state: 'active',
        parent_requirement_id: 92,
        parent_requirement_key: 'Provide signed annex A.',
        applicability: { lot: '1' },
        conditions: ['Before service start'],
        exceptions: ['Optional modules excluded'],
        metadata_json: { sources: [{ candidate_id: 702 }] },
        created_at: '2026-04-04T10:30:00Z',
    },
    {
        id: 92,
        canonical_text: 'Provide signed annex A.',
        normalized_text: 'provide signed annex a',
        category: 'Section 1',
        priority: 'high',
        confidence: 0.9,
        source_count: 1,
        consolidation_method: 'staging_v1',
        review_state: 'approved',
        graph_state: 'active',
        parent_requirement_id: null,
        parent_requirement_key: null,
        applicability: {},
        conditions: [],
        exceptions: [],
        metadata_json: {
            sources: [{ candidate_id: 701 }],
            document_precedence: {
                primary_role: 'clarification',
                superseded_sources: [{ document_role: 'disciplinare' }],
            },
            source_variants: {
                variant_count: 2,
                has_variants: true,
                examples: ['Provide signed annex A with wet signature.', 'Provide signed annex A.'],
            },
        },
        created_at: '2026-04-04T10:31:00Z',
    },
];

const obsoleteRequirements: ConsolidatedRequirementRecord[] = [
    {
        id: 190,
        canonical_text: 'Legacy warranty declaration.',
        normalized_text: 'legacy warranty declaration',
        category: 'Historical',
        priority: 'low',
        confidence: 0.45,
        source_count: 1,
        consolidation_method: 'staging_v1',
        review_state: 'approved',
        graph_state: 'obsolete',
        parent_requirement_id: null,
        parent_requirement_key: null,
        applicability: {},
        conditions: [],
        exceptions: [],
        metadata_json: { lifecycle: { graph_state: 'obsolete', reason: 'missing_from_latest_rebuild' } },
        created_at: '2026-04-08T10:20:00Z',
    },
];

const relations: RequirementRelationRecord[] = [
    {
        id: 501,
        source_requirement_id: 91,
        source_requirement_text: 'Submit insurance certificate with broker attestation.',
        target_requirement_id: 92,
        target_requirement_text: 'Submit insurance certificate.',
        relation_type: 'overrides',
        confidence: 0.91,
        review_state: 'pending',
        graph_state: 'active',
        metadata_json: {
            inference_method: 'lexical_override_v1',
            shared_terms: ['submit', 'insurance', 'certificate'],
            source_role: 'clarification',
            target_role: 'capitolato',
            conflict_signals: ['numeric_mismatch'],
        },
        created_at: '2026-04-04T11:10:00Z',
    },
    {
        id: 502,
        source_requirement_id: 93,
        source_requirement_text: 'Submit the final commercial offer after presenting the technical plan.',
        target_requirement_id: 94,
        target_requirement_text: 'Present the technical plan.',
        relation_type: 'depends_on',
        confidence: 0.77,
        review_state: 'approved',
        graph_state: 'active',
        metadata_json: {
            inference_method: 'dependency_clause_v1',
            matched_clause: 'presenting the technical plan',
        },
        created_at: '2026-04-04T11:20:00Z',
    },
    {
        id: 503,
        source_requirement_id: 95,
        source_requirement_text: 'Provide warranty coverage for 12 months.',
        target_requirement_id: 96,
        target_requirement_text: 'Provide warranty coverage for 24 months.',
        relation_type: 'conflicts_with',
        confidence: 0.8,
        review_state: 'pending',
        graph_state: 'active',
        metadata_json: {
            inference_method: 'cross_document_conflict_v1',
            source_role: 'annex',
            target_role: 'annex',
            conflict_signals: ['numeric_mismatch'],
        },
        created_at: '2026-04-04T11:30:00Z',
    },
];

const obsoleteRelations: RequirementRelationRecord[] = [
    {
        id: 590,
        source_requirement_id: 190,
        source_requirement_text: 'Legacy source requirement.',
        target_requirement_id: 191,
        target_requirement_text: 'Legacy target requirement.',
        relation_type: 'overrides',
        confidence: 0.52,
        review_state: 'approved',
        graph_state: 'obsolete',
        metadata_json: { lifecycle: { graph_state: 'obsolete', reason: 'missing_from_latest_rebuild' } },
        created_at: '2026-04-08T10:25:00Z',
    },
];

const pipelineData: RequirementWorkbenchData = {
    candidateRuns,
    consolidatedRequirements,
    obsoleteRequirements,
    reviewQueue: consolidatedRequirements.filter((item) => item.review_state === 'pending'),
    relationReviewQueue: relations.filter((item) => item.review_state === 'pending'),
    relations,
    obsoleteRelations,
};

describe('ComplianceDrilldownPanel', () => {
    it('preserves requirement coverage and automatic gate narrative after adding the workbench', () => {
        const html = renderToStaticMarkup(
            <ComplianceDrilldownPanel
                tenderDetail={tenderDetail}
                workspace={workspace}
                analyticalPhase="S8"
            />
        );

        expect(html).toContain('Requirement coverage');
        expect(html).toContain('Automatic compliance gate');
        expect(html).toContain('Provide signed annex');
        expect(html).toContain('consolidated approved');
        expect(html).toContain('Provide insurance');
        expect(html).toContain('Not mapped to a proposal section yet.');
        expect(html).toContain('automatic gate remains open');
    });

    it('renders staged runs, consolidated requirements and review queue in the requirement workbench', () => {
        const html = renderToStaticMarkup(
            <RequirementWorkbenchContent
                tenderId={12}
                tenderTitle="Healthcare tender"
                data={pipelineData}
                noteDrafts={{ 91: 'Need legal confirmation.' }}
                relationNoteDrafts={{ 501: 'Clarification should override the base clause.' }}
                editorialDrafts={{ 91: 'Submit insurance certificate with broker attestation.' }}
                mergeTargetDrafts={{ 91: '92' }}
                splitDrafts={{ 91: 'Submit insurance certificate.\nProvide broker attestation.' }}
                relationTypeDrafts={{ 501: 'overrides' }}
            />
        );

        expect(html).toContain('Requirement pipeline workbench');
        expect(html).toContain('Latest extraction runs');
        expect(html).toContain('Consolidated requirement set');
        expect(html).toContain('Review queue');
        expect(html).toContain('rfp.pdf');
        expect(html).toContain('Provide signed annex A.');
        expect(html).toContain('Submit insurance certificate.');
        expect(html).toContain('Pending review');
        expect(html).toContain('Need legal confirmation.');
        expect(html).toContain('Manual edit: corrected canonical requirement text');
        expect(html).toContain('Submit insurance certificate with broker attestation.');
        expect(html).toContain('Merge into requirement id');
        expect(html).toContain('Split into atomic requirements');
        expect(html).toContain('Save edit');
        expect(html).toContain('Merge');
        expect(html).toContain('Split');
        expect(html).toContain('Dismiss');
        expect(html).toContain('Requirement relations');
        expect(html).toContain('Relation review queue');
        expect(html).toContain('Submit insurance certificate with broker attestation.');
        expect(html).toContain('Submit the final commercial offer after presenting the technical plan.');
        expect(html).toContain('Clarification should override the base clause.');
        expect(html).toContain('Save relation edit');
        expect(html).toContain('Dismiss relation');
        expect(html).toContain('Relations');
        expect(html).toContain('Relation review');
        expect(html).toContain('1 overrides');
        expect(html).toContain('1 depends on');
        expect(html).toContain('1 conflicts');
        expect(html).toContain('conflicts with');
        expect(html).toContain('Precedence: clarification over disciplinare');
        expect(html).toContain('Source variants: 2');
        expect(html).toContain('Document route: clarification -&gt; capitolato');
        expect(html).toContain('Document route: annex -&gt; annex');
        expect(html).toContain('Conflict signals: numeric mismatch');
        expect(html).toContain('Graph V2');
        expect(html).toContain('parent Provide signed annex A.');
        expect(html).toContain('applies to lot: 1');
        expect(html).toContain('conditions Before service start');
        expect(html).toContain('exceptions Optional modules excluded');
        expect(html).toContain('Obsolete graph');
        expect(html).toContain('Graph audit trail');
        expect(html).toContain('Obsolete consolidated requirements');
        expect(html).toContain('Obsolete requirement relations');
        expect(html).toContain('Legacy warranty declaration.');
        expect(html).toContain('Legacy source requirement.');
        expect(html).toContain('missing_from_latest_rebuild');
        expect(html).toContain('1 obsolete requirements');
        expect(html).toContain('1 obsolete relations');
    });
});
