// src/components/UpgradePrompt.jsx
import React, { useState, useEffect, memo } from 'react';
import PropTypes from 'prop-types';
import '../styles/UpgradePrompt.css';

const UpgradePrompt = ({ condition, commonName, isMildCase, requiresUpgrade, onDismiss }) => {
  const [loadingSubscription, setLoadingSubscription] = useState(false);
  const [loadingOneTime, setLoadingOneTime] = useState(false);

  // Create a display name combining common and medical terms
  const displayName = commonName ? `${commonName} (${condition})` : condition;

  // Log props for debugging and scroll to "Maybe Later" if present
  useEffect(() => {
    console.log("UpgradePrompt Loaded with Props:", {
      condition,
      commonName,
      isMildCase,
      requiresUpgrade,
    });

    if (isMildCase) {
      const timeoutId = setTimeout(() => {
        document.querySelector('.continue-free-button')?.scrollIntoView({ behavior: 'smooth' });
      }, 100);
      return () => clearTimeout(timeoutId); // Cleanup timeout on unmount
    }
  }, [condition, commonName, isMildCase, requiresUpgrade]);

  // Handle upgrade button clicks with loading state and navigation
  const handleSubscriptionClick = () => {
    if (loadingSubscription || loadingOneTime) return;
    setLoadingSubscription(true);
    setTimeout(() => {
      window.location.href = '/subscribe';
    }, 300);
  };

  const handleOneTimeClick = () => {
    if (loadingSubscription || loadingOneTime) return;
    setLoadingOneTime(true);
    setTimeout(() => {
      window.location.href = '/one-time-report';
    }, 300);
  };

  return (
    <div className="upgrade-options-inline" role="dialog" aria-labelledby="upgrade-title">
      <h3 id="upgrade-title">
        I’ve identified <strong>{displayName}</strong> as a possible condition based on your symptoms.
      </h3>

      {isMildCase && (
        <p className="mild-case-note">
          Good news—it looks like you can manage this at home! If you’d like more details, upgrading can help.
        </p>
      )}
      {!isMildCase && (
        <p>
          To get a deeper understanding and the best next steps, here are your options:
        </p>
      )}

      <ul className="premium-features-list" aria-label="Upgrade options">
        <li>
          <span className="feature-name">🔹 Premium Access ($9.99/month)</span>
          <span
            className="tooltip-icon"
            title="Get deeper insights, track symptoms, and receive doctor-ready reports"
            aria-label="Premium feature details"
          >
            ⓘ
          </span>
          <span className="feature-description">
            Unlimited symptom checks, detailed assessments, and personalized health monitoring.
          </span>
        </li>
        <li>
          <span className="feature-name">🔹 One-time Consultation Report ($4.99)</span>
          <span
            className="tooltip-icon"
            title="A comprehensive report you can share with your doctor"
            aria-label="One-time report details"
          >
            ⓘ
          </span>
          <span className="feature-description">
            A detailed analysis of your current symptoms.
          </span>
        </li>
      </ul>

      <p>Ready to unlock more insights?</p>
      <div className="upgrade-buttons">
        <button
          className={`upgrade-button subscription ${loadingSubscription ? 'loading' : ''}`}
          onClick={handleSubscriptionClick}
          disabled={loadingSubscription || loadingOneTime}
          aria-busy={loadingSubscription}
          aria-label="Subscribe to Premium Access for $9.99 per month"
        >
          {loadingSubscription ? 'Processing...' : '🩺 Get Premium Access ($9.99/month)'}
        </button>
        <button
          className={`upgrade-button one-time ${loadingOneTime ? 'loading' : ''}`}
          onClick={handleOneTimeClick}
          disabled={loadingSubscription || loadingOneTime}
          aria-busy={loadingOneTime}
          aria-label="Get a one-time consultation report for $4.99"
        >
          {loadingOneTime ? 'Processing...' : '📄 Get Consultation Report ($4.99)'}
        </button>

        {isMildCase && (
          <button
            className="continue-free-button"
            onClick={onDismiss}
            aria-label="Continue with free version"
          >
            Maybe Later
          </button>
        )}
      </div>
    </div>
  );
};

// PropTypes for type checking
UpgradePrompt.propTypes = {
  condition: PropTypes.string.isRequired,
  commonName: PropTypes.string,
  isMildCase: PropTypes.bool.isRequired,
  requiresUpgrade: PropTypes.bool,
  onDismiss: PropTypes.func.isRequired,
};

// Memoize to prevent unnecessary re-renders
export default memo(UpgradePrompt);