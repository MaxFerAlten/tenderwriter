import type { SystemCapabilitiesData } from '../api/client';

const OPS_UNAVAILABLE_PATTERNS = [
    'ops agent unavailable',
    'docker monitoring is disabled',
    'unable to fetch container',
    'unable to list containers',
    'unable to reach docker api',
    'docker api unavailable',
    'service unavailable',
    'all connection attempts failed',
    'connection refused',
    'timed out',
];

export function isOpsMonitoringUnavailableError(error: unknown): boolean {
    if (!(error instanceof Error)) {
        return false;
    }

    const message = error.message.toLowerCase();
    return OPS_UNAVAILABLE_PATTERNS.some((pattern) => message.includes(pattern));
}

export function buildUnavailableCapabilities(
    current: SystemCapabilitiesData | null,
    reason: string,
): SystemCapabilitiesData {
    const normalizedReason = reason.trim() || 'Ops agent unavailable.';

    return {
        ops_agent: {
            available: false,
            reason: normalizedReason,
        },
        ops_monitoring: {
            available: false,
            reason: normalizedReason,
        },
        nginx_hot_reload: {
            available: false,
            reason: current?.nginx_hot_reload.reason ?? normalizedReason,
        },
    };
}
