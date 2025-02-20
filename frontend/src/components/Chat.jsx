import React, { useState, useRef, useEffect, useCallback } from 'react';
import PropTypes from 'prop-types';
import axios from 'axios';
import '../styles/Chat.css';

// Constants
const CONFIG = {
    DEBUG_MODE: true,
    MAX_FREE_MESSAGES: 15,
    TYPING_SPEED: 30,
    THINKING_DELAY: 1000,
    DEFAULT_CONFIDENCE: 75,
    MIN_CONFIDENCE: 50,
    MAX_CONFIDENCE: 95,
    API_URL: 'https://healthtrackerai.pythonanywhere.com/api/symptoms/analyze'
};

// Message type definitions
const MessageType = {
    USER: 'user',
    BOT: 'bot'
};

const TriageLevel = {
    MILD: 'mild',
    MODERATE: 'moderate',
    SEVERE: 'severe'
};

// Initial bot message
const WELCOME_MESSAGE = {
    sender: MessageType.BOT,
    text: "Hi, I'm Michele—your AI medical assistant. Think of me as that doctor you absolutely trust, here to listen, guide, and help you make sense of your symptoms. While I can't replace a real doctor, I can give you insights, ask the right questions, and help you feel more in control of your health. So, tell me—what's going on today?",
    confidence: null,
    careRecommendation: null
};

