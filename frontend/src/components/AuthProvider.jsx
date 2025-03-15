import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom'; // Add this for navigation
import { getLocalStorageItem, removeLocalStorageItem, setLocalStorageItem } from '../utils/utils';
import axios from 'axios';

// API URL handling with warning for missing environment variable
const API_BASE_URL = import.meta.env.VITE_API_URL || 'https://healthtrackermichele.onrender.com/api';
if (!import.meta.env.VITE_API_URL) {
    console.warn('VITE_API_URL not set in environment variables, using fallback URL');
}

export const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
    const [isAuthenticated, setIsAuthenticated] = useState(false);
    const [isLoading, setIsLoading] = useState(true);
    const [subscriptionTier, setSubscriptionTier] = useState(null);
    const navigate = useNavigate(); // Add navigation hook

    const refreshToken = useCallback(async () => {
        const refreshTokenValue = getLocalStorageItem('refresh_token');
        console.log('Attempting to refresh token. Refresh token:', refreshTokenValue ? 'exists' : 'missing');
        if (!refreshTokenValue) {
            console.log('No refresh token available');
            return false; // Don’t throw, just return false
        }

        try {
            const response = await axios.post(`${API_BASE_URL}/auth/refresh/`, {}, {
                headers: {
                    'Authorization': `Bearer ${refreshTokenValue}`,
                    'Content-Type': 'application/json', // Ensure header is set
                },
            });

            if (response.data && response.data.access_token) {
                setLocalStorageItem('access_token', response.data.access_token);
                console.log('Token refresh successful. New access token:', response.data.access_token.substring(0, 20) + '...');
                setIsAuthenticated(true);
                return true;
            }
            console.log('Invalid refresh token response:', response.data);
            return false;
        } catch (error) {
            console.error('Token refresh failed:', error.response?.data || error.message);
            return false; // Don’t clear tokens here, let logout handle it
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
                    'Content-Type': 'application/json', // Ensure header is set
                },
            });
            console.log('Token validation successful. Response:', response.data);
            setSubscriptionTier(response.data.subscription_tier); // Update tier from validate response
            return response.status === 200;
        } catch (error) {
            console.log('Token validation failed:', error.response?.data || error.message);
            if (error.response?.status === 401 && !isRetry) {
                console.log('Attempting token refresh due to 401');
                const refreshed = await refreshToken();
                if (refreshed) {
                    const newToken = getLocalStorageItem('access_token');
                    return await validateToken(newToken, true);
                }
            }
            return false;
        }
    };

    const fetchSubscriptionStatus = useCallback(async () => {
        if (!isAuthenticated) {
            console.log('Not authenticated, skipping subscription status fetch');
            return;
        }

        try {
            const token = getLocalStorageItem('access_token');
            console.log('Fetching subscription status. Token:', token ? 'exists' : 'missing');
            const response = await axios.get(`${API_BASE_URL}/subscription/status`, {
                headers: { 'Authorization': `Bearer ${token}` },
            });
            console.log('Subscription status fetched:', response.data.subscription_tier);
            setSubscriptionTier(response.data.subscription_tier);
        } catch (err) {
            console.error('Failed to fetch subscription status:', err.response?.data || err.message);
        }
    }, [isAuthenticated]);

    const checkAuth = useCallback(async () => {
        const accessToken = getLocalStorageItem('access_token');
        const userId = getLocalStorageItem('user_id');

        console.log('Checking authentication...');
        console.log('Access token exists:', !!accessToken, 'Value:', accessToken ? accessToken.substring(0, 20) + '...' : 'none');
        console.log('User ID exists:', !!userId, 'Value:', userId || 'none');

        if (!accessToken || !userId) {
            console.log('Missing tokens or user ID, setting isAuthenticated to false');
            setIsAuthenticated(false);
            setIsLoading(false);
            return;
        }

        try {
            const isValid = await validateToken(accessToken);
            console.log('Token validation result:', isValid);
            setIsAuthenticated(isValid);

            if (isValid) {
                console.log('User is authenticated, fetching subscription status');
                await fetchSubscriptionStatus();
            } else {
                console.log('Token invalid, user not authenticated');
            }
        } catch (error) {
            console.error('Authentication check error:', error);
            setIsAuthenticated(false);
        } finally {
            console.log('Authentication check complete, isAuthenticated:', isAuthenticated);
            setIsLoading(false);
        }
    }, [fetchSubscriptionStatus]);

    const login = useCallback(async (credentials) => {
        setIsLoading(true);
        console.log('Sending login request to', `${API_BASE_URL}/login`, credentials);
        try {
            const response = await axios.post(`${API_BASE_URL}/login`, credentials, {
                headers: { 'Content-Type': 'application/json' },
            });
            console.log('Response received:', response.data);
            setLocalStorageItem('access_token', response.data.access_token);
            setLocalStorageItem('refresh_token', response.data.refresh_token);
            setLocalStorageItem('user_id', response.data.user_id);
            console.log('Tokens stored:', {
                access_token: response.data.access_token.substring(0, 20) + '...',
                user_id: response.data.user_id,
            });
            setIsAuthenticated(true);
            setSubscriptionTier(response.data.subscription_tier);
            navigate('/dashboard'); // Redirect after successful login
        } catch (error) {
            console.error('Login failed:', error.response?.data || error.message);
            throw error;
        } finally {
            setIsLoading(false);
        }
    }, [navigate]);

    const logout = useCallback(async () => {
        setIsLoading(true);
        console.log('Logging out...');
        const token = getLocalStorageItem('access_token');

        if (token) {
            try {
                await axios.post(`${API_BASE_URL}/logout/`, {}, {
                    headers: { 'Authorization': `Bearer ${token}` },
                });
                console.log('Server logout successful');
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
        console.log('Logout complete');
        navigate('/auth'); // Redirect to login page
    }, [navigate]);

    useEffect(() => {
        console.log('AuthProvider mounted, checking authentication');
        checkAuth();

        const interval = setInterval(checkAuth, 60000);
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
        login, // Add login to context
        checkAuth,
        logout,
        refreshToken,
        subscriptionTier,
        setSubscriptionTier,
        fetchSubscriptionStatus,
    };

    return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export const useAuth = () => {
    const context = useContext(AuthContext);
    if (!context) {
        throw new Error('useAuth must be used within an AuthProvider');
    }
    return context;
};