import { describe, expect, it } from 'vitest';

import {
    derivePresetSimulationMetrics,
    runSearchPresetSimulation,
} from './searchSettingsSimulation';
import { getSearchPresetConfig } from './searchSettings';

describe('searchSettings preset simulation', () => {
    it('keeps Balanced as the best fit for the balanced scenario', () => {
        const simulation = runSearchPresetSimulation();

        expect(simulation.balanced[0].preset).toBe('balanced');
        expect(simulation.balanced[0].score).toBeGreaterThan(simulation.balanced[1].score);
        expect(simulation.balanced[0].score - simulation.balanced[1].score).toBeGreaterThan(0.015);
    });

    it('keeps Precise as the best fit for the precise scenario', () => {
        const simulation = runSearchPresetSimulation();

        expect(simulation.precise[0].preset).toBe('precise');
        expect(simulation.precise[0].score).toBeGreaterThan(simulation.precise[1].score);
        expect(simulation.precise[0].score - simulation.precise[1].score).toBeGreaterThan(0.03);
    });

    it('keeps Exploratory as the best fit for the exploratory scenario', () => {
        const simulation = runSearchPresetSimulation();

        expect(simulation.exploratory[0].preset).toBe('exploratory');
        expect(simulation.exploratory[0].score).toBeGreaterThan(simulation.exploratory[1].score);
        expect(simulation.exploratory[0].score - simulation.exploratory[1].score).toBeGreaterThan(0.025);
    });

    it('derives metrics consistent with the intent of each preset', () => {
        const balanced = derivePresetSimulationMetrics(getSearchPresetConfig('balanced'));
        const precise = derivePresetSimulationMetrics(getSearchPresetConfig('precise'));
        const exploratory = derivePresetSimulationMetrics(getSearchPresetConfig('exploratory'));

        expect(precise.exactness).toBeGreaterThan(balanced.exactness);
        expect(precise.answerDiscipline).toBeGreaterThan(balanced.answerDiscipline);
        expect(exploratory.breadth).toBeGreaterThan(balanced.breadth);
        expect(exploratory.graphAffinity).toBeGreaterThan(balanced.graphAffinity);
        expect(balanced.exactness).toBeGreaterThan(exploratory.exactness);
    });
});
