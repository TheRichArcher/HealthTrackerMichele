import React, { useState } from 'react';
import PropTypes from 'prop-types';
import '../styles/ChatOnboarding.css';

const ChatOnboarding = ({ onComplete }) => {
  const [currentStep, setCurrentStep] = useState(0);
  
  const steps = [
    {
      title: "Welcome to HealthTracker AI Chat",
      content: "I'm Michele, your AI medical assistant. I'm here to help you understand your symptoms and provide guidance.",
      image: "/onboarding-welcome.png"
    },
    {
      title: "How to Describe Symptoms",
      content: "Be specific about your symptoms, when they started, and any factors that make them better or worse.",
      image: "/onboarding-symptoms.png"
    },
    {
      title: "Understanding Results",
      content: "After asking some questions, I'll provide possible conditions with confidence levels and care recommendations.",
      image: "/onboarding-results.png"
    }
  ];
  
  const handleNext = () => {
    if (currentStep < steps.length - 1) {
      setCurrentStep(currentStep + 1);
    } else {
      // Save that the user has completed onboarding
      localStorage.setItem('healthtracker_chat_onboarding_complete', 'true');
      onComplete();
    }
  };
  
  const handleSkip = () => {
    localStorage.setItem('healthtracker_chat_onboarding_complete', 'true');
    onComplete();
  };
  
  return (
    <div className="chat-onboarding-overlay">
      <div className="chat-onboarding-modal">
        <button className="chat-onboarding-close" onClick={handleSkip} aria-label="Skip onboarding">
          &times;
        </button>
        
        <div className="chat-onboarding-content">
          {steps[currentStep].image && (
            <div className="chat-onboarding-image">
              <img 
                src={steps[currentStep].image} 
                alt={steps[currentStep].title}
                onError={(e) => {
                  e.target.onerror = null;
                  e.target.src = '/default-onboarding.png';
                }}
              />
            </div>
          )}
          
          <h2>{steps[currentStep].title}</h2>
          <p>{steps[currentStep].content}</p>
          
          <div className="chat-onboarding-progress">
            {steps.map((_, index) => (
              <div 
                key={index} 
                className={`progress-dot ${index === currentStep ? 'active' : ''}`}
                aria-label={`Step ${index + 1} of ${steps.length}`}
              />
            ))}
          </div>
          
          <div className="chat-onboarding-buttons">
            <button 
              className="chat-onboarding-button secondary" 
              onClick={handleSkip}
            >
              Skip
            </button>
            <button 
              className="chat-onboarding-button primary" 
              onClick={handleNext}
            >
              {currentStep < steps.length - 1 ? 'Next' : 'Get Started'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

ChatOnboarding.propTypes = {
  onComplete: PropTypes.func.isRequired
};

export default ChatOnboarding;