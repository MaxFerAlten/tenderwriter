export interface HealthPalette {
    accent: string;
    soft: string;
    text: string;
}

export interface SignalPalette {
    accent: string;
    soft: string;
}

export function healthColor(health: string): string {
    switch (health) {
        case 'green':
            return '#10b981';
        case 'amber':
            return '#f59e0b';
        case 'red':
            return '#ef4444';
        default:
            return '#64748b';
    }
}

export function healthColors(health: string): HealthPalette {
    switch (health) {
        case 'green':
            return { accent: '#10b981', soft: 'rgba(16, 185, 129, 0.12)', text: '#d1fae5' };
        case 'amber':
            return { accent: '#f59e0b', soft: 'rgba(245, 158, 11, 0.14)', text: '#fef3c7' };
        case 'red':
            return { accent: '#ef4444', soft: 'rgba(239, 68, 68, 0.14)', text: '#fee2e2' };
        default:
            return { accent: '#64748b', soft: 'rgba(100, 116, 139, 0.14)', text: '#e2e8f0' };
    }
}

export function signalTone(signal: string | null | undefined): SignalPalette {
    switch (signal) {
        case 'observed':
            return { accent: '#10b981', soft: 'rgba(16, 185, 129, 0.12)' };
        case 'inferred':
            return { accent: '#f59e0b', soft: 'rgba(245, 158, 11, 0.14)' };
        case 'reconstructed':
        case 'predicted':
        case 'calibrated':
            return { accent: '#38bdf8', soft: 'rgba(56, 189, 248, 0.14)' };
        case 'shadow':
            return { accent: '#14b8a6', soft: 'rgba(20, 184, 166, 0.14)' };
        case 'locked':
            return { accent: '#64748b', soft: 'rgba(100, 116, 139, 0.14)' };
        default:
            return { accent: '#64748b', soft: 'rgba(100, 116, 139, 0.14)' };
    }
}

export function semanticStatusTone(status: string | null | undefined): SignalPalette {
    switch (status) {
        case 'official':
            return { accent: '#22c55e', soft: 'rgba(34, 197, 94, 0.14)' };
        case 'fallback':
            return { accent: '#f59e0b', soft: 'rgba(245, 158, 11, 0.14)' };
        case 'shadow':
            return { accent: '#14b8a6', soft: 'rgba(20, 184, 166, 0.14)' };
        default:
            return { accent: '#64748b', soft: 'rgba(100, 116, 139, 0.14)' };
    }
}

export function analysisJobColors(jobStatus: string | null | undefined): SignalPalette {
    switch (jobStatus) {
        case 'queued':
            return { accent: '#38bdf8', soft: 'rgba(56, 189, 248, 0.14)' };
        case 'running':
            return { accent: '#f59e0b', soft: 'rgba(245, 158, 11, 0.14)' };
        case 'succeeded':
            return { accent: '#10b981', soft: 'rgba(16, 185, 129, 0.14)' };
        case 'failed':
        case 'degraded':
            return { accent: '#ef4444', soft: 'rgba(239, 68, 68, 0.14)' };
        default:
            return { accent: '#64748b', soft: 'rgba(100, 116, 139, 0.14)' };
    }
}

export function actionPriorityTone(priority: string | null | undefined): SignalPalette {
    switch (priority) {
        case 'now':
            return { accent: '#ef4444', soft: 'rgba(239, 68, 68, 0.14)' };
        case 'next':
            return { accent: '#f59e0b', soft: 'rgba(245, 158, 11, 0.14)' };
        default:
            return { accent: '#38bdf8', soft: 'rgba(56, 189, 248, 0.14)' };
    }
}

export function chipStyle(accent: string, soft: string) {
    return {
        padding: '0.24rem 0.62rem',
        borderRadius: '999px',
        fontSize: '0.72rem',
        background: soft,
        color: accent,
        border: `1px solid ${accent}33`,
        textTransform: 'capitalize' as const,
    };
}
