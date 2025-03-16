import React, { useState, useEffect, memo } from 'react';
import PropTypes from 'prop-types';
import { useNavigate } from 'react-router-dom';
import { useAuth } from './AuthProvider';
import axios from 'axios';
import { getLocalStorageItem } from '../utils/utils';
import '../styles/UpgradePrompt.css';
import '../styles/shared.css';

const API_BASE_URL = 'https://healthtrackermichele.onrender.com/api';

const UpgradePrompt = ({ condition, commonName, isMildCase, requiresUpgrade, confidence, triageLevel, recommendation, onDismiss }) => {
    const [loadingSubscription, setLoadingSubscription] = useState(false);
    const [loadingOneTime, setLoadingOneTime] = useState(false);
    const [report, setReport] = useState(null);
    const [error, setError] = useState(null);
    const { isAuthenticated, checkAuth, isLoggingOut } = useAuth();
    const navigate = useNavigate();

    const displayName = commonName ? `${commonName} (${condition})` : condition;

    useEffect(() => {
        console.log("UpgradePrompt Props:", { condition, commonName, isMildCase, requiresUpgrade, confidence, triageLevel, recommendation });
        if (isMildCase) {
            document.querySelector('.continue-free-button')?.scrollIntoView({ behavior: 'smooth' });
        }
    }, [condition, commonName, isMildCase, requiresUpgrade, confidence, triageLevel, recommendation]);

    const handleSubscriptionClick = async () => {
        if (loadingSubscription || loadingOneTime || isLoggingOut) {
            setError('Please wait while processing.');
            return;
        }
        setLoadingSubscription(true);
        setError(null);

        const isValid = await checkAuth();
        if (!isValid) {
            navigate('/auth', { state: { from: '/subscription', plan: 'paid' } });
        } else {
            navigate('/subscription', { state: { plan: 'paid' } });
        }
        setLoadingSubscription(false);
    };

    const handleOneTimeClick = async () => {
        if (loadingSubscription || loadingOneTime || isLoggingOut) {
            setError('Please wait while processing.');
            return;
        }
        setLoadingOneTime(true);
        setError(null);

        const isValid = await checkAuth();
        if (!isValid) {
            navigate('/auth', { state: { from: '/one-time-report', plan: 'one_time' } });
            setLoadingOneTime(false);
            return;
        }

        await checkSubscriptionAndGenerateReport();
    };

    const checkSubscriptionAndGenerateReport = async () => {
        try {
            const isValid = await checkAuth();
            if (!isValid) {
                navigate('/auth', { state: { from: '/one-time-report', plan: 'one_time' } });
                return;
            }

            const token = getLocalStorageItem('access_token');
            const response = await axios.get(`${API_BASE_URL}/subscription/status`, {
                headers: { 'Authorization': `Bearer ${token}` }
            });

            const userTier = response.data.subscription_tier;

            if (userTier === 'paid' || userTier === 'one_time') {
                await generateReport();
            } else {
                navigate('/one-time-report', { state: { plan: 'one_time' } });
            }
        } catch (err) {
            console.error('Error checking subscription status:', err);
            setError(
                err.response?.status === 401
                    ? 'Session expired. Please log in again.'
                    : 'Failed to check subscription status. Please try again.'
            );
            if (err.response?.status === 401) {
                navigate('/auth');
            }
        } finally {
            setLoadingOneTime(false);
        }
    };

    const generateReport = async () => {
        try {
            const isValid = await checkAuth();
            if (!isValid) {
                navigate('/auth');
                return;
            }

            const token = getLocalStorageItem('access_token');
            const chatMessages = getLocalStorageItem('healthtracker_chat_messages');
            let conversationHistory = [];
            try {
                conversationHistory = JSON.parse(chatMessages || '[]')
                    .map(msg => ({ message: msg.text, isBot: msg.sender === 'bot' }));
            } catch (e) {
                console.error('Error parsing chat messages:', e);
            }

            const userSymptoms = conversationHistory.find(msg => !msg.isBot)?.message || condition;

            if (!userSymptoms) {
                throw new Error('No symptoms found to generate a report.');
            }

            const response = await axios.post(
                `${API_BASE_URL}/symptoms/doctor-report`,
                {
                    symptom: userSymptoms,
                    conversation_history: conversationHistory
                },
                {
                    headers: { 'Authorization': `Bearer ${token}` }
                }
            );

            if (response.data.success) {
                setReport(response.data.doctors_report);
            } else {
                throw new Error(response.data.error || 'Failed to generate report');
            }
        } catch (err) {
            console.error('Error generating report:', err);
            setError(
                err.response?.status === 401
                    ? 'Session expired. Please log in again.'
                    : err.message || 'Failed to generate report. Please try again.'
            );
            if (err.response?.status === 401) {
                navigate('/auth');
            }
        } finally {
            setLoadingOneTime(false);
        }
    };

    return (
        <div className="upgrade-options-inline" role="dialog" aria-labelledby="upgrade-title">
            {!report ? (
                <>
                    <h3 id="upgrade-title">
                        I've identified <strong>{displayName}</strong> as a possible condition.
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
                            disabled={loadingSubscription || loadingOneTime || isLoggingOut}
                            aria-busy={loadingSubscription}
                        >
                            {loadingSubscription ? 'Processing...' : '🩺 Get Premium ($9.99/month)'}
                        </button>
                        <button
                            className={`upgrade-button one-time ${loadingOneTime ? 'loading' : ''}`}
                            onClick={handleOneTimeClick}
                            disabled={loadingSubscription || loadingOneTime || isLoggingOut}
                            aria-busy={loadingOneTime}
                        >
                            {loadingOneTime ? 'Generating...' : '📄 Get Report ($4.99)'}
                        </button>
                        {isMildCase && (
                            <button className="continue-free-button" onClick={onDismiss}>
                                Maybe Later
                            </button>
                        )}
                    </div>
                    {error && (
                        <div className="error-message" role="alert">
                            {error}
                        </div>
                    )}
                </>
            ) : (
                <div className="doctor-report">
                    <h3>Doctor's Report</h3>
                    <div className="report-content">
                        {report.split('\n').map((line, i) => (
                            <p key={i}>{line}</p>
                        ))}
                    </div>
                    <button 
                        className="continue-free-button"
                        onClick={onDismiss}
                    >
                        Return to Chat
                    </button>
                </div>
            )}
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