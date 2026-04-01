import { describe, expect, it } from 'vitest';

import { buildDevProxy } from './devProxyConfig';

describe('buildDevProxy', () => {
    it('keeps Mattermost reachable through /mm in dev by default', () => {
        const proxy = buildDevProxy({});

        expect(proxy['/api']).toMatchObject({
            target: 'http://localhost:8000',
            ws: true,
        });
        expect(proxy['/mm']).toMatchObject({
            target: 'http://localhost:8065',
            ws: true,
            xfwd: true,
        });
    });

    it('honors explicit Mattermost proxy overrides from the environment', () => {
        const proxy = buildDevProxy({
            VITE_MM_TARGET: 'http://mattermost:8065',
        });

        expect(proxy['/mm']).toMatchObject({
            target: 'http://mattermost:8065',
            changeOrigin: true,
            ws: true,
            xfwd: true,
        });
    });
});
