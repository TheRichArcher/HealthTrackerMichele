import React, { useState, useRef, useEffect } from 'react';
import axios from 'axios';
import '../styles/Chat.css';

const DEBUG_MODE = true;
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
            confidence: null,
            careRecommendation: null
        }
    ]);
    const [userInput, setUserInput] = useState('');
    const [loading, setLoading] = useState(false);
    const [messageCount, setMessageCount] = useState(0);
    const [signupPrompt, setSignupPrompt] = useState(false);
    const [typing, setTyping] = useState(false);
    const messagesEndRef = useRef(null);

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    };

    useEffect(() => {
        const scrollTimeout = setTimeout(() => scrollToBottom(), 100);
        return () => clearTimeout(scrollTimeout);
    }, [messages]);

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
        if (!response) return { possibleConditions: '', confidenceLevel: DEFAULT_CONFIDENCE, careRecommendation: '' };

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

        return sections;
    };

    const handleSendMessage = async () => {
        if (!userInput.trim() || signupPrompt) return;

        const newMessageCount = messageCount + 1;
        setMessageCount(newMessageCount);

        setMessages(prev => [...prev, { 
            sender: 'user', 
            text: userInput,
            confidence: null,
            careRecommendation: null
        }]);
        setUserInput('');
        setLoading(true);
        setTyping(true);

        if (newMessageCount >= MAX_FREE_MESSAGES) {
            setSignupPrompt(true);
            setMessages(prev => [...prev, { 
                sender: 'bot', 
                text: "You've reached the free message limit. Sign up to continue!",
                confidence: null,
                careRecommendation: null
            }]);
            setLoading(false);
            setTyping(false);
            return;
        }

        try {
            const response = await axios.post('https://healthtrackerai.pythonanywhere.com/api/symptoms/analyze', {
                symptoms: userInput,
                conversation_history: messages.map(msg => ({
                    role: msg.sender === 'user' ? 'user' : 'assistant',
                    content: msg.text
                })).slice(1)
            });

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
        setTyping(false);
        
        setMessages(prev => [
            ...prev,
            { sender: 'bot', text: cleanMessage, confidence, careRecommendation: triage }
        ]);
    };

    const handleKeyDown = (event) => {
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            handleSendMessage();
        }
    };

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
                {messages.map((msg, index) => (
                    <div key={index} className={`message ${msg.sender}`}>
                        <div className="message-content">
                            <p>{msg.text}</p>
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
                        </div>
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
