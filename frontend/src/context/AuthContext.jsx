import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { getLocalStorageItem, removeLocalStorageItem, setLocalStorageItem } from '../utils/utils';
import axios from 'axios';

// API URL handling with warning for missing environment variable
const API_BASE_URL = import.meta.env.VITE_API_URL || 'https://healthtrackermichele.onrender.com/api';
if (!import.meta.env.VITE_API_URL) {
    console.warn('VITE_API_URL not set in environment variables, using fallback URL');
}

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
    const [isAuthenticated, setIsAuthenticated] = useState(false);
    const [isLoading, setIsLoading] = useState(true);
    const [subscriptionTier, setSubscriptionTier] = useState(null);

    const refreshToken = useCallback(async () => {
        const refreshTokenValue = getLocalStorageItem('refresh_token');
        if (!refreshTokenValue) {
            throw new Error('No refresh token available');
        }

        try {
            const response = await axios.post(`${API_BASE_URL}/auth/refresh/`, {
                refresh_token: refreshTokenValue
            });

            if (response.data && response.data.access_token) {
                setLocalStorageItem('access_token', response.data.access_token);
                if (response.data.refresh_token) {
                    setLocalStorageItem('refresh_token', response.data.refresh_token);
                }
                return true;
            }
            throw new Error('Invalid refresh token response');
        } catch (error) {
            console.error('Token refresh failed:', error);
            // Clear tokens on refresh failure
            removeLocalStorageItem('access_token');
            removeLocalStorageItem('refresh_token');
            setIsAuthenticated(false);
            throw error;
        }
    }, []);

    const validateToken = async (token, isRetry = false) => {
        if (!token) return false;

        try {
            // Fixed: Added trailing slash to match backend route
            const response = await axios.get(`${API_BASE_URL}/auth/validate/`, {
                headers: {
                    'Authorization': `Bearer ${token}`
                }
            });
            return response.status === 200;
        } catch (error) {
            if (error.response?.status === 401 && !isRetry) {
                try {
                    await refreshToken();
                    const newToken = getLocalStorageItem('access_token');
                    if (!newToken) return false;
                    return await validateToken(newToken, true);
                } catch (refreshError) {
                    return false;
                }
            }
            return false;
        }
    };

    const fetchSubscriptionStatus = useCallback(async () => {
        if (!isAuthenticated) return;
        
        try {
            const token = getLocalStorageItem('access_token');
            const response = await axios.get(`${API_BASE_URL}/subscription/status`, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            setSubscriptionTier(response.data.subscription_tier);
        } catch (err) {
            console.error('Failed to fetch subscription status:', err);
        }
    }, [isAuthenticated]);

    const checkAuth = useCallback(async () => {
        const accessToken = getLocalStorageItem('access_token');
        const userId = getLocalStorageItem('user_id');

        if (!accessToken || !userId) {
            setIsAuthenticated(false);
            setIsLoading(false);
            return;
        }

        try {
            const isValid = await validateToken(accessToken);
            setIsAuthenticated(isValid);
            if (isValid) {
                fetchSubscriptionStatus();
            }
        } catch (error) {
            setIsAuthenticated(false);
        } finally {
            setIsLoading(false);
        }
    }, [fetchSubscriptionStatus]);

    const logout = useCallback(async () => {
        setIsLoading(true);
        
        const token = getLocalStorageItem('access_token');

        if (token) {
            try {
                // Fixed: Added trailing slash to match backend route
                await axios.post(`${API_BASE_URL}/logout/`, {}, {
                    headers: {
                        'Authorization': `Bearer ${token}`
                    }
                });
            } catch (error) {
                console.error('Server logout notification failed:', error);
            }
        }

        // Clear all auth-related items from localStorage
        removeLocalStorageItem('access_token');
        removeLocalStorageItem('refresh_token');
        removeLocalStorageItem('user_id');
        removeLocalStorageItem('lastPath');
        
        setIsAuthenticated(false);
        setSubscriptionTier(null);
        setIsLoading(false);
    }, []);

    useEffect(() => {
        checkAuth();

        // Check authentication status periodically
        const interval = setInterval(checkAuth, 60000); // Every minute

        // Handle storage changes (for multi-tab support)
        const handleStorageChange = (e) => {
            if (['access_token', 'refresh_token', 'user_id'].includes(e.key)) {
                checkAuth();
            }
        };

        // Check auth when tab becomes visible again
        const handleVisibilityChange = () => {
            if (document.visibilityState === 'visible') {
                checkAuth();
            }
        };

        // Add event listeners
        window.addEventListener('storage', handleStorageChange);
        document.addEventListener('visibilitychange', handleVisibilityChange);
        window.addEventListener('focus', checkAuth);

        // Cleanup event listeners and interval
        return () => {
            clearInterval(interval);
            window.removeEventListener('storage', handleStorageChange);
            document.removeEventListener('visibilitychange', handleVisibilityChange);
            window.removeEventListener('focus', checkAuth);
        };
    }, [checkAuth]);

    const value = {
        isAuthenticated,
        isLoading,
        checkAuth,
        logout,
        refreshToken,
        subscriptionTier,
        setSubscriptionTier,
        fetchSubscriptionStatus
    };

    return (
        <AuthContext.Provider value={value}>
            {children}
        </AuthContext.Provider>
    );
};

export const useAuth = () => {
    const context = useContext(AuthContext);
    if (!context) {
        throw new Error('useAuth must be used within an AuthProvider');
    }
    return context;
};