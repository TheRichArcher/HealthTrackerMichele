import React, { useState, useRef, useEffect, useCallback, memo } from 'react';
import axios from 'axios';
import PropTypes from 'prop-types';
import { debounce } from 'lodash';
import '../styles/Chat.css';

// Import the ChatOnboarding component (assumed to exist in your project)
import ChatOnboarding from './ChatOnboarding';

// Define UI state enum
const UI_STATES = {
  DEFAULT: 'default',
  ASSESSMENT: 'assessment',
  UPGRADE_PROMPT: 'upgrade_prompt',
  ASSESSMENT_WITH_UPGRADE: 'assessment_with_upgrade', // New state for combined assessment + upgrade
  SECONDARY_PROMPT: 'secondary_prompt'
};

// Configuration constants
const CONFIG = {
    MAX_FREE_MESSAGES: 15,
    TYPING_SPEED: 30,
    THINKING_DELAY: 1000,
    API_TIMEOUT: 10000,
    API_URL: '/api/symptoms/analyze', // Use relative URL for same-origin deployment
    RESET_URL: '/api/symptoms/reset',
    MAX_MESSAGE_LENGTH: 1000,
    MIN_MESSAGE_LENGTH: 1, // Allows short responses like "yes" or "no"
    SCROLL_DEBOUNCE_DELAY: 100,
    LOCAL_STORAGE_KEY: 'healthtracker_chat_messages',
    DEBUG_MODE: process.env.NODE_ENV === 'development'
};

// Enhanced welcome message with example prompts
const WELCOME_MESSAGE = {
    sender: 'bot',
    text: "Hi, I'm Michele—your AI medical assistant. Think of me as that doctor you absolutely trust, here to listen, guide, and help you make sense of your symptoms. While I can't replace a real doctor, I can give you insights, ask the right questions, and help you feel more in control of your health.\n\nYou can start by describing your symptoms like:\n• \"I've had a headache for two days\"\n• \"My throat is sore and I have a fever\"\n• \"I have a rash on my arm that's itchy\"",
    confidence: null,
    careRecommendation: null,
    isAssessment: false
};

// Error boundary component to handle runtime errors gracefully
class ChatErrorBoundary extends React.Component {
    state = { hasError: false };

    static getDerivedStateFromError(error) {
        return { hasError: true };
    }

    componentDidCatch(error, errorInfo) {
        if (CONFIG.DEBUG_MODE) {
            console.error('Chat Error:', error, errorInfo);
        }
    }

    render() {
        if (this.state.hasError) {
            return (
                <div className="error-boundary" role="alert">
                    <h2>Something went wrong</h2>
                    <button onClick={() => window.location.reload()}>
                        Refresh Page
                    </button>
                </div>
            );
        }
        return this.props.children;
    }
}

