import { useEffect, useRef, useState, useCallback, useMemo } from 'react';
import { Loader2, AlertCircle } from 'lucide-react';

declare global {
    interface Window {
        DocsAPI: {
            // Use any to avoid strict TypeScript constructor constraints with the OnlyOffice API
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            DocEditor: any;
        };
    }
}

export interface OnlyOfficeEditorProps {
    mode?: 'proposal' | 'library' | 'create';
    proposalId?: number;
    sectionId?: number;
    libraryBlockId?: number;
    title: string;
    onlyofficeApiUrl: string;
    onConfigLoaded?: (config: any) => void;
    onDocumentStateChange?: (isDirty: boolean) => void;
}

interface EditorConfig {
    config: any;
    token: string;
    onlyoffice_url: string;
}

const onlyOfficeScriptLoaders = new Map<string, Promise<void>>();

function loadOnlyOfficeApiScript(onlyofficeApiUrl: string): Promise<void> {
    if (window.DocsAPI) {
        return Promise.resolve();
    }

    const src = `${onlyofficeApiUrl}/web-apps/apps/api/documents/api.js`;
    const existingLoader = onlyOfficeScriptLoaders.get(src);
    if (existingLoader) {
        return existingLoader;
    }

    const loader = new Promise<void>((resolve, reject) => {
        const handleLoad = () => {
            if (window.DocsAPI) {
                resolve();
                return;
            }

            reject(
                new Error(
                    `OnlyOffice API loaded but DocsAPI is unavailable at ${onlyofficeApiUrl}`
                )
            );
        };

        const handleError = () => {
            reject(
                new Error(
                    `Cannot load OnlyOffice. Verify the server is running at ${onlyofficeApiUrl}`
                )
            );
        };

        const existingScript = document.querySelector<HTMLScriptElement>(
            `script[src="${src}"], script[data-onlyoffice-api="true"]`
        );

        if (existingScript) {
            existingScript.addEventListener('load', handleLoad, { once: true });
            existingScript.addEventListener('error', handleError, { once: true });
            return;
        }

        const script = document.createElement('script');
        script.src = src;
        script.setAttribute('data-onlyoffice-api', 'true');
        script.async = true;
        script.addEventListener('load', handleLoad, { once: true });
        script.addEventListener('error', handleError, { once: true });
        document.head.appendChild(script);
    }).catch((error) => {
        onlyOfficeScriptLoaders.delete(src);
        throw error;
    });

    onlyOfficeScriptLoaders.set(src, loader);
    return loader;
}

