import React, { createContext, useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { getLocalStorageItem, setLocalStorageItem, removeLocalStorageItem } from '../utils/utils';

const API_BASE_URL = 'https://healthtrackermichele.onrender.com/api'; // Already correct

// Debounce utility to prevent concurrent checkAuth calls
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
    const [isAuthenticated, setIsAuthenticated] = useState(false);
    const [isLoading, setIsLoading] = useState(true);
    const [isLoggingOut, setIsLoggingOut] = useState(false);
    const [subscriptionTier, setSubscriptionTier] = useState(null);

    const fetchSubscriptionStatus = useCallback(async () => {
        const token = getLocalStorageItem('access_token');
        if (!token) return;
        try {
            const response = await axios.get(`${API_BASE_URL}/subscription/status`, {
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json',
                },
            });
            setSubscriptionTier(response.data.subscription_tier);
        } catch (error) {
            console.error('Error fetching subscription status:', error.response?.data || error.message);
        }
    }, []);

    const validateToken = async (token, isRetry = false) => {
        console.log('Validating token. Token provided:', token ? 'yes' : 'no');
        if (!token) {
            console.log('No token provided for validation');
            return false;
        }

        try {
            const response = await axios.get(`${API_BASE_URL}/auth/validate/`, {
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json',
                },
            });
            console.log('Token validation successful. Response:', response.data);
            setSubscriptionTier(response.data.subscription_tier);
            return true;
        } catch (error) {
            console.log('Token validation failed:', error.response?.data || error.message);
            if (error.response?.status === 401 && !isRetry) {
                console.log('Attempting token refresh due to 401');
                const refreshed = await refreshToken();
                if (refreshed) {
                    const newToken = getLocalStorageItem('access_token');
                    return await validateToken(newToken, true);
                } else {
                    console.log('Token refresh failed, logging out');
                    await logout();
                    return false;
                }
            }
            return false;
        }
    };

    const refreshToken = useCallback(async () => {
        const refreshTokenValue = getLocalStorageItem('refresh_token');
        console.log('Attempting to refresh token. Refresh token:', refreshTokenValue ? 'exists' : 'missing');
        if (!refreshTokenValue) {
            throw new Error('No refresh token available');
        }

        try {
            const response = await axios.post(`${API_BASE_URL}/auth/refresh/`, {}, {
                headers: {
                    'Authorization': `Bearer ${refreshTokenValue}`,
                    'Content-Type': 'application/json',
                },
            });

            if (response.data && response.data.access_token) {
                setLocalStorageItem('access_token', response.data.access_token);
                console.log('Token refresh successful. New access token:', response.data.access_token.substring(0, 20) + '...');
                setIsAuthenticated(true);
                return true;
            }
            throw new Error('Invalid refresh token response');
        } catch (error) {
            console.error('Token refresh failed:', error.response?.data || error.message);
            throw error; // Propagate error to trigger logout
        }
    }, []);

    const checkAuth = useCallback(debounce(async () => {
        console.log('Checking authentication status');
        const accessToken = getLocalStorageItem('access_token');
        const userId = getLocalStorageItem('user_id');
        if (!accessToken || !userId) {
            console.log('No access token or user ID found, setting isAuthenticated to false');
            setIsAuthenticated(false);
            setIsLoading(false);
            return false;
        }

        try {
            const isValid = await validateToken(accessToken);
            setIsAuthenticated(isValid);
            if (isValid) await fetchSubscriptionStatus();
            return isValid;
        } catch (error) {
            console.error('Authentication check error:', error);
            setIsAuthenticated(false);
            return false;
        } finally {
            setIsLoading(false);
        }
    }, 300), [fetchSubscriptionStatus]);

    const login = useCallback(async (credentials, navigateTo = '/dashboard') => {
        setIsLoading(true);
        try {
            const endpoint = credentials.username ? `${API_BASE_URL}/users` : `${API_BASE_URL}/login`;
            const response = await axios.post(endpoint, credentials);
            if (response.data && response.data.access_token && response.data.refresh_token) {
                setLocalStorageItem('access_token', response.data.access_token);
                setLocalStorageItem('refresh_token', response.data.refresh_token);
                setLocalStorageItem('user_id', response.data.user_id);
                setIsAuthenticated(true);
                await fetchSubscriptionStatus();
                await checkAuth(); // Ensure auth state is updated
                navigate(navigateTo); // Navigate after successful login/signup
                return true;
            }
            throw new Error('Invalid login response');
        } catch (error) {
            console.error('Login error:', error.response?.data || error.message);
            throw error;
        } finally {
            setIsLoading(false);
        }
    }, [fetchSubscriptionStatus, checkAuth, navigate]);

    const logout = useCallback(async () => {
        setIsLoggingOut(true);
        setIsLoading(true);
        const token = getLocalStorageItem('access_token');
        if (token) {
            try {
                await axios.post(`${API_BASE_URL}/logout/`, {}, {
                    headers: { 'Authorization': `Bearer ${token}` },
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
        console.log('AuthProvider mounted, checking authentication');
        checkAuth();

        const interval = setInterval(checkAuth, 60000);
        const refreshInterval = setInterval(async () => {
            console.log('Proactively refreshing token');
            try {
                await refreshToken();
                await checkAuth();
            } catch (error) {
                console.error('Proactive refresh failed:', error);
                await logout();
            }
        }, 3300000); // 55 minutes

        const handleStorageChange = (e) => {
            if (['access_token', 'refresh_token', 'user_id'].includes(e.key)) {
                console.log('Storage change detected for auth keys, rechecking auth');
                checkAuth();
            }
        };
        const handleVisibilityChange = () => {
            if (document.visibilityState === 'visible') {
                console.log('Tab became visible, rechecking auth');
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
            console.log('AuthProvider unmounted, cleaned up listeners');
        };
    }, [checkAuth]);

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