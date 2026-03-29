import { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react';
import { authApi, User } from '../api/client';
import {
    initKeycloak,
    keycloakLogin,
    keycloakLogout,
    getKeycloakToken,
    getKeycloakUserInfo,
    type KeycloakConfig,
} from '../auth/keycloak';
import { getAuthRuntimeConfig, type AuthMode, type AuthRuntimeConfig } from '../config/runtime';

type SessionKind = 'legacy' | 'keycloak' | null;

function resolveSessionKind(userData: User): SessionKind {
    return userData.auth_source === 'keycloak' ? 'keycloak' : 'legacy';
}

interface AuthContextType {
    user: User | null;
    isLoading: boolean;
    authMode: AuthMode;
    login: (token: string, userData: User) => void;
    loginWithKeycloak: () => void;
    logout: () => void | Promise<void>;
    /** Get a valid bearer token (works for both modes) */
    getToken: () => Promise<string | null>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
    const [user, setUser] = useState<User | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [authMode, setAuthMode] = useState<AuthMode>('legacy');
    const [keycloakConfig, setKeycloakConfig] = useState<KeycloakConfig | null>(null);
    const [sessionKind, setSessionKind] = useState<SessionKind>(null);

    // ── Stored session: validate the token already present in localStorage ──
    const initStoredSession = useCallback(async (): Promise<SessionKind> => {
        const token = localStorage.getItem('token');
        if (!token) {
            setUser(null);
            setSessionKind(null);
            return null;
        }

        try {
            const userData = await authApi.me();
            setUser(userData);
            const resolvedKind = resolveSessionKind(userData);
            setSessionKind(resolvedKind);
            return resolvedKind;
        } catch {
            localStorage.removeItem('token');
            setUser(null);
            setSessionKind(null);
            return null;
        }
    }, []);

    // ── Keycloak mode: init OIDC and fetch user profile ──
    const initKeycloakAuth = useCallback(async (
        config: AuthRuntimeConfig,
        options?: { clearLegacyToken?: boolean },
    ): Promise<boolean> => {
        const resolvedConfig: KeycloakConfig = {
            url: config.keycloak_url || 'http://localhost:8180',
            realm: config.keycloak_realm || 'tenderwriter',
            clientId: config.keycloak_client_id || 'tw-frontend',
        };
        setKeycloakConfig(resolvedConfig);

        if (options?.clearLegacyToken) {
            localStorage.removeItem('token');
            setUser(null);
            setSessionKind(null);
        }

        try {
            const authenticated = await initKeycloak(resolvedConfig);
            if (!authenticated) {
                return false;
            }

            const token = await getKeycloakToken();
            if (!token) {
                localStorage.removeItem('token');
                setSessionKind(null);
                return false;
            }

            localStorage.setItem('token', token);
            try {
                const userData = await authApi.me();
                setUser(userData);
            } catch {
                const kcInfo = getKeycloakUserInfo();
                if (kcInfo) {
                    setUser({
                        id: 0,
                        email: kcInfo.email,
                        name: kcInfo.name,
                        role: 'editor',
                        auth_source: 'keycloak',
                    });
                } else {
                    setUser(null);
                    setSessionKind(null);
                    return false;
                }
            }

            setSessionKind('keycloak');
            return true;
        } catch (err) {
            console.error('[auth] keycloak init failed:', err);
            return false;
        }
    }, []);

    useEffect(() => {
        let cancelled = false;

        const bootstrapAuth = async () => {
            const runtimeConfig = await getAuthRuntimeConfig();
            if (cancelled) {
                return;
            }

            setAuthMode(runtimeConfig.auth_mode);

            if (runtimeConfig.auth_mode === 'keycloak') {
                await initKeycloakAuth(runtimeConfig, { clearLegacyToken: true });
                if (!cancelled) {
                    setIsLoading(false);
                }
                return;
            }

            if (runtimeConfig.auth_mode === 'hybrid') {
                const restoredSession = await initStoredSession();
                if (restoredSession === 'keycloak') {
                    void initKeycloakAuth(runtimeConfig, { clearLegacyToken: false });
                } else if (!restoredSession) {
                    await initKeycloakAuth(runtimeConfig, { clearLegacyToken: false });
                }
                if (!cancelled) {
                    setIsLoading(false);
                }
                return;
            }

            setKeycloakConfig(null);
            await initStoredSession();
            if (!cancelled) {
                setIsLoading(false);
            }
        };

        void bootstrapAuth();

        return () => {
            cancelled = true;
        };
    }, [initStoredSession, initKeycloakAuth]);

    // ── Legacy login (email/password) ──
    const login = useCallback((token: string, userData: User) => {
        localStorage.setItem('token', token);
        setUser(userData);
        setSessionKind('legacy');
    }, []);

    // ── Keycloak login (redirect to IdP) ──
    const loginWithKeycloak = useCallback(() => {
        keycloakLogin(keycloakConfig || undefined);
    }, [keycloakConfig]);

    // ── Logout (works for both modes) ──
    const logout = useCallback(async () => {
        const wasKeycloakSession = authMode === 'keycloak' || sessionKind === 'keycloak';

        // Call server-side logout for audit logging
        try {
            const token = localStorage.getItem('token');
            if (token) {
                await fetch('/api/auth/logout', {
                    method: 'POST',
                    headers: { 'Authorization': `Bearer ${token}` },
                });
            }
        } catch {
            // Best-effort — don't block logout on server failure
        }

        localStorage.removeItem('token');
        setUser(null);
        setSessionKind(null);

        if (wasKeycloakSession) {
            keycloakLogout(keycloakConfig || undefined); // Redirects to Keycloak end-session → federated logout
        }
    }, [authMode, keycloakConfig, sessionKind]);

    // ── Get token (works for both modes) ──
    const getToken = useCallback(async (): Promise<string | null> => {
        if (authMode === 'keycloak' || sessionKind === 'keycloak') {
            const token = await getKeycloakToken();
            if (token) {
                // Keep localStorage in sync for API client
                localStorage.setItem('token', token);
            } else {
                localStorage.removeItem('token');
                setSessionKind(null);
            }
            return token;
        }
        return localStorage.getItem('token');
    }, [authMode, sessionKind]);

    return (
        <AuthContext.Provider value={{
            user,
            isLoading,
            authMode,
            login,
            loginWithKeycloak,
            logout,
            getToken,
        }}>
            {children}
        </AuthContext.Provider>
    );
}

export function useAuth() {
    const context = useContext(AuthContext);
    if (context === undefined) {
        throw new Error('useAuth must be used within an AuthProvider');
    }
    return context;
}