// Memoized Message component for rendering individual chat messages
const Message = memo(({ message, onRetry, index, hideAssessmentDetails }) => {
    const { sender, text, confidence, careRecommendation, isAssessment, triageLevel, className } = message;

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

    return (
        <div className={`message-row ${sender === 'user' ? 'user' : ''}`}>
            <div className="avatar-container">
                {avatarContent}
            </div>
            <div className={`message ${sender} ${className || ''}`}>
                {isAssessment && !hideAssessmentDetails && (
                    <div className="assessment-indicator">Assessment</div>
                )}
                <div className="message-content">
                    {text.split('\n').map((line, i) => (
                        <p key={i}>{line}</p>
                    ))}
                </div>
                {/* Only show metrics if this is an assessment AND we're not hiding details */}
                {sender === 'bot' && isAssessment && !hideAssessmentDetails && (confidence || careRecommendation || triageLevel) && (
                    <div className="assessment-info">
                        {confidence && (
                            <div 
                                className="assessment-item confidence"
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

Message.displayName = 'Message';
Message.propTypes = {
    message: PropTypes.shape({
        sender: PropTypes.string.isRequired,
        text: PropTypes.string.isRequired,
        confidence: PropTypes.number,
        careRecommendation: PropTypes.string,
        isAssessment: PropTypes.bool,
        triageLevel: PropTypes.string,
        className: PropTypes.string
    }).isRequired,
    onRetry: PropTypes.func.isRequired,
    index: PropTypes.number.isRequired,
    hideAssessmentDetails: PropTypes.bool
};

// Memoized Assessment Summary component to display sticky assessment info
const AssessmentSummary = memo(({ assessment }) => {
    if (!assessment) return null;
    
    return (
        <div 
            className="assessment-summary" 
            role="region" 
            aria-label="Assessment summary"
        >
            <h4>Assessment Summary</h4>
            <div className="assessment-condition">
                <strong>Condition:</strong> {assessment.condition}
                {assessment.confidence && (
                    <span> - {assessment.confidence}% confidence</span>
                )}
            </div>
            {assessment.recommendation && (
                <div className="assessment-recommendation">
                    <strong>Recommendation:</strong> {assessment.recommendation}
                </div>
            )}
        </div>
    );
});

AssessmentSummary.displayName = 'AssessmentSummary';
AssessmentSummary.propTypes = {
    assessment: PropTypes.shape({
        condition: PropTypes.string,
        confidence: PropTypes.number,
        recommendation: PropTypes.string
    })
};

// Main Chat component
const Chat = () => {
    const [messages, setMessages] = useState(() => {
        try {
            const savedMessages = localStorage.getItem(CONFIG.LOCAL_STORAGE_KEY);
            return savedMessages ? JSON.parse(savedMessages) : [WELCOME_MESSAGE];
        } catch (error) {
            if (CONFIG.DEBUG_MODE) {
                console.error('Error loading saved messages:', error);
            }
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
    const [currentBotMessage, setCurrentBotMessage] = useState('');
    const [isTypingComplete, setIsTypingComplete] = useState(true);
    const [botMessageCount, setBotMessageCount] = useState(0); // Counter for bot messages
    const [uiState, setUiState] = useState(UI_STATES.DEFAULT); // Unified UI state
    const [loadingSubscription, setLoadingSubscription] = useState(false); // Upgrade button loading states
    const [loadingOneTime, setLoadingOneTime] = useState(false);
    const [latestAssessment, setLatestAssessment] = useState(null); // Sticky assessment state
    const [showChatOnboarding, setShowChatOnboarding] = useState(() => {
        return !localStorage.getItem('healthtracker_chat_onboarding_complete');
    });

    const messagesEndRef = useRef(null);
    const abortControllerRef = useRef(null);
    const chatContainerRef = useRef(null);
    const inputRef = useRef(null);
    const messagesContainerRef = useRef(null);
    const upgradeOptionsRef = useRef(null);

    // Debug mode toggle (development only)
    useEffect(() => {
        if (CONFIG.DEBUG_MODE) {
            const handleKeyPress = (e) => {
                if (e.ctrlKey && e.shiftKey && e.key === 'D') {
                    console.log('Current UI State:', uiState);
                    console.log('Latest Assessment:', latestAssessment);
                    console.log('Message Count:', messageCount);
                    console.log('Bot Message Count:', botMessageCount);
                    console.log('Current Messages:', messages);
                }
            };
            window.addEventListener('keydown', handleKeyPress);
            return () => window.removeEventListener('keydown', handleKeyPress);
        }
    }, [uiState, latestAssessment, messageCount, botMessageCount, messages]);

    // Force focus on input field
    const forceFocus = useCallback(() => {
        if (inputRef.current) {
            setTimeout(() => inputRef.current?.focus(), 0);
            setTimeout(() => inputRef.current?.focus(), 100);
            setTimeout(() => inputRef.current?.focus(), 500);
        }
    }, []);

    // Auto-focus and container click handler
    useEffect(() => {
        forceFocus();
        const container = chatContainerRef.current;
        if (container) {
            const handleContainerClick = (e) => {
                if (
                    e.target.tagName !== 'BUTTON' && 
                    e.target.tagName !== 'A' && 
                    e.target.tagName !== 'INPUT' && 
                    e.target.tagName !== 'TEXTAREA'
                ) {
                    inputRef.current?.focus();
                }
            };
            container.addEventListener('click', handleContainerClick);
            return () => container.removeEventListener('click', handleContainerClick);
        }
    }, [forceFocus]);

    // Save messages to localStorage
    useEffect(() => {
        try {
            if (messages.length > 0 && isTypingComplete) {
                localStorage.setItem(CONFIG.LOCAL_STORAGE_KEY, JSON.stringify(messages));
            }
        } catch (error) {
            if (CONFIG.DEBUG_MODE) {
                console.error('Error saving messages:', error);
            }
        }
    }, [messages, isTypingComplete]);

    // Enhanced scroll function
    const scrollToBottom = useCallback((force = false) => {
        requestAnimationFrame(() => {
            const container = messagesContainerRef.current;
            if (!container) return;

            const stickyHeight = document.querySelector('.assessment-summary')?.offsetHeight || 0;
            const isNearBottom = container.scrollHeight - container.scrollTop <= container.clientHeight + 100;
            
            if (force || isNearBottom || !typing) {
                container.scrollTop = container.scrollHeight;
                if (messagesEndRef.current) {
                    messagesEndRef.current.scrollIntoView({ behavior: "auto", block: "end" });
                }
                setTimeout(() => {
                    if (container) container.scrollTop = container.scrollHeight;
                }, 100);
            }
            
            if (CONFIG.DEBUG_MODE) {
                console.log({ 
                    scrollTop: container.scrollTop, 
                    scrollHeight: container.scrollHeight, 
                    clientHeight: container.clientHeight,
                    isNearBottom,
                    stickyHeight
                });
            }
        });
    }, [typing]);

    // MutationObserver for dynamic content changes
    useEffect(() => {
        if (messagesContainerRef.current) {
            const observer = new MutationObserver((mutations) => {
                for (const mutation of mutations) {
                    if (mutation.addedNodes.length > 0) {
                        scrollToBottom();
                    }
                }
            });
            observer.observe(messagesContainerRef.current, { childList: true, subtree: true });
            return () => observer.disconnect();
        }
    }, [scrollToBottom]);

    // Scroll when messages change
    useEffect(() => {
        if (messages.length > 0) {
            scrollToBottom(true);
            const timeouts = [
                setTimeout(() => scrollToBottom(true), 100),
                setTimeout(() => scrollToBottom(true), 500)
            ];
            return () => timeouts.forEach(clearTimeout);
        }
    }, [messages, scrollToBottom]);

    // Scroll when upgrade options appear
    useEffect(() => {
        if (uiState === UI_STATES.UPGRADE_PROMPT || uiState === UI_STATES.ASSESSMENT_WITH_UPGRADE) {
            scrollToBottom(true);
            const timeouts = [
                setTimeout(() => {
                    scrollToBottom(true);
                    if (upgradeOptionsRef.current) {
                        upgradeOptionsRef.current.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    }
                }, 300),
                setTimeout(() => scrollToBottom(true), 800)
            ];
            return () => timeouts.forEach(clearTimeout);
        }
    }, [uiState, scrollToBottom]);

    // Update UI state for assessments
    useEffect(() => {
        if (latestAssessment && !typing && isTypingComplete && uiState === UI_STATES.DEFAULT) {
            setUiState(UI_STATES.ASSESSMENT);
            setTimeout(() => {
                const container = messagesContainerRef.current;
                if (container) {
                    const lastMessage = container.querySelector('.message-row:last-child');
                    if (lastMessage) {
                        lastMessage.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    } else {
                        scrollToBottom(true);
                    }
                }
            }, 100);
        }
    }, [latestAssessment, typing, isTypingComplete, uiState, scrollToBottom]);

    // Cleanup abort controller
    useEffect(() => {
        return () => {
            if (abortControllerRef.current) {
                abortControllerRef.current.abort();
            }
        };
    }, []);

    const validateInput = useCallback((input) => {
        if (!input.trim()) return "Please enter a message";
        if (input.length > CONFIG.MAX_MESSAGE_LENGTH) return "Message is too long";
        return null;
    }, []);

    // Type message without mid-typing scroll to prevent bouncing
    const typeMessage = useCallback((message, isAssessment = false, confidence = null, triageLevel = null, careRecommendation = null) => {
        if (isAssessment && (uiState === UI_STATES.ASSESSMENT || uiState === UI_STATES.ASSESSMENT_WITH_UPGRADE)) {
            message = "Based on your symptoms, I've completed an assessment. Please see the summary below.";
        }
        
        let index = 0;
        setIsTypingComplete(false);
        setCurrentBotMessage('');

        const interval = setInterval(() => {
            if (index < message.length) {
                setCurrentBotMessage(prev => message.slice(0, index + 1));
                index++;
            } else {
                clearInterval(interval);
                if (!isAssessment) setBotMessageCount(prev => prev + 1);
                setMessages(prev => [...prev, {
                    sender: 'bot',
                    text: message,
                    isAssessment,
                    confidence,
                    triageLevel,
                    careRecommendation,
                    className: isAssessment ? 'assessment-message' : ''
                }]);
                setCurrentBotMessage('');
                setTyping(false);
                setIsTypingComplete(true);
                
                // Multiple delayed scrolls to ensure visibility
                scrollToBottom(true);
                setTimeout(() => scrollToBottom(true), 50);
                setTimeout(() => scrollToBottom(true), 150);
                setTimeout(() => scrollToBottom(true), 300);
                setTimeout(() => scrollToBottom(true), 600);
                
                forceFocus();
            }
        }, CONFIG.TYPING_SPEED);
    }, [scrollToBottom, forceFocus, uiState, botMessageCount]);

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
        try {
            await axios.post(CONFIG.RESET_URL);
            setMessages([WELCOME_MESSAGE]);
            setMessageCount(0);
            setBotMessageCount(0);
            setError(null);
            setInputError(null);
            setCurrentBotMessage('');
            setIsTypingComplete(true);
            setLoadingSubscription(false);
            setLoadingOneTime(false);
            setLatestAssessment(null);
            setUiState(UI_STATES.DEFAULT);
            localStorage.setItem(CONFIG.LOCAL_STORAGE_KEY, JSON.stringify([WELCOME_MESSAGE]));
            forceFocus();
            if (CONFIG.DEBUG_MODE) console.log("Conversation reset successfully");
        } catch (error) {
            if (CONFIG.DEBUG_MODE) console.error("Error resetting conversation:", error);
            setMessages([WELCOME_MESSAGE]);
            setMessageCount(0);
            setBotMessageCount(0);
            setCurrentBotMessage('');
            setIsTypingComplete(true);
            setLoadingSubscription(false);
            setLoadingOneTime(false);
            setLatestAssessment(null);
            setUiState(UI_STATES.DEFAULT);
            localStorage.setItem(CONFIG.LOCAL_STORAGE_KEY, JSON.stringify([WELCOME_MESSAGE]));
        } finally {
            setResetting(false);
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

        const newMessageCount = messageCount + 1;
        setMessageCount(newMessageCount);
        setError(null);
        setInputError(null);

        if (newMessageCount >= CONFIG.MAX_FREE_MESSAGES && uiState === UI_STATES.DEFAULT) {
            setUiState(UI_STATES.UPGRADE_PROMPT);
            return;
        }

        setMessages(prev => [...prev, {
            sender: 'user',
            text: messageToSend.trim(),
            confidence: null,
            careRecommendation: null,
            isAssessment: false
        }]);
        
        if (uiState === UI_STATES.DEFAULT && messageCount > CONFIG.MAX_FREE_MESSAGES) {
            setUiState(UI_STATES.SECONDARY_PROMPT);
            const userMessages = messages.filter(msg => msg.sender === 'user');
            const latestUserMessage = userMessages.length > 0 ? userMessages[userMessages.length - 1].text : "your symptoms";
            const symptomSnippet = latestUserMessage.length > 30 ? latestUserMessage.substring(0, 30) + "..." : latestUserMessage;
            setTimeout(() => {
                setMessages(prev => [...prev, {
                    sender: 'bot',
                    text: `🔎 You mentioned "${symptomSnippet}". Want a deeper understanding? Unlock Premium Access for continuous tracking or get a one-time Consultation Report for a detailed summary!`,
                    confidence: null,
                    careRecommendation: null,
                    isAssessment: false
                }]);
                setTimeout(() => scrollToBottom(true), 0);
                setTimeout(() => scrollToBottom(true), 100);
            }, 1000);
        }
        
        if (!retryMessage) setUserInput('');
        setLoading(true);
        setTyping(true);
        forceFocus();
        setTimeout(() => scrollToBottom(true), 0);
        setTimeout(() => scrollToBottom(true), 100);

        if (abortControllerRef.current) abortControllerRef.current.abort();
        abortControllerRef.current = new AbortController();

        try {
            const conversationHistory = messages
                .filter(msg => msg.text.trim() !== "")
                .map(msg => ({
                    message: msg.text,
                    isBot: msg.sender === 'bot'
                }));

            const enhancedRequest = {
                symptom: messageToSend,
                conversation_history: conversationHistory,
                context_notes: "Pay close attention to timing details the user has already mentioned, such as when symptoms started or how long they've been present. Avoid asking redundant questions about information already provided."
            };

            if (CONFIG.DEBUG_MODE) console.log("Sending request with conversation history:", enhancedRequest);

            const response = await axios.post(
                CONFIG.API_URL,
                enhancedRequest,
                {
                    signal: abortControllerRef.current.signal,
                    timeout: CONFIG.API_TIMEOUT
                }
            );

            if (CONFIG.DEBUG_MODE) {
                console.log("Raw API response:", response.data);
                console.log("Requires upgrade:", response.data.requires_upgrade);
                console.log("Is assessment:", response.data.is_assessment);
            }

            setTimeout(() => {
                const isQuestion = response.data.is_question === true;
                const isAssessment = response.data.is_assessment === true;
                const requiresUpgrade = response.data.requires_upgrade === true;
                
                if (isAssessment) {
                    let formattedMessage = '';
                    let confidence = null;
                    let triageLevel = null;
                    let careRecommendation = null;
                    
                    if (response.data.assessment?.conditions) {
                        const conditions = response.data.assessment.conditions;
                        triageLevel = response.data.assessment.triage_level || 'UNKNOWN';
                        careRecommendation = response.data.assessment.care_recommendation || response.data.care_recommendation;
                        const disclaimer = response.data.assessment.disclaimer || "This assessment is for informational purposes only and does not replace professional medical advice.";
                        
                        if (conditions.length > 0) {
                            setLatestAssessment({
                                condition: conditions[0].name,
                                confidence: conditions[0].confidence,
                                recommendation: careRecommendation
                            });
                        }
                        
                        if (requiresUpgrade) {
                            formattedMessage = "Based on your symptoms, I've completed an assessment. Please see the summary below.";
                            typeMessage(formattedMessage, true, conditions[0]?.confidence, triageLevel, null);
                            setUiState(UI_STATES.ASSESSMENT_WITH_UPGRADE);
                        } else {
                            formattedMessage += 'Based on your symptoms, here are some possible conditions:\n\n';
                            conditions.forEach(condition => {
                                formattedMessage += `${condition.name} – ${condition.confidence}%\n`;
                            });
                            formattedMessage += `\n${careRecommendation}\n\n${disclaimer}`;
                            confidence = conditions[0]?.confidence || response.data.confidence;
                            typeMessage(formattedMessage, true, confidence, triageLevel, careRecommendation);
                            setUiState(UI_STATES.ASSESSMENT);
                        }
                    } else {
                        formattedMessage = response.data.possible_conditions || "Based on your symptoms, I can provide an assessment.";
                        confidence = response.data.confidence;
                        triageLevel = response.data.triage_level;
                        careRecommendation = response.data.care_recommendation;
                        
                        setLatestAssessment({
                            condition: "Assessment",
                            confidence: confidence,
                            recommendation: careRecommendation
                        });
                        
                        if (requiresUpgrade) {
                            typeMessage("Based on your symptoms, I've completed an assessment. Please see the summary below.", true, confidence, triageLevel, null);
                            setUiState(UI_STATES.ASSESSMENT_WITH_UPGRADE);
                        } else {
                            typeMessage(formattedMessage, true, confidence, triageLevel, careRecommendation);
                            setUiState(UI_STATES.ASSESSMENT);
                        }
                    }
                } else {
                    const responseText = response.data.question || response.data.possible_conditions || "Could you tell me more about your symptoms?";
                    typeMessage(responseText, false);
                }
            }, CONFIG.THINKING_DELAY);

        } catch (error) {
            if (!axios.isCancel(error)) {
                if (CONFIG.DEBUG_MODE) console.error("API error details:", error);
                let errorMessage = "I apologize, but I'm having trouble processing your request.";
                if (error.response) {
                    if (error.response.status === 429) {
                        errorMessage = "I'm receiving too many requests right now. Please try again in a moment.";
                    } else if (error.response.status >= 500) {
                        errorMessage = "I'm having trouble connecting to my medical knowledge. Please try again shortly.";
                    }
                } else if (error.request) {
                    errorMessage = "I'm having trouble connecting to my medical database. Please check your internet connection and try again.";
                }
                setError(errorMessage);
                setTimeout(() => typeMessage(errorMessage, false), CONFIG.THINKING_DELAY);
            }
        } finally {
            setLoading(false);
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
            <div 
                className={`chat-container ${uiState === UI_STATES.ASSESSMENT_WITH_UPGRADE ? 'assessment-with-upgrade' : ''}`} 
                ref={chatContainerRef} 
                role="main" 
                aria-label="Chat interface"
            >
                <div className="chat-header">
                    <div className="chat-header-left">
                        <img
                            src="/doctor-avatar.png"
                            alt="Dr. Michele"
                            className="chat-avatar"
                            onError={(e) => {
                                e.target.onerror = null;
                                e.target.src = '/default-avatar.png';
                            }}
                        />
                        <div className="chat-header-title">
                            <span className="chat-header-name">HealthTracker AI</span>
                            <span className="chat-header-role">AI Medical Assistant</span>
                        </div>
                    </div>
                    <button 
                        className="reset-button"
                        onClick={handleResetConversation}
                        disabled={loading || resetting}
                        aria-label="Reset conversation"
                    >
                        {resetting ? 'Resetting...' : 'Reset Conversation'}
                    </button>
                    <div className="chat-header-disclaimer">
                        For informational purposes only. Not a substitute for professional medical advice.
                    </div>
                </div>

                <div 
                    className="messages-container" 
                    role="log" 
                    aria-live="polite"
                    ref={messagesContainerRef}
                >
                    {messages.map((msg, index) => (
                        <Message
                            key={index}
                            message={msg}
                            onRetry={handleRetry}
                            index={index}
                            hideAssessmentDetails={(uiState === UI_STATES.ASSESSMENT || uiState === UI_STATES.ASSESSMENT_WITH_UPGRADE) && msg.isAssessment}
                        />
                    ))}
                    
                    {typing && (
                        <div className="message-row">
                            <div className="avatar-container">
                                <img src="/doctor-avatar.png" alt="AI Assistant" />
                            </div>
                            {currentBotMessage ? (
                                <div className="message bot">
                                    <div className="message-content">
                                        {currentBotMessage.split('\n').map((line, i) => (
                                            <p key={i}>{line}</p>
                                        ))}
                                    </div>
                                </div>
                            ) : (
                                <div className="typing-indicator">
                                    <span></span>
                                    <span></span>
                                    <span></span>
                                </div>
                            )}
                        </div>
                    )}
                    
                    {loading && !typing && (
                        <div className="loading-indicator" aria-live="polite">
                            <div className="loading-spinner"></div>
                            <span>Analyzing your symptoms...</span>
                        </div>
                    )}
                    
                    {error && (
                        <div className="error-message" role="alert">
                            {error}
                        </div>
                    )}
                    <div ref={messagesEndRef} />
                </div>

                {(uiState === UI_STATES.ASSESSMENT || uiState === UI_STATES.ASSESSMENT_WITH_UPGRADE) && latestAssessment && (
                    <AssessmentSummary assessment={latestAssessment} />
                )}

                <div className="chat-input-container">
                    <div className="chat-input-wrapper">
                        <textarea
                            ref={inputRef}
                            className="chat-input"
                            value={userInput}
                            onChange={(e) => {
                                setUserInput(e.target.value);
                                setInputError(null);
                            }}
                            onKeyDown={handleKeyDown}
                            placeholder="Describe your symptoms in detail..."
                            disabled={loading || (uiState === UI_STATES.UPGRADE_PROMPT && uiState !== UI_STATES.ASSESSMENT_WITH_UPGRADE) || resetting}
                            maxLength={CONFIG.MAX_MESSAGE_LENGTH}
                            aria-label="Symptom description input"
                            aria-invalid={!!inputError}
                            aria-describedby={inputError ? "input-error" : undefined}
                            autoFocus={true}
                            onFocus={(e) => {
                                const value = e.target.value;
                                e.target.value = '';
                                e.target.value = value;
                            }}
                            onClick={(e) => e.stopPropagation()}
                        />
                        <button
                            className="send-button"
                            onClick={() => handleSendMessage()}
                            disabled={loading || (uiState === UI_STATES.UPGRADE_PROMPT && uiState !== UI_STATES.ASSESSMENT_WITH_UPGRADE) || resetting || !userInput.trim()}
                            aria-label="Send message"
                        >
                            Send
                        </button>
                    </div>
                    {inputError && (
                        <div id="input-error" className="input-error" role="alert">
                            {inputError}
                        </div>
                    )}
                </div>

                {(uiState === UI_STATES.UPGRADE_PROMPT || uiState === UI_STATES.ASSESSMENT_WITH_UPGRADE) && (
                    <div className="upgrade-options" ref={upgradeOptionsRef}>
                        <button 
                            className="close-upgrade" 
                            onClick={() => {
                                setUiState(uiState === UI_STATES.ASSESSMENT_WITH_UPGRADE ? UI_STATES.ASSESSMENT : UI_STATES.DEFAULT);
                                forceFocus();
                            }}
                            aria-label="Dismiss upgrade prompt"
                        >
                            ✖
                        </button>
                        <div className="upgrade-message">
                            <h3>Based on your symptoms, I've identified a condition that may require further evaluation.</h3>
                            <p>💡 To get more insights, you can choose one of these options:</p>
                            <ul>
                                <li>🔹 Premium Access ($9.99/month): Unlimited symptom checks, detailed assessments, and personalized health monitoring.</li>
                                <li>🔹 One-time Consultation Report ($4.99): Get a comprehensive analysis of your current symptoms.</li>
                            </ul>
                            <p>Would you like to continue with one of these options?</p>
                        </div>
                        <div className="upgrade-buttons">
                            <button 
                                className={`upgrade-button subscription ${loadingSubscription ? 'loading' : ''}`}
                                onClick={() => {
                                    if (loadingSubscription || loadingOneTime) return;
                                    setLoadingSubscription(true);
                                    setTimeout(() => window.location.href = '/subscribe', 300);
                                }}
                                disabled={loadingSubscription || loadingOneTime}
                            >
                                {loadingSubscription ? 'Processing...' : '🩺 Get Premium Access ($9.99/month)'}
                            </button>
                            <button 
                                className={`upgrade-button one-time ${loadingOneTime ? 'loading' : ''}`}
                                onClick={() => {
                                    if (loadingSubscription || loadingOneTime) return;
                                    setLoadingOneTime(true);
                                    setTimeout(() => window.location.href = '/one-time-report', 300);
                                }}
                                disabled={loadingSubscription || loadingOneTime}
                            >
                                {loadingOneTime ? 'Processing...' : '📄 Get Consultation Report ($4.99)'}
                            </button>
                        </div>
                    </div>
                )}
                
                {showChatOnboarding && (
                    <ChatOnboarding onComplete={() => setShowChatOnboarding(false)} />
                )}
            </div>
        </ChatErrorBoundary>
    );
};

Chat.propTypes = {
    maxFreeMessages: PropTypes.number,
    apiUrl: PropTypes.string,
    typingSpeed: PropTypes.number,
    thinkingDelay: PropTypes.number
};

Chat.defaultProps = {
    maxFreeMessages: CONFIG.MAX_FREE_MESSAGES,
    apiUrl: CONFIG.API_URL,
    typingSpeed: CONFIG.TYPING_SPEED,
    thinkingDelay: CONFIG.THINKING_DELAY
};

export default Chat;