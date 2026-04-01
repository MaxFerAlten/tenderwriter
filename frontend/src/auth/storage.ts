export type StoredSessionKind = 'legacy' | 'keycloak';

export const AUTH_TOKEN_STORAGE_KEY = 'token';
export const AUTH_SESSION_KIND_STORAGE_KEY = 'auth_session_kind';

export function getStoredAuthToken(): string | null {
    return localStorage.getItem(AUTH_TOKEN_STORAGE_KEY);
}

export function setStoredAuthToken(token: string): void {
    localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, token);
}

export function clearStoredAuthToken(): void {
    localStorage.removeItem(AUTH_TOKEN_STORAGE_KEY);
}

export function getStoredSessionKind(): StoredSessionKind | null {
    const value = localStorage.getItem(AUTH_SESSION_KIND_STORAGE_KEY);
    return value === 'legacy' || value === 'keycloak' ? value : null;
}

export function setStoredSessionKind(kind: StoredSessionKind): void {
    localStorage.setItem(AUTH_SESSION_KIND_STORAGE_KEY, kind);
}

export function clearStoredSessionKind(): void {
    localStorage.removeItem(AUTH_SESSION_KIND_STORAGE_KEY);
}

export function clearStoredAuthSession(): void {
    clearStoredAuthToken();
    clearStoredSessionKind();
}
