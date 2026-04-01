export interface SearchResultRevealState<Result> {
    pendingResults: Result[] | null;
    initialAnswerPainted: boolean;
    sourcesRevealed: boolean;
}

export interface SearchResultRevealTransition<Result> {
    nextState: SearchResultRevealState<Result>;
    revealedResults: Result[] | null;
    shouldScheduleReveal: boolean;
}

export function createSearchResultRevealState<Result>(): SearchResultRevealState<Result> {
    return {
        pendingResults: null,
        initialAnswerPainted: false,
        sourcesRevealed: false,
    };
}

export function noteInitialAnswerPainted<Result>(
    state: SearchResultRevealState<Result>
): SearchResultRevealTransition<Result> {
    if (state.initialAnswerPainted) {
        return {
            nextState: state,
            revealedResults: null,
            shouldScheduleReveal: false,
        };
    }

    return {
        nextState: {
            ...state,
            initialAnswerPainted: true,
        },
        revealedResults: null,
        shouldScheduleReveal: Boolean(state.pendingResults),
    };
}

export function stageSearchResults<Result>(
    state: SearchResultRevealState<Result>,
    nextResults: Result[]
): SearchResultRevealTransition<Result> {
    if (state.sourcesRevealed) {
        return {
            nextState: {
                ...state,
                pendingResults: null,
                sourcesRevealed: true,
            },
            revealedResults: nextResults,
            shouldScheduleReveal: false,
        };
    }

    return {
        nextState: {
            ...state,
            pendingResults: nextResults,
        },
        revealedResults: null,
        shouldScheduleReveal: state.initialAnswerPainted,
    };
}

export function revealStagedSearchResults<Result>(
    state: SearchResultRevealState<Result>
): SearchResultRevealTransition<Result> {
    if (!state.pendingResults) {
        return {
            nextState: state,
            revealedResults: null,
            shouldScheduleReveal: false,
        };
    }

    return {
        nextState: {
            ...state,
            pendingResults: null,
            sourcesRevealed: true,
        },
        revealedResults: state.pendingResults,
        shouldScheduleReveal: false,
    };
}

export function finalizeSearchResults<Result>(
    state: SearchResultRevealState<Result>,
    nextResults: Result[]
): SearchResultRevealTransition<Result> {
    if (!state.initialAnswerPainted) {
        return {
            nextState: {
                ...state,
                pendingResults: null,
                sourcesRevealed: true,
            },
            revealedResults: nextResults,
            shouldScheduleReveal: false,
        };
    }

    return {
        nextState: {
            ...state,
            pendingResults: nextResults,
        },
        revealedResults: null,
        shouldScheduleReveal: true,
    };
}
