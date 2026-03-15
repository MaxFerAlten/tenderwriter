import type { ComplianceGateRecord, Requirement } from '../../api/client';

export interface RequirementSummary {
    total: number;
    fullyAddressed: number;
    partiallyAddressed: number;
    notAddressed: number;
    mapped: number;
    unmapped: number;
}

export function summarizeRequirements(requirements: Requirement[]): RequirementSummary {
    return requirements.reduce<RequirementSummary>(
        (summary, requirement) => {
            summary.total += 1;
            if (requirement.mapped_section_id) {
                summary.mapped += 1;
            } else {
                summary.unmapped += 1;
            }

            switch (requirement.compliance_status) {
                case 'fully_addressed':
                    summary.fullyAddressed += 1;
                    break;
                case 'partially_addressed':
                    summary.partiallyAddressed += 1;
                    break;
                default:
                    summary.notAddressed += 1;
                    break;
            }

            return summary;
        },
        {
            total: 0,
            fullyAddressed: 0,
            partiallyAddressed: 0,
            notAddressed: 0,
            mapped: 0,
            unmapped: 0,
        }
    );
}

export function findAutoComplianceGate(gates: ComplianceGateRecord[]): ComplianceGateRecord | null {
    return gates.find((gate) => gate.gate_name.trim().toLowerCase() === 'auto compliance readiness') || null;
}

export function buildComplianceGateNarrative(
    summary: RequirementSummary,
    gate: ComplianceGateRecord | null,
    analyticalPhase: string | null
): string {
    if (summary.total === 0) {
        return 'No extracted requirements are mirrored yet, so the automatic compliance gate cannot explain risk.';
    }

    if (!gate) {
        if (analyticalPhase === 'S8') {
            return 'The tender is already in compliance-gate phase, but no automatic gate record is available yet in the operational workspace.';
        }
        return 'The automatic compliance gate has not materialized yet; current risk is inferred from requirement coverage only.';
    }

    if (gate.status === 'failed') {
        return `${summary.notAddressed + summary.partiallyAddressed} requirements are still unresolved and the automatic gate is failed.`;
    }

    if (gate.status === 'open') {
        return `${summary.notAddressed + summary.partiallyAddressed} requirements still need attention, so the automatic gate remains open.`;
    }

    if (gate.status === 'passed') {
        return `All ${summary.total} mirrored requirements are fully addressed, so the automatic gate is passed.`;
    }

    return 'The automatic compliance gate is present, but its current state requires manual inspection.';
}

