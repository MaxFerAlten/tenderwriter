export function collapseDuplicateSearchHistory<T extends { query: string; response: string; created_at: string }>(
    items: T[],
    dedupeWindowMs = 3000,
): T[] {
    const collapsed: T[] = [];

    for (const item of items) {
        const previous = collapsed[collapsed.length - 1];
        if (!previous) {
            collapsed.push(item);
            continue;
        }

        const sameQuery = previous.query === item.query;
        const sameResponse = previous.response === item.response;
        const previousTs = new Date(previous.created_at).getTime();
        const currentTs = new Date(item.created_at).getTime();
        const withinWindow = Number.isFinite(previousTs)
            && Number.isFinite(currentTs)
            && Math.abs(previousTs - currentTs) <= dedupeWindowMs;

        if (sameQuery && sameResponse && withinWindow) {
            continue;
        }

        collapsed.push(item);
    }

    return collapsed;
}