export default function OnlyOfficeEditor({
    mode = 'proposal',
    proposalId,
    sectionId,
    libraryBlockId,
    title,
    onlyofficeApiUrl,
    onConfigLoaded,
    onDocumentStateChange,
}: OnlyOfficeEditorProps) {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const editorRef = useRef<any>(null);
    const containerRef = useRef<HTMLDivElement>(null);
    const initRunRef = useRef(0);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const editorContainerId = useMemo(() => {
        if (mode === 'create') return `onlyoffice-editor-create-${Math.random().toString(36).substring(7)}`;
        if (mode === 'library') return `onlyoffice-editor-lib-${libraryBlockId}`;
        return `onlyoffice-editor-${proposalId}-${sectionId}`;
    }, [mode, libraryBlockId, proposalId, sectionId]);

    // Initialize editor when script is loaded
    const initEditor = useCallback(async () => {
        const runId = ++initRunRef.current;

        try {
            setLoading(true);
            setError(null);

            await loadOnlyOfficeApiScript(onlyofficeApiUrl);
            if (runId !== initRunRef.current || !window.DocsAPI) {
                return;
            }

            // Fetch document config from backend
            const token = localStorage.getItem('token');
            let apiUrl = '';
            if (mode === 'create') {
                apiUrl = '/api/onlyoffice/document/create';
            } else if (mode === 'library') {
                apiUrl = `/api/onlyoffice/document/library/${libraryBlockId}`;
            } else {
                apiUrl = `/api/onlyoffice/document/proposal/${proposalId}/${sectionId}`;
            }

            const response = await fetch(apiUrl, {
                headers: token
                    ? { Authorization: `Bearer ${token}` }
                    : {},
            });

            if (!response.ok) {
                const err = await response
                    .json()
                    .catch(() => ({ detail: 'Unknown error' }));

                if (runId !== initRunRef.current) {
                    return;
                }

                let errorMsg = err.detail;
                if (Array.isArray(err.detail)) {
                    errorMsg = err.detail.map((e: any) => `${e.loc?.join('.') || ''}: ${e.msg}`).join(', ');
                } else if (typeof err.detail === 'object') {
                    errorMsg = JSON.stringify(err.detail);
                }

                throw new Error(errorMsg || `HTTP ${response.status}`);
            }

            const config: EditorConfig = await response.json();
            if (runId !== initRunRef.current) {
                return;
            }

            if (onConfigLoaded) {
                onConfigLoaded(config);
            }

            // Destroy previous editor instance
            if (editorRef.current) {
                try {
                    editorRef.current.destroyEditor();
                } catch {
                    // ignore
                }
                editorRef.current = null;
            }

            // Clear container
            const container = document.getElementById(editorContainerId);
            if (container) {
                container.innerHTML = '';
            } else {
                throw new Error('OnlyOffice editor container not found');
            }

            // Initialize OnlyOffice editor
            // Note: The token from the backend contains the full configuration.
            // When JWT is enabled, the parameters in the token overwrite the parameters in the config object.
            editorRef.current = new window.DocsAPI.DocEditor(
                editorContainerId,
                {
                    ...config.config,
                    token: config.token,
                    events: {
                        onAppReady: () => {
                            setLoading(false);
                        },
                        // eslint-disable-next-line @typescript-eslint/no-explicit-any
                        onDocumentStateChange: (event: any) => {
                            // event.data is true when document has unsaved changes
                            if (onDocumentStateChange) {
                                onDocumentStateChange(!!event?.data);
                            }
                        },
                        // eslint-disable-next-line @typescript-eslint/no-explicit-any
                        onError: (event: any) => {
                            console.error('OnlyOffice Error:', event);
                            // Detail error for debugging if it's an object
                            const detail = typeof event === 'object'
                                ? JSON.stringify(event)
                                : String(event);
                            setError(`OnlyOffice Error: ${detail}`);
                            setLoading(false);
                        },
                    },
                }
            );
        } catch (err) {
            if (runId !== initRunRef.current) {
                return;
            }

            setError(
                err instanceof Error
                    ? err.message
                    : 'Error loading document'
            );
            setLoading(false);
        }
    }, [
        mode,
        proposalId,
        sectionId,
        libraryBlockId,
        editorContainerId,
        onConfigLoaded,
        onDocumentStateChange,
        onlyofficeApiUrl,
    ]);

    useEffect(() => {
        void initEditor();

        return () => {
            initRunRef.current += 1;
            if (editorRef.current) {
                try {
                    editorRef.current.destroyEditor();
                } catch {
                    // ignore
                }
                editorRef.current = null;
            }
        };
    }, [initEditor]);

    return (
        <div
            ref={containerRef}
            style={{
                position: 'relative',
                width: '100%',
                height: '100%',
                borderRadius: 'var(--radius-md)',
                overflow: 'hidden',
                border: '1px solid var(--border-default)',
                background: 'var(--bg-secondary)',
            }}
        >
            {/* Loading overlay */}
            {loading && (
                <div
                    style={{
                        position: 'absolute',
                        inset: 0,
                        display: 'flex',
                        flexDirection: 'column',
                        alignItems: 'center',
                        justifyContent: 'center',
                        background: 'var(--bg-primary)',
                        zIndex: 10,
                        gap: '0.75rem',
                    }}
                >
                    <Loader2
                        size={28}
                        className="spin"
                        color="var(--accent-blue)"
                    />
                    <p
                        style={{
                            color: 'var(--text-muted)',
                            fontSize: '0.875rem',
                        }}
                    >
                        Loading editor for "{title}"...
                    </p>
                </div>
            )}

            {/* Error state */}
            {error && (
                <div
                    style={{
                        position: 'absolute',
                        inset: 0,
                        display: 'flex',
                        flexDirection: 'column',
                        alignItems: 'center',
                        justifyContent: 'center',
                        background: 'var(--bg-primary)',
                        zIndex: 10,
                        gap: '0.75rem',
                        padding: '2rem',
                    }}
                >
                    <AlertCircle size={32} color="#ef4444" />
                    <p
                        style={{
                            color: '#ef4444',
                            fontSize: '0.875rem',
                            textAlign: 'center',
                            maxWidth: '400px',
                        }}
                    >
                        {error}
                    </p>
                    <button
                        className="btn btn-secondary btn-sm"
                        onClick={() => initEditor()}
                        style={{ marginTop: '0.5rem' }}
                    >
                        Riprova
                    </button>
                </div>
            )}

            {/* OnlyOffice editor container (Uncontrolled by React to prevent unmount crashes) */}
            <div
                style={{ width: '100%', height: '100%' }}
                dangerouslySetInnerHTML={{
                    __html: `<div id="${editorContainerId}" style="width: 100%; height: 100%;"></div>`
                }}
            />
        </div>
    );
}
