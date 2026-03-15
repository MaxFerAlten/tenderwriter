import { lazy, Suspense } from 'react';
import { Loader2 } from 'lucide-react';

import type { OnlyOfficeEditorProps } from '../pages/OnlyOfficeEditor';

const loadOnlyOfficeEditor = () => import('../pages/OnlyOfficeEditor');
const OnlyOfficeEditor = lazy(loadOnlyOfficeEditor);
let preloadPromise: Promise<unknown> | null = null;

export function prefetchOnlyOfficeEditor(): Promise<void> {
    if (!preloadPromise) {
        preloadPromise = loadOnlyOfficeEditor();
    }

    return preloadPromise.then(() => undefined);
}

function EditorFallback({ minHeight }: { minHeight: string }) {
    return (
        <div
            style={{
                minHeight,
                height: '100%',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '0.6rem',
                color: 'var(--text-secondary)',
                background: 'rgba(15, 23, 42, 0.18)',
            }}
        >
            <Loader2 size={18} className="spin" />
            <span>Loading editor...</span>
        </div>
    );
}

interface LazyOnlyOfficeEditorProps extends OnlyOfficeEditorProps {
    minHeight?: string;
}

export default function LazyOnlyOfficeEditor({ minHeight = '420px', ...props }: LazyOnlyOfficeEditorProps) {
    return (
        <Suspense fallback={<EditorFallback minHeight={minHeight} />}>
            <OnlyOfficeEditor {...props} />
        </Suspense>
    );
}
