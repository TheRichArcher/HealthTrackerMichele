import React, { useState, useEffect, memo } from 'react';
import PropTypes from 'prop-types';
import { useNavigate } from 'react-router-dom';
import { useAuth } from './AuthProvider'; // Updated import
import axios from 'axios';
import '../styles/UpgradePrompt.css';
import '../styles/shared.css';

const UpgradePrompt = ({ condition, commonName, isMildCase, requiresUpgrade, confidence, triageLevel, recommendation, onDismiss }) => {
    const [loadingSubscription, setLoadingSubscription] = useState(false);
    const [loadingOneTime, setLoadingOneTime] = useState(false);
    const [report, setReport] = useState(null);
    const [error, setError] = useState(null);
    const { isAuthenticated, fetchSubscriptionStatus } = useAuth();
    const navigate = useNavigate();

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
        
        if (!isAuthenticated) {
            navigate('/auth', { state: { from: '/subscription', plan: 'paid' } });
            return;
        }
        
        navigate('/subscription', { state: { plan: 'paid' } });
    };

    const handleOneTimeClick = () => {
        if (loadingSubscription || loadingOneTime) return;
        setLoadingOneTime(true);
        
        if (!isAuthenticated) {
            navigate('/auth', { state: { from: '/one-time-report', plan: 'one_time' } });
            return;
        }
        
        checkSubscriptionAndGenerateReport();
    };
    
    const checkSubscriptionAndGenerateReport = async () => {
        try {
            const token = localStorage.getItem('access_token');
            if (!token) {
                setError('Authentication required. Please log in.');
                setLoadingOneTime(false);
                navigate('/auth');
                return;
            }

            const response = await axios.get(`${import.meta.env.VITE_API_URL || '/api'}/subscription/status`, {
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
            setError('Failed to check subscription status. Please try again.');
            setLoadingOneTime(false);
        }
    };
    
    const generateReport = async () => {
        try {
            const token = localStorage.getItem('access_token');
            if (!token) {
                setError('Authentication required. Please log in.');
                setLoadingOneTime(false);
                navigate('/auth');
                return;
            }

            const conversationHistory = JSON.parse(localStorage.getItem('healthtracker_chat_messages') || '[]')
                .map(msg => ({ message: msg.text, isBot: msg.sender === 'bot' }));
            
            const userSymptoms = conversationHistory.find(msg => !msg.isBot)?.message || condition;
            
            const response = await axios.post(
                `${import.meta.env.VITE_API_URL || '/api'}/symptoms/doctor-report`, 
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
                await fetchSubscriptionStatus();
            } else {
                throw new Error(response.data.error || 'Failed to generate report');
            }
        } catch (err) {
            console.error('Error generating report:', err);
            setError('Failed to generate report. Please try again.');
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
                            {loadingOneTime ? 'Generating...' : '📄 Get Report ($4.99)'}
                        </button>
                        {isMildCase && (
                            <button className="continue-free-button" onClick={onDismiss}>
                                Maybe Later
                            </button>
                        )}
                    </div>
                    {error && <div className="error-message">{error}</div>}
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