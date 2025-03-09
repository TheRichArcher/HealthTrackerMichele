// src/components/UpgradePrompt.jsx
import React, { useState, useEffect, memo } from 'react';
import PropTypes from 'prop-types';
import '../styles/UpgradePrompt.css';

const UpgradePrompt = ({ condition, commonName, isMildCase, requiresUpgrade, confidence, triageLevel, recommendation, onDismiss }) => {
  const [loadingSubscription, setLoadingSubscription] = useState(false);
  const [loadingOneTime, setLoadingOneTime] = useState(false);

  const displayName = commonName ? `${commonName} (${condition})` : condition;

  useEffect(() => {
    console.log("UpgradePrompt Props:", { condition, commonName, isMildCase, requiresUpgrade, confidence, triageLevel, recommendation });
    if (isMildCase) {
      document.querySelector('.continue-free-button')?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [condition, commonName, isMildCase, requiresUpgrade, confidence, triageLevel, recommendation]);

  const handleSubscriptionClick = () => {
    if (loadingSubscription || loadingOneTime) return;
    setLoadingSubscription(true);
    setTimeout(() => { window.location.href = '/subscribe'; }, 300);
  };

  const handleOneTimeClick = () => {
    if (loadingSubscription || loadingOneTime) return;
    setLoadingOneTime(true);
    setTimeout(() => { window.location.href = '/one-time-report'; }, 300);
  };

  return (
    <div className="upgrade-options-inline" role="dialog" aria-labelledby="upgrade-title">
      <h3 id="upgrade-title">
        I’ve identified <strong>{displayName}</strong> as a possible condition.
      </h3>
      {confidence && (
        <p>Confidence: <strong>{confidence}%</strong></p>
      )}
      {triageLevel && (
        <p>Severity: <strong>{triageLevel}</strong></p>
      )}
      {recommendation && (
        <p>Recommendation: <strong>{recommendation}</strong></p>
      )}
      {isMildCase ? (
        <p className="mild-case-note">
          Good news—it looks manageable at home! Upgrade for detailed insights.
        </p>
      ) : (
        <p>
          For deeper analysis and next steps, consider upgrading:
        </p>
      )}
      <ul className="premium-features-list" aria-label="Upgrade options">
        <li>
          <span className="feature-name">🔹 Premium Access ($9.99/month)</span>
          <span className="feature-description">
            Unlimited checks, detailed assessments, and health monitoring.
          </span>
        </li>
        <li>
          <span className="feature-name">🔹 One-time Report ($4.99)</span>
          <span className="feature-description">
            A detailed analysis of your current condition.
          </span>
        </li>
      </ul>
      <p>Ready to unlock more?</p>
      <div className="upgrade-buttons">
        <button
          className={`upgrade-button subscription ${loadingSubscription ? 'loading' : ''}`}
          onClick={handleSubscriptionClick}
          disabled={loadingSubscription || loadingOneTime}
          aria-busy={loadingSubscription}
        >
          {loadingSubscription ? 'Processing...' : '🩺 Get Premium ($9.99/month)'}
        </button>
        <button
          className={`upgrade-button one-time ${loadingOneTime ? 'loading' : ''}`}
          onClick={handleOneTimeClick}
          disabled={loadingSubscription || loadingOneTime}
          aria-busy={loadingOneTime}
        >
          {loadingOneTime ? 'Processing...' : '📄 Get Report ($4.99)'}
        </button>
        {isMildCase && (
          <button className="continue-free-button" onClick={onDismiss}>
            Maybe Later
          </button>
        )}
      </div>
    </div>
  );
};

UpgradePrompt.propTypes = {
  condition: PropTypes.string.isRequired,
  commonName: PropTypes.string,
  isMildCase: PropTypes.bool.isRequired,
  requiresUpgrade: PropTypes.bool,
  confidence: PropTypes.number,
  triageLevel: PropTypes.string,
  recommendation: PropTypes.string,
  onDismiss: PropTypes.func.isRequired,
};

export default memo(UpgradePrompt);