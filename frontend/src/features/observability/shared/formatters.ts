export function formatDateTime(value: string | null | undefined, fallback = 'n/a'): string {
    if (!value) {
        return fallback;
    }
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) {
        return value;
    }
    return parsed.toLocaleString('it-IT');
}

export function formatScoreValue(score: { value: number | null | undefined } | number | null | undefined): string {
    const rawValue = typeof score === 'number' || score === null || score === undefined
        ? score
        : score.value;

    if (rawValue === null || rawValue === undefined) {
        return '--';
    }
    return `${rawValue.toFixed(1)}`;
}

export function formatGeneratedAt(value: string | null): string {
    return formatDateTime(value, 'Not generated yet');
}

export function formatProbability(value: number | null | undefined): string {
    if (value === null || value === undefined) {
        return '--';
    }
    return `${Math.round(value * 100)}%`;
}

export function formatConfidenceValue(value: number | null | undefined): string {
    if (value === null || value === undefined) {
        return '--';
    }
    return value.toFixed(2);
}