const Chat = () => {
    // State management
    const [messages, setMessages] = useState([WELCOME_MESSAGE]);
    const [userInput, setUserInput] = useState('');
    const [loading, setLoading] = useState(false);
    const [messageCount, setMessageCount] = useState(0);
    const [signupPrompt, setSignupPrompt] = useState(false);
    const [typing, setTyping] = useState(false);
    const [error, setError] = useState(null);
    
    // Refs
    const messagesEndRef = useRef(null);
    const abortControllerRef = useRef(null);

    // Auto-scrolling
    const scrollToBottom = useCallback(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }, []);

    useEffect(() => {
        const scrollTimeout = setTimeout(scrollToBottom, 100);
        return () => clearTimeout(scrollTimeout);
    }, [messages, scrollToBottom]);

    // Text cleaning utilities
    const cleanText = useCallback((text) => {
        if (!text) return '';
        
        const cleaningSteps = [
            [/\*\*([^*]+)\*\*/g, '$1'],  // Remove **bold** but keep content
            [/\*([^*]+)\*/g, '$1'],       // Remove *italic* but keep content
            [/`([^`]+)`/g, '$1'],         // Remove `code` but keep content
            [/#\s*/g, ''],                // Remove markdown headers
            [/^\s*[-•]\s*/gm, ''],        // Remove bullet points at start of lines
            [/\n\s*[-•]\s*/g, '\n'],      // Remove bullet points after newlines
            [/\[\]/g, ''],                // Remove empty brackets
            [/\s+/g, ' ']                 // Normalize whitespace
        ];

        return cleaningSteps.reduce(
            (text, [pattern, replacement]) => text.replace(pattern, replacement),
            text
        ).trim();
    }, []);

    // Response parsing
    const parseAIResponse = useCallback((response) => {
        if (!response) {
            return {
                possibleConditions: '',
                confidenceLevel: CONFIG.DEFAULT_CONFIDENCE,
                careRecommendation: TriageLevel.MODERATE
            };
        }

        const cleanedResponse = cleanText(response);
        
        // Extract sections using more reliable patterns
        const sections = {
            possibleConditions: '',
            confidenceLevel: CONFIG.DEFAULT_CONFIDENCE,
            careRecommendation: TriageLevel.MODERATE
        };

        try {
            // Extract possible conditions
            const conditionsMatch = cleanedResponse.match(
                /Possible Conditions:\s*(.*?)(?=\nConfidence Level:|$)/s
            );
            sections.possibleConditions = cleanText(conditionsMatch?.[1] || '');

            // Extract confidence level
            const confidenceMatch = cleanedResponse.match(/Confidence Level:\s*(\d+)/);
            sections.confidenceLevel = Math.min(
                Math.max(
                    CONFIG.MIN_CONFIDENCE,
                    parseInt(confidenceMatch?.[1]) || CONFIG.DEFAULT_CONFIDENCE
                ),
                CONFIG.MAX_CONFIDENCE
            );

            // Extract care recommendation
            const careMatch = cleanedResponse.match(/Care Recommendation:\s*(.*?)(?=\n|$)/s);
            sections.careRecommendation = cleanText(careMatch?.[1] || TriageLevel.MODERATE);

        } catch (error) {
            console.error('Error parsing AI response:', error);
        }

        return sections;
    }, [cleanText]);

    // Message handling
    const handleSendMessage = async () => {
        if (!userInput.trim() || signupPrompt || loading) return;

        const newMessageCount = messageCount + 1;
        setMessageCount(newMessageCount);
        setError(null);

        // Add user message
        const userMessage = {
            sender: MessageType.USER,
            text: userInput.trim(),
            confidence: null,
            careRecommendation: null
        };
        
        setMessages(prev => [...prev, userMessage]);
        setUserInput('');
        setLoading(true);
        setTyping(true);

        // Check message limit
        if (newMessageCount >= CONFIG.MAX_FREE_MESSAGES) {
            handleFreeMessageLimit();
            return;
        }

        // Create new abort controller
        abortControllerRef.current = new AbortController();

        try {
            const response = await axios.post(
                CONFIG.API_URL,
                {
                    symptoms: userMessage.text,
                    conversation_history: messages
                        .map(msg => ({
                            role: msg.sender === MessageType.USER ? 'user' : 'assistant',
                            content: msg.text
                        }))
                        .slice(1)
                },
                {
                    signal: abortControllerRef.current.signal,
                    timeout: 10000
                }
            );

            const { possible_conditions, triage_level, confidence } = response.data;
            const parsedResponse = parseAIResponse(possible_conditions);

            setTimeout(() => {
                addBotMessage(
                    parsedResponse.possibleConditions,
                    triage_level || parsedResponse.careRecommendation,
                    confidence ?? parsedResponse.confidenceLevel
                );
            }, CONFIG.THINKING_DELAY);

        } catch (error) {
            if (!axios.isCancel(error)) {
                handleError(error);
            }
        }
    };

    // Helper functions
    const handleFreeMessageLimit = () => {
        setSignupPrompt(true);
        addBotMessage(
            "You've reached the free message limit. Sign up to continue!",
            TriageLevel.MODERATE,
            CONFIG.MIN_CONFIDENCE
        );
    };

    const handleError = (error) => {
        console.error('Chat error:', error);
        const errorMessage = "Sorry, I couldn't process your request. Please try again.";
        addBotMessage(errorMessage, TriageLevel.MODERATE, CONFIG.MIN_CONFIDENCE);
        setError(errorMessage);
    };

    const addBotMessage = (text, triage, confidence) => {
        setTyping(false);
        setLoading(false);
        
        setMessages(prev => [
            ...prev,
            {
                sender: MessageType.BOT,
                text: cleanText(text),
                confidence,
                careRecommendation: triage
            }
        ]);
    };

    const handleKeyDown = (event) => {
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            handleSendMessage();
        }
    };

    // Cleanup
    useEffect(() => {
        return () => {
            if (abortControllerRef.current) {
                abortControllerRef.current.abort();
            }
        };
    }, []);

    // Render methods
    const renderMessage = (msg, index) => (
        <div key={index} className={`message ${msg.sender}`}>
            <div className="message-content">
                <p>{msg.text}</p>
                {(msg.confidence !== null || msg.careRecommendation) && (
                    <>
                        <hr className="divider" />
                        <div className="response-metrics">
                            {msg.confidence !== null && (
                                <span className="confidence-badge">
                                    Confidence: {msg.confidence}%
                                </span>
                            )}
                            {msg.careRecommendation && (
                                <span className="care-badge">
                                    Care Recommendation: {msg.careRecommendation}
                                </span>
                            )}
                        </div>
                    </>
                )}
            </div>
        </div>
    );

    const renderInput = () => (
        !signupPrompt ? (
            <>
                <textarea
                    className="chat-input"
                    value={userInput}
                    onChange={(e) => setUserInput(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder="Describe your symptoms..."
                    disabled={loading}
                    aria-label="Symptom description input"
                />
                <button 
                    className="send-button"
                    onClick={handleSendMessage} 
                    disabled={loading || !userInput.trim()}
                    aria-label="Send message"
                >
                    {loading ? 'Sending...' : 'Send'}
                </button>
            </>
        ) : (
            <div className="signup-prompt">
                <p>You've reached the free message limit.</p>
                <button 
                    className="signup-button" 
                    onClick={() => window.location.href = '/auth'}
                    aria-label="Sign up to continue"
                >
                    Sign up to continue
                </button>
            </div>
        )
    );

    return (
        <div className="chat-container">
            <div className="chat-header">
                <img src="/doctor-avatar.png" alt="HealthTracker AI" className="chat-avatar"/>
                <div className="chat-header-text">
                    <h1>HealthTracker AI</h1>
                    <p>AI Medical Assistant</p>
                </div>
            </div>

            <div className="messages-container">
                {messages.map(renderMessage)}
                {typing && (
                    <div className="typing-indicator">
                        HealthTracker AI is typing...
                    </div>
                )}
                {error && (
                    <div className="error-message">
                        {error}
                    </div>
                )}
                <div ref={messagesEndRef} />
            </div>

            <div className="input-container">
                {renderInput()}
            </div>
        </div>
    );
};

Chat.propTypes = {
    maxFreeMessages: PropTypes.number,
    apiUrl: PropTypes.string,
    debug: PropTypes.bool
};

Chat.defaultProps = {
    maxFreeMessages: CONFIG.MAX_FREE_MESSAGES,
    apiUrl: CONFIG.API_URL,
    debug: CONFIG.DEBUG_MODE
};

export default Chat;