import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
    loadOnlyOfficeApiScript,
    resetOnlyOfficeScriptLoadersForTest,
} from './OnlyOfficeEditor';

type ScriptEventType = 'load' | 'error';

class MockScriptElement {
    src = '';
    async = false;
    private listeners: Record<ScriptEventType, Array<() => void>> = {
        load: [],
        error: [],
    };

    addEventListener(type: ScriptEventType, listener: () => void): void {
        this.listeners[type].push(listener);
    }

    setAttribute(_name: string, _value: string): void {
        // Attribute values are not used by the loader assertions in these tests.
    }

    dispatch(type: ScriptEventType): void {
        this.listeners[type].forEach((listener) => listener());
    }
}

describe('loadOnlyOfficeApiScript', () => {
    const createElement = vi.fn();
    const querySelector = vi.fn();
    const appendChild = vi.fn();

    beforeEach(() => {
        createElement.mockReset();
        querySelector.mockReset();
        appendChild.mockReset();
        resetOnlyOfficeScriptLoadersForTest();

        vi.stubGlobal('window', { DocsAPI: undefined });
        vi.stubGlobal('document', {
            querySelector,
            createElement,
            head: { appendChild },
        });
    });

    afterEach(() => {
        resetOnlyOfficeScriptLoadersForTest();
        vi.unstubAllGlobals();
        vi.restoreAllMocks();
    });

    it('waits for an existing script tag to finish loading before resolving', async () => {
        const existingScript = new MockScriptElement();
        querySelector.mockReturnValue(existingScript);

        let resolved = false;
        const promise = loadOnlyOfficeApiScript('http://localhost:8443').then(() => {
            resolved = true;
        });

        await Promise.resolve();
        expect(resolved).toBe(false);
        expect(createElement).not.toHaveBeenCalled();

        (window as typeof globalThis & { DocsAPI?: unknown }).DocsAPI = { DocEditor: vi.fn() };
        existingScript.dispatch('load');

        await promise;
        expect(resolved).toBe(true);
        expect(appendChild).not.toHaveBeenCalled();
    });

    it('reuses the same in-flight loader promise for duplicate requests', async () => {
        const appendedScripts: MockScriptElement[] = [];
        createElement.mockImplementation(() => new MockScriptElement());
        querySelector.mockReturnValue(null);
        appendChild.mockImplementation((script: MockScriptElement) => {
            appendedScripts.push(script);
        });

        const firstPromise = loadOnlyOfficeApiScript('http://localhost:8443');
        const secondPromise = loadOnlyOfficeApiScript('http://localhost:8443');

        expect(secondPromise).toBe(firstPromise);
        expect(createElement).toHaveBeenCalledTimes(1);
        expect(appendedScripts).toHaveLength(1);

        (window as typeof globalThis & { DocsAPI?: unknown }).DocsAPI = { DocEditor: vi.fn() };
        appendedScripts[0].dispatch('load');

        await expect(Promise.all([firstPromise, secondPromise])).resolves.toEqual([
            undefined,
            undefined,
        ]);
    });
});
