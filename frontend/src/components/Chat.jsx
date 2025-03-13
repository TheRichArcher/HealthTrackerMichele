import React, { useState, useRef, useEffect, useCallback, memo } from 'react';
import PropTypes from 'prop-types';
import { debounce } from 'lodash';
import { useAuth } from '../context/AuthContext';
import axios from 'axios';
import UpgradePrompt from './UpgradePrompt';
import '../styles/Chat.css';

console.log("CHAT.JSX LOADED AT", new Date().toISOString());

const UI_STATES = {
  DEFAULT: 'default',
  ASSESSMENT_COMPLETE: 'assessment_complete'
};

const CONFIG = {
  MAX_FREE_MESSAGES: 5, // Adjusted for subscription limits
  THINKING_DELAY: 300, // Reduced from 1000ms to 300ms
  API_TIMEOUT: 10000,
  API_URL: `${import.meta.env.VITE_API_URL || '/api'}/symptoms/analyze`,
  RESET_URL: `${import.meta.env.VITE_API_URL || '/api'}/symptoms/reset`,
  MAX_MESSAGE_LENGTH: 1000,
  MIN_MESSAGE_LENGTH: 1,
  SCROLL_DEBOUNCE_DELAY: 100,
  LOCAL_STORAGE_KEY: 'healthtracker_chat_messages',
  DEBUG_MODE: process.env.NODE_ENV === 'development',
  MIN_CONFIDENCE_THRESHOLD: 95, // Aligned with backend
  MESSAGE_DELAY: 1000, // Standard delay between messages (1 second)
  ASSESSMENT_DELAY: 1000, // Delay after assessment
  RECOMMENDATION_DELAY: 1000, // Delay after recommendation
  SALES_PITCH_DELAY: 1000, // Delay after sales pitch
  UPGRADE_OPTIONS_DELAY: 1000 // Delay after upgrade options
};

const WELCOME_MESSAGE = {
  sender: 'bot',
  text: "Hi, I'm Michele—your AI medical assistant. Think of me as that doctor you absolutely trust, here to listen, guide, and help you make sense of your symptoms. While I can't replace a real doctor, I can give you insights, ask the right questions, and help you feel more in control of your health.\n\nYou can start by describing your symptoms like:\n• \"I've had a headache for two days\"\n• \"My throat is sore and I have a fever\"\n• \"I have a rash on my arm that's itchy\"",
  confidence: null,
  careRecommendation: null,
  isAssessment: false,
  isUpgradeOptions: false
};

class ChatErrorBoundary extends React.Component {
  state = { hasError: false };

  static getDerivedStateFromError(error) {
    return { hasError: true };
  }

  componentDidCatch(error, errorInfo) {
    if (CONFIG.DEBUG_MODE) console.error('Chat Error:', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="error-boundary" role="alert">
          <h2>Something went wrong</h2>
          <button onClick={() => window.location.reload()}>Refresh Page</button>
        </div>
      );
    }
    return this.props.children;
  }
}

