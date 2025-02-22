import React, { useState, useRef, useEffect } from 'react';
import axios from 'axios';
import PropTypes from 'prop-types';
import '../styles/Chat.css';

// Configuration constants
const CONFIG = {
    MAX_FREE_MESSAGES: 15,
    TYPING_SPEED: 30,
    THINKING_DELAY: 1000,
    API_TIMEOUT: 10000,
    API_URL: 'https://healthtrackermichele.onrender.com/api/symptoms/analyze'
};

const WELCOME_MESSAGE = {
    sender: 'bot',
    text: "Hi, I'm Michele—your AI medical assistant. Think of me as that doctor you absolutely trust, here to listen, guide, and help you make sense of your symptoms. While I can't replace a real doctor, I can give you insights, ask the right questions, and help you feel more in control of your health. So, tell me—what's going on today?",
    triage: null,
    confidence: null
};

const Chat = () => {
    const [messages, setMessages] = useState([WELCOME_MESSAGE]);
    const [userInput, setUserInput] = useState('');
    const [loading, setLoading] = useState(false);
    const [messageCount, setMessageCount] = useState(0);
    const [signupPrompt, setSignupPrompt] = useState(false);
    const [typing, setTyping] = useState(false);
    const [error, setError] = useState(null);

    const messagesEndRef = useRef(null);
    const abortControllerRef = useRef(null);

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    };

    useEffect(() => {
        const scrollTimeout = setTimeout(scrollToBottom, 100);
        return () => clearTimeout(scrollTimeout);
    }, [messages]);

    useEffect(() => {
        return () => {
            if (abortControllerRef.current) {
                abortControllerRef.current.abort();
            }
        };
    }, []);

    const typeMessage = (message, triage, confidence) => {
        let index = 0;
        setTyping(false);
        setMessages(prev => [...prev, {
            sender: 'bot',
            text: "",
            triage: triage,
            confidence: confidence
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
    };

    const handleSendMessage = async () => {
        if (!userInput.trim() || signupPrompt || loading) return;

        const newMessageCount = messageCount + 1;
        setMessageCount(newMessageCount);
        setError(null);

        // Check message limit
        if (newMessageCount >= CONFIG.MAX_FREE_MESSAGES - 3 && newMessageCount < CONFIG.MAX_FREE_MESSAGES) {
            setMessages(prev => [...prev, {
                sender: 'bot',
                text: `You have ${CONFIG.MAX_FREE_MESSAGES - newMessageCount} free messages left before signing up.`,
                triage: null,
                confidence: null
            }]);
        }

        if (newMessageCount >= CONFIG.MAX_FREE_MESSAGES) {
            setSignupPrompt(true);
            setMessages(prev => [...prev, {
                sender: 'bot',
                text: "You've reached the free message limit. Sign up to continue!",
                triage: null,
                confidence: null
            }]);
            return;
        }

        // Add user message
        setMessages(prev => [...prev, {
            sender: 'user',
            text: userInput.trim(),
            triage: null,
            confidence: null
        }]);
        setUserInput('');
        setLoading(true);
        setTyping(true);

        // Create new abort controller
        abortControllerRef.current = new AbortController();

        try {
            const response = await axios.post(
                CONFIG.API_URL,
                {
                    symptoms: userInput,
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

            const botResponse = response.data.possible_conditions || "I apologize, but I couldn't process that properly.";
            const triageLevel = response.data.triage_level || "moderate";
            const confidenceScore = response.data.confidence || 85;

            setTimeout(() => {
                typeMessage(botResponse, triageLevel, confidenceScore);
            }, CONFIG.THINKING_DELAY);

        } catch (error) {
            if (!axios.isCancel(error)) {
                console.error("API error:", error);
                const errorMessage = "I apologize, but I'm having trouble processing your request. Please try again.";
                setError(errorMessage);
                setTimeout(() => {
                    typeMessage(errorMessage, "moderate", null);
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

    const getCareRecommendation = (triage) => {
        switch(triage) {
            case 'mild':
                return "You can likely manage this at home.";
            case 'severe':
                return "You should seek urgent care.";
            case 'moderate':
            default:
                return "Consider seeing a doctor soon.";
        }
    };

    return (
        <div className="chat-container">
            <div className="chat-header">
                <div className="chat-header-left">
                    <img
                        src="/michele-avatar.png"
                        alt="Michele"
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

            <div className="messages-container">
                {messages.map((msg, index) => (
                    <div key={index} className={`message ${msg.sender}`}>
                        <div className="message-content">{msg.text}</div>
                        {(msg.confidence || msg.triage) && (
                            <div className="metrics-container">
                                {msg.confidence && (
                                    <div className="confidence">
                                        Confidence: {msg.confidence}%
                                    </div>
                                )}
                                {msg.triage && (
                                    <div className={`care-recommendation ${msg.triage.toLowerCase()}`}>
                                        Care Recommendation: {getCareRecommendation(msg.triage)}
                                    </div>
                                )}
                            </div>
                        )}
                    </div>
                ))}
                {typing && <div className="typing-indicator">HealthTracker AI is typing...</div>}
                {error && <div className="error-message">{error}</div>}
                <div ref={messagesEndRef} />
            </div>

            <div className="chat-input-container">
                <div className="chat-input-form">
                    <div className="chat-input-wrapper">
                        <textarea
                            className="chat-input"
                            value={userInput}
                            onChange={(e) => setUserInput(e.target.value)}
                            onKeyDown={handleKeyDown}
                            placeholder="Describe your symptoms in detail..."
                            disabled={loading || signupPrompt}
                            aria-label="Symptom description input"
                        />
                    </div>
                    <button
                        className="send-button"
                        onClick={handleSendMessage}
                        disabled={loading || signupPrompt || !userInput.trim()}
                        aria-label="Send message"
                    >
                        {loading ? 'Sending...' : signupPrompt ? 'Sign Up' : 'Send'}
                    </button>
                </div>
            </div>
        </div>
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