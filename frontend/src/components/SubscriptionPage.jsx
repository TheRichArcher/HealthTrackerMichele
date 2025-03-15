import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from './AuthProvider'; // Updated import
import '../styles/SubscriptionPage.css';

const API_BASE_URL = 'https://healthtrackermichele.onrender.com/api';

const SubscriptionPage = () => {
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const [subscriptionStatus, setSubscriptionStatus] = useState(null);
    const { isAuthenticated, checkAuth } = useAuth();
    const navigate = useNavigate();
    const location = useLocation();

    const initialPlan = location.state?.plan || 'paid';

    const fetchSubscriptionStatus = async () => {
        const token = localStorage.getItem('access_token');
        if (!token) {
            console.log('No access token available for subscription status');
            return;
        }

        try {
            const response = await axios.get(`${API_BASE_URL}/subscription/status`, {
                headers: { Authorization: `Bearer ${token}` },
            });
            setSubscriptionStatus(response.data.subscription_tier);
            console.log('Subscription status fetched:', response.data.subscription_tier);
        } catch (err) {
            console.error('Failed to fetch subscription status:', err);
            setError('Failed to load subscription status.');
        }
    };

    useEffect(() => {
        if (isAuthenticated) {
            fetchSubscriptionStatus();
        } else {
            console.log('Not authenticated, skipping subscription status fetch');
        }
    }, [isAuthenticated]);

    const upgradeSubscription = async (plan) => {
        setLoading(true);
        setError(null);
        const token = localStorage.getItem('access_token');

        if (!token) {
            setError('Authentication required. Please log in.');
            navigate('/auth');
            return;
        }

        try {
            const response = await axios.post(
                `${API_BASE_URL}/subscription/upgrade`,
                { plan },
                { headers: { Authorization: `Bearer ${token}` } }
            );
            window.location.href = response.data.checkout_url;
        } catch (err) {
            setError(err.response?.data?.error || 'Upgrade failed');
            console.error('Upgrade error:', err);
        } finally {
            setLoading(false);
        }
    };

    const confirmSubscription = useCallback(async (sessionId) => {
        const token = localStorage.getItem('access_token');
        if (!token) {
            setError('Authentication required. Please log in.');
            navigate('/auth');
            return;
        }

        try {
            const response = await axios.post(
                `${API_BASE_URL}/subscription/confirm`,
                { session_id: sessionId },
                { headers: { Authorization: `Bearer ${token}` } }
            );
            setSubscriptionStatus(response.data.subscription_tier);
            await checkAuth();
            navigate('/dashboard');
        } catch (err) {
            setError(err.response?.data?.error || 'Confirmation failed');
            console.error('Confirmation error:', err);
        }
    }, [checkAuth, navigate]);

    useEffect(() => {
        const sessionId = new URLSearchParams(location.search).get('session_id');
        if (sessionId) {
            confirmSubscription(sessionId);
        }
    }, [location, confirmSubscription]);

    useEffect(() => {
        if (isAuthenticated && initialPlan && !subscriptionStatus) {
            upgradeSubscription(initialPlan);
        }
    }, [isAuthenticated, initialPlan, subscriptionStatus]);

    if (!isAuthenticated) {
        return <div className="subscription-container">Please log in to manage your subscription.</div>;
    }

    return (
        <div className="subscription-container">
            <h2>Upgrade Your Subscription</h2>
            {subscriptionStatus && (
                <p className="current-plan">Current Plan: {subscriptionStatus.toUpperCase()}</p>
            )}
            {error && <p className="error">{error}</p>}
            <div className="subscription-buttons">
                <button
                    className="subscription-button"
                    onClick={() => upgradeSubscription('paid')}
                    disabled={loading || subscriptionStatus === 'paid'}
                >
                    {loading ? 'Processing...' : 'Upgrade to Premium ($9.99/month)'}
                </button>
                <button
                    className="subscription-button"
                    onClick={() => upgradeSubscription('one_time')}
                    disabled={loading || subscriptionStatus === 'one_time'}
                >
                    {loading ? 'Processing...' : 'One-Time Premium Report ($4.99)'}
                </button>
            </div>
        </div>
    );
};

export default SubscriptionPage;