import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { useAuth } from './AuthProvider';
import { getLocalStorageItem } from '../utils/utils';
import '../styles/Dashboard.css';

const API_BASE_URL = 'https://healthtrackermichele.onrender.com/api';

const Dashboard = () => {
    const navigate = useNavigate();
    const { isAuthenticated, subscriptionTier, checkAuth, isLoggingOut } = useAuth();
    const [userData, setUserData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    const fetchData = useCallback(async () => {
        if (isLoggingOut) {
            setError('Currently logging out. Please wait.');
            return;
        }

        const isValid = await checkAuth();
        if (!isValid) {
            navigate('/auth');
            return;
        }

        try {
            const token = getLocalStorageItem('access_token');
            const [userResponse, subResponse] = await Promise.all([
                axios.get(`${API_BASE_URL}/users/me`, { headers: { 'Authorization': `Bearer ${token}` } }),
                axios.get(`${API_BASE_URL}/subscription/status`, { headers: { 'Authorization': `Bearer ${token}` } }),
            ]);

            setUserData(userResponse.data);
            setError(null);
        } catch (err) {
            console.error('Error fetching user data:', err);
            setError('Unable to load dashboard data. Please try again.');
            if (err.response?.status === 401) {
                navigate('/auth');
            }
        } finally {
            setLoading(false);
        }
    }, [navigate, checkAuth, isLoggingOut]);

    useEffect(() => {
        if (!isAuthenticated) {
            const verifyAuth = async () => {
                const isValid = await checkAuth();
                if (!isValid) {
                    navigate('/auth');
                    return;
                }
                fetchData();
            };
            verifyAuth();
        } else {
            fetchData();
        }
    }, [isAuthenticated, navigate, fetchData, checkAuth]);

    if (loading) {
        return <div className="dashboard-loading">Loading dashboard...</div>;
    }

    if (error) {
        return (
            <div className="dashboard-error">
                <p>{error}</p>
                <button onClick={fetchData} className="retry-button">Retry</button>
            </div>
        );
    }

    return (
        <div className="dashboard-container">
            <h1>Dashboard</h1>
            {userData && (
                <div className="user-info">
                    <h2>Welcome, {userData.name || 'User'}</h2>
                    <p>Email: {userData.email}</p>
                    <p>Subscription Tier: {subscriptionTier || 'Not available'}</p>
                </div>
            )}
            <div className="dashboard-actions">
                <button onClick={() => navigate('/symptom-logger')} className="action-button">
                    Log Symptoms
                </button>
                <button onClick={() => navigate('/report')} className="action-button">
                    Generate Report
                </button>
                <button onClick={() => navigate('/chat')} className="action-button">
                    Chat with AI
                </button>
            </div>
        </div>
    );
};

export default Dashboard;