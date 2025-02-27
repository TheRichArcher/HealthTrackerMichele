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
    API_URL: '/api/symptoms/analyze', // Use relative URL for same-origin deployment
    RESET_URL: '/api/symptoms/reset',
    MAX_MESSAGE_LENGTH: 1000,
    MIN_MESSAGE_LENGTH: 1, // Changed from 3 to 1 to allow short responses
    SCROLL_DEBOUNCE_DELAY: 100,
    LOCAL_STORAGE_KEY: 'healthtracker_chat_messages',
    DEBUG_MODE: process.env.NODE_ENV === 'development'
};

const WELCOME_MESSAGE = {
    sender: 'bot',
    text: "Hi, I'm Michele—your AI medical assistant. Think of me as that doctor you absolutely trust, here to listen, guide, and help you make sense of your symptoms. While I can't replace a real doctor, I can give you insights, ask the right questions, and help you feel more in control of your health. So, tell me—what's going on today?",
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
            <div className={`message ${sender}`}>
                <div className="message-content">
                    {text.split('\n').map((line, i) => (
                        <p key={i}>{line}</p>
                    ))}
                </div>
                {/* Only show metrics if this is an assessment */}
                {sender === 'bot' && isAssessment && (confidence || careRecommendation || triageLevel) && (
                    <div className="assessment-info">
                        {confidence && (
                            <div className="assessment-item confidence">
                                Confidence: {confidence}%
                            </div>
                        )}
                        {(careRecommendation || triageLevel) && (
                            <div className="assessment-item care-recommendation">
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
    const [resetting, setResetting] = useState(false);

    const messagesEndRef = useRef(null);
    const abortControllerRef = useRef(null);
    const chatContainerRef = useRef(null);
    const inputRef = useRef(null);
    const messagesContainerRef = useRef(null);

    // Force focus on input field - more aggressive approach
    const forceFocus = useCallback(() => {
        if (inputRef.current) {
            // Try multiple times with increasing delays
            setTimeout(() => inputRef.current?.focus(), 0);
            setTimeout(() => inputRef.current?.focus(), 100);
            setTimeout(() => inputRef.current?.focus(), 500);
        }
    }, []);

    // Auto-focus when component mounts
    useEffect(() => {
        forceFocus();
        // Also add a click handler to the container to focus input when clicked
        const container = chatContainerRef.current;
        if (container) {
            const handleContainerClick = (e) => {
                // Only focus if we're not clicking on another interactive element
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

    // Save messages to localStorage when they change
    useEffect(() => {
        try {
            // Only save if we have meaningful messages to save
            if (messages.length > 0 && !typing) {
                localStorage.setItem(CONFIG.LOCAL_STORAGE_KEY, JSON.stringify(messages));
            }
        } catch (error) {
            if (CONFIG.DEBUG_MODE) {
                console.error('Error saving messages:', error);
            }
        }
    }, [messages, typing]);

    // Improved scroll function with multiple approaches
    const scrollToBottom = useCallback(() => {
        // Method 1: Using scrollIntoView
        if (messagesEndRef.current) {
            messagesEndRef.current.scrollIntoView({ behavior: "smooth", block: "end" });
        }
        
        // Method 2: Direct scrollTop manipulation
        if (messagesContainerRef.current) {
            const container = messagesContainerRef.current;
            container.scrollTop = container.scrollHeight;
        }
    }, []);

    // Scroll when messages change or typing state changes
    useEffect(() => {
        // Immediate scroll
        scrollToBottom();
        
        // Delayed scrolls to handle content rendering
        const timeouts = [
            setTimeout(scrollToBottom, 100),
            setTimeout(scrollToBottom, 500),
            setTimeout(scrollToBottom, 1000)
        ];
        
        return () => timeouts.forEach(clearTimeout);
    }, [messages, typing, scrollToBottom]);

    // Scroll during typing animation
    useEffect(() => {
        if (typing) {
            const interval = setInterval(scrollToBottom, 500);
            return () => clearInterval(interval);
        }
    }, [typing, scrollToBottom]);

    useEffect(() => {
        return () => {
            if (abortControllerRef.current) {
                abortControllerRef.current.abort();
            }
        };
    }, []);

    const validateInput = useCallback((input) => {
        if (!input.trim()) return "Please enter a message";
        // Removed minimum length check to allow short responses like "no" or "8"
        if (input.length > CONFIG.MAX_MESSAGE_LENGTH) {
            return "Message is too long";
        }
        return null;
    }, []);

    const typeMessage = useCallback((message, isAssessment = false, confidence = null, triageLevel = null, careRecommendation = null) => {
        let index = 0;
        setTyping(true);
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
                    // Scroll on each update
                    setTimeout(scrollToBottom, 0);
                }
                return updatedMessages;
            });
            index++;
            if (index >= message.length) {
                clearInterval(interval);
                setTyping(false);
                // Final scroll after typing completes
                setTimeout(scrollToBottom, 100);
                // Re-focus input after typing completes
                forceFocus();
            }
        }, CONFIG.TYPING_SPEED);
    }, [scrollToBottom, forceFocus]);

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
            // Call the reset endpoint
            await axios.post(CONFIG.RESET_URL);
            
            // Reset local state
            setMessages([WELCOME_MESSAGE]);
            setMessageCount(0);
            setError(null);
            setInputError(null);
            setSignupPrompt(false);
            localStorage.setItem(CONFIG.LOCAL_STORAGE_KEY, JSON.stringify([WELCOME_MESSAGE]));
            
            // Focus the input after reset
            forceFocus();
            
            if (CONFIG.DEBUG_MODE) {
                console.log("Conversation reset successfully");
            }
        } catch (error) {
            if (CONFIG.DEBUG_MODE) {
                console.error("Error resetting conversation:", error);
            }
            // Even if the API call fails, reset the local state
            setMessages([WELCOME_MESSAGE]);
            setMessageCount(0);
            setSignupPrompt(false);
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

        // Handle free tier message limit
        if (newMessageCount >= CONFIG.MAX_FREE_MESSAGES && !signupPrompt) {
            setSignupPrompt(true);
            setMessages(prev => [...prev, {
                sender: 'bot',
                text: "You've reached the free message limit. Subscribe for unlimited access or purchase a one-time AI report for this conversation.",
                confidence: null,
                careRecommendation: null,
                isAssessment: false
            }]);
            return;
        }

        // Add user message to chat
        setMessages(prev => [...prev, {
            sender: 'user',
            text: messageToSend.trim(),
            confidence: null,
            careRecommendation: null,
            isAssessment: false
        }]);
        
        if (!retryMessage) setUserInput('');
        setLoading(true);
        
        // Force focus on input after sending
        forceFocus();

        // Scroll to bottom after adding user message
        setTimeout(scrollToBottom, 0);
        setTimeout(scrollToBottom, 100);

        // Cancel any pending requests
        if (abortControllerRef.current) {
            abortControllerRef.current.abort();
        }
        abortControllerRef.current = new AbortController();

        try {
            // Prepare conversation history with proper formatting
            const conversationHistory = messages
                .filter(msg => msg.text.trim() !== "") // Filter out empty messages
                .map(msg => ({
                    message: msg.text,
                    isBot: msg.sender === 'bot'
                }));

            // Add context notes to help the AI avoid redundant questions
            const enhancedRequest = {
                symptom: messageToSend,
                conversation_history: conversationHistory,
                context_notes: "Pay close attention to timing details the user has already mentioned, such as when symptoms started or how long they've been present. Avoid asking redundant questions about information already provided."
            };

            if (CONFIG.DEBUG_MODE) {
                console.log("Sending request with conversation history:", enhancedRequest);
            }

            const response = await axios.post(
                CONFIG.API_URL,
                enhancedRequest,
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
                // Check if this is a question or assessment
                const isQuestion = response.data.is_question === true;
                const isAssessment = response.data.is_assessment === true;
                
                if (isAssessment) {
                    // It's a final assessment with conditions
                    let formattedMessage = '';
                    let confidence = null;
                    let triageLevel = null;
                    let careRecommendation = null;
                    
                    // Check if we have a structured JSON response
                    if (response.data.assessment?.conditions) {
                        const conditions = response.data.assessment.conditions;
                        triageLevel = response.data.assessment.triage_level || 'UNKNOWN';
                        careRecommendation = response.data.assessment.care_recommendation || response.data.care_recommendation;
                        const disclaimer = response.data.assessment.disclaimer || "This assessment is for informational purposes only and does not replace professional medical advice.";
                        
                        formattedMessage += 'Based on your symptoms, here are some possible conditions:\n\n';
                        conditions.forEach(condition => {
                            formattedMessage += `${condition.name} – ${condition.confidence}%\n`;
                        });
                        formattedMessage += `\n${careRecommendation}\n\n${disclaimer}`;
                        
                        confidence = conditions[0]?.confidence || response.data.confidence;
                    } else {
                        // Unstructured assessment
                        formattedMessage = response.data.possible_conditions || "Based on your symptoms, I can provide an assessment.";
                        confidence = response.data.confidence;
                        triageLevel = response.data.triage_level;
                        careRecommendation = response.data.care_recommendation;
                    }
                    
                    typeMessage(
                        formattedMessage,
                        true,
                        confidence,
                        triageLevel,
                        careRecommendation
                    );
                } else {
                    // It's a follow-up question or other response
                    const responseText = response.data.question || response.data.possible_conditions || "Could you tell me more about your symptoms?";
                    typeMessage(responseText, false);
                }

                // Handle upgrade prompts if present
                if (response.data.requires_upgrade) {
                    setSignupPrompt(true);
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
                        />
                    ))}
                    {typing && (
                        <div className="message-row">
                            <div className="avatar-container">
                                <img src="/doctor-avatar.png" alt="AI Assistant" />
                            </div>
                            <div className="typing-indicator">
                                <span></span>
                                <span></span>
                                <span></span>
                            </div>
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
                            disabled={loading || signupPrompt || resetting}
                            maxLength={CONFIG.MAX_MESSAGE_LENGTH}
                            aria-label="Symptom description input"
                            aria-invalid={!!inputError}
                            aria-describedby={inputError ? "input-error" : undefined}
                            autoFocus={true} // Add explicit autoFocus prop
                            onFocus={(e) => {
                                // Ensure cursor is at the end when focused
                                const value = e.target.value;
                                e.target.value = '';
                                e.target.value = value;
                            }}
                            onClick={(e) => {
                                // Prevent click from removing focus
                                e.stopPropagation();
                            }}
                        />
                        <button
                            className="send-button"
                            onClick={() => handleSendMessage()}
                            disabled={loading || signupPrompt || resetting || !userInput.trim()}
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

                {signupPrompt && (
                    <div className="upgrade-options">
                        <div className="upgrade-header">Choose an option to continue:</div>
                        <div className="upgrade-buttons">
                            <button className="upgrade-button subscription">
                                Subscribe to PA Mode
                                <span className="price">$9.99/month</span>
                            </button>
                            <button className="upgrade-button one-time">
                                One-time AI Doctor Report
                                <span className="price">$4.99</span>
                            </button>
                        </div>
                    </div>
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