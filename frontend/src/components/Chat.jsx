import React, { useState, useRef, useEffect } from 'react';
import axios from 'axios';
import '../styles/Chat.css';

const DEBUG_MODE = false;
const MAX_FREE_MESSAGES = 15;
const TYPING_SPEED = 30;
const THINKING_DELAY = 1000;
const DEFAULT_CONFIDENCE = 75;
const MIN_CONFIDENCE = 50;

const Chat = () => {
    const [messages, setMessages] = useState([
        { 
            sender: 'bot', 
            text: "Hi, I'm Michele—your AI medical assistant. Think of me as that doctor you absolutely trust, here to listen, guide, and help you make sense of your symptoms. While I can't replace a real doctor, I can give you insights, ask the right questions, and help you feel more in control of your health. So, tell me—what's going on today?",
            triage: null,
            confidence: null
        }
    ]);
    const [userInput, setUserInput] = useState('');
    const [loading, setLoading] = useState(false);
    const [messageCount, setMessageCount] = useState(0);
    const [signupPrompt, setSignupPrompt] = useState(false);
    const [typing, setTyping] = useState(false);
    const [typingMessage, setTypingMessage] = useState('');
    const [currentTypingIndex, setCurrentTypingIndex] = useState(0);

    const messagesEndRef = useRef(null);
    const typingIntervalRef = useRef(null);

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    };

    useEffect(() => {
        const scrollTimeout = setTimeout(() => scrollToBottom(), 100);
        return () => clearTimeout(scrollTimeout);
    }, [messages, typingMessage]);

    // Cleanup typing animation on unmount
    useEffect(() => {
        return () => {
            if (typingIntervalRef.current) {
                clearInterval(typingIntervalRef.current);
            }
        };
    }, []);

    const cleanText = (text) => {
        if (!text) return '';
        return text
            .replace(/\*\*/g, '')
            .replace(/\*/g, '')
            .replace(/`/g, '')
            .replace(/#/g, '')
            .replace(/\n\s*-\s*/g, '\n')
            .replace(/\[\]/g, '')
            .trim();
    };

    const parseAIResponse = (response) => {
        if (!response) {
            if (DEBUG_MODE) console.log('Empty response received in parseAIResponse');
            return { 
                possibleConditions: '', 
                confidenceLevel: DEFAULT_CONFIDENCE, 
                careRecommendation: '' 
            };
        }

        const cleanedResponse = cleanText(response);
        
        const sections = {
            possibleConditions: '',
            confidenceLevel: DEFAULT_CONFIDENCE,
            careRecommendation: ''
        };

        const matches = {
            possibleConditions: cleanedResponse.match(/Possible Conditions:\s*(.*?)(?=\nConfidence Level:|$)/s),
            confidenceLevel: cleanedResponse.match(/Confidence Level:\s*(\d+)/),
            careRecommendation: cleanedResponse.match(/Care Recommendation:\s*(.*?)$/s)
        };

        sections.possibleConditions = cleanText(matches.possibleConditions?.[1] || '');
        sections.confidenceLevel = Math.max(
            MIN_CONFIDENCE,
            parseInt(matches.confidenceLevel?.[1]) || DEFAULT_CONFIDENCE
        );
        sections.careRecommendation = cleanText(matches.careRecommendation?.[1] || '');

        if (DEBUG_MODE) {
            console.log('Parsed AI Response:', sections);
        }

        return sections;
    };

    const handleSendMessage = async () => {
        if (!userInput.trim() || signupPrompt) return;

        const newMessageCount = messageCount + 1;
        setMessageCount(newMessageCount);

        // Add user message
        setMessages(prev => [...prev, { 
            sender: 'user', 
            text: userInput,
            triage: null,
            confidence: null
        }]);
        setUserInput('');
        setLoading(true);
        setTyping(true);

        // Check message limit after user message
        if (newMessageCount >= MAX_FREE_MESSAGES) {
            setSignupPrompt(true);
            setMessages(prev => [...prev, { 
                sender: 'bot', 
                text: "You've reached the free message limit. Sign up to continue!",
                triage: null,
                confidence: null
            }]);
            setLoading(false);
            setTyping(false);
            return;
        }

        try {
            if (DEBUG_MODE) console.log("Sending request with user input:", userInput);
            
            const response = await axios.post('https://healthtrackerai.pythonanywhere.com/api/symptoms/analyze', {
                symptoms: userInput,
                conversation_history: messages.map(msg => ({
                    role: msg.sender === 'user' ? 'user' : 'assistant',
                    content: msg.text
                })).slice(1)
            });

            if (DEBUG_MODE) console.log("API Response:", response.data);

            const { possible_conditions, triage_level, confidence } = response.data;
            const parsedResponse = parseAIResponse(possible_conditions);

            setTimeout(() => {
                typeMessage(
                    parsedResponse.possibleConditions,
                    triage_level || parsedResponse.careRecommendation || "moderate",
                    confidence ?? parsedResponse.confidenceLevel ?? MIN_CONFIDENCE
                );
            }, THINKING_DELAY);

        } catch (error) {
            if (DEBUG_MODE) console.error("API error:", error);
            
            setTimeout(() => {
                typeMessage(
                    "Sorry, I couldn't process your request. Please try again.",
                    "moderate",
                    MIN_CONFIDENCE
                );
            }, THINKING_DELAY);
        } finally {
            setLoading(false);
        }
    };

    const typeMessage = (message, triage, confidence) => {
        const cleanMessage = cleanText(message);
        setTyping(true);
        setCurrentTypingIndex(0);
        setTypingMessage('');

        // Clear any existing interval
        if (typingIntervalRef.current) {
            clearInterval(typingIntervalRef.current);
        }

        // Initialize the message immediately with empty text
        setMessages(prev => [...prev, {
            sender: 'bot',
            text: '',
            triage,
            confidence
        }]);

        typingIntervalRef.current = setInterval(() => {
            setCurrentTypingIndex(prevIndex => {
                const nextIndex = prevIndex + 1;
                
                if (nextIndex > cleanMessage.length) {
                    clearInterval(typingIntervalRef.current);
                    setTyping(false);
                    
                    // Update final message
                    setMessages(prev => {
                        const updated = [...prev];
                        updated[updated.length - 1].text = cleanMessage;
                        return updated;
                    });
                    
                    return prevIndex;
                }

                setMessages(prev => {
                    const updated = [...prev];
                    updated[updated.length - 1].text = cleanMessage.slice(0, nextIndex);
                    return updated;
                });

                return nextIndex;
            });
        }, TYPING_SPEED);
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
                return "Consider consulting a healthcare professional.";
        }
    };

    return (
        <div className="chat-container">
            <div className="chat-header">
                <img 
                    src="/doctor-avatar.png" 
                    alt="HealthTracker AI" 
                    className="chat-avatar"
                />
                <div className="chat-header-text">
                    <h1>HealthTracker AI</h1>
                    <p>AI Medical Assistant</p>
                </div>
                <div className="chat-header-disclaimer">
                    For informational purposes only. Not a substitute for professional medical advice.
                </div>
            </div>

            <div className="messages-container">
                {messages.map((msg, index) => (
                    <div key={index} className={`message ${msg.sender}`}>
                        <div className="message-content">{msg.text}</div>
                        {msg.sender === 'bot' && msg.text && (
                            <div className="metrics-container">
                                {msg.confidence != null && (
                                    <div className="confidence-meter">
                                        <div className="confidence-label">
                                            Confidence: {msg.confidence}%
                                        </div>
                                        <div className="confidence-bar">
                                            <div 
                                                className="confidence-fill"
                                                style={{width: `${msg.confidence}%`}}
                                            />
                                        </div>
                                    </div>
                                )}
                                {msg.triage && (
                                    <div className={`care-recommendation ${msg.triage}`}>
                                        {getCareRecommendation(msg.triage)}
                                    </div>
                                )}
                            </div>
                        )}
                    </div>
                ))}
                {typing && <div className="typing-indicator">HealthTracker AI is typing...</div>}
                <div ref={messagesEndRef} />
            </div>

            <div className="input-container">
                {!signupPrompt ? (
                    <>
                        <textarea
                            className="chat-input"
                            value={userInput}
                            onChange={(e) => setUserInput(e.target.value)}
                            onKeyDown={handleKeyDown}
                            placeholder="Describe your symptoms..."
                            disabled={loading}
                        />
                        <button 
                            className="send-button"
                            onClick={handleSendMessage} 
                            disabled={loading || !userInput.trim()}
                        >
                            {loading ? 'Sending...' : 'Send'}
                        </button>
                        <div className="message-limit-info">
                            {MAX_FREE_MESSAGES - messageCount} messages remaining
                        </div>
                    </>
                ) : (
                    <div className="signup-prompt">
                        <p>You've reached the free message limit.</p>
                        <button className="signup-button" onClick={() => window.location.href = '/auth'}>
                            Sign up to continue
                        </button>
                    </div>
                )}
            </div>
        </div>
    );
};

export default Chat;