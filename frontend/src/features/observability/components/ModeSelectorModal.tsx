import { motion } from 'framer-motion';
import { X } from 'lucide-react';
import type { KpiViewMode } from '../hooks/useKpiViewMode';
import { MODE_CONFIG } from '../hooks/useKpiViewMode';

interface ModeSelectorModalProps {
    onSelect: (mode: KpiViewMode) => void;
    onDismiss: () => void;
}

const MODES: KpiViewMode[] = ['manageriale', 'amministrativa', 'operativa'];

export default function ModeSelectorModal({ onSelect, onDismiss }: ModeSelectorModalProps) {
    return (
        <div className="modal-overlay">
            <motion.div
                className="modal"
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.95 }}
                style={{ maxWidth: '600px' }}
            >
                <div className="modal-header">
                    <div>
                        <h2 style={{ margin: 0, fontSize: '1.25rem', fontWeight: 600 }}>
                            Scegli la modalità di visualizzazione
                        </h2>
                        <p style={{ margin: '0.5rem 0 0 0', fontSize: '0.875rem', color: 'var(--text-muted)' }}>
                            Puoi cambiare modalità in qualsiasi momento dall&apos;header della pagina
                        </p>
                    </div>
                    <button
                        onClick={onDismiss}
                        className="btn btn-ghost btn-sm"
                        aria-label="Chiudi"
                    >
                        <X size={18} />
                    </button>
                </div>

                <div style={{ display: 'grid', gap: '1.25rem', gridTemplateColumns: 'repeat(3, 1fr)' }}>
                    {MODES.map((mode) => {
                        const config = MODE_CONFIG[mode];
                        return (
                            <button
                                key={mode}
                                onClick={() => onSelect(mode)}
                                style={{
                                    display: 'flex',
                                    flexDirection: 'column',
                                    alignItems: 'center',
                                    padding: '1.5rem 1rem',
                                    background: 'var(--bg-card)',
                                    border: '1px solid var(--border-default)',
                                    borderRadius: 'var(--radius-lg)',
                                    cursor: 'pointer',
                                    transition: 'all 0.2s',
                                    textAlign: 'center',
                                }}
                                onMouseEnter={(e) => {
                                    e.currentTarget.style.borderColor = 'var(--color-primary)';
                                    e.currentTarget.style.background = 'var(--bg-card-hover)';
                                }}
                                onMouseLeave={(e) => {
                                    e.currentTarget.style.borderColor = 'var(--border-default)';
                                    e.currentTarget.style.background = 'var(--bg-card)';
                                }}
                            >
                                <span style={{ fontSize: '2.5rem', marginBottom: '0.75rem' }}>
                                    {config.icon}
                                </span>
                                <span style={{ fontWeight: 600, fontSize: '1rem', marginBottom: '0.4rem', color: 'white' }}>
                                    {config.label}
                                </span>
                                <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)', lineHeight: 1.45 }}>
                                    {config.description}
                                </span>
                            </button>
                        );
                    })}
                </div>

                <div style={{ marginTop: '1.5rem', textAlign: 'center' }}>
                    <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', margin: 0 }}>
                        La tua preferenza verrà salvata e applicata automaticamente alle prossime visite
                    </p>
                </div>
            </motion.div>
        </div>
    );
}
