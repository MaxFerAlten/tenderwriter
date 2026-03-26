export const MANAGERIALE_SECTIONS = [
    'overview',
    'kpi',
    'forecast',
    'compliance',
    'lifecycle',
    'operations',
] as const;

export type ManagerialeSection = (typeof MANAGERIALE_SECTIONS)[number];

export function isManagerialeSection(value: string | null | undefined): value is ManagerialeSection {
    return Boolean(value && MANAGERIALE_SECTIONS.includes(value as ManagerialeSection));
}

export function buildObservabilityPath(
    tenderId?: number | null,
    section?: ManagerialeSection | null
): string {
    if (tenderId === null || tenderId === undefined) {
        return '/observability-kpi';
    }

    if (section) {
        return `/observability-kpi/${tenderId}/${section}`;
    }

    return `/observability-kpi/${tenderId}`;
}
