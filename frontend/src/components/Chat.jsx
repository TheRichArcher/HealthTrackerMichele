import React, { useState, useRef, useEffect, useCallback, memo } from 'react';
import axios from 'axios';
import PropTypes from 'prop-types';
import { debounce } from 'lodash';
import '../styles/Chat.css';

const CONFIG = {
    MAX_FREE_MESSAGES: 15,
    TYPING_SPEED: 30,
    THINKING_DELAY: 1000,
    API_TIMEOUT: 10000,
    API_URL: '/api/symptoms/analyze', // Changed to relative URL for better portability
    MAX_MESSAGE_LENGTH: 1000,
    MIN_MESSAGE_LENGTH: 3,
    SCROLL_DEBOUNCE_DELAY: 100,
    LOCAL_STORAGE_KEY: 'healthtracker_chat_messages',
    DEBUG_MODE: process.env.NODE_ENV === 'development'
};

const WELCOME_MESSAGE = {
    sender: 'bot',
    text: "Hello! I'm your AI medical assistant. Please describe your current symptoms.",
    confidence: null,
    careRecommendation: null,
    isAssessment: false
};

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

const Message = memo(({ message, onRetry, index }) => {
    const { sender, text, confidence, careRecommendation, isAssessment, triageLevel } = message;

    const getCareRecommendation = useCallback((level) => {
        switch(level?.toLowerCase()) {
            case 'mild': return "You can likely manage this at home";
            case 'severe': return "You should seek urgent care";
            case 'moderate': return "Consider seeing a doctor soon";
            default: return null;
        }
    }, []);

    return (
        <div className={`message ${sender}`}>
            <div className="message-content">
                {text.split('\n').map((line, i) => (
                    <p key={i}>{line}</p>
                ))}
            </div>
            {/* Only show metrics if this is an assessment */}
            {sender === 'bot' && isAssessment && (confidence || careRecommendation || triageLevel) && (
                <div className="metrics-container">
                    {confidence && (
                        <div className="confidence">
                            Confidence: {confidence}%
                        </div>
                    )}
                    {(careRecommendation || triageLevel) && (
                        <div className="care-recommendation">
                            {careRecommendation || getCareRecommendation(triageLevel)}
                        </div>
                    )}
                    {triageLevel && (
                        <div className="triage-level">
                            <span className={`triage-badge ${triageLevel?.toLowerCase()}`}>
                                {triageLevel}
                            </span>
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
        triageLevel: PropTypes.string
    }).isRequired,
    onRetry: PropTypes.func.isRequired,
    index: PropTypes.number.isRequired
};

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
    const [signupPrompt, setSignupPrompt] = useState(false);
    const [typing, setTyping] = useState(false);
    const [error, setError] = useState(null);
    const [inputError, setInputError] = useState(null);

    const messagesEndRef = useRef(null);
    const abortControllerRef = useRef(null);
    const chatContainerRef = useRef(null);

    useEffect(() => {
        try {
            localStorage.setItem(CONFIG.LOCAL_STORAGE_KEY, JSON.stringify(messages));
        } catch (error) {
            if (CONFIG.DEBUG_MODE) {
                console.error('Error saving messages:', error);
            }
        }
    }, [messages]);

    const debouncedScrollToBottom = useCallback(
        debounce(() => {
            messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
        }, CONFIG.SCROLL_DEBOUNCE_DELAY),
        []
    );

    useEffect(() => {
        debouncedScrollToBottom();
        return () => debouncedScrollToBottom.cancel();
    }, [messages, debouncedScrollToBottom]);

    useEffect(() => {
        return () => {
            if (abortControllerRef.current) {
                abortControllerRef.current.abort();
            }
        };
    }, []);

    const validateInput = useCallback((input) => {
        if (!input.trim()) return "Please enter a message";
        if (input.length < CONFIG.MIN_MESSAGE_LENGTH) {
            return "Please provide more details about your symptoms";
        }
        if (input.length > CONFIG.MAX_MESSAGE_LENGTH) {
            return "Message is too long";
        }
        return null;
    }, []);

    const typeMessage = useCallback((message, isAssessment = false, confidence = null, triageLevel = null, careRecommendation = null) => {
        let index = 0;
        setTyping(false);
        setMessages(prev => [...prev, {
            sender: 'bot',
            text: "",
            isAssessment,
            confidence,
            triageLevel,
            careRecommendation
        }]);

        const interval = setInterval(() => {
            setMessages(prev => {
                const updatedMessages = [...prev];
                const lastMessageIndex = updatedMessages.length - 1;
                if (lastMessageIndex >= 0 && index < message.length) {
                    updatedMessages[lastMessageIndex].text = message.slice(0, index + 1);
                }
                return updatedMessages;
            });
            index++;
            if (index >= message.length) clearInterval(interval);
        }, CONFIG.TYPING_SPEED);
    }, []);

    const handleRetry = useCallback(async (messageIndex) => {
        const originalMessage = messages[messageIndex - 1];
        if (originalMessage && originalMessage.sender === 'user') {
            setMessages(messages => messages.slice(0, messageIndex));
            setUserInput(originalMessage.text);
            await handleSendMessage(originalMessage.text);
        }
    }, [messages]);

    const handleSendMessage = async (retryMessage = null) => {
        const messageToSend = retryMessage || userInput;
        const validationError = validateInput(messageToSend);
        
        if (validationError) {
            setInputError(validationError);
            return;
        }

        if (signupPrompt || loading) return;

        const newMessageCount = messageCount + 1;
        setMessageCount(newMessageCount);
        setError(null);
        setInputError(null);

        if (newMessageCount >= CONFIG.MAX_FREE_MESSAGES) {
            setSignupPrompt(true);
            setMessages(prev => [...prev, {
                sender: 'bot',
                text: "You've reached the free message limit. Sign up to continue!",
                confidence: null,
                careRecommendation: null,
                isAssessment: false
            }]);
            return;
        }

        setMessages(prev => [...prev, {
            sender: 'user',
            text: messageToSend.trim(),
            confidence: null,
            careRecommendation: null,
            isAssessment: false
        }]);
        
        if (!retryMessage) setUserInput('');
        setLoading(true);
        setTyping(true);

        if (abortControllerRef.current) {
            abortControllerRef.current.abort();
        }
        abortControllerRef.current = new AbortController();

        try {
            const response = await axios.post(
                CONFIG.API_URL,
                {
                    symptom: messageToSend,
                    conversation_history: messages
                        .filter(msg => msg.text.trim() !== "") // Filter out empty messages
                        .map(msg => ({
                            message: msg.text,
                            isBot: msg.sender === 'bot'
                        }))
                },
                {
                    signal: abortControllerRef.current.signal,
                    timeout: CONFIG.API_TIMEOUT
                }
            );

            // Debug logging
            if (CONFIG.DEBUG_MODE) {
                console.log("Raw API response:", response.data);
            }

            setTimeout(() => {
                // Handle the response based on whether it's a question or assessment
                if (response.data.is_assessment) {
                    // It's a final assessment with conditions
                    const conditions = response.data.assessment?.conditions || [];
                    const triageLevel = response.data.assessment?.triage_level || 'UNKNOWN';
                    const careRecommendation = response.data.assessment?.care_recommendation || '';
                    const disclaimer = response.data.assessment?.disclaimer || '';
                    
                    // Format the message for display
                    let formattedMessage = '';
                    
                    if (conditions.length > 0) {
                        formattedMessage += 'Based on your symptoms, here are some possible conditions:\n\n';
                        conditions.forEach(condition => {
                            formattedMessage += `${condition.name} – ${condition.confidence}%\n`;
                        });
                        formattedMessage += `\n${careRecommendation}\n\n${disclaimer}`;
                    } else {
                        formattedMessage = "I need more information to provide an assessment. Could you tell me more about your symptoms?";
                    }
                    
                    typeMessage(
                        formattedMessage,
                        true,
                        conditions[0]?.confidence || null,
                        triageLevel,
                        careRecommendation
                    );
                } else {
                    // It's a follow-up question
                    const question = response.data.question || "Could you tell me more about your symptoms?";
                    typeMessage(question, false);
                }
            }, CONFIG.THINKING_DELAY);

        } catch (error) {
            if (!axios.isCancel(error)) {
                if (CONFIG.DEBUG_MODE) {
                    console.error("API error details:", error);
                }
                const errorMessage = "I apologize, but I'm having trouble processing your request. Could you try rephrasing that?";
                setError(errorMessage);
                setTimeout(() => {
                    typeMessage(errorMessage, false);
                }, CONFIG.THINKING_DELAY);
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
            <div className="chat-container" ref={chatContainerRef} role="main" aria-label="Chat interface">
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
                    <div className="chat-header-disclaimer">
                        For informational purposes only. Not a substitute for professional medical advice.
                    </div>
                </div>

                <div className="messages-container" role="log" aria-live="polite">
                    {messages.map((msg, index) => (
                        <Message
                            key={index}
                            message={msg}
                            onRetry={handleRetry}
                            index={index}
                        />
                    ))}
                    {typing && (
                        <div className="typing-indicator" aria-live="polite">
                            Michele is typing...
                        </div>
                    )}
                    {error && (
                        <div className="error-message" role="alert">
                            {error}
                        </div>
                    )}
                    <div ref={messagesEndRef} />
                </div>

                <div className="chat-input-container">
                    <div className="chat-input-form">
                        <textarea
                            className={`chat-input ${inputError ? 'error' : ''}`}
                            value={userInput}
                            onChange={(e) => {
                                setUserInput(e.target.value);
                                setInputError(null);
                            }}
                            onKeyDown={handleKeyDown}
                            placeholder="Describe your symptoms in detail..."
                            disabled={loading || signupPrompt}
                            maxLength={CONFIG.MAX_MESSAGE_LENGTH}
                            aria-label="Symptom description input"
                            aria-invalid={!!inputError}
                            aria-describedby={inputError ? "input-error" : undefined}
                        />
                        {inputError && (
                            <div id="input-error" className="input-error" role="alert">
                                {inputError}
                            </div>
                        )}
                        <button
                            className={`send-button ${loading ? 'loading' : ''}`}
                            onClick={() => handleSendMessage()}
                            disabled={loading || signupPrompt || !userInput.trim()}
                            aria-label="Send message"
                        >
                            {loading ? (
                                <span className="loading-spinner" aria-hidden="true" />
                            ) : 'Send'}
                        </button>
                    </div>
                </div>
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