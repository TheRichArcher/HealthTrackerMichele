// src/components/MessageItem.jsx
import React, { memo, useCallback } from 'react';
import PropTypes from 'prop-types';
import '../styles/MessageItem.css';

const MessageItem = memo(({ message, onRetry, index, hideAssessmentDetails }) => {
    const { sender, text, confidence, careRecommendation, isAssessment, triageLevel } = message;

    // Clean any "(Medical Condition)" text from messages
    const cleanBotMessage = (messageText) => {
        return messageText.replace(/\s*\(Medical Condition\)\s*/g, '').trim();
    };

    const getCareRecommendation = useCallback((level) => {
        switch(level?.toLowerCase()) {
            case 'mild': return "You can likely manage this at home";
            case 'severe': return "You should seek urgent care";
            case 'moderate': return "Consider seeing a doctor soon";
            default: return null;
        }
    }, []);

    // Create avatar content based on sender
    const avatarContent = sender === 'bot' ? (
        <img src="/doctor-avatar.png" alt="AI Assistant" />
    ) : (
        <img src="/user-avatar.png" alt="User" />
    );

    // Clean the message text if it's from the bot
    const displayText = sender === 'bot' ? cleanBotMessage(text) : text;

    return (
        <div className={`message-row ${sender === 'user' ? 'user' : ''}`}>
            <div className="avatar-container">
                {avatarContent}
            </div>
            <div className={`message ${sender}`}>
                {isAssessment && <div className="assessment-indicator">Assessment</div>}
                <div className="message-content">
                    {displayText.split('\n').map((line, i) => (
                        <p key={i}>{line}</p>
                    ))}
                </div>
                {/* Only show metrics if this is an assessment AND we're not hiding assessment details */}
                {sender === 'bot' && isAssessment && !hideAssessmentDetails && (confidence || careRecommendation || triageLevel) && (
                    <div className="assessment-info">
                        {confidence && (
                            <div 
                                className={`assessment-item confidence ${
                                    confidence >= 95 ? 'confidence-high' : 
                                    confidence >= 70 ? 'confidence-medium' : 
                                    'confidence-low'
                                }`}
                                title="Confidence indicates how likely this condition matches your symptoms based on available information"
                            >
                                Confidence: {confidence}%
                            </div>
                        )}
                        {(careRecommendation || triageLevel) && (
                            <div 
                                className="assessment-item care-recommendation"
                                title="This recommendation is based on the severity of your symptoms and potential conditions"
                            >
                                {careRecommendation || getCareRecommendation(triageLevel)}
                            </div>
                        )}
                    </div>
                )}
                {sender === 'bot' && text.includes("trouble processing") && (
                    <button 
                        className="retry-button"
                        onClick={() => onRetry(index)}
                        aria-label="Retry message"
                    >
                        Retry
                    </button>
                )}
            </div>
        </div>
    );
});

MessageItem.displayName = 'MessageItem';
MessageItem.propTypes = {
    message: PropTypes.shape({
        sender: PropTypes.string.isRequired,
        text: PropTypes.string.isRequired,
        confidence: PropTypes.number,
        careRecommendation: PropTypes.string,
        isAssessment: PropTypes.bool,
        triageLevel: PropTypes.string
    }).isRequired,
    onRetry: PropTypes.func.isRequired,
    index: PropTypes.number.isRequired,
    hideAssessmentDetails: PropTypes.bool
};

export default MessageItem;