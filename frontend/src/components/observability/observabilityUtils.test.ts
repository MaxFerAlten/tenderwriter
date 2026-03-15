import { describe, expect, it } from 'vitest';

import type { ComplianceGateRecord, Requirement } from '../../api/client';
import {
    buildComplianceGateNarrative,
    findAutoComplianceGate,
    summarizeRequirements,
} from './observabilityUtils';

const requirements: Requirement[] = [
    {
        id: 1,
        requirement_text: 'Provide signed annex',
        category: 'legal',
        priority: 'high',
        compliance_status: 'fully_addressed',
        mapped_section_id: 10,
        mapped_section_title: 'Compliance matrix',
    },
    {
        id: 2,
        requirement_text: 'Provide insurance',
        category: 'risk',
        priority: 'medium',
        compliance_status: 'partially_addressed',
        mapped_section_id: null,
        mapped_section_title: null,
    },
];

describe('observabilityUtils', () => {
    it('summarizes requirement coverage for the admin drilldown', () => {
        const summary = summarizeRequirements(requirements);

        expect(summary).toEqual({
            total: 2,
            fullyAddressed: 1,
            partiallyAddressed: 1,
            notAddressed: 0,
            mapped: 1,
            unmapped: 1,
        });
    });

    it('finds the automatic compliance gate from the operational workspace', () => {
        const gate = findAutoComplianceGate([
            {
                id: 7,
                tender_id: 99,
                contribution_unit_id: null,
                owner_user_id: null,
                gate_name: 'Manual legal review',
                due_at: null,
                evaluated_at: null,
                decision_notes: null,
                status: 'open',
            },
            {
                id: 8,
                tender_id: 99,
                contribution_unit_id: null,
                owner_user_id: null,
                gate_name: 'Auto compliance readiness',
                due_at: null,
                evaluated_at: null,
                decision_notes: 'Waiting for one annex',
                status: 'failed',
            } satisfies ComplianceGateRecord,
        ]);

        expect(gate?.id).toBe(8);
    });

    it('explains why the automatic gate is blocking the tender', () => {
        const summary = summarizeRequirements(requirements);
        const narrative = buildComplianceGateNarrative(summary, {
            id: 8,
            tender_id: 99,
            contribution_unit_id: null,
            owner_user_id: null,
            gate_name: 'Auto compliance readiness',
            due_at: null,
            evaluated_at: null,
            decision_notes: 'Waiting for one annex',
            status: 'open',
        }, 'S8');

        expect(narrative).toContain('automatic gate remains open');
        expect(narrative).toContain('1 requirements still need attention');
    });
});