const Message = memo(({ message, onRetry, index }) => {
  const { sender, text, confidence, careRecommendation, isAssessment, triageLevel } = message;

  let displayText = text;
  if (sender === 'bot' && text) {
    if (text.includes("<json>")) displayText = text.split("<json>")[0].trim();
    else if (text.includes('"assessment"') || text.includes('"conditions"')) {
      const jsonStartIndex = text.indexOf('{');
      if (jsonStartIndex > 0) displayText = text.substring(0, jsonStartIndex).trim();
    }
    displayText = displayText.replace(/\s*\(Medical Condition\)\s*/g, '').trim();
    displayText = displayText.replace(/\(\d+%\s*confidence\)/g, '').trim();
    displayText = displayText.replace(/\*\*([^*]+)\*\*/g, (match, p1) => `**${p1.replace(/\*/g, '')}**`);
  }

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

  return (
    <div className={`message-row ${sender === 'user' ? 'user' : ''}`}>
      <div className="avatar-container">{avatarContent}</div>
      <div className={`message ${sender} ${displayText.includes('?') && sender === 'bot' ? 'follow-up-question' : ''} ${isAssessment ? 'assessment-message' : ''}`}>
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

Message.displayName = 'Message';
Message.propTypes = {
  message: PropTypes.shape({
    sender: PropTypes.string,
    text: PropTypes.string,
    confidence: PropTypes.number,
    careRecommendation: PropTypes.string,
    isAssessment: PropTypes.bool,
    triageLevel: PropTypes.string,
    isUpgradeOptions: PropTypes.bool,
    isMildCase: PropTypes.bool
  }).isRequired,
  onRetry: PropTypes.func.isRequired,
  index: PropTypes.number.isRequired
};

const Chat = () => {
  const [messages, setMessages] = useState(() => {
    try {
      const saved = localStorage.getItem(CONFIG.LOCAL_STORAGE_KEY);
      return saved ? JSON.parse(saved) : [WELCOME_MESSAGE];
    } catch (error) {
      if (CONFIG.DEBUG_MODE) console.error('Error loading messages:', error);
      return [WELCOME_MESSAGE];
    }
  });
  const [userInput, setUserInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [messageCount, setMessageCount] = useState(0);
  const [typing, setTyping] = useState(false);
  const [error, setError] = useState(null);
  const [inputError, setInputError] = useState(null);
  const [resetting, setResetting] = useState(false);
  const [uiState, setUiState] = useState(UI_STATES.DEFAULT);
  const [latestAssessment, setLatestAssessment] = useState(null);
  const [latestResponseData, setLatestResponseData] = useState(null);
  const [hasFinalAssessment, setHasFinalAssessment] = useState(false);
  const [subscriptionTier, setSubscriptionTier] = useState(null);

  const { isAuthenticated } = useAuth();
  const messagesEndRef = useRef(null);
  const abortControllerRef = useRef(null);
  const inputRef = useRef(null);

  const focusInput = useCallback(debounce(() => {
    if (inputRef.current) inputRef.current.focus();
  }, 100), []);

  const saveMessages = useCallback(debounce((msgs) => {
    try {
      localStorage.setItem(CONFIG.LOCAL_STORAGE_KEY, JSON.stringify(msgs));
    } catch (error) {
      if (CONFIG.DEBUG_MODE) console.error('Error saving messages:', error);
    }
  }, 500), []);

  const debouncedScrollToBottom = useCallback(debounce(() => {
    if (messagesEndRef.current) messagesEndRef.current.scrollIntoView({ behavior: "smooth" });
  }, CONFIG.SCROLL_DEBOUNCE_DELAY), []);

  const scrollToBottomImmediate = useCallback(() => {
    if (messagesEndRef.current) messagesEndRef.current.scrollIntoView({ behavior: "auto" });
  }, []);

  useEffect(() => {
    focusInput();
    if (isAuthenticated) {
      const token = localStorage.getItem('jwt_token');
      axios.get(`${import.meta.env.VITE_API_URL || '/api'}/subscription/status`, {
        headers: { 'Authorization': `Bearer ${token}` }
      })
        .then(res => setSubscriptionTier(res.data.subscription_tier))
        .catch(err => console.error('Failed to fetch subscription status:', err));
    }
  }, [focusInput, isAuthenticated]);

  useEffect(() => {
    if (messages.length > 0 && !typing) saveMessages(messages);
  }, [messages, typing, saveMessages]);

  useEffect(() => {
    debouncedScrollToBottom();
  }, [messages, typing, debouncedScrollToBottom]);

  useEffect(() => {
    const hasAssessment = messages.some(msg => 
      msg.sender === 'bot' && 
      msg.isAssessment && 
      msg.confidence >= CONFIG.MIN_CONFIDENCE_THRESHOLD
    );
    setHasFinalAssessment(hasAssessment);
  }, [messages]);

  useEffect(() => {
    return () => {
      if (abortControllerRef.current) abortControllerRef.current.abort();
      debouncedScrollToBottom.cancel();
      saveMessages.cancel();
      focusInput.cancel();
    };
  }, [debouncedScrollToBottom, saveMessages, focusInput]);

  const validateInput = useCallback((input) => {
    if (!input.trim()) return "Please enter a message";
    if (input.length > CONFIG.MAX_MESSAGE_LENGTH) return "Message is too long";
    return null;
  }, []);

  const addBotMessage = useCallback((message, isAssessment = false, confidence = null, triageLevel = null, careRecommendation = null) => {
    setTyping(true);
    const wordCount = message.split(/\s+/).length;
    const thinkingDelay = Math.min(500 + (wordCount * 15), 1500);
    setTimeout(() => {
      setMessages(prev => [...prev, {
        sender: 'bot',
        text: message,
        isAssessment,
        confidence,
        triageLevel,
        careRecommendation,
        isUpgradeOptions: false
      }]);
      setTyping(false);
      requestAnimationFrame(() => {
        scrollToBottomImmediate();
        focusInput();
      });
    }, thinkingDelay);
  }, [scrollToBottomImmediate, focusInput]);

  const handleDismissUpgrade = useCallback(() => {
    addBotMessage("No problem! Let me know if you have any other questions or symptoms to discuss.");
    setUiState(UI_STATES.DEFAULT);
  }, [addBotMessage]);

  const handleRetry = useCallback(async (messageIndex) => {
    const originalMessage = messages[messageIndex - 1];
    if (originalMessage && originalMessage.sender === 'user') {
      setMessages(messages => messages.slice(0, messageIndex));
      setUserInput(originalMessage.text);
      await handleSendMessage(originalMessage.text);
    }
  }, [messages]);

  const handleResetConversation = async () => {
    if (loading || resetting) return;
    setResetting(true);
    setError(null);

    try {
      const token = localStorage.getItem('jwt_token');
      const response = await fetch(CONFIG.RESET_URL, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token && { 'Authorization': `Bearer ${token}` })
        },
        body: JSON.stringify({ conversation_history: messages.map(msg => ({ message: msg.text, isBot: msg.sender === 'bot' })) })
      });

      const data = await response.json();

      if (!response.ok) {
        if (response.status === 403) throw new Error(data.message || "Upgrade required to reset conversation.");
        throw new Error(`Reset failed: ${response.status}`);
      }

      setMessages([WELCOME_MESSAGE]);
      setMessageCount(0);
      setError(null);
      setInputError(null);
      setUiState(UI_STATES.DEFAULT);
      setLatestAssessment(null);
      setLatestResponseData(null);
      setHasFinalAssessment(false);
      saveMessages([WELCOME_MESSAGE]);
    } catch (error) {
      if (CONFIG.DEBUG_MODE) console.error("Error resetting conversation:", error);
      setError(error.message || "Failed to reset conversation—please try again.");
      addBotMessage("I couldn't reset the conversation—please try again or describe your symptoms.");
    } finally {
      setResetting(false);
      focusInput();
    }
  };

  const handleSendMessage = async (retryMessage = null) => {
    const messageToSend = retryMessage || userInput;
    const validationError = validateInput(messageToSend);
    if (validationError) {
      setInputError(validationError);
      return;
    }
    if (loading) return;

    if (isAuthenticated && subscriptionTier === 'free' && messageCount >= CONFIG.MAX_FREE_MESSAGES) {
      setError("Free message limit reached. Please upgrade.");
      addBotMessage("You've reached the free message limit. Upgrade for unlimited access!");
      setTimeout(() => {
        setMessages(prev => [...prev, {
          sender: 'bot',
          text: '',
          isAssessment: false,
          isUpgradeOptions: true,
          upgradeProps: {
            condition: "Message Limit",
            commonName: "Free Tier",
            isMildCase: true,
            requiresUpgrade: true,
            onDismiss: handleDismissUpgrade
          }
        }]);
        setUiState(UI_STATES.ASSESSMENT_COMPLETE);
      }, CONFIG.UPGRADE_OPTIONS_DELAY);
      return;
    }

    const newMessageCount = messageCount + 1;
    setMessageCount(newMessageCount);
    setError(null);
    setInputError(null);

    setMessages(prev => [...prev, {
      sender: 'user',
      text: messageToSend.trim(),
      confidence: null,
      careRecommendation: null,
      isAssessment: false,
      isUpgradeOptions: false
    }]);

    if (!retryMessage) setUserInput('');
    setLoading(true);
    setTyping(true);

    requestAnimationFrame(() => {
      scrollToBottomImmediate();
      focusInput();
    });

    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      const token = localStorage.getItem('jwt_token');
      const conversationHistory = messages.map(msg => ({
        message: msg.text,
        isBot: msg.sender === 'bot'
      }));

      const response = await fetch(CONFIG.API_URL, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token && { 'Authorization': `Bearer ${token}` })
        },
        body: JSON.stringify({
          symptom: messageToSend,
          conversation_history: conversationHistory,
          context_notes: "Focus on the user's input and history. Ask one clear question at a time if more info is needed.",
          reset: false
        }),
        signal: controller.signal
      });

      if (!response.ok) {
        if (response.status === 401) throw new Error("Authentication required—please log in.");
        if (response.status === 403) throw new Error("Upgrade required to continue.");
        throw new Error(`API error: ${response.status}`);
      }

      const responseData = await response.json();
      setLatestResponseData(responseData);
      setLoading(false);
      setTyping(false);

      if (CONFIG.DEBUG_MODE) {
        console.log("API response:", responseData);
        console.log("API response structure:", {
          hasResponse: !!responseData.response,
          responseType: typeof responseData.response,
          isAssessment: responseData.response?.is_assessment,
          isQuestion: responseData.response?.is_question,
          confidence: responseData.response?.confidence,
          possibleConditions: responseData.response?.possible_conditions
        });
      }

      const requiresUpgrade = responseData.requires_upgrade === true;

      if (responseData.message) {
        addBotMessage(responseData.message);
      } else if (typeof responseData.response === 'string') {
        addBotMessage(responseData.response);
      } else if (responseData.response && responseData.response.is_assessment) {
        console.log("Processing assessment:", responseData.response);

        const conditionName = responseData.response.possible_conditions || "Unknown condition";
        const triageLevel = responseData.response.triage_level || "unknown";
        const careRecommendation = responseData.response.care_recommendation || "";
        const confidence = responseData.response.confidence || 
                          (responseData.response.assessment?.confidence) || 
                          (responseData.response.assessment?.conditions?.[0]?.confidence) || 
                          95;

        let medicalTerm = "";
        let commonName = "";
        if (typeof conditionName === 'string') {
          const match = conditionName.match(/([^(]+)\s*\(([^)]+)\)/);
          if (match) {
            medicalTerm = match[1].trim();
            commonName = match[2].trim();
          } else {
            medicalTerm = conditionName.replace(/\*/g, '').trim();
            commonName = medicalTerm;
          }
        } else {
          medicalTerm = "Unknown condition";
          commonName = "Unknown condition";
        }

        setLatestAssessment({
          condition: medicalTerm,
          commonName: commonName,
          confidence,
          triageLevel,
          recommendation: careRecommendation
        });

        const assessmentMessage = `I've identified ${commonName} (${medicalTerm}) as a possible condition.\n\nConfidence: ${confidence}%`;
        addBotMessage(assessmentMessage, true, confidence, null, null);

        setTimeout(() => {
          const recommendationMessage = `Severity: ${triageLevel.toUpperCase()}\nRecommendation: ${careRecommendation}`;
          addBotMessage(recommendationMessage);

          setTimeout(() => {
            const isMildCase = triageLevel?.toLowerCase() === "mild" || careRecommendation?.toLowerCase().includes("manage at home");
            const salesPitchMessage = isMildCase
              ? "Good news—it looks manageable at home! Upgrade for detailed insights."
              : "For deeper analysis and next steps, consider upgrading:";
            addBotMessage(salesPitchMessage);

            setTimeout(() => {
              setMessages(prev => [...prev, {
                sender: 'bot',
                text: '',
                isAssessment: false,
                isUpgradeOptions: true,
                upgradeProps: {
                  condition: medicalTerm,
                  commonName: commonName,
                  isMildCase: isMildCase,
                  requiresUpgrade: requiresUpgrade,
                  confidence,
                  triageLevel,
                  recommendation: careRecommendation,
                  onDismiss: handleDismissUpgrade
                }
              }]);
              setUiState(UI_STATES.ASSESSMENT_COMPLETE);
            }, CONFIG.UPGRADE_OPTIONS_DELAY);
          }, CONFIG.SALES_PITCH_DELAY);
        }, CONFIG.ASSESSMENT_DELAY);
      } else if (requiresUpgrade && latestAssessment) {
        const isMildCase = latestAssessment.triageLevel?.toLowerCase() === "mild" || 
                          latestAssessment.recommendation?.toLowerCase().includes("manage at home");
        setMessages(prev => [...prev, {
          sender: 'bot',
          text: '',
          isAssessment: false,
          isUpgradeOptions: true,
          upgradeProps: {
            condition: latestAssessment.condition,
            commonName: latestAssessment.commonName,
            isMildCase: isMildCase,
            requiresUpgrade: true,
            confidence: latestAssessment.confidence,
            triageLevel: latestAssessment.triageLevel,
            recommendation: latestAssessment.recommendation,
            onDismiss: handleDismissUpgrade
          }
        }]);
        setUiState(UI_STATES.ASSESSMENT_COMPLETE);
      } else {
        addBotMessage(responseData.response?.next_question || responseData.response?.possible_conditions || "Can you tell me more about your symptoms?");
      }
    } catch (error) {
      setLoading(false);
      setTyping(false);
      if (error.name !== 'AbortError') {
        if (CONFIG.DEBUG_MODE) console.error("API error:", error);
        setError(error.message || "I'm having trouble connecting—please try again.");
        addBotMessage("I'm sorry, I couldn't process that right now. Please try again, or let me know how I can assist further!");
      }
    }
  };

  const handleKeyDown = (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      handleSendMessage();
    }
  };

  return (
    <ChatErrorBoundary>
      <div className="chat-container" role="main" aria-label="Chat interface">
        <div className="reset-button-container">
          <button
            className="reset-button"
            onClick={handleResetConversation}
            disabled={loading || resetting}
            aria-label="Reset conversation"
          >
            {resetting ? 'Resetting...' : 'Reset Conversation'}
          </button>
        </div>

        <div className="messages-container" role="log" aria-live="polite">
          {messages.map((msg, index) => (
            msg.isUpgradeOptions ? (
              <UpgradePrompt key={index} {...msg.upgradeProps} />
            ) : (
              <Message 
                key={index} 
                message={msg} 
                onRetry={handleRetry} 
                index={index} 
              />
            )
          ))}

          {typing && (
            <div className="message-row">
              <div className="avatar-container">
                <img src="/doctor-avatar.png" alt="AI Assistant" />
              </div>
              <div className="typing-indicator">
                <span></span><span></span><span></span>
              </div>
            </div>
          )}

          {loading && !typing && (
            <div className="loading-indicator" aria-live="polite">
              <div className="loading-spinner"></div>
              <span>Analyzing...</span>
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
              onChange={(e) => { setUserInput(e.target.value); setInputError(null); }}
              onKeyDown={handleKeyDown}
              placeholder={hasFinalAssessment ? "Reset to discuss new symptoms" : "Describe your symptoms..."}
              disabled={loading || resetting || hasFinalAssessment}
              maxLength={CONFIG.MAX_MESSAGE_LENGTH}
              aria-label="Symptom input"
              aria-invalid={!!inputError}
              aria-describedby={inputError ? "input-error" : undefined}
              autoFocus={true}
            />
            <button
              className="send-button"
              onClick={() => handleSendMessage()}
              disabled={loading || resetting || !userInput.trim() || hasFinalAssessment}
              aria-label="Send message"
            >
              Send
            </button>
          </div>
          {inputError && <div id="input-error" className="input-error" role="alert">{inputError}</div>}
        </div>
      </div>
    </ChatErrorBoundary>
  );
};

Chat.propTypes = {
  maxFreeMessages: PropTypes.number,
  apiUrl: PropTypes.string,
  thinkingDelay: PropTypes.number
};

Chat.defaultProps = {
  maxFreeMessages: CONFIG.MAX_FREE_MESSAGES,
  apiUrl: CONFIG.API_URL,
  thinkingDelay: CONFIG.THINKING_DELAY
};

export default Chat;