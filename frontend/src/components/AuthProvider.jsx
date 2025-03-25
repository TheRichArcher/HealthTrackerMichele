import React, { createContext, useState, useEffect, useCallback } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import axios from 'axios';
import { getLocalStorageItem, setLocalStorageItem, removeLocalStorageItem } from '../utils/utils';

const API_BASE_URL = 'https://healthtrackermichele.onrender.com/api';

const debounce = (func, wait) => {
    let timeout;
    return (...args) => {
        clearTimeout(timeout);
        return new Promise((resolve) => {
            timeout = setTimeout(() => resolve(func(...args)), wait);
        });
    };
};

const AuthContext = createContext();

const AuthProvider = ({ children }) => {
    const navigate = useNavigate();
    const location = useLocation();
    const [isAuthenticated, setIsAuthenticated] = useState(false);
    const [isLoading, setIsLoading] = useState(true);
    const [isLoggingOut, setIsLoggingOut] = useState(false);
    const [subscriptionTier, setSubscriptionTier] = useState(null);

    const fetchSubscriptionStatus = useCallback(async () => {
        const token = getLocalStorageItem('access_token');
        if (!token) return;
        try {
            const response = await axios.get(`${API_BASE_URL}/subscription/status`, {
                headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
                withCredentials: true,
            });
            setSubscriptionTier(response.data.subscription_tier);
        } catch (error) {
            console.error('Error fetching subscription status:', error.response?.data || error.message);
            if (error.response?.status === 401 || error.response?.status === 422) {
                removeLocalStorageItem('access_token');
                removeLocalStorageItem('refresh_token');
                setIsAuthenticated(false);
            }
        }
    }, []);

    const validateToken = async (token, isRetry = false) => {
        if (!token) return false;
        try {
            const response = await axios.get(`${API_BASE_URL}/auth/validate/`, {
                headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
                withCredentials: true,
            });
            setSubscriptionTier(response.data.subscription_tier);
            return true;
        } catch (error) {
            if (error.response?.status === 401 || error.response?.status === 422) {
                removeLocalStorageItem('access_token');
                removeLocalStorageItem('refresh_token');
                setIsAuthenticated(false);
                if (!isRetry) {
                    const refreshed = await refreshToken();
                    if (refreshed) return await validateToken(getLocalStorageItem('access_token'), true);
                }
            }
            return false;
        }
    };

    const refreshToken = useCallback(async () => {
        const refreshTokenValue = getLocalStorageItem('refresh_token');
        if (!refreshTokenValue) throw new Error('No refresh token available');
        try {
            const response = await axios.post(`${API_BASE_URL}/auth/refresh/`, {}, {
                headers: { 'Authorization': `Bearer ${refreshTokenValue}`, 'Content-Type': 'application/json' },
                withCredentials: true,
            });
            if (response.data.access_token) {
                setLocalStorageItem('access_token', response.data.access_token);
                setIsAuthenticated(true);
                return true;
            }
            throw new Error('Invalid refresh token response');
        } catch (error) {
            if (error.response?.status === 401 || error.response?.status === 422) {
                removeLocalStorageItem('access_token');
                removeLocalStorageItem('refresh_token');
                setIsAuthenticated(false);
            }
            throw error;
        }
    }, []);

    const checkAuth = useCallback(debounce(async () => {
        console.log('Checking authentication status');
        const accessToken = getLocalStorageItem('access_token');
        const userId = getLocalStorageItem('user_id');
        const currentPath = location.pathname;
        const publicRoutes = ['/chat', '/auth', '/subscription', '/one-time-report', '/library', '/'];

        if (!accessToken || !userId) {
            console.log('No tokens found. Allowing /chat to proceed without redirect.');
            // Only update isAuthenticated if not on a public route
            if (!publicRoutes.includes(currentPath)) {
                setIsAuthenticated(false);
            }
            setIsLoading(false);
            if (['/dashboard', '/subscribe'].includes(currentPath)) {
                console.log('Redirecting to /auth for protected route:', currentPath);
                navigate('/auth');
            }
            return false;
        }

        try {
            const isValid = await validateToken(accessToken);
            console.log('checkAuth: Token validation result:', isValid);
            setIsAuthenticated(isValid);
            if (isValid) await fetchSubscriptionStatus();
            else if (['/dashboard', '/subscribe'].includes(currentPath)) {
                console.log('Redirecting to /auth due to invalid token on protected route:', currentPath);
                navigate('/auth');
            }
            return isValid;
        } catch (error) {
            console.error('Authentication check error:', error);
            setIsAuthenticated(false);
            if (['/dashboard', '/subscribe'].includes(currentPath)) {
                console.log('Redirecting to /auth due to error on protected route:', currentPath);
                navigate('/auth');
            }
            return false;
        } finally {
            setIsLoading(false);
        }
    }, 300), [fetchSubscriptionStatus, navigate, location]);

    const login = useCallback(async (credentials, navigateTo = '/dashboard') => {
        setIsLoading(true);
        try {
            const endpoint = credentials.username ? `${API_BASE_URL}/users` : `${API_BASE_URL}/login`;
            const response = await axios.post(endpoint, credentials, {
                headers: { 'Content-Type': 'application/json' },
                withCredentials: true,
            });
            if (response.data.access_token && response.data.refresh_token) {
                setLocalStorageItem('access_token', response.data.access_token);
                setLocalStorageItem('refresh_token', response.data.refresh_token);
                setLocalStorageItem('user_id', response.data.user_id);
                setIsAuthenticated(true);
                setSubscriptionTier(response.data.subscription_tier);
                navigate(navigateTo);
                return true;
            }
            throw new Error('Invalid login response: Missing tokens');
        } catch (error) {
            console.error('Login error:', error.response?.data || error.message);
            throw error;
        } finally {
            setIsLoading(false);
        }
    }, [navigate]);

    const logout = useCallback(async () => {
        setIsLoggingOut(true);
        setIsLoading(true);
        const token = getLocalStorageItem('access_token');
        if (token) {
            try {
                await axios.post(`${API_BASE_URL}/logout/`, {}, {
                    headers: { 'Authorization': `Bearer ${token}` },
                    withCredentials: true,
                });
            } catch (error) {
                console.error('Server logout notification failed:', error);
            }
        }
        removeLocalStorageItem('access_token');
        removeLocalStorageItem('refresh_token');
        removeLocalStorageItem('user_id');
        removeLocalStorageItem('lastPath');
        setIsAuthenticated(false);
        setSubscriptionTier(null);
        setIsLoading(false);
        setIsLoggingOut(false);
        navigate('/auth');
    }, [navigate]);

    useEffect(() => {
        console.log('AuthProvider mounted, checking authentication for path:', location.pathname);
        const publicRoutes = ['/chat', '/auth', '/subscription', '/one-time-report', '/library', '/'];
        if (!publicRoutes.includes(location.pathname)) {
            checkAuth();
        } else {
            setIsLoading(false);
            console.log('Skipping checkAuth on public route:', location.pathname);
        }

        const interval = setInterval(checkAuth, 60000);
        const refreshInterval = setInterval(async () => {
            try {
                await refreshToken();
                await checkAuth();
            } catch (error) {
                console.error('Proactive refresh failed:', error);
                if (isAuthenticated) await logout();
            }
        }, 3300000); // 55 minutes

        const handleStorageChange = (e) => {
            if (['access_token', 'refresh_token', 'user_id'].includes(e.key)) {
                checkAuth();
            }
        };
        const handleVisibilityChange = () => {
            if (document.visibilityState === 'visible') {
                checkAuth();
            }
        };

        window.addEventListener('storage', handleStorageChange);
        document.addEventListener('visibilitychange', handleVisibilityChange);
        window.addEventListener('focus', checkAuth);

        return () => {
            clearInterval(interval);
            clearInterval(refreshInterval);
            window.removeEventListener('storage', handleStorageChange);
            document.removeEventListener('visibilitychange', handleVisibilityChange);
            window.removeEventListener('focus', checkAuth);
        };
    }, [location.pathname, checkAuth, isAuthenticated, refreshToken]);

    const value = {
        isAuthenticated,
        setIsAuthenticated,
        isLoading,
        login,
        checkAuth,
        logout,
        refreshToken,
        subscriptionTier,
        setSubscriptionTier,
        fetchSubscriptionStatus,
        isLoggingOut,
    };

    return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export default AuthProvider;
export const useAuth = () => React.useContext(AuthContext);