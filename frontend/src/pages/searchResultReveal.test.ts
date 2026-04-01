import { describe, expect, it } from 'vitest';

import {
    createSearchResultRevealState,
    finalizeSearchResults,
    noteInitialAnswerPainted,
    revealStagedSearchResults,
    stageSearchResults,
} from './searchResultReveal';

describe('searchResultReveal', () => {
    it('keeps retrieved sources pending until the first answer paint happens', () => {
        const initialState = createSearchResultRevealState<string>();

        const staged = stageSearchResults(initialState, ['Fonte 1', 'Fonte 2']);

        expect(staged.revealedResults).toBeNull();
        expect(staged.shouldScheduleReveal).toBe(false);
        expect(staged.nextState.pendingResults).toEqual(['Fonte 1', 'Fonte 2']);
        expect(staged.nextState.sourcesRevealed).toBe(false);

        const painted = noteInitialAnswerPainted(staged.nextState);

        expect(painted.shouldScheduleReveal).toBe(true);
        expect(painted.revealedResults).toBeNull();
        expect(painted.nextState.initialAnswerPainted).toBe(true);

        const revealed = revealStagedSearchResults(painted.nextState);

        expect(revealed.revealedResults).toEqual(['Fonte 1', 'Fonte 2']);
        expect(revealed.nextState.pendingResults).toBeNull();
        expect(revealed.nextState.sourcesRevealed).toBe(true);
    });

    it('reveals sources immediately when the stream ends without a painted answer', () => {
        const initialState = createSearchResultRevealState<string>();

        const finalized = finalizeSearchResults(initialState, ['Fallback source']);

        expect(finalized.revealedResults).toEqual(['Fallback source']);
        expect(finalized.shouldScheduleReveal).toBe(false);
        expect(finalized.nextState.sourcesRevealed).toBe(true);
        expect(finalized.nextState.pendingResults).toBeNull();
    });

    it('updates sources immediately once they have already been revealed', () => {
        const revealedState = {
            pendingResults: null,
            initialAnswerPainted: true,
            sourcesRevealed: true,
        };

        const staged = stageSearchResults(revealedState, ['Nuova fonte']);

        expect(staged.revealedResults).toEqual(['Nuova fonte']);
        expect(staged.shouldScheduleReveal).toBe(false);
        expect(staged.nextState.sourcesRevealed).toBe(true);
    });
});
