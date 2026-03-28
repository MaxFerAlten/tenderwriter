import { useState, FormEvent, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Sparkles, Mail, Lock, Loader2, AlertCircle, ArrowRight, Shield } from 'lucide-react';
import { authApi } from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import '../index.css';

export default function Login() {
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState('');

    const navigate = useNavigate();
    const { login, loginWithKeycloak, authMode, user } = useAuth();

    // If already authenticated (e.g. Keycloak SSO), redirect immediately
    useEffect(() => {
        if (user) navigate('/');
    }, [user, navigate]);

    const handleSubmit = async (e: FormEvent) => {
        e.preventDefault();
        setError('');

        if (authMode === 'keycloak') {
            setError('L’accesso con email/password è disabilitato in modalità SSO. Usa "Accedi con SSO".');
            return;
        }

        setIsLoading(true);

        try {
            const response = await authApi.login({ email, password });
            login(response.access_token, response.user);
            navigate('/');
        } catch (err: any) {
            setError(err.message || 'Error during login');
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
                    <h1>Bentornato in TenderWriter</h1>
                    <p>Accedi per continuare a gestire le tue gare d'appalto</p>
                </div>

                {error && (
                    <div className="auth-error">
                        <AlertCircle size={18} />
                        <span>{error}</span>
                    </div>
                )}

                {/* Keycloak SSO button — shown when SSO is available */}
                {authMode !== 'legacy' && (
                    <>
                        <button
                            type="button"
                            className="btn-primary auth-submit"
                            onClick={loginWithKeycloak}
                            style={{ marginBottom: '1rem', background: '#0058CC' }}
                        >
                            <Shield size={18} />
                            Accedi con SSO
                        </button>

                        {authMode === 'hybrid' && (
                            <div style={{
                                display: 'flex', alignItems: 'center', gap: '0.75rem',
                                margin: '0.5rem 0 1rem', color: '#64748b', fontSize: '0.85rem'
                            }}>
                                <hr style={{ flex: 1, border: 'none', borderTop: '1px solid #334155' }} />
                                oppure con email
                                <hr style={{ flex: 1, border: 'none', borderTop: '1px solid #334155' }} />
                            </div>
                        )}

                        {authMode === 'keycloak' && (
                            <p style={{
                                marginBottom: '1rem',
                                color: '#94a3b8',
                                fontSize: '0.9rem',
                                textAlign: 'center',
                            }}>
                                In questa modalità l’accesso locale con email/password è disabilitato.
                            </p>
                        )}
                        </>
                    )}

                {authMode !== 'keycloak' && (
                    <form className="auth-form" onSubmit={handleSubmit}>
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
                                />
                            </div>
                        </div>

                        <button
                            type="submit"
                            className="btn-primary auth-submit"
                            disabled={isLoading}
                        >
                            {isLoading ? <Loader2 className="animate-spin" size={20} /> : 'Accedi'}
                            {!isLoading && <ArrowRight size={18} />}
                        </button>
                    </form>
                )}

                <div className="auth-footer">
                    <p>Non hai un account? <Link to="/register">Registrati</Link></p>
                </div>
            </motion.div>
        </div>
    );
}
