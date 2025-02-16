import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { getLocalStorageItem, removeLocalStorageItem, setLocalStorageItem } from '../utils/utils';
import axios from 'axios';

// API URL handling with warning for missing environment variable
const API_BASE_URL = import.meta.env.VITE_API_URL || 'https://healthtrackerai.pythonanywhere.com/api';
if (!import.meta.env.VITE_API_URL) {
    console.warn('VITE_API_URL not set in environment variables, using fallback URL');
}

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
    const [isAuthenticated, setIsAuthenticated] = useState(false);
    const [isLoading, setIsLoading] = useState(true);

    const refreshAccessToken = async (refreshToken) => {
        try {
            const response = await axios.post(`${API_BASE_URL}/auth/refresh`, {
                refresh_token: refreshToken
            });

            if (response.data && response.data.access_token) {
                setLocalStorageItem('access_token', response.data.access_token);
                return true;
            }
            return false;
        } catch (error) {
            console.error('Token refresh failed:', error);
            return false;
        }
    };

    const validateToken = async (token, isRetry = false) => {
        if (!token) return false;

        try {
            const response = await axios.get(`${API_BASE_URL}/auth/validate`, {
                headers: {
                    'Authorization': `Bearer ${token}`
                }
            });
            return response.status === 200;
        } catch (error) {
            if (error.response?.status === 401 && !isRetry) {
                // Token expired, try to refresh
                const refreshToken = getLocalStorageItem('refresh_token');
                if (refreshToken) {
                    const refreshSuccess = await refreshAccessToken(refreshToken);
                    if (refreshSuccess) {
                        // Retry validation with new token
                        const newToken = getLocalStorageItem('access_token');
                        if (!newToken) return false; // Explicit check for new token
                        return await validateToken(newToken, true);
                    }
                }
            }
            return false; // Explicit return false for all other cases
        }
    };

    const checkAuth = useCallback(async () => {
        const accessToken = getLocalStorageItem('access_token');
        const userId = getLocalStorageItem('user_id');

        // Simple check for required tokens
        if (!accessToken || !userId) {
            setIsAuthenticated(false);
            setIsLoading(false);
            return;
        }

        // Single validation call that handles refresh internally
        const isValid = await validateToken(accessToken);
        setIsAuthenticated(isValid);
        setIsLoading(false);
    }, []);

    const logout = useCallback(async () => {
        // Immediate UI update
        setIsAuthenticated(false);
        setIsLoading(true);

        // Get token before clearing storage
        const token = getLocalStorageItem('access_token');

        // Clear all auth-related data immediately
        removeLocalStorageItem('access_token');
        removeLocalStorageItem('refresh_token');
        removeLocalStorageItem('user_id');
        removeLocalStorageItem('lastPath');

        // Only attempt server logout if we have a token
        if (token) {
            try {
                await axios.post(`${API_BASE_URL}/logout`, {}, {
                    headers: {
                        'Authorization': `Bearer ${token}`
                    }
                });
            } catch (error) {
                // Log but don't handle - local logout is already complete
                console.error('Server logout notification failed:', error);
            }
        }

        setIsLoading(false);
    }, []);

    useEffect(() => {
        // Initial auth check
        checkAuth();

        // Periodic auth check every 60 seconds
        const interval = setInterval(checkAuth, 60000);

        // Handle storage changes across tabs
        const handleStorageChange = (e) => {
            if (['access_token', 'refresh_token', 'user_id'].includes(e.key)) {
                checkAuth();
            }
        };

        // Handle visibility changes
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
            window.removeEventListener('storage', handleStorageChange);
            document.removeEventListener('visibilitychange', handleVisibilityChange);
            window.removeEventListener('focus', checkAuth);
        };
    }, [checkAuth]);

    const value = {
        isAuthenticated,
        isLoading,
        checkAuth,
        logout
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