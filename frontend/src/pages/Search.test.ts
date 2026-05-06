import { describe, expect, it } from 'vitest';

import {
    normalizeSearchErrorMessage,
    shouldShowEmptySearchState,
    shouldShowSearchResults,
} from './Search';

describe('Search page helpers', () => {
    it('keeps rendering the results area when sources already exist', () => {
        expect(shouldShowSearchResults({
            hasSearched: true,
            isSearching: false,
            visibleAnswer: '',
            resultsLength: 3,
        })).toBe(true);
    });

    it('keeps rendering retrieved sources even after a stream error', () => {
        expect(shouldShowSearchResults({
            hasSearched: true,
            isSearching: false,
            visibleAnswer: '',
            resultsLength: 3,
        })).toBe(true);
        expect(shouldShowEmptySearchState({
            isSearching: false,
            visibleAnswer: '',
            resultsLength: 3,
            error: 'NoValidHarFileError: No .har file found',
        })).toBe(false);
    });

    it('normalizes backend reachability errors into the friendly message', () => {
        const reachabilityMessage = 'Could not reach the backend. Make sure the API server is running on port 8000.';
        expect(normalizeSearchErrorMessage('Failed to fetch')).toBe(reachabilityMessage);
        expect(normalizeSearchErrorMessage('TypeError: Failed to fetch')).toBe(reachabilityMessage);
        expect(normalizeSearchErrorMessage('NetworkError when attempting to fetch resource')).toBe(reachabilityMessage);
        expect(normalizeSearchErrorMessage('ERR_CONNECTION_REFUSED')).toBe(reachabilityMessage);
    });

    it('preserves application-level errors that contain transport keywords', () => {
        expect(normalizeSearchErrorMessage('Generation failed')).toBe('Generation failed');
        expect(normalizeSearchErrorMessage('RAG engine not initialized')).toBe('RAG engine not initialized');
        expect(normalizeSearchErrorMessage('NoValidHarFileError: No .har file found')).toBe(
            'NoValidHarFileError: No .har file found'
        );
        expect(normalizeSearchErrorMessage('Unable to fetch tender summary')).toBe('Unable to fetch tender summary');
    });
});
