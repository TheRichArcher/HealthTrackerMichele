import React, { useState, useRef, useEffect, useCallback, memo } from 'react';
import PropTypes from 'prop-types';
import { debounce } from 'lodash';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from './AuthProvider'; // Assuming this exists
import '../styles/Chat.css';

const CONFIG = {
  API_URL: `${import.meta.env.VITE_API_URL || '/api'}/symptoms/analyze`,
  RESET_URL: `${import.meta.env.VITE_API_URL || '/api'}/symptoms/reset`,
  SUBSCRIPTION_URL: `${import.meta.env.VITE_API_URL || '/api'}/subscription`,
  CONFIRM_URL: `${import.meta.env.VITE_API_URL || '/api'}/subscription/confirm`,
  MAX_MESSAGE_LENGTH: 1000,
  MIN_CONFIDENCE_THRESHOLD: 95,
  THINKING_DELAY: 300,
  ASSESSMENT_DELAY: 1000,
  RECOMMENDATION_DELAY: 1000,
  SALES_PITCH_DELAY: 1000,
  UPGRADE_OPTIONS_DELAY: 1000,
  LOCAL_STORAGE_KEY: 'healthtracker_chat_messages',
  DEBUG_MODE: process.env.NODE_ENV === 'development',
};

const WELCOME_MESSAGE = {
  sender: 'bot',
  text: "Hi, I'm Michele—your AI medical assistant. Think of me as that doctor you absolutely trust, here to listen, guide, and help you make sense of your symptoms. While I can't replace a real doctor, I can give you insights, ask the right questions, and help you feel more in control of your health.\n\nYou can start by describing your symptoms like:\n• \"I've had a headache for two days\"\n• \"My throat is sore and I have a fever\"\n• \"I have a rash on my arm that's itchy\"",
  confidence: null,
  careRecommendation: null,
  isAssessment: false,
  isUpgradeOptions: false,
};

class ChatErrorBoundary extends React.Component {
  state = { hasError: false };
  static getDerivedStateFromError() { return { hasError: true }; }
  componentDidCatch(error, errorInfo) {
    if (CONFIG.DEBUG_MODE) console.error('Chat Error:', error, errorInfo);
  }
  render() {
    return this.state.hasError ? (
      <div className="error-boundary" role="alert">
        <h2>Something went wrong</h2>
        <button onClick={() => window.location.reload()}>Refresh Page</button>
      </div>
    ) : this.props.children;
  }
}

