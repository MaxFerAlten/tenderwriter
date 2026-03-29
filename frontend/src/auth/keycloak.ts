/**
 * TenderWriter — Keycloak OIDC Service
 *
 * Wraps keycloak-js for OIDC authentication.
 * Initialized when AUTH_MODE enables SSO (keycloak or hybrid).
 */

import Keycloak from 'keycloak-js';

// Keycloak singleton — lazy initialized
let _kc: Keycloak | null = null;

export interface KeycloakConfig {
    url: string;       // e.g. http://localhost:8180
    realm: string;     // e.g. tenderwriter
    clientId: string;  // e.g. tw-frontend
}

const DEFAULT_CONFIG: KeycloakConfig = {
    url: import.meta.env.VITE_KC_URL || 'http://localhost:8180',
    realm: import.meta.env.VITE_KC_REALM || 'tenderwriter',
    clientId: import.meta.env.VITE_KC_CLIENT_ID || 'tw-frontend',
};

const KEYCLOAK_MESSAGE_TIMEOUT_MS = 2_000;

function isThirdPartyCheckTimeout(err: unknown): boolean {
    if (!(err instanceof Error)) {
        return false;
    }

    return err.message.includes('3rd party check iframe message');
}

/**
 * Get or create the Keycloak instance (singleton).
 */
export function getKeycloak(config?: Partial<KeycloakConfig>): Keycloak {
    if (!_kc) {
        const cfg = { ...DEFAULT_CONFIG, ...config };
        _kc = new Keycloak({
            url: cfg.url,
            realm: cfg.realm,
            clientId: cfg.clientId,
        });
    }
    return _kc;
}

/**
 * Initialize Keycloak and attempt SSO silent check.
 * Returns true if user is authenticated, false otherwise.
 */
export async function initKeycloak(config?: Partial<KeycloakConfig>): Promise<boolean> {
    const kc = getKeycloak(config);

    try {
        const authenticated = await kc.init({
            onLoad: 'check-sso',
            pkceMethod: 'S256',
            checkLoginIframe: false,
            silentCheckSsoFallback: false,
            silentCheckSsoRedirectUri: window.location.origin + '/silent-check-sso.html',
            messageReceiveTimeout: KEYCLOAK_MESSAGE_TIMEOUT_MS,
        });

        if (authenticated) {
            // Schedule token refresh before expiry
            _scheduleTokenRefresh(kc);
        }

        return authenticated;
    } catch (err) {
        if (isThirdPartyCheckTimeout(err)) {
            console.warn('[keycloak] silent SSO unavailable in this browser context, continuing without Keycloak session');
            return false;
        }

        console.error('[keycloak] init failed:', err);
        return false;
    }
}

/**
 * Redirect user to Keycloak login page.
 */
export function keycloakLogin(config?: Partial<KeycloakConfig>): void {
    const kc = getKeycloak(config);
    kc.login({ redirectUri: window.location.origin + '/' });
}

/**
 * Logout from Keycloak (federated logout).
 */
export function keycloakLogout(config?: Partial<KeycloakConfig>): void {
    const kc = getKeycloak(config);
    kc.logout({ redirectUri: window.location.origin + '/login' });
}

/**
 * Get the current bearer token (refreshes if needed).
 *
 * We prefer the ID token because TenderWriter's backend authenticates
 * the end-user directly from identity claims.
 * Returns null if not authenticated.
 */
export async function getKeycloakToken(): Promise<string | null> {
    const kc = getKeycloak();
    if (!kc.authenticated) return null;

    try {
        // Refresh if token expires within 30 seconds
        await kc.updateToken(30);
        return kc.idToken || kc.token || null;
    } catch {
        console.warn('[keycloak] token refresh failed, redirecting to login');
        kc.login();
        return null;
    }
}

/**
 * Extract user info from the Keycloak token.
 */
export function getKeycloakUserInfo(): { email: string; name: string } | null {
    const kc = getKeycloak();
    const parsed = (kc.idTokenParsed || kc.tokenParsed) as Record<string, unknown> | undefined;
    if (!kc.authenticated || !parsed) return null;

    return {
        email: (parsed.email as string) || '',
        name: [parsed.given_name, parsed.family_name].filter(Boolean).join(' ')
            || (parsed.preferred_username as string)
            || '',
    };
}

// ── Internal helpers ──

let _refreshTimer: ReturnType<typeof setTimeout> | null = null;

function _scheduleTokenRefresh(kc: Keycloak): void {
    if (_refreshTimer) clearTimeout(_refreshTimer);

    // Refresh 60s before expiry
    const expiresIn = (kc.tokenParsed?.exp ?? 0) - Math.floor(Date.now() / 1000);
    const refreshIn = Math.max((expiresIn - 60) * 1000, 10_000);

    _refreshTimer = setTimeout(async () => {
        try {
            await kc.updateToken(70);
            _scheduleTokenRefresh(kc);
        } catch {
            console.warn('[keycloak] scheduled refresh failed');
        }
    }, refreshIn);
}
