// src/components/UpgradePrompt.jsx
import React, { useState } from 'react';
import PropTypes from 'prop-types';
import '../styles/UpgradePrompt.css'; // We'll create this file next

const UpgradePrompt = ({ onDismiss }) => {
    const [loadingSubscription, setLoadingSubscription] = useState(false);
    const [loadingOneTime, setLoadingOneTime] = useState(false);

    return (
        <div className="upgrade-options">
            <button 
                className="close-upgrade" 
                onClick={onDismiss}
                aria-label="Dismiss upgrade prompt"
            >
                ✖
            </button>
            <div className="upgrade-message">
                <h3>Based on your symptoms, I've identified a condition that may require further evaluation.</h3>
                <p>💡 To get more insights, you can choose one of these options:</p>
                <ul>
                    <li>🔹 PA Mode ($9.99/month): Unlock full symptom tracking, detailed assessments, and AI-driven health monitoring.</li>
                    <li>🔹 One-time AI Doctor Report ($4.99): Get a comprehensive summary of your case, formatted for medical professionals.</li>
                </ul>
                <p>Would you like to continue with one of these options?</p>
            </div>
            <div className="upgrade-buttons">
                <button 
                    className={`upgrade-button subscription ${loadingSubscription ? 'loading' : ''}`}
                    onClick={() => {
                        if (loadingSubscription || loadingOneTime) return; // Prevent duplicate clicks
                        setLoadingSubscription(true);
                        // Short timeout to show loading state before navigation
                        setTimeout(() => {
                            window.location.href = '/subscribe';
                        }, 300);
                    }}
                    disabled={loadingSubscription || loadingOneTime}
                >
                    {loadingSubscription ? 'Processing...' : '🩺 Unlock Full Health Insights (PA Mode - $9.99/month)'}
                </button>
                <button 
                    className={`upgrade-button one-time ${loadingOneTime ? 'loading' : ''}`}
                    onClick={() => {
                        if (loadingSubscription || loadingOneTime) return; // Prevent duplicate clicks
                        setLoadingOneTime(true);
                        // Short timeout to show loading state before navigation
                        setTimeout(() => {
                            window.location.href = '/one-time-report';
                        }, 300);
                    }}
                    disabled={loadingSubscription || loadingOneTime}
                >
                    {loadingOneTime ? 'Processing...' : '📄 Generate AI Doctor\'s Report ($4.99 - One Time)'}
                </button>
            </div>
        </div>
    );
};

UpgradePrompt.propTypes = {
    onDismiss: PropTypes.func.isRequired
};

export default UpgradePrompt;