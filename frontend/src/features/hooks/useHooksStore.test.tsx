import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { useHooksStore } from './useHooksStore';
import { useHookStatus } from './index';

function HooksStoreHarness() {
    const hookStore = useHooksStore();

    return (
        <div>
            <span>{hookStore.hooks.length}</span>
            <span>{hookStore.events.length}</span>
            <span>{String(hookStore.loading)}</span>
            <span>{hookStore.error ?? 'none'}</span>
        </div>
    );
}

function HookStatusHarness() {
    const status = useHookStatus();

    return (
        <div>
            <span>{status.totalHooks}</span>
            <span>{status.activeHooks}</span>
            <span>{status.disabledHooks}</span>
            <span>{status.error ?? 'none'}</span>
        </div>
    );
}

describe('useHooksStore', () => {
    it('preserves the empty initial state contract before effects run', () => {
        const html = renderToStaticMarkup(<HooksStoreHarness />);

        expect(html).toContain('<span>0</span><span>0</span><span>false</span><span>none</span>');
    });

    it('keeps the hooks feature entrypoint renderable after wiring api imports', () => {
        const html = renderToStaticMarkup(<HookStatusHarness />);

        expect(html).toContain('<span>0</span><span>0</span><span>0</span><span>none</span>');
    });
});
