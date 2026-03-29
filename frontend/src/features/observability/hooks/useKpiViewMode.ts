import { useState, useEffect, useCallback } from 'react';

export type KpiViewMode = 'manageriale' | 'amministrativa' | 'operativa';

const STORAGE_KEY = 'kpi_view_mode';
const MODES: KpiViewMode[] = ['manageriale', 'amministrativa', 'operativa'];

const MODE_CONFIG = {
    manageriale: {
        label: 'Manageriale',
        description: 'Vista compatta con executive summary e navigazione a tab',
        icon: '📊',
    },
    amministrativa: {
        label: 'Amministrativa',
        description: 'Dettaglio completo con tutti i pannelli espansi',
        icon: '🔧',
    },
    operativa: {
        label: 'Operativa',
        description: 'Focus su workflow, job queue e operazioni real-time',
        icon: '⚙️',
    },
};

export { MODE_CONFIG };

function getStoredMode(): KpiViewMode | null {
    if (typeof window === 'undefined') return null;
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored && MODES.includes(stored as KpiViewMode)) {
        return stored as KpiViewMode;
    }
    return null;
}

function setStoredMode(mode: KpiViewMode): void {
    if (typeof window !== 'undefined') {
        localStorage.setItem(STORAGE_KEY, mode);
    }
}

function getDefaultMode(): KpiViewMode {
    return 'manageriale';
}

export interface UseKpiViewModeReturn {
    mode: KpiViewMode;
    setMode: (mode: KpiViewMode) => void;
    modeConfig: typeof MODE_CONFIG;
    isFirstAccess: boolean;
    dismissFirstAccess: () => void;
}

export function useKpiViewMode(): UseKpiViewModeReturn {
    const [mode, setModeState] = useState<KpiViewMode>(getDefaultMode);
    const [isFirstAccess, setIsFirstAccess] = useState(false);
    const [isInitialized, setIsInitialized] = useState(false);

    useEffect(() => {
        const stored = getStoredMode();
        if (stored) {
            setModeState(stored);
        } else {
            setIsFirstAccess(true);
        }
        setIsInitialized(true);
    }, []);

    const setMode = useCallback((newMode: KpiViewMode) => {
        setModeState(newMode);
        setStoredMode(newMode);
    }, []);

    const dismissFirstAccess = useCallback(() => {
        setIsFirstAccess(false);
        if (!getStoredMode()) {
            setStoredMode(getDefaultMode());
        }
    }, []);

    return {
        mode: isInitialized ? mode : getDefaultMode(),
        setMode,
        modeConfig: MODE_CONFIG,
        isFirstAccess: isInitialized && isFirstAccess,
        dismissFirstAccess,
    };
}
