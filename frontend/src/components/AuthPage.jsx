import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { setLocalStorageItem, removeLocalStorageItem } from '../utils/utils';
import { useAuth } from './AuthProvider';
import '../styles/AuthPage.css';

const MIN_PASSWORD_LENGTH = 6;
const API_BASE_URL = 'https://healthtrackermichele.onrender.com/api';

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
    const { checkAuth, setIsAuthenticated } = useAuth();

    const from = location.state?.from?.pathname || '/dashboard';

    const handleInputChange = useCallback((setter) => (e) => {
        setError(null);
        setter(e.target.value.trim());
    }, []);

    const validateInputs = useCallback(() => {
        if (!email) {
            setError('Email is required.');
            return false;
        }
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        if (!emailRegex.test(email)) {
            setError('Please enter a valid email address.');
            return false;
        }
        if (password.length < MIN_PASSWORD_LENGTH) {
            setError(`Password must be at least ${MIN_PASSWORD_LENGTH} characters long.`);
            return false;
        }
        if (!isLogin && username && username.length < 3) {
            setError('Username must be at least 3 characters long.');
            return false;
        }
        return true;
    }, [email, password, username, isLogin]);

    const toggleMode = useCallback(() => {
        setIsLogin((prev) => !prev);
        setError(null);
        setMessage('');
    }, []);

    const handleSubmit = useCallback(async (e) => {
        e.preventDefault();
        setError(null);
        setMessage('');

        if (!validateInputs()) return;

        setIsLoading(true);
        const endpoint = isLogin ? 'login' : 'users';

        try {
            const requestBody = isLogin 
                ? { email, password } 
                : { email, password, username };
                
            console.log(`Sending ${isLogin ? 'login' : 'signup'} request to ${API_BASE_URL}/${endpoint}`, requestBody);
            const response = await fetch(`${API_BASE_URL}/${endpoint}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(requestBody),
            });

            const data = await response.json();
            console.log('Response received:', data);

            if (!response.ok) {
                throw new Error(data.error || `${isLogin ? 'Login' : 'Signup'} failed.`);
            }

            if (!data.user_id || !data.access_token || !data.refresh_token) {
                console.error('Invalid response structure:', data);
                throw new Error('Invalid response from server: missing user_id, access_token, or refresh_token');
            }

            setLocalStorageItem('user_id', data.user_id);
            setLocalStorageItem('access_token', data.access_token);
            setLocalStorageItem('refresh_token', data.refresh_token);
            console.log('Tokens stored:', {
                user_id: data.user_id,
                access_token: data.access_token.substring(0, 20) + '...',
                refresh_token: data.refresh_token.substring(0, 20) + '...'
            });

            const storedAccessToken = localStorage.getItem('access_token');
            console.log('Access token in localStorage after storage:', storedAccessToken ? storedAccessToken.substring(0, 20) + '...' : 'missing');

            setMessage(`${isLogin ? 'Login' : 'Signup'} successful! Redirecting...`);
            setIsAuthenticated(true);
            await checkAuth();
            setTimeout(() => navigate(from, { replace: true }), 1000);
        } catch (error) {
            console.error(`${isLogin ? 'Login' : 'Signup'} error:`, error.message);
            setError(error.message);
            removeLocalStorageItem('user_id');
            removeLocalStorageItem('access_token');
            removeLocalStorageItem('refresh_token');
        } finally {
            setIsLoading(false);
            setShowLoading(false);
        }
    }, [isLogin, email, username, password, validateInputs, checkAuth, setIsAuthenticated, navigate, from]);

    useEffect(() => {
        // Clear inconsistent state on mount
        const userId = localStorage.getItem('user_id');
        const accessToken = localStorage.getItem('access_token');
        if (userId && !accessToken) {
            console.log('Inconsistent state: user_id exists but access_token is missing. Clearing localStorage.');
            removeLocalStorageItem('user_id');
            removeLocalStorageItem('access_token');
            removeLocalStorageItem('refresh_token');
        }
    }, []);

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