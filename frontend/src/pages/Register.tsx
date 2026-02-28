import { useState, FormEvent } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Sparkles, Mail, Lock, Loader2, AlertCircle, ArrowRight, User as UserIcon, ShieldCheck } from 'lucide-react';
import { authApi } from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import '../index.css';

export default function Register() {
    const [step, setStep] = useState<1 | 2>(1);

    // Step 1 data
    const [name, setName] = useState('');
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');

    // Step 2 data
    const [otp, setOtp] = useState('');

    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState('');
    const [successMessage, setSuccessMessage] = useState('');

    const navigate = useNavigate();
    const { login } = useAuth();

    const handleRegister = async (e: FormEvent) => {
        e.preventDefault();
        setError('');
        setIsLoading(true);

        try {
            const response = await authApi.register({ name, email, password });
            setSuccessMessage(response.message || 'Controlla la tua email per il codice OTP.');
            setStep(2);
        } catch (err: any) {
            setError(err.message || 'Errore durante la registrazione');
        } finally {
            setIsLoading(false);
        }
    };

    const handleVerifyOtp = async (e: FormEvent) => {
        e.preventDefault();
        setError('');
        setIsLoading(true);

        try {
            const response = await authApi.verifyOtp({ email, otp });
            login(response.access_token, response.user);
            navigate('/');
        } catch (err: any) {
            setError(err.message || 'OTP non valido o scaduto');
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="auth-container">
            <motion.div
                className="auth-card"
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.5 }}
            >
                <div className="auth-header">
                    <Sparkles size={40} color="#60a5fa" />
                    <h1>Crea un account</h1>
                    <p>Unisciti a TenderWriter per scrivere proposte vincenti</p>
                </div>

                {error && (
                    <div className="auth-error">
                        <AlertCircle size={18} />
                        <span>{error}</span>
                    </div>
                )}

                {successMessage && step === 2 && (
                    <div className="auth-success">
                        <ShieldCheck size={18} />
                        <span>{successMessage}</span>
                    </div>
                )}

                <AnimatePresence mode="wait">
                    {step === 1 ? (
                        <motion.form
                            key="step1"
                            className="auth-form"
                            onSubmit={handleRegister}
                            initial={{ opacity: 0, x: -20 }}
                            animate={{ opacity: 1, x: 0 }}
                            exit={{ opacity: 0, x: 20 }}
                        >
                            <div className="form-group">
                                <label>Nome completo</label>
                                <div className="input-wrapper">
                                    <UserIcon className="input-icon" size={18} />
                                    <input
                                        type="text"
                                        placeholder="Mario Rossi"
                                        value={name}
                                        onChange={(e) => setName(e.target.value)}
                                        required
                                    />
                                </div>
                            </div>

                            <div className="form-group">
                                <label>Email</label>
                                <div className="input-wrapper">
                                    <Mail className="input-icon" size={18} />
                                    <input
                                        type="email"
                                        placeholder="tu@email.com"
                                        value={email}
                                        onChange={(e) => setEmail(e.target.value)}
                                        required
                                    />
                                </div>
                            </div>

                            <div className="form-group">
                                <label>Password</label>
                                <div className="input-wrapper">
                                    <Lock className="input-icon" size={18} />
                                    <input
                                        type="password"
                                        placeholder="••••••••"
                                        value={password}
                                        onChange={(e) => setPassword(e.target.value)}
                                        required
                                        minLength={6}
                                    />
                                </div>
                            </div>

                            <button
                                type="submit"
                                className="btn-primary auth-submit"
                                disabled={isLoading}
                            >
                                {isLoading ? <Loader2 className="animate-spin" size={20} /> : 'Registrati'}
                                {!isLoading && <ArrowRight size={18} />}
                            </button>

                            <div className="auth-footer">
                                <p>Hai già un account? <Link to="/login">Accedi</Link></p>
                            </div>
                        </motion.form>
                    ) : (
                        <motion.form
                            key="step2"
                            className="auth-form"
                            onSubmit={handleVerifyOtp}
                            initial={{ opacity: 0, x: 20 }}
                            animate={{ opacity: 1, x: 0 }}
                            exit={{ opacity: 0, x: -20 }}
                        >
                            <div className="form-group">
                                <label>Codice OTP (6 cifre)</label>
                                <div className="input-wrapper otp-wrapper">
                                    <input
                                        type="text"
                                        placeholder="000000"
                                        value={otp}
                                        onChange={(e) => setOtp(e.target.value)}
                                        required
                                        maxLength={6}
                                        pattern="\d{6}"
                                    />
                                </div>
                                <p className="help-text">Abbiamo inviato un codice OTP a {email}. Controlla la posta (e lo spam).</p>
                            </div>

                            <button
                                type="submit"
                                className="btn-primary auth-submit"
                                disabled={isLoading || otp.length !== 6}
                            >
                                {isLoading ? <Loader2 className="animate-spin" size={20} /> : 'Verifica e Accedi'}
                                {!isLoading && <ShieldCheck size={18} />}
                            </button>

                            <div className="auth-footer">
                                <button type="button" className="btn-secondary" style={{ width: '100%' }} onClick={() => setStep(1)} disabled={isLoading}>
                                    Torna indietro
                                </button>
                            </div>
                        </motion.form>
                    )}
                </AnimatePresence>
            </motion.div>
        </div>
    );
}
