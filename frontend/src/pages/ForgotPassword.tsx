import { FormEvent, useMemo, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { motion } from 'framer-motion';
import { AlertCircle, ArrowRight, CheckCircle2, KeyRound, Loader2, Lock, Mail } from 'lucide-react';
import { authApi } from '../api/client';
import '../index.css';

export default function ForgotPassword() {
    const [searchParams] = useSearchParams();
    const navigate = useNavigate();
    const token = searchParams.get('token') || '';
    const isResetMode = useMemo(() => token.length > 0, [token]);

    const [email, setEmail] = useState('');
    const [newPassword, setNewPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState('');
    const [message, setMessage] = useState('');
    const [resetCompleted, setResetCompleted] = useState(false);

    const handleRequestReset = async (e: FormEvent) => {
        e.preventDefault();
        setError('');
        setMessage('');
        setIsLoading(true);

        try {
            const response = await authApi.requestPasswordReset({ email });
            setMessage(response.message);
        } catch (err: any) {
            setError(err.message || 'Unable to send reset link');
        } finally {
            setIsLoading(false);
        }
    };

    const handleResetPassword = async (e: FormEvent) => {
        e.preventDefault();
        setError('');
        setMessage('');

        if (newPassword.length < 8) {
            setError('La nuova password deve contenere almeno 8 caratteri.');
            return;
        }

        if (newPassword !== confirmPassword) {
            setError('Le password non coincidono.');
            return;
        }

        setIsLoading(true);

        try {
            const response = await authApi.resetPassword({
                token,
                new_password: newPassword,
            });
            setMessage(response.message);
            setResetCompleted(true);
            setNewPassword('');
            setConfirmPassword('');
        } catch (err: any) {
            setError(err.message || 'Unable to reset password');
        } finally {
            setIsLoading(false);
        }
    };

    const title = resetCompleted
        ? 'Password aggiornata'
        : isResetMode
            ? 'Imposta una nuova password'
            : 'Reset password';

    const description = resetCompleted
        ? 'La tua password locale e stata aggiornata. Ora puoi tornare al login ed entrare con la nuova password.'
        : isResetMode
            ? 'Inserisci una nuova password locale per il tuo account TenderWriter.'
            : 'Inserisci la tua email e ti invieremo un link per reimpostare la password.';

    return (
        <div className="auth-container">
            <motion.div
                className="auth-card"
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.35 }}
            >
                <div className="auth-header">
                    <KeyRound size={40} color="#60a5fa" />
                    <h1>{title}</h1>
                    <p>{description}</p>
                </div>

                {error && (
                    <div className="auth-error">
                        <AlertCircle size={18} />
                        <span>{error}</span>
                    </div>
                )}

                {message && (
                    <div
                        style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '0.75rem',
                            background: 'rgba(34, 197, 94, 0.12)',
                            color: '#bbf7d0',
                            border: '1px solid rgba(34, 197, 94, 0.35)',
                            borderRadius: '12px',
                            padding: '0.9rem 1rem',
                            marginBottom: '1rem',
                        }}
                    >
                        <CheckCircle2 size={18} />
                        <span>{message}</span>
                    </div>
                )}

                {!resetCompleted && (
                    <form className="auth-form" onSubmit={isResetMode ? handleResetPassword : handleRequestReset}>
                        {!isResetMode ? (
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
                        ) : (
                            <>
                                <div className="form-group">
                                    <label>Nuova password</label>
                                    <div className="input-wrapper">
                                        <Lock className="input-icon" size={18} />
                                        <input
                                            type="password"
                                            placeholder="Almeno 8 caratteri"
                                            value={newPassword}
                                            onChange={(e) => setNewPassword(e.target.value)}
                                            required
                                            minLength={8}
                                        />
                                    </div>
                                </div>

                                <div className="form-group">
                                    <label>Conferma password</label>
                                    <div className="input-wrapper">
                                        <Lock className="input-icon" size={18} />
                                        <input
                                            type="password"
                                            placeholder="Ripeti la nuova password"
                                            value={confirmPassword}
                                            onChange={(e) => setConfirmPassword(e.target.value)}
                                            required
                                            minLength={8}
                                        />
                                    </div>
                                </div>
                            </>
                        )}

                        <button
                            type="submit"
                            className="btn-primary auth-submit"
                            disabled={isLoading}
                        >
                            {isLoading ? <Loader2 className="animate-spin" size={20} /> : (isResetMode ? 'Aggiorna password' : 'Invia link di reset')}
                            {!isLoading && <ArrowRight size={18} />}
                        </button>
                    </form>
                )}

                {resetCompleted && (
                    <button
                        type="button"
                        className="btn-primary auth-submit"
                        onClick={() => navigate('/login')}
                    >
                        Vai al login
                        <ArrowRight size={18} />
                    </button>
                )}

                <div className="auth-footer">
                    <p><Link to="/login">Torna al login</Link></p>
                </div>
            </motion.div>
        </div>
    );
}
