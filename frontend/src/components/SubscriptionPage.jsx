import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import axios from 'axios';
import { useAuth } from './AuthProvider';
import { removeLocalStorageItem } from '../utils/utils';
import '../styles/SubscriptionPage.css';

const API_BASE_URL = 'https://healthtrackermichele.onrender.com/api';

const SubscriptionPage = () => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const { isAuthenticated, checkAuth } = useAuth();

  useEffect(() => {
    const urlParams = new URLSearchParams(location.search);
    const sessionId = urlParams.get('session_id');
    if (sessionId) {
      handleConfirmSubscription(sessionId);
    }
  }, [location]);

  const handleUpgrade = async (selectedPlan) => {
    setLoading(true);
    setError(null);
    setSuccess(false);

    try {
      await checkAuth();
      if (!isAuthenticated) {
        setError('Please log in to proceed with the upgrade.');
        setTimeout(() => navigate('/auth'), 2000);
        return;
      }

      const payload = { plan: selectedPlan };
      const response = await axios.post(
        `${API_BASE_URL}/subscription/upgrade`,
        payload,
        { withCredentials: true }
      );
      window.location.href = response.data.checkout_url;
    } catch (err) {
      console.error(`Error initiating ${selectedPlan} upgrade:`, err);
      setError(`Failed to initiate ${selectedPlan} upgrade. Please try again or contact support.`);
    } finally {
      setLoading(false);
    }
  };

  const handleConfirmSubscription = async (sessionId) => {
    setLoading(true);
    setError(null);
    setSuccess(false);

    try {
      const response = await axios.post(
        `${API_BASE_URL}/subscription/confirm`,
        { session_id: sessionId },
        { withCredentials: true }
      );
      const { report_url, access_token, plan: confirmedPlan } = response.data;

      if (access_token) {
        localStorage.setItem('access_token', access_token);
      }

      if (report_url) {
        localStorage.setItem('healthtracker_report_url', report_url);
        setSuccess(true);
        if (confirmedPlan === 'one_time') {
          removeLocalStorageItem('access_token');
          console.log('Cleared access_token from localStorage after one-time report purchase');
          setTimeout(() => navigate('/chat'), 2000);
        } else {
          setTimeout(() => navigate('/chat'), 2000);
        }
      } else {
        setError('Failed to confirm subscription. Please try again.');
      }
    } catch (err) {
      console.error('Error confirming subscription:', err);
      setError('Failed to confirm subscription. Please try again or contact support.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="subscription-page">
      <h2>Upgrade Your Plan</h2>
      {error && (
        <div className="error-message" role="alert">
          {error}
        </div>
      )}
      {success && (
        <div className="success-message" role="alert">
          Subscription confirmed! Redirecting to chat...
        </div>
      )}
      <div className="subscription-options">
        <div className="subscription-option">
          <h3>💎 Premium Access</h3>
          <p>$9.99/month</p>
          <ul>
            <li>Unlimited symptom checks</li>
            <li>Detailed health assessments</li>
            <li>Health monitoring dashboard</li>
            <li>Priority support</li>
          </ul>
          <button
            className="upgrade-button premium"
            onClick={() => handleUpgrade('subscription')}
            disabled={loading}
          >
            {loading ? 'Processing...' : 'Get Premium'}
          </button>
        </div>
        <div className="subscription-option">
          <h3>📄 One-time Report</h3>
          <p>$4.99</p>
          <ul>
            <li>Detailed analysis of your current condition</li>
            <li>One-time use</li>
            <li>Downloadable PDF report</li>
          </ul>
          <button
            className="upgrade-button report"
            onClick={() => handleUpgrade('one_time')}
            disabled={loading}
          >
            {loading ? 'Processing...' : 'Get Report'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default SubscriptionPage;