const Message = memo(({ message, onRetry, index, onUpgradeAction }) => {
  const { sender, text, confidence, careRecommendation, isAssessment, triageLevel, isUpgradeOptions, isMildCase } = message;
  let displayText = text
    .replace(/\s*\(Medical Condition\)\s*/g, '')
    .replace(/\(\d+%\s*confidence\)/g, '')
    .trim();

  const getCareRecommendation = useCallback((level) => {
    switch (level?.toLowerCase()) {
      case 'mild': return "You can likely manage this at home";
      case 'severe': return "Seek urgent care immediately";
      case 'moderate': return "Consider seeing a doctor soon";
      default: return null;
    }
  }, []);

  const avatarContent = sender === 'bot' ? (
    <img src="/doctor-avatar.png" alt="AI Assistant" />
  ) : (
    <img src="/user-avatar.png" alt="User" />
  );

  let confidenceClass = '';
  if (confidence) {
    if (confidence >= CONFIG.MIN_CONFIDENCE_THRESHOLD) confidenceClass = 'confidence-high';
    else if (confidence >= 70) confidenceClass = 'confidence-medium';
    else confidenceClass = 'confidence-low';
  }

  if (isUpgradeOptions) {
    return (
      <div className="message-row">
        <div className="avatar-container">{avatarContent}</div>
        <div className="message bot upgrade-options">
          <div className="message-content">
            <p className="upgrade-intro">{displayText}</p>
            <div className="upgrade-options-container">
              <div className="upgrade-option">
                <h4>💎 Premium Access ($9.99/month)</h4>
                <p>Unlimited checks, detailed assessments, and health monitoring.</p>
              </div>
              <div className="upgrade-option">
                <h4>📄 One-time Report ($4.99)</h4>
                <p>A detailed analysis of your current condition.</p>
              </div>
              <div className="upgrade-buttons">
                <button className="upgrade-button premium" onClick={() => onUpgradeAction('premium')}>
                  Get Premium ($9.99/month)
                </button>
                <button className="upgrade-button report" onClick={() => onUpgradeAction('report')}>
                  Get Report ($4.99)
                </button>
                {isMildCase && (
                  <button className="upgrade-button maybe-later" onClick={() => onUpgradeAction('later')}>
                    Maybe Later
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={`message-row ${sender === 'user' ? 'user' : ''}`}>
      <div className="avatar-container">{avatarContent}</div>
      <div className={`message ${sender} ${isAssessment ? 'assessment-message' : ''}`}>
        {isAssessment && <div className="assessment-indicator">Assessment</div>}
        <div className="message-content">
          {displayText.split('\n').map((line, i) => <p key={i}>{line}</p>)}
        </div>
        {sender === 'bot' && isAssessment && (confidence || careRecommendation || triageLevel) && (
          <div className="assessment-info">
            {confidence && (
              <div className={`assessment-item confidence ${confidenceClass}`} title="Confidence level">
                Confidence: {confidence}%
              </div>
            )}
            {(careRecommendation || triageLevel) && (
              <div className="assessment-item care-recommendation" title="Care recommendation">
                {careRecommendation || getCareRecommendation(triageLevel)}
              </div>
            )}
          </div>
        )}
        {sender === 'bot' && displayText.includes("trouble processing") && (
          <button className="retry-button" onClick={() => setTimeout(() => onRetry(index), 500)} aria-label="Retry message">
            Retry
          </button>
        )}
      </div>
    </div>
  );
});

Message.propTypes = {
  message: PropTypes.shape({
    sender: PropTypes.string,
    text: PropTypes.string,
    confidence: PropTypes.number,
    careRecommendation: PropTypes.string,
    isAssessment: PropTypes.bool,
    triageLevel: PropTypes.string,
    isUpgradeOptions: PropTypes.bool,
    isMildCase: PropTypes.bool,
  }).isRequired,
  onRetry: PropTypes.func.isRequired,
  index: PropTypes.number.isRequired,
  onUpgradeAction: PropTypes.func,
};

const Chat = () => {
  const [messages, setMessages] = useState(() => {
    const saved = localStorage.getItem(CONFIG.LOCAL_STORAGE_KEY);
    return saved ? JSON.parse(saved) : [WELCOME_MESSAGE];
  });
  const [userInput, setUserInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [typing, setTyping] = useState(false);
  const [error, setError] = useState(null);
  const [inputError, setInputError] = useState(null);
  const [resetting, setResetting] = useState(false);
  const [hasFinalAssessment, setHasFinalAssessment] = useState(false);
  const [latestAssessment, setLatestAssessment] = useState(null);

  const { isAuthenticated, checkAuth, refreshToken } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  const focusInput = useCallback(debounce(() => inputRef.current?.focus(), 100), []);
  const saveMessages = useCallback(debounce((msgs) => {
    localStorage.setItem(CONFIG.LOCAL_STORAGE_KEY, JSON.stringify(msgs));
  }, 500), []);
  const debouncedScrollToBottom = useCallback(debounce(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, 100), []);

  useEffect(() => {
    focusInput();
    checkAuth();
    const savedMessages = localStorage.getItem(CONFIG.LOCAL_STORAGE_KEY);
    if (!savedMessages) setMessages([WELCOME_MESSAGE]);
  }, [checkAuth, focusInput]);

  useEffect(() => {
    saveMessages(messages);
    setHasFinalAssessment(messages.some(msg => msg.isAssessment && msg.confidence >= CONFIG.MIN_CONFIDENCE_THRESHOLD));
  }, [messages, saveMessages]);

  useEffect(() => {
    debouncedScrollToBottom();
  }, [messages, typing, debouncedScrollToBottom]);

  // Token refresh
  useEffect(() => {
    if (isAuthenticated) {
      const refreshInterval = setInterval(() => {
        refreshToken().catch(() => console.warn('Token refresh failed'));
      }, 30 * 60 * 1000);
      return () => clearInterval(refreshInterval);
    }
  }, [isAuthenticated, refreshToken]);

  // Report confirmation
  useEffect(() => {
    const sessionId = new URLSearchParams(location.search).get('session_id');
    if (sessionId) {
      fetch(CONFIG.CONFIRM_URL, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('jwt_token') || ''}`,
        },
        credentials: 'include',
        body: JSON.stringify({ session_id: sessionId }),
      })
        .then(res => res.json())
        .then(data => {
          if (data.report_url) {
            setMessages(prev => [...prev, { sender: 'bot', text: `Your one-time report is ready! [Download PDF](${data.report_url})`, isAssessment: false }]);
          } else {
            setMessages(prev => [...prev, { sender: 'bot', text: 'Payment confirmed, but report generation failed. Please contact support.', isAssessment: false }]);
          }
        })
        .catch(err => {
          console.error('Error confirming report:', err);
          setMessages(prev => [...prev, { sender: 'bot', text: 'Failed to confirm report. Please contact support.', isAssessment: false }]);
        });
      navigate('/chat', { replace: true });
    }
  }, [location, navigate]);

  const addBotMessage = useCallback((message, isAssessment = false, confidence = null, triageLevel = null, careRecommendation = null, isUpgradeOptions = false, isMildCase = false) => {
    setTyping(true);
    const thinkingDelay = Math.min(500 + (message.split(/\s+/).length * 15), 1500);
    setTimeout(() => {
      setMessages(prev => [...prev, { sender: 'bot', text: message, isAssessment, confidence, triageLevel, careRecommendation, isUpgradeOptions, isMildCase }]);
      setTyping(false);
      requestAnimationFrame(() => messagesEndRef.current?.scrollIntoView({ behavior: 'auto' }));
    }, thinkingDelay);
  }, []);

  const handleUpgradeAction = useCallback((action, assessmentId) => {
    const token = localStorage.getItem('jwt_token') || '';
    if (action === 'premium') {
      if (!isAuthenticated) navigate('/auth');
      else navigate('/subscribe');
    } else if (action === 'report') {
      fetch(`${CONFIG.SUBSCRIPTION_URL}/upgrade`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        credentials: 'include',
        body: JSON.stringify({ plan: 'one_time', assessment_id: assessmentId || latestAssessment?.assessmentId }),
      })
        .then(res => res.json())
        .then(data => {
          if (data.checkout_url) window.location.href = data.checkout_url;
          else addBotMessage('Failed to initiate report purchase. Please try again.');
        })
        .catch(err => addBotMessage('Failed to initiate report purchase. Please try again.'));
    } else if (action === 'later') {
      addBotMessage("No problem! Let me know if you have any other questions or symptoms to discuss.");
    }
  }, [isAuthenticated, navigate, addBotMessage, latestAssessment]);

  const handleSendMessage = async () => {
    if (!userInput.trim() || loading) return;
    setMessages(prev => [...prev, { sender: 'user', text: userInput.trim(), isAssessment: false }]);
    setUserInput('');
    setLoading(true);
    setTyping(true);

    const token = localStorage.getItem('jwt_token') || '';
    const conversationHistory = messages.map(msg => ({ message: msg.text, isBot: msg.sender === 'bot' }));

    try {
      const response = await fetch(CONFIG.API_URL, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        credentials: 'include',
        body: JSON.stringify({ symptom: userInput, conversation_history: conversationHistory, context_notes: "Focus on user input and history." }),
      });

      if (!response.ok) throw new Error(`API error: ${response.status}`);
      const data = await response.json();

      setLoading(false);
      setTyping(false);

      if (data.response?.is_assessment) {
        const { confidence, triage_level, care_recommendation, possible_conditions, assessment_id } = data.response;
        const medicalTerm = possible_conditions || 'Unknown condition';
        const assessmentMessage = `I've identified ${medicalTerm} as a possible condition.\n\nConfidence: ${confidence}%`;
        addBotMessage(assessmentMessage, true, confidence);

        setTimeout(() => {
          const recommendationMessage = `Severity: ${triage_level.toUpperCase()}\nRecommendation: ${care_recommendation}`;
          addBotMessage(recommendationMessage);
          setLatestAssessment({
            condition: medicalTerm,
            confidence,
            triageLevel: triage_level,
            recommendation: care_recommendation,
            assessmentId: assessment_id
          });

          setTimeout(() => {
            const isMildCase = triage_level.toLowerCase() === 'mild';
            addBotMessage("For deeper analysis, consider upgrading:", false);
            setTimeout(() => addBotMessage("Ready to unlock more?", false, null, null, null, true, isMildCase), CONFIG.SALES_PITCH_DELAY);
          }, CONFIG.RECOMMENDATION_DELAY);
        }, CONFIG.ASSESSMENT_DELAY);
      } else {
        addBotMessage(data.response?.next_question || "Can you tell me more?");
      }
    } catch (err) {
      setLoading(false);
      setTyping(false);
      addBotMessage("I'm having trouble processing that—please try again!");
      setError(err.message);
    }
  };

  const handleResetConversation = async () => {
    if (loading || resetting) return;
    setResetting(true);
    try {
      const token = localStorage.getItem('jwt_token') || '';
      const response = await fetch(CONFIG.RESET_URL, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        credentials: 'include',
        body: JSON.stringify({ conversation_history: messages.map(msg => ({ message: msg.text, isBot: msg.sender === 'bot' })) }),
      });
      const data = await response.json();
      setMessages([{ sender: 'bot', text: data.response, isAssessment: false }]);
      setHasFinalAssessment(false);
    } catch (err) {
      addBotMessage("Failed to reset—try again!");
    } finally {
      setResetting(false);
    }
  };

  return (
    <ChatErrorBoundary>
      <div className="chat-container" role="main" aria-label="Chat interface">
        <div className="reset-button-container">
          <button className="reset-button" onClick={handleResetConversation} disabled={loading || resetting}>
            {resetting ? 'Resetting...' : 'Reset Conversation'}
          </button>
        </div>
        <div className="messages-container" role="log" aria-live="polite">
          {messages.map((msg, i) => (
            <Message key={i} message={msg} onRetry={() => {}} index={i} onUpgradeAction={handleUpgradeAction} />
          ))}
          {typing && (
            <div className="message-row">
              <div className="avatar-container">
                <img src="/doctor-avatar.png" alt="AI Assistant" />
              </div>
              <div className="typing-indicator"><span></span><span></span><span></span></div>
            </div>
          )}
          {error && <div className="error-message" role="alert">{error}</div>}
          <div ref={messagesEndRef} />
        </div>
        <div className="chat-input-container">
          <div className="chat-input-wrapper">
            <textarea
              ref={inputRef}
              className="chat-input"
              value={userInput}
              onChange={(e) => setUserInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && (e.preventDefault(), handleSendMessage())}
              placeholder={hasFinalAssessment ? "Reset to discuss new symptoms" : "Describe your symptoms..."}
              disabled={loading || resetting || hasFinalAssessment}
              maxLength={CONFIG.MAX_MESSAGE_LENGTH}
            />
            <button className="send-button" onClick={handleSendMessage} disabled={loading || !userInput.trim()}>
              Send
            </button>
            {!isAuthenticated && (
              <button className="sign-in-button" onClick={() => navigate('/auth')}>
                Sign In
              </button>
            )}
          </div>
        </div>
      </div>
    </ChatErrorBoundary>
  );
};

export default Chat;