import React, { useState, useCallback, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from './AuthProvider';
import '../styles/AuthPage.css';

const MIN_PASSWORD_LENGTH = 6;

const AuthPage = ({ initialMode = "login" }) => {
    const [isLogin, setIsLogin] = useState(initialMode === "login");
    const [email, setEmail] = useState('');
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState(null);
    const [message, setMessage] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [showLoading, setShowLoading] = useState(false);

    const navigate = useNavigate();
    const location = useLocation();
    const { login } = useAuth();

    const from = location.state?.from?.pathname || '/dashboard';

    const handleInputChange = useCallback((setter) => (e) => {
        setError(null);
        setter(e.target.value.trim());
    }, []);

    const validateInputs = useCallback(() => {
        console.log('Validating inputs:', { email, password, username, isLogin });
        if (!email) {
            setError('Email is required.');
            console.log('Validation failed: Email is required');
            return false;
        }
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        if (!emailRegex.test(email)) {
            setError('Please enter a valid email address.');
            console.log('Validation failed: Invalid email format');
            return false;
        }
        if (!password) {
            setError('Password is required.');
            console.log('Validation failed: Password is required');
            return false;
        }
        if (password.length < MIN_PASSWORD_LENGTH) {
            setError(`Password must be at least ${MIN_PASSWORD_LENGTH} characters long.`);
            console.log(`Validation failed: Password too short (${password.length} < ${MIN_PASSWORD_LENGTH})`);
            return false;
        }
        if (!isLogin && username && username.length < 3) {
            setError('Username must be at least 3 characters long.');
            console.log('Validation failed: Username too short');
            return false;
        }
        console.log('Validation passed');
        return true;
    }, [email, password, username, isLogin]);

    const toggleMode = useCallback(() => {
        setIsLogin((prev) => !prev);
        setError(null);
        setMessage('');
    }, []);

    const handleSubmit = useCallback(
        async (e) => {
            e.preventDefault();
            setError(null);
            setMessage('');

            if (!validateInputs()) return;

            setIsLoading(true);
            const credentials = isLogin
                ? { email, password }
                : { email, password, username: username || null }; // Send null instead of undefined

            console.log('Submitting credentials:', credentials);

            try {
                await login(credentials, from);
                setMessage(`${isLogin ? 'Login' : 'Signup'} successful! Redirecting...`);
            } catch (error) {
                console.error(`${isLogin ? 'Login' : 'Signup'} error:`, error.response?.data || error.message);
                const errorMessage = error.response?.data?.error || error.message || `${isLogin ? 'Login' : 'Signup'} failed.`;
                setError(errorMessage);
            } finally {
                setIsLoading(false);
                setShowLoading(false);
            }
        },
        [isLogin, email, username, password, validateInputs, login, from]
    );

    useEffect(() => {
        let timer;
        if (isLoading) {
            timer = setTimeout(() => setShowLoading(true), 200);
        }
        return () => clearTimeout(timer);
    }, [isLoading]);

    return (
        <div className="auth-container">
            <div className="auth-box">
                <h2 className="auth-title">{isLogin ? 'Sign In' : 'Create Account'}</h2>
                <form onSubmit={handleSubmit} className="auth-form">
                    <div className="auth-group">
                        <label htmlFor="email">Email:</label>
                        <input
                            type="email"
                            id="email"
                            value={email}
                            onChange={handleInputChange(setEmail)}
                            required
                            disabled={isLoading}
                            autoComplete="email"
                        />
                    </div>

                    {!isLogin && (
                        <div className="auth-group">
                            <label htmlFor="username">Username (optional):</label>
                            <input
                                type="text"
                                id="username"
                                value={username}
                                onChange={handleInputChange(setUsername)}
                                disabled={isLoading}
                                placeholder="Leave blank to use email"
                                autoComplete="username"
                            />
                        </div>
                    )}

                    <div className="auth-group">
                        <label htmlFor="password">Password:</label>
                        <input
                            type="password"
                            id="password"
                            value={password}
                            onChange={handleInputChange(setPassword)}
                            required
                            disabled={isLoading}
                            minLength={MIN_PASSWORD_LENGTH}
                            autoComplete={isLogin ? 'current-password' : 'new-password'}
                        />
                    </div>
                    {error && <p className="auth-error">{error}</p>}
                    {message && <p className="auth-success">{message}</p>}
                    <button type="submit" className="auth-button" disabled={isLoading}>
                        {showLoading ? 'Processing...' : isLogin ? 'Sign In' : 'Sign Up'}
                    </button>
                </form>
                <p className="auth-toggle">
                    {isLogin ? "Don't have an account? " : "Already have an account? "}
                    <button onClick={toggleMode} className="auth-toggle-button" disabled={isLoading}>
                        {isLogin ? 'Sign Up' : 'Sign In'}
                    </button>
                </p>
            </div>
        </div>
    );
};

export default AuthPage;