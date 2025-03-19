import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from './AuthProvider';
import axios from 'axios';
import '../styles/SubscriptionPage.css';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'https://healthtrackermichele.onrender.com/api';

const SubscriptionPage = () => {
  const [subscriptionStatus, setSubscriptionStatus] = useState(null);
  const [error, setError] = useState(null);
  const { isAuthenticated, checkAuth } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const upgradeSubscription = useCallback(async (plan) => {
    try {
      const token = localStorage.getItem('access_token') || '';
      const response = await axios.post(
        `${API_BASE_URL}/subscription/upgrade`,
        { plan },
        {
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`,
          },
          withCredentials: true,
        }
      );
      if (response.data.checkout_url) {
        window.location.href = response.data.checkout_url;
      } else {
        setError('Failed to initiate subscription upgrade');
      }
    } catch (err) {
      setError(err.response?.data?.error || 'Upgrade request failed');
    }
  }, []);

  const confirmSubscription = useCallback(async (sessionId) => {
    try {
      const token = localStorage.getItem('access_token') || '';
      const response = await axios.post(
        `${API_BASE_URL}/subscription/confirm`,
        { session_id: sessionId },
        {
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`,
          },
          withCredentials: true,
        }
      );
      setSubscriptionStatus(response.data.subscription_tier);
      // Store access_token if provided (for unauthenticated users)
      if (response.data.access_token) {
        localStorage.setItem('access_token', response.data.access_token);
      }
      // Persist report_url in localStorage for later access
      if (response.data.report_url) {
        localStorage.setItem('healthtracker_report_url', response.data.report_url);
      }
      // Redirect to chat with report_url in state
      navigate('/chat', { state: { reportUrl: response.data.report_url } });
    } catch (err) {
      setError(err.response?.data?.error || 'Confirmation failed');
      navigate('/auth');
    }
  }, [navigate]);

  useEffect(() => {
    const searchParams = new URLSearchParams(location.search);
    const sessionId = searchParams.get('session_id');
    if (sessionId) {
      confirmSubscription(sessionId);
    }
  }, [location.search, confirmSubscription]);

  useEffect(() => {
    if (isAuthenticated) {
      checkAuth();
    }
  }, [isAuthenticated, checkAuth]);

  return (
    <div className="subscription-page">
      <h1>Subscription</h1>
      {error && <div className="error-message" role="alert">{error}</div>}
      {subscriptionStatus ? (
        <div className="subscription-status">
          <h2>Subscription Status: {subscriptionStatus}</h2>
          <p>
            {subscriptionStatus === 'paid'
              ? 'You now have unlimited access to all features!'
              : 'Your one-time report is being prepared.'}
          </p>
        </div>
      ) : (
        <div className="subscription-options">
          <h2>Choose Your Plan</h2>
          <div className="plan-option">
            <h3>Premium Access ($9.99/month)</h3>
            <p>Unlimited checks, detailed assessments, and health monitoring.</p>
            <button onClick={() => upgradeSubscription('premium')}>
              Upgrade to Premium
            </button>
          </div>
          <div className="plan-option">
            <h3>One-time Report ($4.99)</h3>
            <p>A detailed analysis of your current condition.</p>
            <button onClick={() => upgradeSubscription('one_time')}>
              Get One-time Report
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default SubscriptionPage;