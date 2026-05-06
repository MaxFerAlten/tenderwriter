import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import type { KpiForecast, RehearsalSummary } from '../../../api/client';
import ForecastTab from './ForecastTab';

function makeForecast(rehearsal_summary: RehearsalSummary | null | undefined): KpiForecast {
    return {
        status: 'ok',
        external_tender_id: '10',
        generated_at: '2026-04-17T18:40:00Z',
        summary: 'Forecast summary text.',
        overall_confidence: 0.73,
        scenarios: [],
        next_best_actions: [],
        analysis_metadata: {
            forecast_signal_type: null,
            forecast_engine_active: null,
            markov_projected_path: [],
            forecast_driver_kpis: [],
        } as unknown as KpiForecast['analysis_metadata'],
        rehearsal_summary,
    };
}

describe('ForecastTab rehearsal_summary', () => {
    it('renders populated rehearsal summary with health, score, divergence and counts', () => {
        const summary: RehearsalSummary = {
            run_id: 42,
            tender_id: 10,
            proposal_id: 7,
            last_rehearsal_at: '2026-04-17T18:40:00+00:00',
            overall_score: 71.4,
            persona_divergence: 0.28,
            blocking_findings: 3,
            high_severity_rework_suggestions: 2,
            health_projection: 'amber',
            version: 'tw-rehearsal-v1',
        };
        const html = renderToStaticMarkup(
            <ForecastTab
                forecast={makeForecast(summary)}
                diagnostics={null}
                analysisJob={null}
                tender={null}
            />,
        );
        expect(html).toContain('Rehearsal Summary');
        expect(html).toContain('Health: Amber');
        expect(html).toContain('Score: 71.4');
        expect(html).toContain('Divergence: 0.28');
        expect(html).toContain('Blocking: 3');
        expect(html).toContain('High-severity rework: 2');
        expect(html).toContain('Run #42');
    });

    it('renders empty state when run_id is null', () => {
        const summary: RehearsalSummary = {
            run_id: null,
            tender_id: 10,
            proposal_id: null,
            last_rehearsal_at: null,
            overall_score: null,
            persona_divergence: null,
            blocking_findings: 0,
            high_severity_rework_suggestions: 0,
            health_projection: null,
            version: 'tw-rehearsal-v1',
        };
        const html = renderToStaticMarkup(
            <ForecastTab
                forecast={makeForecast(summary)}
                diagnostics={null}
                analysisJob={null}
                tender={null}
            />,
        );
        expect(html).toContain('Rehearsal Summary');
        expect(html).toContain('No rehearsal has completed yet');
        expect(html).not.toContain('Health:');
        expect(html).not.toContain('Run #');
    });

    it('omits rehearsal summary card when forecast has no rehearsal_summary field', () => {
        const html = renderToStaticMarkup(
            <ForecastTab
                forecast={makeForecast(null)}
                diagnostics={null}
                analysisJob={null}
                tender={null}
            />,
        );
        expect(html).not.toContain('Rehearsal Summary');
    });

    it('hides zero-count chips but still shows score and divergence', () => {
        const summary: RehearsalSummary = {
            run_id: 5,
            tender_id: 10,
            proposal_id: 1,
            last_rehearsal_at: '2026-04-10T09:00:00Z',
            overall_score: 88.0,
            persona_divergence: 0.05,
            blocking_findings: 0,
            high_severity_rework_suggestions: 0,
            health_projection: 'green',
            version: 'tw-rehearsal-v1',
        };
        const html = renderToStaticMarkup(
            <ForecastTab
                forecast={makeForecast(summary)}
                diagnostics={null}
                analysisJob={null}
                tender={null}
            />,
        );
        expect(html).toContain('Health: Green');
        expect(html).toContain('Score: 88.0');
        expect(html).toContain('Divergence: 0.05');
        expect(html).not.toContain('Blocking:');
        expect(html).not.toContain('High-severity rework:');
    });
});
