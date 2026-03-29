import { useEffect, useRef } from 'react';

import { kpiAdminApi, type KpiAnalysisJob } from '../../../api/client';
import { isAnalysisJobActive } from '../shared';

interface UseAnalysisJobPollingOptions {
    selectedTenderId: number | null;
    analysisJob: KpiAnalysisJob | null;
    onAnalysisJobChange: (job: KpiAnalysisJob) => void;
    onRecomputingChange: (value: boolean) => void;
    onJobSucceeded?: () => Promise<void> | void;
    onError?: (message: string) => void;
}

export function useAnalysisJobPolling({
    selectedTenderId,
    analysisJob,
    onAnalysisJobChange,
    onRecomputingChange,
    onJobSucceeded,
    onError,
}: UseAnalysisJobPollingOptions) {
    const pollInFlightRef = useRef(false);

    useEffect(() => {
        if (selectedTenderId === null || !isAnalysisJobActive(analysisJob)) {
            return;
        }

        let cancelled = false;
        const intervalId = window.setInterval(() => {
            void (async () => {
                if (pollInFlightRef.current) {
                    return;
                }

                pollInFlightRef.current = true;
                try {
                    const latestJob = await kpiAdminApi.getLatestAnalysisJob(selectedTenderId);
                    if (cancelled) {
                        return;
                    }

                    onAnalysisJobChange(latestJob);
                    if (!isAnalysisJobActive(latestJob)) {
                        onRecomputingChange(false);
                        window.clearInterval(intervalId);

                        if (latestJob.job_status === 'succeeded') {
                            await onJobSucceeded?.();
                        } else if (latestJob.error_message) {
                            onError?.(latestJob.error_message);
                        }
                    }
                } catch (jobError) {
                    if (!cancelled) {
                        onRecomputingChange(false);
                        onError?.(jobError instanceof Error ? jobError.message : 'Failed to refresh KPI recompute status.');
                        window.clearInterval(intervalId);
                    }
                } finally {
                    if (!cancelled) {
                        pollInFlightRef.current = false;
                    }
                }
            })();
        }, 1200);

        return () => {
            cancelled = true;
            pollInFlightRef.current = false;
            window.clearInterval(intervalId);
        };
    }, [analysisJob?.job_status, selectedTenderId]);
}
