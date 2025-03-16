import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from './AuthProvider';
import UpgradePrompt from './UpgradePrompt';
import '../styles/Chat.css';

const API_BASE_URL = 'https://healthtrackermichele.onrender.com/api';
const CHAT_STORAGE_KEY = 'healthTrackerChatMessages';

const Chat = () => {
    const [messages, setMessages] = useState([]);
    const [input, setInput] = useState('');
    const [loading, setLoading] = useState(false);
    const { isAuthenticated, userId, checkAuth, refreshToken } = useAuth();
    const navigate = useNavigate();
    const location = useLocation();

    // Load messages from localStorage on mount
    useEffect(() => {
        const savedMessages = localStorage.getItem(CHAT_STORAGE_KEY);
        if (savedMessages) {
            setMessages(JSON.parse(savedMessages));
        }
        checkAuth();
    }, [checkAuth]);

    // Save messages to localStorage after each update
    useEffect(() => {
        localStorage.setItem(CHAT_STORAGE_KEY, JSON.stringify(messages));
    }, [messages]);

    // Handle redirect back from Stripe after payment
    useEffect(() => {
        const sessionId = new URLSearchParams(location.search).get('session_id');
        if (sessionId) {
            axios.post(`${API_BASE_URL}/subscription/confirm`, { session_id: sessionId }, { withCredentials: true })
                .then(response => {
                    if (response.data.report_url) {
                        setMessages(prevMessages => [
                            ...prevMessages,
                            { text: `Your one-time report is ready! [Download PDF](${response.data.report_url})`, isBot: true }
                        ]);
                    }
                })
                .catch(err => {
                    console.error('Error confirming report:', err);
                    setMessages(prevMessages => [
                        ...prevMessages,
                        { text: 'Failed to confirm report. Please contact support.', isBot: true }
                    ]);
                });
            navigate('/chat', { replace: true });
        }
    }, [location, navigate]);

    // Periodic token refresh (every 30 minutes)
    useEffect(() => {
        if (isAuthenticated) {
            const refreshInterval = setInterval(() => {
                console.log('Attempting token refresh');
                refreshToken().then(success => {
                    if (!success) {
                        console.warn('Token refresh failed, user may need to re-authenticate');
                    }
                });
            }, 30 * 60 * 1000); // 30 minutes
            return () => clearInterval(refreshInterval);
        }
    }, [isAuthenticated, refreshToken]);

    const handleSendMessage = async () => {
        if (!input.trim()) return;

        const newMessages = [...messages, { text: input, isBot: false }];
        setMessages(newMessages);
        setInput('');
        setLoading(true);

        try {
            const conversationHistory = newMessages.map(msg => ({
                message: msg.text,
                isBot: msg.isBot,
            }));
            const response = await axios.post(
                `${API_BASE_URL}/symptoms/analyze`,
                { symptom: input, conversation_history: conversationHistory },
                { 
                    headers: { Authorization: `Bearer ${localStorage.getItem('access_token')}` }, 
                    withCredentials: true 
                }
            );
            const botResponse = response.data.response;

            let reply = '';
            if (botResponse.requires_upgrade) {
                reply = `${botResponse.care_recommendation}\n\nUpgrade required for detailed insights.`;
            } else if (botResponse.is_assessment && botResponse.confidence >= 95) {
                reply = `${botResponse.care_recommendation}\n\n`;
            } else {
                reply = botResponse.response || 'Please provide more details.';
            }

            setMessages([...newMessages, { text: reply, isBot: true, data: botResponse }]);
        } catch (err) {
            console.error('Error analyzing symptoms:', err);
            const errorMessage = err.response?.data?.response || 'Error processing your request. Please try again.';
            setMessages([...newMessages, { text: errorMessage, isBot: true }]);
        } finally {
            setLoading(false);
        }
    };

    const handleUpgrade = (option) => {
        if (option === 'report') {
            axios.post(`${API_BASE_URL}/subscription/upgrade`, { plan: 'one_time' }, { withCredentials: true })
                .then(response => {
                    console.log('Redirecting to Stripe for one-time report:', response.data.checkout_url);
                    window.location.href = response.data.checkout_url;
                })
                .catch(err => {
                    console.error('Error initiating report purchase:', err);
                    setMessages([...messages, { text: 'Failed to initiate report purchase. Please try again.', isBot: true }]);
                });
        } else if (option === 'subscribe') {
            if (!isAuthenticated) {
                navigate('/auth');
            } else {
                navigate('/subscription');
            }
        }
    };

    const handleNotNow = () => {
        setMessages([...messages, { text: 'Noted. Let me know if you need help later!', isBot: true }]);
    };

    const resetConversation = () => {
        setMessages([]);
        localStorage.removeItem(CHAT_STORAGE_KEY);
        console.log('Conversation reset');
    };

    return (
        <div className="chat-container">
            <div className="reset-button-container">
                <button className="reset-button" onClick={resetConversation} disabled={loading}>
                    Reset Conversation
                </button>
            </div>
            <div className="messages-container">
                {messages.map((msg, index) => (
                    <div key={index} className={`message-row ${msg.isBot ? 'bot' : 'user'}`}>
                        <div className="avatar-container">
                            <img
                                src={msg.isBot ? '/bot-avatar.png' : '/user-avatar.png'}
                                alt={msg.isBot ? 'Bot Avatar' : 'User Avatar'}
                            />
                        </div>
                        <div className={`message ${msg.isBot ? 'bot' : 'user'}`}>
                            <div className="message-content">
                                {msg.isBot && msg.data && (msg.data.is_assessment || msg.data.requires_upgrade) ? (
                                    <UpgradePrompt
                                        careRecommendation={msg.data.care_recommendation || 'Consider consulting a healthcare provider'}
                                        triageLevel={msg.data.triage_level || 'MODERATE'}
                                        onReport={() => handleUpgrade('report')}
                                        onSubscribe={() => handleUpgrade('subscribe')}
                                        onNotNow={handleNotNow}
                                        requiresUpgrade={msg.data.requires_upgrade || false}
                                    />
                                ) : (
                                    <p>{msg.text}</p>
                                )}
                            </div>
                        </div>
                    </div>
                ))}
                {loading && (
                    <div className="message-row bot">
                        <div className="avatar-container">
                            <img src="/bot-avatar.png" alt="Bot Avatar" />
                        </div>
                        <div className="typing-indicator">
                            <span></span>
                            <span></span>
                            <span></span>
                        </div>
                    </div>
                )}
            </div>
            <div className="chat-input-container">
                <div className="chat-input-wrapper">
                    <textarea
                        className="chat-input"
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        placeholder="Describe your symptoms..."
                        disabled={loading}
                        onKeyPress={(e) => e.key === 'Enter' && !e.shiftKey && (e.preventDefault(), handleSendMessage())}
                    />
                    <button className="send-button" onClick={handleSendMessage} disabled={loading}>
                        Send
                    </button>
                    {!isAuthenticated && (
                        <button className="sign-in-button" onClick={() => navigate('/auth')}>
                            Sign In
                        </button>
                    )}
                </div>
            </div>
        </div>
    );
};

export default Chat;