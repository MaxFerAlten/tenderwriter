import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Save, RefreshCw, CheckCircle, AlertCircle, Loader2, Sliders, Info } from 'lucide-react';
import { ragApi } from '../api/client';

function CustomTooltip({ text }: { text: string }) {
    const [visible, setVisible] = useState(false);
    return (
        <span 
            onMouseEnter={() => setVisible(true)} 
            onMouseLeave={() => setVisible(false)}
            style={{ position: 'relative', display: 'inline-flex', alignItems: 'center', cursor: 'help' }}
        >
            <Info size={14} color="var(--text-muted)" />
            {visible && (
                <div style={{
                    position: 'absolute',
                    bottom: '100%',
                    left: '0',
                    marginBottom: '6px',
                    padding: '8px 12px',
                    backgroundColor: '#1e293b',
                    color: '#f8fafc',
                    fontSize: '0.75rem',
                    borderRadius: '6px',
                    boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.5)',
                    width: 'max-content',
                    maxWidth: '280px',
                    zIndex: 50,
                    lineHeight: '1.4',
                    whiteSpace: 'normal',
                    pointerEvents: 'none'
                }}>
                    {text}
                    <div style={{
                        position: 'absolute',
                        top: '100%',
                        left: '6px',
                        borderWidth: '4px',
                        borderStyle: 'solid',
                        borderColor: '#1e293b transparent transparent transparent'
                    }} />
                </div>
            )}
        </span>
    );
}

