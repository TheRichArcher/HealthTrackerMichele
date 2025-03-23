import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { useAuth } from './AuthProvider';
import PropTypes from 'prop-types';
import '../styles/UpgradePrompt.css';

const API_BASE_URL = 'https://healthtrackermichele.onrender.com/api';

const UpgradePrompt = ({
  text, // Added to match Chat.jsx's displayText
  careRecommendation,
  triageLevel,
  onReport,
  onSubscribe,
  onNotNow,
  requiresUpgrade,
  assessmentId,
  assessmentData,
  condition,
  commonName,
  isMildCase,
  onDismiss,
  onUpgradeAction, // Added to match Chat.jsx's onUpgradeAction
}) => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(false);
  const [showFeatures, setShowFeatures] = useState(false);
  const [showConfirmModal, setShowConfirmModal] = useState(false);
  const [pendingAction, setPendingAction] = useState(null);
  const { isAuthenticated, checkAuth } = useAuth();
  const navigate = useNavigate();

  // Use fallbacks from SymptomLogger if careRecommendation/triageLevel are missing
  const effectiveRecommendation = careRecommendation || condition || 'Consider consulting a healthcare provider.';
  const effectiveTriageLevel = triageLevel || (commonName ? 'MODERATE' : 'AT_HOME') || 'MODERATE';
  const effectiveRequiresUpgrade = requiresUpgrade || (commonName && isMildCase !== undefined);

  useEffect(() => {
    setSuccess(false);
    setError(null);
    setLoading(false);
    setShowConfirmModal(false);
    setPendingAction(null);
    checkAuth();
  }, [careRecommendation, triageLevel, requiresUpgrade, assessmentId, condition, commonName, checkAuth]);

  const premiumFeatures = [
    { name: 'Detailed Assessments', description: 'Get in-depth analysis...', tooltip: 'Includes medical terms...' },
    { name: 'Doctor’s Report', description: 'Receive a comprehensive report...', tooltip: 'PDF download...' },
    { name: 'Symptom History', description: 'Track all your past symptom logs...', tooltip: 'Access your health history...' },
    { name: 'Priority Support', description: 'Get faster responses...', tooltip: 'Email and chat support...' },
  ];

  const validateAssessmentData = () => {
    if (assessmentData && typeof assessmentData === 'object') {
      return {
        condition_common: assessmentData.condition || 'Unknown',
        condition_medical: assessmentData.condition_medical || 'N/A',
        confidence: parseFloat(assessmentData.confidence) || 0,
        triage_level: assessmentData.triageLevel || 'MODERATE',
        care_recommendation: assessmentData.recommendation || 'Consult a healthcare provider',
      };
    }
    return {
      condition_common: 'Unknown',
      condition_medical: 'N/A',
      confidence: 0,
      triage_level: 'MODERATE',
      care_recommendation: 'Consult a healthcare provider',
    };
  };

  const initiateUpgrade = (plan) => {
    setLoading(true);
    setError(null);
    setSuccess(false);

    const payload = isAuthenticated
      ? { plan, assessment_id: assessmentId }
      : { plan, assessment_data: validateAssessmentData() };

    axios.post(`${API_BASE_URL}/subscription/upgrade`, payload, { withCredentials: true })
      .then(response => {
        console.log(`Redirecting to Stripe for ${plan}:`, response.data.checkout_url);
        window.location.href = response.data.checkout_url;
      })
      .catch(err => {
        console.error(`Error initiating ${plan} purchase:`, err);
        setError(`Failed to initiate ${plan} purchase. Please try again or contact support.`);
      })
      .finally(() => setLoading(false));
  };

  const confirmAction = (action) => {
    setPendingAction(action);
    setShowConfirmModal(true);
  };

  const handleConfirm = () => {
    if (pendingAction === 'report') {
      if (onReport) onReport();
      if (onUpgradeAction) onUpgradeAction('report');
      else initiateUpgrade('one_time');
    } else if (pendingAction === 'subscribe') {
      if (onSubscribe) onSubscribe();
      if (onUpgradeAction) onUpgradeAction('premium');
      else initiateUpgrade('subscription');
    }
    setShowConfirmModal(false);
    setPendingAction(null);
  };

  const handleNotNowClick = () => {
    if (onNotNow) onNotNow();
    if (onDismiss) onDismiss();
    if (onUpgradeAction) onUpgradeAction('later');
    setSuccess(true);
  };

  const toggleFeatures = () => setShowFeatures(!showFeatures);

  const LoadingSpinner = () => (
    <div className="custom-spinner">
      <svg width="24" height="24" viewBox="0 0 24 24">
        <circle cx="12" cy="12" r="10" stroke="#4285f4" strokeWidth="2" fill="none" strokeDasharray="31.415" strokeDashoffset="10">
          <animateTransform attributeName="transform" type="rotate" from="0 12 12" to="360 12 12" dur="1s" repeatCount="indefinite" />
        </circle>
      </svg>
    </div>
  );

  return (
    <div className="message bot upgrade-options">
      <div className="message-content">
        <p className="upgrade-intro">{text || (effectiveRequiresUpgrade ? 'Upgrade Required for Full Insights' : 'Unlock Detailed Health Insights')}</p>
        {error && (
          <div className="error-message" role="alert">
            {error}
            <button className="retry-button" onClick={() => confirmAction(pendingAction)}>Retry</button>
          </div>
        )}
        {success && <div className="success-message" role="alert">Noted. Reach out anytime for more insights!</div>}
        <p><strong>Recommendation:</strong> {effectiveRecommendation}</p>
        <p><strong>Triage Level:</strong> {effectiveTriageLevel}</p>
        {effectiveTriageLevel === 'AT_HOME' && !effectiveRequiresUpgrade && (
          <div className="mild-case-note">This appears to be a mild case... Continue monitoring your symptoms.</div>
        )}
        {effectiveRequiresUpgrade && (
          <p>Your assessment indicates a {effectiveTriageLevel.toLowerCase()} condition. Upgrade to access detailed insights.</p>
        )}
        <div className="upgrade-options-container">
          <button
            className="upgrade-button toggle-features"
            onClick={toggleFeatures}
            aria-expanded={showFeatures}
            aria-controls="premium-features"
          >
            {showFeatures ? 'Hide Premium Features' : 'Show Premium Features'}
          </button>
          {showFeatures && (
            <ul id="premium-features" className="premium-features-list">
              {premiumFeatures.map((feature, index) => (
                <li key={index}>
                  <span className="feature-name">{feature.name}</span>
                  <span className="tooltip-icon" title={feature.tooltip} aria-label={`Tooltip: ${feature.tooltip}`}>
                    ?
                  </span>
                  <span className="feature-description">{feature.description}</span>
                </li>
              ))}
            </ul>
          )}
          <div className="upgrade-options-container">
            <div className="upgrade-option">
              <h4>💎 Premium Access ($9.99/month)</h4>
              <p>Unlimited checks, detailed assessments, and health monitoring.</p>
            </div>
            <div className="upgrade-option">
              <h4>📄 One-time Report ($4.99)</h4>
              <p>A detailed analysis of your current condition.</p>
            </div>
            <div className="upgrade-buttons">
              <button
                className={`upgrade-button one-time ${loading ? 'loading' : ''}`}
                onClick={() => confirmAction('report')}
                disabled={loading}
                aria-label="Purchase a one-time report for $4.99"
              >
                {loading ? <LoadingSpinner /> : 'Get Report ($4.99)'}
              </button>
              <button
                className={`upgrade-button subscription ${loading ? 'loading' : ''}`}
                onClick={() => confirmAction('subscribe')}
                disabled={loading}
                aria-label="Subscribe for $9.99 per month (requires login)"
              >
                {loading ? <LoadingSpinner /> : 'Get Premium ($9.99/month)'}
              </button>
              {isMildCase && (
                <button
                  className="upgrade-button maybe-later"
                  onClick={handleNotNowClick}
                  disabled={loading}
                  aria-label="Maybe Later - Continue without upgrading"
                >
                  Maybe Later
                </button>
              )}
            </div>
          </div>
        </div>
        {showConfirmModal && (
          <div className="confirm-modal">
            <div className="modal-content">
              <h4>Confirm Action</h4>
              <p>
                Are you sure you want to{' '}
                {pendingAction === 'report' ? 'purchase a one-time report for $4.99' : 'subscribe for $9.99/month'}?
              </p>
              <div className="modal-buttons">
                <button className="confirm-button" onClick={handleConfirm} disabled={loading}>
                  {loading ? <LoadingSpinner /> : 'Yes'}
                </button>
                <button
                  className="cancel-button"
                  onClick={() => setShowConfirmModal(false)}
                  disabled={loading}
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

UpgradePrompt.propTypes = {
  text: PropTypes.string, // Added to match Chat.jsx
  careRecommendation: PropTypes.string,
  triageLevel: PropTypes.oneOf(['AT_HOME', 'MODERATE', 'SEVERE']),
  onReport: PropTypes.func,
  onSubscribe: PropTypes.func,
  onNotNow: PropTypes.func,
  requiresUpgrade: PropTypes.bool,
  assessmentId: PropTypes.number,
  assessmentData: PropTypes.shape({
    condition: PropTypes.string,
    confidence: PropTypes.number,
    triageLevel: PropTypes.string,
    recommendation: PropTypes.string,
    assessmentId: PropTypes.number,
  }),
  condition: PropTypes.string,
  commonName: PropTypes.string,
  isMildCase: PropTypes.bool,
  onDismiss: PropTypes.func,
  onUpgradeAction: PropTypes.func, // Added to match Chat.jsx
};

UpgradePrompt.defaultProps = {
  text: 'Ready to unlock more?', // Added to match Chat.jsx
  careRecommendation: null,
  triageLevel: null,
  onReport: () => {},
  onSubscribe: () => {},
  onNotNow: () => {},
  requiresUpgrade: false,
  assessmentId: null,
  assessmentData: null,
  condition: null,
  commonName: null,
  isMildCase: false,
  onDismiss: () => {},
  onUpgradeAction: () => {}, // Added to match Chat.jsx
};

export default UpgradePrompt;