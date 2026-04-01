export interface DevProxyEnv {
    VITE_API_TARGET?: string;
    VITE_MM_TARGET?: string;
}

export interface DevProxyOptions {
    target: string;
    changeOrigin: boolean;
    ws: boolean;
    xfwd?: boolean;
}

export function buildDevProxy(env: DevProxyEnv): Record<string, DevProxyOptions> {
    const apiTarget = env.VITE_API_TARGET || 'http://localhost:8000';
    const mattermostTarget = env.VITE_MM_TARGET || 'http://localhost:8065';

    return {
        '/api': {
            target: apiTarget,
            changeOrigin: true,
            ws: true,
        },
        '/mm': {
            target: mattermostTarget,
            changeOrigin: true,
            ws: true,
            xfwd: true,
        },
    };
}
