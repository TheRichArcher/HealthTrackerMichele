import React, { useState, useRef, useEffect } from 'react';
import axios from 'axios';
import PropTypes from 'prop-types';
import '../styles/Chat.css';

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
    confidence: null,
    careRecommendation: null
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

    const typeMessage = (message, confidence, careRecommendation) => {
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
    };

    const handleSendMessage = async () => {
        if (!userInput.trim() || signupPrompt || loading) return;

        const newMessageCount = messageCount + 1;
        setMessageCount(newMessageCount);
        setError(null);

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
            text: userInput.trim(),
            confidence: null,
            careRecommendation: null
        }]);
        setUserInput('');
        setLoading(true);
        setTyping(true);

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

            const { possible_conditions, triage_level, confidence } = response.data;
            
            // Format the response as a conversational message
            const botResponse = possible_conditions || "I need more information to help you better. Could you tell me more about your symptoms?";
            
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

    const getCareRecommendation = (level) => {
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
    };

    return (
        <div className="chat-container">
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

            <div className="messages-container">
                {messages.map((msg, index) => (
                    <div key={index} className={`message ${msg.sender}`}>
                        <div className="message-content">{msg.text}</div>
                        {(msg.confidence || msg.careRecommendation) && (
                            <div className="metrics-container">
                                {msg.confidence && (
                                    <div className="confidence">
                                        Confidence: {msg.confidence}%
                                    </div>
                                )}
                                {msg.careRecommendation && (
                                    <div className={`care-recommendation ${msg.careRecommendation}`}>
                                        {getCareRecommendation(msg.careRecommendation)}
                                    </div>
                                )}
                            </div>
                        )}
                    </div>
                ))}
                {typing && <div className="typing-indicator">Michele is typing...</div>}
                {error && <div className="error-message">{error}</div>}
                <div ref={messagesEndRef} />
            </div>

            <div className="chat-input-container">
                <div className="chat-input-form">
                    <textarea
                        className="chat-input"
                        value={userInput}
                        onChange={(e) => setUserInput(e.target.value)}
                        onKeyDown={handleKeyDown}
                        placeholder="Describe your symptoms in detail..."
                        disabled={loading || signupPrompt}
                        aria-label="Symptom description input"
                    />
                    <button
                        className="send-button"
                        onClick={handleSendMessage}
                        disabled={loading || signupPrompt || !userInput.trim()}
                        aria-label="Send message"
                    >
                        {loading ? 'Sending...' : 'Send'}
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