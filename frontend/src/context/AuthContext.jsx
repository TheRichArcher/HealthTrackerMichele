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
            console.log('No refresh token available');
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
                console.log('Token refresh successful');
                return true;
            }
            console.log('Invalid refresh token response');
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
        if (!token) {
            console.log('No token provided for validation');
            return false;
        }

        try {
            // Fixed: Added trailing slash to match backend route
            const response = await axios.get(`${API_BASE_URL}/auth/validate/`, {
                headers: {
                    'Authorization': `Bearer ${token}`
                }
            });
            console.log('Token validation successful');
            return response.status === 200;
        } catch (error) {
            console.log('Token validation failed:', error.message);
            if (error.response?.status === 401 && !isRetry) {
                try {
                    console.log('Attempting token refresh');
                    await refreshToken();
                    const newToken = getLocalStorageItem('access_token');
                    if (!newToken) {
                        console.log('No new token after refresh');
                        return false;
                    }
                    return await validateToken(newToken, true);
                } catch (refreshError) {
                    console.error('Token refresh failed during validation:', refreshError);
                    return false;
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
            const response = await axios.get(`${API_BASE_URL}/subscription/status`, {
                headers: { 'Authorization': `Bearer ${token}` }
            });
            console.log('Subscription status fetched:', response.data.subscription_tier);
            setSubscriptionTier(response.data.subscription_tier);
        } catch (err) {
            console.error('Failed to fetch subscription status:', err);
        }
    }, [isAuthenticated]);

    const checkAuth = useCallback(async () => {
        const accessToken = getLocalStorageItem('access_token');
        const userId = getLocalStorageItem('user_id');

        console.log('Checking authentication...');
        console.log('Access token exists:', !!accessToken);
        console.log('User ID exists:', !!userId);

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
                fetchSubscriptionStatus();
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

    const logout = useCallback(async () => {
        setIsLoading(true);
        console.log('Logging out...');
        
        const token = getLocalStorageItem('access_token');

        if (token) {
            try {
                // Fixed: Added trailing slash to match backend route
                await axios.post(`${API_BASE_URL}/logout/`, {}, {
                    headers: {
                        'Authorization': `Bearer ${token}`
                    }
                });
                console.log('Server logout successful');
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
        console.log('Logout complete');
    }, []);

    useEffect(() => {
        console.log('AuthProvider mounted, checking authentication');
        checkAuth();

        // Check authentication status periodically
        const interval = setInterval(checkAuth, 60000); // Every minute

        // Handle storage changes (for multi-tab support)
        const handleStorageChange = (e) => {
            if (['access_token', 'refresh_token', 'user_id'].includes(e.key)) {
                console.log('Storage change detected for auth keys, rechecking auth');
                checkAuth();
            }
        };

        // Check auth when tab becomes visible again
        const handleVisibilityChange = () => {
            if (document.visibilityState === 'visible') {
                console.log('Tab became visible, rechecking auth');
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
            console.log('AuthProvider unmounted, cleaned up listeners');
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