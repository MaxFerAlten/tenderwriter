function trimTrailingSlash(value: string): string {
    return value.replace(/\/+$/, '');
}

export type AuthMode = 'legacy' | 'keycloak' | 'hybrid';

export interface AuthRuntimeConfig {
    auth_mode: AuthMode;
    keycloak_url?: string;
    keycloak_realm?: string;
    keycloak_client_id?: string;
}

export const ONLYOFFICE_URL = trimTrailingSlash(
    import.meta.env.VITE_ONLYOFFICE_URL || buildLocalServiceUrl(8443)
);

export const MATTERMOST_URL = trimTrailingSlash(
    import.meta.env.VITE_MATTERMOST_URL || buildLocalServiceUrl(8065)
);

export function buildLocalServiceUrl(port: number, path = ''): string {
    const normalizedPath = path ? (path.startsWith('/') ? path : `/${path}`) : '';
    return `${window.location.protocol}//${window.location.hostname}:${port}${normalizedPath}`;
}

function normalizeAuthMode(value: string | undefined): AuthMode {
    switch ((value || '').toLowerCase()) {
        case 'keycloak':
            return 'keycloak';
        case 'hybrid':
            return 'hybrid';
        default:
            return 'legacy';
    }
}

const DEFAULT_AUTH_CONFIG: AuthRuntimeConfig = {
    auth_mode: normalizeAuthMode(import.meta.env.VITE_AUTH_MODE),
    keycloak_url: trimTrailingSlash(import.meta.env.VITE_KC_URL || buildLocalServiceUrl(8180)),
    keycloak_realm: import.meta.env.VITE_KC_REALM || 'tenderwriter',
    keycloak_client_id: import.meta.env.VITE_KC_CLIENT_ID || 'tw-frontend',
};

let authConfigPromise: Promise<AuthRuntimeConfig> | null = null;

export function getDefaultAuthRuntimeConfig(): AuthRuntimeConfig {
    return DEFAULT_AUTH_CONFIG;
}

export async function getAuthRuntimeConfig(): Promise<AuthRuntimeConfig> {
    if (!authConfigPromise) {
        authConfigPromise = (async () => {
            try {
                const response = await fetch('/api/auth/config', { cache: 'no-store' });
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}`);
                }

                const rawConfig = await response.json() as Partial<AuthRuntimeConfig>;
                return {
                    ...DEFAULT_AUTH_CONFIG,
                    ...rawConfig,
                    auth_mode: normalizeAuthMode(rawConfig.auth_mode),
                    keycloak_url: trimTrailingSlash(
                        rawConfig.keycloak_url || DEFAULT_AUTH_CONFIG.keycloak_url || buildLocalServiceUrl(8180)
                    ),
                };
            } catch (err) {
                console.warn('[runtime] failed to load auth config, using defaults:', err);
                return DEFAULT_AUTH_CONFIG;
            }
        })();
    }

    return authConfigPromise;
}