export default function LlmSetting() {
    const [isLoading, setIsLoading] = useState(true);
    const [isSaving, setIsSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [saveMessage, setSaveMessage] = useState<string | null>(null);

    const [settings, setSettings] = useState({
        temperature: '',
        top_p: '',
        presence_penalty: '',
        frequency_penalty: '',
        repeat_penalty: '',
        repeat_last_n: '',
        dry_multiplier: '',
        dry_base: '',
        dry_allowed_length: '',
        max_tokens: '',
    });

    useEffect(() => {
        loadSettings();
    }, []);

    const loadSettings = async () => {
        try {
            setIsLoading(true);
            setError(null);
            const data = await ragApi.getLlmSettings();
            setSettings({
                temperature: data.temperature?.toString() ?? '0.3',
                top_p: data.top_p?.toString() ?? '0.9',
                presence_penalty: data.presence_penalty?.toString() ?? '0.0',
                frequency_penalty: data.frequency_penalty?.toString() ?? '0.0',
                repeat_penalty: data.repeat_penalty?.toString() ?? '1.10',
                repeat_last_n: data.repeat_last_n?.toString() ?? '64',
                dry_multiplier: data.dry_multiplier?.toString() ?? '0.8',
                dry_base: data.dry_base?.toString() ?? '1.75',
                dry_allowed_length: data.dry_allowed_length?.toString() ?? '2',
                max_tokens: data.max_tokens?.toString() ?? '512',
            });
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Unable to load settings.');
        } finally {
            setIsLoading(false);
        }
    };

    const handleSave = async () => {
        try {
            setIsSaving(true);
            setError(null);
            setSaveMessage(null);

            const payload: Record<string, number | null> = {};
            for (const [key, val] of Object.entries(settings)) {
                if (val.trim() === '') {
                    payload[key] = null;
                } else {
                    payload[key] = Number(val);
                }
            }

            // Provide a check to ensure valid numbers
            for (const [key, val] of Object.entries(payload)) {
                if (val !== null && isNaN(val as number)) {
                    throw new Error(`The field ${key} must be a valid number.`);
                }
            }

            await ragApi.updateLlmSettings(payload as any);
            setSaveMessage('Settings successfully saved!');
            
            // Clear success message after 3 seconds
            setTimeout(() => {
                setSaveMessage(null);
            }, 3000);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Unable to save settings.');
        } finally {
            setIsSaving(false);
        }
    };

    if (isLoading) {
        return (
            <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%', flexDirection: 'column', gap: '1rem' }}>
                <Loader2 size={32} className="animate-spin text-muted" />
                <div style={{ color: 'var(--text-muted)' }}>Loading LLM parameters...</div>
            </div>
        );
    }

    const handleChange = (key: keyof typeof settings, value: string) => {
        setSettings(prev => ({ ...prev, [key]: value }));
    };

    return (
        <motion.div
            className="animate-in"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            transition={{ duration: 0.3 }}
            style={{ maxWidth: '56rem', margin: '0 auto', paddingBottom: '3rem' }}
        >
            <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div>
                    <h1 className="page-title">
                        <Sliders size={28} color="var(--accent-blue)" style={{ verticalAlign: 'middle', marginRight: 8 }} />
                        LLM Advanced Tuner
                    </h1>
                    <p className="page-subtitle">Dynamically override the sampling parameters of the LLM model.</p>
                </div>
                <div style={{ display: 'flex', gap: '0.75rem' }}>
                    <button className="btn btn-ghost" onClick={loadSettings} disabled={isLoading || isSaving}>
                        <RefreshCw size={18} /> Resync
                    </button>
                    <button className="btn btn-primary" onClick={handleSave} disabled={isLoading || isSaving}>
                        {isSaving ? <Loader2 size={18} className="animate-spin" /> : <Save size={18} />}
                        Save Override
                    </button>
                </div>
            </div>

            {error && (
                <div style={{ padding: '0.75rem 1rem', borderRadius: 'var(--radius-sm)', background: 'rgba(239, 68, 68, 0.1)', color: '#ef4444', display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1.5rem', border: '1px solid rgba(239, 68, 68, 0.3)' }}>
                    <AlertCircle size={16} />
                    {error}
                </div>
            )}

            {saveMessage && (
                <div style={{ padding: '0.75rem 1rem', borderRadius: 'var(--radius-sm)', background: 'rgba(16, 185, 129, 0.1)', color: '#10b981', display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1.5rem', border: '1px solid rgba(16, 185, 129, 0.3)' }}>
                    <CheckCircle size={16} />
                    {saveMessage}
                </div>
            )}

            <div className="card" style={{ display: 'grid', gap: '1.5rem', padding: '1.5rem' }}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                    <h3 style={{ margin: 0, fontSize: '1.1rem' }}>Primary Parameters</h3>
                    <p style={{ margin: 0, fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                        Clear the field (leave empty) to let the system use the default engine parameters.
                    </p>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                    <div className="form-group">
                        <label className="form-label" style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                            Temperature
                            <CustomTooltip text="Controls the randomness of the generated text. Lower values make the output more deterministic and focused. Ref: Vaswani et al. (2017) 'Attention Is All You Need', sec. decoding strategies." />
                        </label>
                        <input
                            type="number"
                            step="0.05"
                            className="form-input"
                            placeholder="e.g. 0.3"
                            value={settings.temperature}
                            onChange={(e) => handleChange('temperature', e.target.value)}
                        />
                    </div>
                    <div className="form-group">
                        <label className="form-label" style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                            Max Tokens
                            <CustomTooltip text="The maximum number of tokens to generate. Limits the length of the output text. Ref: OpenAI API Reference (max_tokens parameter)." />
                        </label>
                        <input
                            type="number"
                            className="form-input"
                            placeholder="e.g. 512"
                            value={settings.max_tokens}
                            onChange={(e) => handleChange('max_tokens', e.target.value)}
                        />
                    </div>
                    <div className="form-group">
                        <label className="form-label" style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                            Top P
                            <CustomTooltip text="Nucleus sampling threshold. The model considers only the tokens comprising the top-p probability mass. Ref: Holtzman et al. (2019) 'The Curious Case of Neural Text Degeneration'." />
                        </label>
                        <input
                            type="number"
                            step="0.05"
                            className="form-input"
                            placeholder="e.g. 0.9"
                            value={settings.top_p}
                            onChange={(e) => handleChange('top_p', e.target.value)}
                        />
                    </div>
                    <div className="form-group">
                        <label className="form-label" style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                            Presence Penalty
                            <CustomTooltip text="Penalizes new tokens based on whether they appear in the text so far, encouraging the model to talk about new topics. Ref: OpenAI API Reference." />
                        </label>
                        <input
                            type="number"
                            step="0.1"
                            className="form-input"
                            placeholder="e.g. 0.0"
                            value={settings.presence_penalty}
                            onChange={(e) => handleChange('presence_penalty', e.target.value)}
                        />
                    </div>
                    <div className="form-group">
                        <label className="form-label" style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                            Frequency Penalty
                            <CustomTooltip text="Penalizes new tokens based on their existing frequency in the text, decreasing the model's likelihood to repeat the same line verbatim. Ref: OpenAI API Reference." />
                        </label>
                        <input
                            type="number"
                            step="0.1"
                            className="form-input"
                            placeholder="e.g. 0.0"
                            value={settings.frequency_penalty}
                            onChange={(e) => handleChange('frequency_penalty', e.target.value)}
                        />
                    </div>
                </div>

                <hr style={{ border: 0, borderTop: '1px solid var(--border-color)', margin: '0.5rem 0' }} />

                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                    <h3 style={{ margin: 0, fontSize: '1.1rem' }}>Antirepetition (DRY Sampler)</h3>
                    <p style={{ margin: 0, fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                        Controls aggressive repetition penalties for llama.cpp-based LLMs.
                    </p>
                </div>
                
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                    <div className="form-group">
                        <label className="form-label" style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                            Repeat Penalty (1.0 = disabled)
                            <CustomTooltip text="Aggressively penalizes tokens that have already been generated, commonly used in Llama.cpp to prevent looping. Ref: Keskar et al. (2019) 'CTRL: A Conditional Transformer Language Model for Controllable Generation'." />
                        </label>
                        <input
                            type="number"
                            step="0.01"
                            className="form-input"
                            placeholder="e.g. 1.05"
                            value={settings.repeat_penalty}
                            onChange={(e) => handleChange('repeat_penalty', e.target.value)}
                        />
                    </div>
                    <div className="form-group">
                        <label className="form-label" style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                            Repeat Last N
                            <CustomTooltip text="The number of previous tokens to consider when applying the repeat penalty. Ref: Llama.cpp Documentation / Community parameters." />
                        </label>
                        <input
                            type="number"
                            className="form-input"
                            placeholder="e.g. 128"
                            value={settings.repeat_last_n}
                            onChange={(e) => handleChange('repeat_last_n', e.target.value)}
                        />
                    </div>
                    <div className="form-group">
                        <label className="form-label" style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                            DRY Multiplier
                            <CustomTooltip text="DRY (Don't Repeat Yourself) penalty multiplier. Penalizes repeating patterns. Ref: 'DRY Sampling' by Oobabooga / Llama.cpp active contributors (2024)." />
                        </label>
                        <input
                            type="number"
                            step="0.1"
                            className="form-input"
                            placeholder="e.g. 0.4"
                            value={settings.dry_multiplier}
                            onChange={(e) => handleChange('dry_multiplier', e.target.value)}
                        />
                    </div>
                    <div className="form-group">
                        <label className="form-label" style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                            DRY Base
                            <CustomTooltip text="The exponential base for the DRY penalty. Determines how quickly the penalty grows with pattern length. Ref: Llama.cpp DRY parameter proposal." />
                        </label>
                        <input
                            type="number"
                            step="0.1"
                            className="form-input"
                            placeholder="e.g. 1.75"
                            value={settings.dry_base}
                            onChange={(e) => handleChange('dry_base', e.target.value)}
                        />
                    </div>
                    <div className="form-group">
                        <label className="form-label" style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                            DRY Allowed Length
                            <CustomTooltip text="Maximum length of repeated sequence permitted before the DRY penalty is applied. Ref: Llama.cpp DRY sampling documentation." />
                        </label>
                        <input
                            type="number"
                            className="form-input"
                            placeholder="e.g. 2"
                            value={settings.dry_allowed_length}
                            onChange={(e) => handleChange('dry_allowed_length', e.target.value)}
                        />
                    </div>
                </div>
            </div>
        </motion.div>
    );
}
