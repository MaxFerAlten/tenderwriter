function trimTrailingSlash(value: string): string {
    return value.replace(/\/+$/, '');
}

export const ONLYOFFICE_URL = trimTrailingSlash(
    import.meta.env.VITE_ONLYOFFICE_URL || `${window.location.protocol}//${window.location.hostname}:8443`
);

export function buildLocalServiceUrl(port: number, path = ''): string {
    const normalizedPath = path ? (path.startsWith('/') ? path : `/${path}`) : '';
    return `${window.location.protocol}//${window.location.hostname}:${port}${normalizedPath}`;
}
