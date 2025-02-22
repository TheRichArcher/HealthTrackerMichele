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
    API_URL: 'https://healthtrackermichele.onrender.com/api/symptoms/analyze',
    MAX_MESSAGE_LENGTH: 1000,
    MIN_MESSAGE_LENGTH: 3,
    SCROLL_DEBOUNCE_DELAY: 100,
    LOCAL_STORAGE_KEY: 'healthtracker_chat_messages'
};

const WELCOME_MESSAGE = {
    sender: 'bot',
    text: "Hi, I'm Michele—your AI medical assistant. Think of me as that doctor you absolutely trust, here to listen, guide, and help you make sense of your symptoms. While I can't replace a real doctor, I can give you insights, ask the right questions, and help you feel more in control of your health. So, tell me—what's going on today?",
    confidence: null,
    careRecommendation: null
};

// Error Boundary Component
class ChatErrorBoundary extends React.Component {
    constructor(props) {
        super(props);
        this.state = { hasError: false };
    }

    static getDerivedStateFromError(error) {
        return { hasError: true };
    }

    componentDidCatch(error, errorInfo) {
        console.error('Chat Error:', error, errorInfo);
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

// Memoized Message Component
const Message = memo(({ message, onRetry, index }) => {
    const getCareRecommendation = useCallback((level) => {
        switch(level) {
            case 'mild':
                return "You can likely manage this at home";
            case 'severe':
                return "You should seek urgent care";
            case 'moderate':
                return "Consider seeing a doctor soon";
            default:
                return null;
        }
    }, []);
    return (
        <div className={`message ${message.sender}`}>
            <div className="message-content">{message.text}</div>
            {(message.confidence || message.careRecommendation) && (
                <div className="metrics-container">
                    {message.confidence && (
                        <div className="confidence">
                            Confidence: {message.confidence}%
                        </div>
                    )}
                    {message.careRecommendation && (
                        <div className="care-recommendation">
                            {getCareRecommendation(message.careRecommendation)}
                        </div>
                    )}
                </div>
            )}
            {message.sender === 'bot' && message.text.includes("trouble processing") && (
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
        careRecommendation: PropTypes.string
    }).isRequired,
    onRetry: PropTypes.func.isRequired,
    index: PropTypes.number.isRequired
};
const Chat = () => {
    const [messages, setMessages] = useState(() => {
        const savedMessages = localStorage.getItem(CONFIG.LOCAL_STORAGE_KEY);
        return savedMessages ? JSON.parse(savedMessages) : [WELCOME_MESSAGE];
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
        localStorage.setItem(CONFIG.LOCAL_STORAGE_KEY, JSON.stringify(messages));
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

    const typeMessage = useCallback((message, confidence, careRecommendation) => {
        let index = 0;
        setTyping(false);
        setMessages(prev => [...prev, {
            sender: 'bot',
            text: "",
            confidence,
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
                careRecommendation: null
            }]);
            return;
        }

        setMessages(prev => [...prev, {
            sender: 'user',
            text: messageToSend.trim(),
            confidence: null,
            careRecommendation: null
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
                    symptoms: messageToSend,
                    conversation_history: messages
                        .map(msg => ({
                            role: msg.sender === 'user' ? 'user' : 'assistant',
                            content: msg.text
                        }))
                        .slice(1)
                },
                {
                    signal: abortControllerRef.current.signal,
                    timeout: CONFIG.API_TIMEOUT
                }
            );

            const { possible_conditions, triage_level, confidence } = response.data;
            
            const botResponse = possible_conditions || 
                "I need more information to help you better. Could you tell me more about your symptoms?";
            
            setTimeout(() => {
                typeMessage(
                    botResponse,
                    confidence || null,
                    triage_level || null
                );
            }, CONFIG.THINKING_DELAY);

        } catch (error) {
            if (!axios.isCancel(error)) {
                console.error("API error:", error);
                const errorMessage = "I apologize, but I'm having trouble processing your request. Could you try rephrasing that?";
                setError(errorMessage);
                setTimeout(() => {
                    typeMessage(errorMessage, null, null);
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
                            ) : (
                                'Send'
                            )}
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