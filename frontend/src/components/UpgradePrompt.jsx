import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { useAuth } from './AuthProvider';
import PropTypes from 'prop-types';
import '../styles/UpgradePrompt.css';

const API_BASE_URL = 'https://healthtrackermichele.onrender.com/api';

const UpgradePrompt = ({
    careRecommendation,
    triageLevel,
    onReport,
    onSubscribe,
    onNotNow,
    requiresUpgrade,
}) => {
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const [success, setSuccess] = useState(false);
    const [showFeatures, setShowFeatures] = useState(false);
    const [showConfirmModal, setShowConfirmModal] = useState(false);
    const [pendingAction, setPendingAction] = useState(null);
    const { isAuthenticated, checkAuth } = useAuth();
    const navigate = useNavigate();

    // Reset states on prop change or mount
    useEffect(() => {
        setSuccess(false);
        setError(null);
        setLoading(false);
        setShowConfirmModal(false);
        setPendingAction(null);
        checkAuth();
    }, [careRecommendation, triageLevel, requiresUpgrade, checkAuth]);

    // Define premium features with tooltips
    const premiumFeatures = [
        {
            name: 'Detailed Assessments',
            description: 'Get in-depth analysis of your symptoms with confidence scores and care recommendations.',
            tooltip: 'Includes medical terms, common names, and triage levels.',
        },
        {
            name: 'Doctor’s Report',
            description: 'Receive a comprehensive report formatted for sharing with healthcare providers.',
            tooltip: 'PDF download with detailed findings and recommendations.',
        },
        {
            name: 'Symptom History',
            description: 'Track all your past symptom logs and assessments in one place.',
            tooltip: 'Access your health history anytime with a premium account.',
        },
        {
            name: 'Priority Support',
            description: 'Get faster responses and dedicated support for your health concerns.',
            tooltip: 'Email and chat support with quicker response times.',
        },
    ];

    // Handle one-time report purchase
    const handleReportPurchase = async () => {
        setLoading(true);
        setError(null);
        setSuccess(false);

        try {
            const response = await axios.post(
                `${API_BASE_URL}/subscription/upgrade`,
                { plan: 'one_time' },
                { withCredentials: true }
            );
            console.log('Redirecting to Stripe for one-time report:', response.data.checkout_url);
            if (onReport) onReport();
            window.location.href = response.data.checkout_url;
        } catch (err) {
            console.error('Error initiating report purchase:', err);
            setError('Failed to initiate report purchase. Please try again or contact support.');
        } finally {
            setLoading(false);
        }
    };

    // Handle subscription action
    const handleSubscribe = () => {
        setLoading(true);
        setError(null);
        setSuccess(false);

        if (!isAuthenticated) {
            navigate('/auth');
            if (onSubscribe) onSubscribe();
            setLoading(false);
        } else {
            navigate('/subscription');
            if (onSubscribe) onSubscribe();
            setLoading(false);
        }
    };

    // Handle confirmation modal
    const confirmAction = (action) => {
        setPendingAction(action);
        setShowConfirmModal(true);
    };

    const handleConfirm = () => {
        if (pendingAction === 'report') {
            handleReportPurchase();
        } else if (pendingAction === 'subscribe') {
            handleSubscribe();
        }
        setShowConfirmModal(false);
        setPendingAction(null);
    };

    // Handle "Not Now" action
    const handleNotNowClick = () => {
        if (onNotNow) onNotNow();
        setSuccess(true);
    };

    // Toggle visibility of premium features
    const toggleFeatures = () => {
        setShowFeatures(!showFeatures);
    };

    // Custom loading spinner component
    const LoadingSpinner = () => (
        <div className="custom-spinner">
            <svg width="24" height="24" viewBox="0 0 24 24">
                <circle
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="#4285f4"
                    strokeWidth="2"
                    fill="none"
                    strokeDasharray="31.415"
                    strokeDashoffset="10"
                >
                    <animateTransform
                        attributeName="transform"
                        type="rotate"
                        from="0 12 12"
                        to="360 12 12"
                        dur="1s"
                        repeatCount="indefinite"
                    />
                </circle>
            </svg>
        </div>
    );

    return (
        <div className="upgrade-options-inline">
            <h3>
                {requiresUpgrade
                    ? 'Upgrade Required for Full Insights'
                    : 'Unlock Detailed Health Insights'}
            </h3>
            {error && (
                <div className="error-message" role="alert">
                    {error}
                    <button
                        className="retry-button"
                        onClick={() => {
                            setError(null);
                            if (pendingAction === 'report') handleReportPurchase();
                            else if (pendingAction === 'subscribe') handleSubscribe();
                        }}
                    >
                        Retry
                    </button>
                </div>
            )}
            {success && (
                <div className="success-message" role="alert">
                    Noted. Reach out anytime for more insights!
                </div>
            )}
            <p>
                <strong>Recommendation:</strong>{' '}
                {careRecommendation || 'Consider consulting a healthcare provider.'}
            </p>
            <p>
                <strong>Triage Level:</strong> {triageLevel || 'MODERATE'}
            </p>
            {triageLevel === 'AT_HOME' && !requiresUpgrade && (
                <div className="mild-case-note">
                    This appears to be a mild case that may be managed at home. You can
                    upgrade for more details or continue monitoring your symptoms.
                </div>
            )}
            {requiresUpgrade && (
                <p>
                    Your assessment indicates a {triageLevel.toLowerCase()} condition.
                    Upgrade to access detailed insights and recommendations.
                </p>
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
                                <span
                                    className="tooltip-icon"
                                    title={feature.tooltip}
                                    aria-label={`Tooltip: ${feature.tooltip}`}
                                >
                                    ?
                                </span>
                                <span className="feature-description">
                                    {feature.description}
                                </span>
                            </li>
                        ))}
                    </ul>
                )}
            </div>
            <div className="upgrade-buttons">
                <button
                    className={`upgrade-button one-time ${
                        loading ? 'loading' : ''
                    }`}
                    onClick={() => confirmAction('report')}
                    disabled={loading}
                    aria-label="Purchase a one-time report for $4.99"
                >
                    {loading ? <LoadingSpinner /> : 'One-Time Report ($4.99)'}
                </button>
                <button
                    className={`upgrade-button subscription ${
                        loading ? 'loading' : ''
                    }`}
                    onClick={() => confirmAction('subscribe')}
                    disabled={loading}
                    aria-label="Subscribe for $9.99 per month (requires login)"
                >
                    {loading ? <LoadingSpinner /> : 'Subscribe ($9.99/month)'}
                </button>
                {triageLevel === 'AT_HOME' && !requiresUpgrade && (
                    <button
                        className="continue-free-button"
                        onClick={handleNotNowClick}
                        disabled={loading}
                        aria-label="Continue without upgrading for now"
                    >
                        Continue Monitoring
                    </button>
                )}
            </div>
            {showConfirmModal && (
                <div className="confirm-modal">
                    <div className="modal-content">
                        <h4>Confirm Action</h4>
                        <p>
                            Are you sure you want to{' '}
                            {pendingAction === 'report'
                                ? 'purchase a one-time report for $4.99'
                                : 'subscribe for $9.99/month'}?
                        </p>
                        <div className="modal-buttons">
                            <button
                                className="confirm-button"
                                onClick={handleConfirm}
                                disabled={loading}
                            >
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
    );
};

UpgradePrompt.propTypes = {
    careRecommendation: PropTypes.string,
    triageLevel: PropTypes.oneOf(['MILD', 'MODERATE', 'SEVERE', 'AT_HOME']),
    onReport: PropTypes.func,
    onSubscribe: PropTypes.func,
    onNotNow: PropTypes.func,
    requiresUpgrade: PropTypes.bool,
};

UpgradePrompt.defaultProps = {
    careRecommendation: 'Consider consulting a healthcare provider.',
    triageLevel: 'MODERATE',
    onReport: () => {},
    onSubscribe: () => {},
    onNotNow: () => {},
    requiresUpgrade: false,
};

export default UpgradePrompt;