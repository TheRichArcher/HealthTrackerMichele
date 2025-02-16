import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { setLocalStorageItem } from '../utils/utils';
import { useAuth } from '../context/AuthContext';
import '../styles/AuthPage.css';

const MIN_USERNAME_LENGTH = 3;
const MIN_PASSWORD_LENGTH = 6;

const AuthPage = () => {
    const [isLogin, setIsLogin] = useState(true);
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState(null);
    const [message, setMessage] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [showLoading, setShowLoading] = useState(false);

    const navigate = useNavigate();
    const location = useLocation();
    const { checkAuth } = useAuth();

    const from = location.state?.from?.pathname || '/dashboard';

    // Clear error when input changes
    const handleInputChange = useCallback((setter) => (e) => {
        setError(null);
        setter(e.target.value.trim());
    }, []);

    // Validate inputs
    const validateInputs = useCallback(() => {
        if (username.length < MIN_USERNAME_LENGTH) {
            setError(`Username must be at least ${MIN_USERNAME_LENGTH} characters long.`);
            return false;
        }
        if (password.length < MIN_PASSWORD_LENGTH) {
            setError(`Password must be at least ${MIN_PASSWORD_LENGTH} characters long.`);
            return false;
        }
        return true;
    }, [username, password]);

    // Toggle login/signup mode
    const toggleMode = useCallback(() => {
        setIsLogin(!isLogin);
        setError(null);
        setMessage('');
    }, [isLogin]);

    // Handle form submission
    const handleSubmit = useCallback(async (e) => {
        e.preventDefault();
        setError(null);
        setMessage('');

        if (!validateInputs()) {
            return;
        }

        setIsLoading(true);
        const endpoint = isLogin ? 'login' : 'signup';

        try {
            const response = await fetch(`https://healthtrackerai.pythonanywhere.com/api/${endpoint}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password }),
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || `${isLogin ? 'Login' : 'Signup'} failed.`);
            }

            setLocalStorageItem('user_id', data.user_id);
            setLocalStorageItem('access_token', data.access_token);
            setLocalStorageItem('refresh_token', data.refresh_token);
            setMessage(`${isLogin ? 'Login' : 'Signup'} successful! Redirecting...`);

            await checkAuth();

            setTimeout(() => {
                navigate(from, { replace: true });
            }, 1000);
        } catch (error) {
            console.error(`${isLogin ? 'Login' : 'Signup'} error:`, error);
            setError(error.message);
        } finally {
            setIsLoading(false);
            setShowLoading(false);
        }
    }, [isLogin, username, password, validateInputs, checkAuth, navigate, from]);

    // Handle loading state
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
                        <label htmlFor="username">Username:</label>
                        <input
                            type="text"
                            id="username"
                            value={username}
                            onChange={handleInputChange(setUsername)}
                            required
                            disabled={isLoading}
                            minLength={MIN_USERNAME_LENGTH}
                        />
                    </div>
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
                        />
                    </div>
                    {error && <p className="auth-error">{error}</p>}
                    {message && <p className="auth-success">{message}</p>}
                    <button type="submit" className="auth-button" disabled={isLoading}>
                        {showLoading ? "Processing..." : isLogin ? "Sign In" : "Sign Up"}
                    </button>
                </form>
                <p className="auth-toggle">
                    {isLogin ? "Don't have an account? " : "Already have an account? "}
                    <button onClick={toggleMode} className="auth-toggle-button" disabled={isLoading}>
                        {isLogin ? "Sign Up" : "Sign In"}
                    </button>
                </p>
            </div>
        </div>
    );
};

export default AuthPage;
