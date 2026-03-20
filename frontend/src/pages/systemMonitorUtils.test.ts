import { describe, expect, it } from 'vitest';

import { buildUnavailableCapabilities, isOpsMonitoringUnavailableError } from './systemMonitorUtils';

describe('isOpsMonitoringUnavailableError', () => {
    it('matches canonical ops-agent availability failures', () => {
        expect(isOpsMonitoringUnavailableError(new Error('Ops agent unavailable.'))).toBe(true);
        expect(isOpsMonitoringUnavailableError(new Error('All connection attempts failed'))).toBe(true);
        expect(isOpsMonitoringUnavailableError(new Error('Docker API unavailable: connection refused'))).toBe(true);
    });

    it('does not treat per-container lookup failures as global outages', () => {
        expect(isOpsMonitoringUnavailableError(new Error("Container 'tw-missing' not found"))).toBe(false);
    });
});

describe('buildUnavailableCapabilities', () => {
    it('forces monitoring capabilities off with a stable reason', () => {
        const capabilities = buildUnavailableCapabilities(
            {
                ops_agent: { available: true, reason: null },
                ops_monitoring: { available: true, reason: null },
                nginx_hot_reload: { available: true, reason: null },
            },
            'Ops agent unavailable.',
        );

        expect(capabilities.ops_agent).toEqual({
            available: false,
            reason: 'Ops agent unavailable.',
        });
        expect(capabilities.ops_monitoring).toEqual({
            available: false,
            reason: 'Ops agent unavailable.',
        });
        expect(capabilities.nginx_hot_reload.available).toBe(false);
    });
});
