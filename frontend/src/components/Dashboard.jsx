import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { getLocalStorageItem } from '../utils/utils';

// API URL handling with warning for missing environment variable
const API_BASE_URL = import.meta.env.VITE_API_URL || 'https://healthtrackermichele.onrender.com/api';
if (!import.meta.env.VITE_API_URL) {
    console.warn('VITE_API_URL not set in environment variables, using fallback URL');
}

const Dashboard = () => {
  const [userData, setUserData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showLogoutConfirm, setShowLogoutConfirm] = useState(false);
  const navigate = useNavigate();
  const { isAuthenticated, isLoading, logout } = useAuth();

  const fetchUserData = async () => {
    if (!isAuthenticated) {
      navigate('/login');
      return;
    }

    try {
      const token = getLocalStorageItem('access_token');
      const response = await axios.get(`${API_BASE_URL}/users/me`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });

      setUserData(response.data);
      setError(null);
    } catch (err) {
      console.error('Error fetching user data:', err);
      setError('Unable to load dashboard data. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    // Only fetch user data if authentication check is complete and user is authenticated
    if (!isLoading && isAuthenticated) {
      fetchUserData();
    }
  }, [isLoading, isAuthenticated]); // Dependencies now include both auth states

  const handleLogoutConfirm = () => {
    setShowLogoutConfirm(true);
  };

  const handleLogout = async () => {
    setShowLogoutConfirm(false);
    await logout();
    navigate('/login');
  };

  const LogoutConfirmDialog = () => (
    <div style={styles.modalOverlay}>
      <div style={styles.modalContent}>
        <h3>Confirm Logout</h3>
        <p>Are you sure you want to log out?</p>
        <div style={styles.modalButtons}>
          <button 
            onClick={handleLogout}
            style={{...styles.actionButton, ...styles.logoutButton}}
          >
            Yes, Logout
          </button>
          <button 
            onClick={() => setShowLogoutConfirm(false)}
            style={styles.cancelButton}
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );

  // Show loading state while authentication is being checked
  if (isLoading) {
    return (
      <div style={styles.loading}>
        <div style={styles.spinner}></div>
        <p>Loading dashboard...</p>
      </div>
    );
  }

  return (
    <div className="dashboard-container" style={styles.container}>
      <h1 style={styles.title}>Dashboard</h1>

      {loading && (
        <div style={styles.loading}>
          <div style={styles.spinner}></div>
          <p>Loading dashboard...</p>
        </div>
      )}

      {error && (
        <div style={styles.errorContainer}>
          <p style={styles.error}>{error}</p>
          <button 
            onClick={fetchUserData} 
            style={styles.retryButton}
          >
            Retry
          </button>
        </div>
      )}

      {userData && (
        <div style={styles.content}>
          <div style={styles.welcomeSection}>
            <h2>Welcome, {userData.username}!</h2>
            <p>Account created: {new Date(userData.created_at).toLocaleDateString()}</p>
          </div>

          <div style={styles.actionsGrid}>
            <h2 style={styles.sectionTitle}>Quick Actions</h2>
            <div style={styles.buttonGrid}>
              <button 
                onClick={() => navigate('/symptom-logger')} 
                style={styles.actionButton}
              >
                Log New Symptom
              </button>
              <button 
                onClick={() => navigate('/reports')} 
                style={styles.actionButton}
              >
                View Reports
              </button>
              <button 
                onClick={handleLogoutConfirm} 
                style={{...styles.actionButton, ...styles.logoutButton}}
              >
                Logout
              </button>
            </div>
          </div>
        </div>
      )}

      {showLogoutConfirm && <LogoutConfirmDialog />}
    </div>
  );
};

// Styles remain exactly the same...

export default Dashboard;
