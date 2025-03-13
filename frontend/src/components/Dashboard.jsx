import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { getLocalStorageItem } from '../utils/utils';
import UpgradePrompt from './UpgradePrompt';
import '../styles/Dashboard.css';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'https://healthtrackermichele.onrender.com/api';
if (!import.meta.env.VITE_API_URL) {
    console.warn('VITE_API_URL not set in environment variables, using fallback URL');
}

const Dashboard = () => {
  const [userData, setUserData] = useState(null);
  const [subscriptionTier, setSubscriptionTier] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showLogoutConfirm, setShowLogoutConfirm] = useState(false);
  const navigate = useNavigate();
  const { isAuthenticated, isLoading, logout } = useAuth();

  const fetchData = async () => {
    if (!isAuthenticated) {
      navigate('/auth');
      return;
    }

    try {
      const token = getLocalStorageItem('access_token');
      const [userResponse, subResponse] = await Promise.all([
        axios.get(`${API_BASE_URL}/users/me`, {
          headers: { 'Authorization': `Bearer ${token}` }
        }),
        axios.get(`${API_BASE_URL}/subscription/status`, {
          headers: { 'Authorization': `Bearer ${token}` }
        })
      ]);

      setUserData(userResponse.data);
      setSubscriptionTier(subResponse.data.subscription_tier);
      setError(null);
    } catch (err) {
      console.error('Error fetching user data:', err);
      setError('Unable to load dashboard data. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!isLoading && isAuthenticated) {
      fetchData();
    }
  }, [isLoading, isAuthenticated]);

  const handleLogoutConfirm = () => {
    setShowLogoutConfirm(true);
  };

  const handleLogout = async () => {
    setShowLogoutConfirm(false);
    await logout();
    navigate('/auth');
  };

  const LogoutConfirmDialog = () => (
    <div className="modal-overlay">
      <div className="modal-content">
        <h3>Confirm Logout</h3>
        <p>Are you sure you want to log out?</p>
        <div className="modal-buttons">
          <button 
            onClick={handleLogout}
            className="btn btn-danger"
          >
            Yes, Logout
          </button>
          <button 
            onClick={() => setShowLogoutConfirm(false)}
            className="btn btn-secondary"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );

  if (isLoading) {
    return (
      <div className="loading">
        <div className="spinner"></div>
        <p>Loading dashboard...</p>
      </div>
    );
  }

  return (
    <div className="dashboard-container">
      <h1 className="dashboard-title">Dashboard</h1>

      {loading && (
        <div className="loading">
          <div className="spinner"></div>
          <p>Loading dashboard...</p>
        </div>
      )}

      {error && (
        <div className="error-container">
          <p className="error">{error}</p>
          <button 
            onClick={fetchData} 
            className="retry-button"
          >
            Retry
          </button>
        </div>
      )}

      {userData && (
        <div className="dashboard-content">
          <div className="welcome-section">
            <h2>Welcome, {userData.username}!</h2>
            <p>Account created: {new Date(userData.created_at).toLocaleDateString()}</p>
            <p>Subscription Tier: <strong>{subscriptionTier ? subscriptionTier.toUpperCase() : 'Loading...'}</strong></p>
          </div>

          <div className="actions-grid">
            <h2 className="section-title">Quick Actions</h2>
            <div className="button-grid">
              <button 
                onClick={() => navigate('/symptom-logger')} 
                className="action-button"
              >
                Log New Symptom
              </button>
              <button 
                onClick={() => navigate('/report')}
                className="action-button"
              >
                View Reports
              </button>
              <button 
                onClick={handleLogoutConfirm} 
                className="action-button logout-button"
              >
                Logout
              </button>
            </div>
          </div>

          {subscriptionTier === 'free' && (
            <UpgradePrompt
              condition="Your Plan"
              commonName="Free Tier"
              isMildCase={true}
              requiresUpgrade={true}
              onDismiss={() => console.log('Upgrade prompt dismissed')}
            />
          )}
        </div>
      )}

      {showLogoutConfirm && <LogoutConfirmDialog />}
    </div>
  );
};

export default Dashboard;