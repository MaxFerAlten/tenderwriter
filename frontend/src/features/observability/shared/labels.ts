export const PHASE_LABELS: Record<string, string> = {
    S0: 'Intake Opportunity',
    S1: 'Go / No-Go',
    S2: 'Bid Planning',
    S3: 'Request Contributions',
    S4: 'Coordination & Collection',
    S5: 'Quality / Technical Review',
    S6: 'Rework / Clarifications',
    S7: 'Integrated Draft',
    S8: 'Compliance Gate',
    S9: 'Submission',
    S10: 'Post-Submission Clarifications',
    S11: 'Win',
    S12: 'Loss',
    S13: 'Excluded / Withdrawn / No-Bid',
};

export function phaseLabel(phase: string | null): string {
    if (!phase) return 'Phase unavailable';
    return PHASE_LABELS[phase] || phase;
}

export function semanticStatusLabel(status: string | null | undefined): string {
    switch (status) {
        case 'official':
            return 'semantic official';
        case 'fallback':
            return 'semantic fallback';
        case 'shadow':
            return 'semantic shadow';
        default:
            return status || 'semantic';
    }
}

export function analysisJobLabel(jobStatus: string | null | undefined): string {
    switch (jobStatus) {
        case 'queued':
            return 'Queued';
        case 'running':
            return 'Running';
        case 'succeeded':
            return 'Completed';
        case 'failed':
            return 'Failed';
        case 'degraded':
            return 'Service degraded';
        default:
            return 'Idle';
    }
}

export function forecastSignalLabel(signalType: string | null | undefined): string {
    switch (signalType) {
        case 'predicted':
            return 'predicted forecast';
        case 'calibrated':
            return 'calibrated forecast';
        case 'locked':
            return 'locked outcome';
        case 'not_ready':
            return 'forecast pending';
        default:
            return signalType || 'forecast signal';
    }
}
