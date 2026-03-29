import { useState, useRef, useEffect } from 'react';
import { ChevronDown, Check } from 'lucide-react';
import type { KpiViewMode } from '../hooks/useKpiViewMode';
import { MODE_CONFIG } from '../hooks/useKpiViewMode';

interface ViewModeToggleProps {
    mode: KpiViewMode;
    onModeChange: (mode: KpiViewMode) => void;
}

const MODES: KpiViewMode[] = ['manageriale', 'amministrativa', 'operativa'];

export default function ViewModeToggle({ mode, onModeChange }: ViewModeToggleProps) {
    const [isOpen, setIsOpen] = useState(false);
    const dropdownRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        function handleClickOutside(event: MouseEvent) {
            if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
                setIsOpen(false);
            }
        }
        document.addEventListener('mousedown', handleClickOutside);
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, []);

    return (
        <div ref={dropdownRef} style={{ position: 'relative' }}>
            <button
                onClick={() => setIsOpen(!isOpen)}
                className="btn btn-secondary btn-sm"
                style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.5rem',
                }}
            >
                <span>{MODE_CONFIG[mode].icon}</span>
                <span>{MODE_CONFIG[mode].label}</span>
                <ChevronDown
                    size={14}
                    style={{
                        transition: 'transform 0.2s',
                        transform: isOpen ? 'rotate(180deg)' : 'rotate(0deg)',
                    }}
                />
            </button>

            {isOpen && (
                <div
                    style={{
                        position: 'absolute',
                        top: 'calc(100% + 4px)',
                        right: 0,
                        background: 'var(--bg-secondary)',
                        border: '1px solid var(--border-default)',
                        borderRadius: 'var(--radius-lg)',
                        boxShadow: 'var(--shadow-lg)',
                        zIndex: 50,
                        minWidth: '320px',
                        overflow: 'hidden',
                    }}
                >
                    <div
                        style={{
                            padding: '0.5rem 0.75rem',
                            fontSize: '0.7rem',
                            color: 'var(--text-muted)',
                            textTransform: 'uppercase',
                            letterSpacing: '0.05em',
                            borderBottom: '1px solid var(--border-default)',
                        }}
                    >
                        Modalità di visualizzazione
                    </div>
                    {MODES.map((m) => {
                        const config = MODE_CONFIG[m];
                        const isSelected = m === mode;
                        return (
                            <button
                                key={m}
                                onClick={() => {
                                    onModeChange(m);
                                    setIsOpen(false);
                                }}
                                style={{
                                    width: '100%',
                                    display: 'flex',
                                    alignItems: 'center',
                                    gap: '0.75rem',
                                    padding: '0.75rem 1rem',
                                    background: 'transparent',
                                    border: 'none',
                                    cursor: 'pointer',
                                    textAlign: 'left',
                                    transition: 'background 0.15s',
                                }}
                                onMouseEnter={(e) => {
                                    e.currentTarget.style.background = 'var(--bg-card)';
                                }}
                                onMouseLeave={(e) => {
                                    e.currentTarget.style.background = 'transparent';
                                }}
                            >
                                <span style={{ fontSize: '1.25rem', flexShrink: 0 }}>{config.icon}</span>
                                <div style={{ flex: 1, minWidth: 0 }}>
                                    <div style={{ fontWeight: 500, fontSize: '0.875rem', color: 'white' }}>
                                        {config.label}
                                    </div>
                                    <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.25rem', lineHeight: 1.4, whiteSpace: 'normal' }}>
                                        {config.description}
                                    </div>
                                </div>
                                {isSelected && (
                                    <Check size={16} style={{ color: 'var(--color-primary)' }} />
                                )}
                            </button>
                        );
                    })}
                </div>
            )}
        </div>
    );
}
