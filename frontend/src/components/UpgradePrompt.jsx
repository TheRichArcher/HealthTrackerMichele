// src/components/UpgradePrompt.jsx
import React, { useState, useEffect } from 'react';
import PropTypes from 'prop-types';
import '../styles/UpgradePrompt.css';

const UpgradePrompt = ({ condition, commonName, isMildCase, onDismiss }) => {
    const [loadingSubscription, setLoadingSubscription] = useState(false);
    const [loadingOneTime, setLoadingOneTime] = useState(false);

    // Create a display name that includes both common and medical terms
    const displayName = commonName ? 
        `${commonName} (${condition})` : 
        condition;
        
    // Add logging for tracking issues
    useEffect(() => {
        console.log("Upgrade Prompt Loaded with Condition:", {
            condition,
            commonName,
            isMildCase
        });
        
        // Make sure Maybe Later button is visible if it exists
        setTimeout(() => {
            document.querySelector('.continue-free-button')?.scrollIntoView({ behavior: "smooth" });
        }, 100);
    }, [condition, commonName, isMildCase]);

    return (
        <div className="upgrade-options-inline" style={{width: '100%', display: 'block'}}>
            <h3>
                Based on your symptoms, I've identified {displayName} as a possible condition that may require further evaluation.
            </h3>
            
            {/* Add conditional section for mild cases */}
            {isMildCase && (
                <p className="mild-case-note">
                    Since this appears to be a condition you can manage at home, you can continue using the free version. 
                    However, for more detailed insights and tracking, consider upgrading.
                </p>
            )}
            
            <p>To get more insights, you can choose one of these options:</p>
            <ul className="premium-features-list">
                <li>
                    <span className="feature-name">🔹 Premium Access ($9.99/month)</span>
                    <span className="tooltip-icon" title="Get deeper insights, track symptoms, and receive doctor-ready reports">ⓘ</span>
                    <span className="feature-description">Unlimited symptom checks, detailed assessments, and personalized health monitoring.</span>
                </li>
                <li>
                    <span className="feature-name">🔹 One-time Consultation Report ($4.99)</span>
                    <span className="tooltip-icon" title="A comprehensive report you can share with your doctor">ⓘ</span>
                    <span className="feature-description">Get a comprehensive analysis of your current symptoms.</span>
                </li>
            </ul>
            <p>Would you like to continue with one of these options?</p>
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
                    {loadingSubscription ? 'Processing...' : '🩺 Get Premium Access ($9.99/month)'}
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
                    {loadingOneTime ? 'Processing...' : '📄 Get Consultation Report ($4.99)'}
                </button>
                
                {/* Only show "Maybe Later" button for mild cases */}
                {isMildCase && (
                    <button 
                        className="continue-free-button"
                        onClick={onDismiss}
                    >
                        Maybe Later
                    </button>
                )}
            </div>
        </div>
    );
};

UpgradePrompt.propTypes = {
    condition: PropTypes.string.isRequired,
    commonName: PropTypes.string, // Add this prop
    isMildCase: PropTypes.bool.isRequired,
    onDismiss: PropTypes.func.isRequired
};

export default UpgradePrompt;