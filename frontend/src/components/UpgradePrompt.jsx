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

  // Don’t render if neither requiresUpgrade nor isMildCase is true
  if (!requiresUpgrade && !isMildCase) {
    console.log("UpgradePrompt not rendering - no upgrade required and not a mild case");
    return null;
  }

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
        Based on your symptoms, I’ve identified{' '}
        <strong>{displayName}</strong> as a possible condition that may require further evaluation.
      </h3>

      {isMildCase && (
        <p className="mild-case-note">
          This appears to be a condition you can manage at home. You can continue with the free version, but upgrading offers detailed insights and tracking.
        </p>
      )}

      <p>To unlock more insights, choose an option below:</p>
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
            A comprehensive analysis of your current symptoms.
          </span>
        </li>
      </ul>

      <p>Would you like to proceed with one of these options?</p>
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