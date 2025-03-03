import React, { useState, useRef, useEffect, useCallback, memo } from 'react';
import axios from 'axios';
import PropTypes from 'prop-types';
import { debounce } from 'lodash';
import '../styles/Chat.css';

// Import the ChatOnboarding component if it exists
// import ChatOnboarding from './ChatOnboarding';

// Define UI state enum
const UI_STATES = {
  DEFAULT: 'default',
  ASSESSMENT: 'assessment',
  UPGRADE_PROMPT: 'upgrade_prompt',
  ASSESSMENT_WITH_UPGRADE: 'assessment_with_upgrade',
  SECONDARY_PROMPT: 'secondary_prompt'
};

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

// Enhanced welcome message with example prompts
const WELCOME_MESSAGE = {
    sender: 'bot',
    text: "Hi, I'm Michele—your AI medical assistant. Think of me as that doctor you absolutely trust, here to listen, guide, and help you make sense of your symptoms. While I can't replace a real doctor, I can give you insights, ask the right questions, and help you feel more in control of your health.\n\nYou can start by describing your symptoms like:\n• \"I've had a headache for two days\"\n• \"My throat is sore and I have a fever\"\n• \"I have a rash on my arm that's itchy\"",
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

const Message = memo(({ message, onRetry, index, hideAssessmentDetails }) => {
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
                {isAssessment && !hideAssessmentDetails && (
                    <div className="assessment-indicator">Assessment</div>
                )}
                <div className="message-content">
                    {text.split('\n').map((line, i) => (
                        <p key={i}>{line}</p>
                    ))}
                </div>
                {/* Only show metrics if this is an assessment AND we're not hiding assessment details */}
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
        triageLevel: PropTypes.string
    }).isRequired,
    onRetry: PropTypes.func.isRequired,
    index: PropTypes.number.isRequired,
    hideAssessmentDetails: PropTypes.bool
};

// New Assessment Summary component to keep assessment visible
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
    const [isTypingComplete, setIsTypingComplete] = useState(true);
    
    // Add a counter for bot messages to track question number
    const [botMessageCount, setBotMessageCount] = useState(0);
    
    // Unified UI state
    const [uiState, setUiState] = useState(UI_STATES.DEFAULT);
    
    // Loading states for upgrade buttons
    const [loadingSubscription, setLoadingSubscription] = useState(false);
    const [loadingOneTime, setLoadingOneTime] = useState(false);
    
    // Add state for the latest assessment to keep it visible
    const [latestAssessment, setLatestAssessment] = useState(null);
    
    // Add state for showing the onboarding component
    const [showChatOnboarding, setShowChatOnboarding] = useState(false);

    const messagesEndRef = useRef(null);
    const abortControllerRef = useRef(null);
    const chatContainerRef = useRef(null);
    const inputRef = useRef(null);
    const messagesContainerRef = useRef(null);

    // Auto-focus when component mounts
    useEffect(() => {
        if (inputRef.current) {
            inputRef.current.focus();
        }
    }, []);

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

    // Simple and effective scrolling mechanism
    const scrollToBottom = useCallback(() => {
        if (messagesEndRef.current) {
            messagesEndRef.current.scrollIntoView({ behavior: "smooth" });
        }
    }, []);

    // Scroll when messages change
    useEffect(() => {
        scrollToBottom();
    }, [messages, scrollToBottom]);

    // Scroll when typing state changes
    useEffect(() => {
        scrollToBottom();
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
        if (input.length > CONFIG.MAX_MESSAGE_LENGTH) {
            return "Message is too long";
        }
        return null;
    }, []);

    const typeMessage = useCallback((message, isAssessment = false, confidence = null, triageLevel = null, careRecommendation = null) => {
        let index = 0;
        setTyping(true);
        setIsTypingComplete(false);
        
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
            
            // Scroll every 20 characters to reduce bouncing
            if (index % 20 === 0) {
                scrollToBottom();
            }
            
            index++;
            
            if (index >= message.length) {
                clearInterval(interval);
                setTyping(false);
                setIsTypingComplete(true);
                
                // Final scroll to ensure message is visible
                setTimeout(scrollToBottom, 50);
                setTimeout(scrollToBottom, 150);
            }
        }, CONFIG.TYPING_SPEED);
        
        return () => clearInterval(interval);
    }, [scrollToBottom]);

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
            setBotMessageCount(0); // Reset bot message counter
            setError(null);
            setInputError(null);
            setIsTypingComplete(true);
            setLoadingSubscription(false);
            setLoadingOneTime(false);
            setLatestAssessment(null); // Reset the latest assessment
            setUiState(UI_STATES.DEFAULT); // Reset UI state
            localStorage.setItem(CONFIG.LOCAL_STORAGE_KEY, JSON.stringify([WELCOME_MESSAGE]));
            
            // Focus the input after reset
            if (inputRef.current) {
                inputRef.current.focus();
            }
            
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
            setBotMessageCount(0); // Reset bot message counter
            setIsTypingComplete(true);
            setLoadingSubscription(false);
            setLoadingOneTime(false);
            setLatestAssessment(null); // Reset the latest assessment
            setUiState(UI_STATES.DEFAULT); // Reset UI state
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
        if (newMessageCount >= CONFIG.MAX_FREE_MESSAGES && uiState === UI_STATES.DEFAULT) {
            // First add the user's message
            setMessages(prev => [...prev, {
                sender: 'user',
                text: messageToSend.trim(),
                confidence: null,
                careRecommendation: null,
                isAssessment: false
            }]);
            
            if (!retryMessage) setUserInput('');
            
            // Then add a bot message explaining the upgrade
            setTimeout(() => {
                typeMessage(
                    "Based on your symptoms, I've identified a condition that may require further evaluation. To get more insights, you can choose between Premium Access for unlimited symptom checks or a one-time Consultation Report for your current symptoms.",
                    false
                );
                
                // Show upgrade prompt after the explanation
                setTimeout(() => {
                    setUiState(UI_STATES.UPGRADE_PROMPT);
                    scrollToBottom();
                }, 1000);
            }, 1000);
            
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
        
        // Check if we need to show the secondary prompt after user dismisses the upgrade prompt
        if (uiState === UI_STATES.DEFAULT && messageCount > CONFIG.MAX_FREE_MESSAGES) {
            setUiState(UI_STATES.SECONDARY_PROMPT);
            
            // Find the latest user message for personalization
            const userMessages = messages.filter(msg => msg.sender === 'user');
            const latestUserMessage = userMessages.length > 0 ? 
                userMessages[userMessages.length - 1].text : 
                "your symptoms";
            
            // Extract a short snippet from the user's message (first 30 chars)
            const symptomSnippet = latestUserMessage.length > 30 ? 
                latestUserMessage.substring(0, 30) + "..." : 
                latestUserMessage;
            
            // Add a slight delay before showing the secondary prompt
            setTimeout(() => {
                // Add a personalized reminder as a bot message with a stronger CTA
                setMessages(prev => [...prev, {
                    sender: 'bot',
                    text: `🔎 You mentioned "${symptomSnippet}". Want a deeper understanding? Unlock Premium Access for continuous tracking or get a one-time Consultation Report for a detailed summary!`,
                    confidence: null,
                    careRecommendation: null,
                    isAssessment: false
                }]);
                
                // Scroll to make the message visible
                scrollToBottom();
            }, 1000);
        }
        
        if (!retryMessage) setUserInput('');
        setLoading(true);
        // Set typing to true here when we start the API request
        setTyping(true);
        
        // Force focus on input after sending
        if (inputRef.current) {
            inputRef.current.focus();
        }

        // Scroll to bottom after adding user message
        scrollToBottom();

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
                context_notes: "Pay close attention to timing details the user has already mentioned, such as when symptoms started or how long they've been present. Avoid asking redundant questions about information already provided. Ask only ONE question at a time to avoid confusion."
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
                console.log("Requires upgrade:", response.data.requires_upgrade);
                console.log("Is assessment:", response.data.is_assessment);
            }

            setTimeout(() => {
                // Check if this is a question or assessment
                const isQuestion = response.data.is_question === true;
                const isAssessment = response.data.is_assessment === true;
                const requiresUpgrade = response.data.requires_upgrade === true;
                
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
                        
                        // Update the latest assessment for the sticky summary
                        if (conditions.length > 0) {
                            setLatestAssessment({
                                condition: conditions[0].name,
                                confidence: conditions[0].confidence,
                                recommendation: careRecommendation
                            });
                        }
                        
                        // If this requires an upgrade, show a simplified message
                        if (requiresUpgrade) {
                            formattedMessage = "Based on your symptoms, I've completed an assessment. Please see the summary below.";
                            
                            // Add the message with minimal details
                            typeMessage(
                                formattedMessage,
                                true,
                                conditions[0]?.confidence,
                                triageLevel,
                                null // Don't include care recommendation in the message
                            );
                            
                            // Add a bot message explaining the upgrade
                            setTimeout(() => {
                                typeMessage(
                                    "I've identified a condition that may require further evaluation. To get more insights, you can choose between Premium Access for unlimited symptom checks or a one-time Consultation Report for your current symptoms.",
                                    false
                                );
                                
                                // Show both assessment and upgrade
                                setTimeout(() => {
                                    setUiState(UI_STATES.ASSESSMENT_WITH_UPGRADE);
                                    scrollToBottom();
                                }, 1000);
                            }, 2000);
                        } else {
                            // Regular assessment without upgrade
                            formattedMessage += 'Based on your symptoms, here are some possible conditions:\n\n';
                            conditions.forEach(condition => {
                                formattedMessage += `${condition.name} – ${condition.confidence}%\n`;
                            });
                            formattedMessage += `\n${careRecommendation}\n\n${disclaimer}`;
                            
                            confidence = conditions[0]?.confidence || response.data.confidence;
                            
                            // For non-upgrade assessments, show the full assessment
                            typeMessage(
                                formattedMessage,
                                true,
                                confidence,
                                triageLevel,
                                careRecommendation
                            );
                            
                            // Set UI state to ASSESSMENT
                            setUiState(UI_STATES.ASSESSMENT);
                        }
                    } else {
                        // Unstructured assessment
                        formattedMessage = response.data.possible_conditions || "Based on your symptoms, I can provide an assessment.";
                        confidence = response.data.confidence;
                        triageLevel = response.data.triage_level;
                        careRecommendation = response.data.care_recommendation;
                        
                        // Update the latest assessment for the sticky summary
                        setLatestAssessment({
                            condition: "Assessment",
                            confidence: confidence,
                            recommendation: careRecommendation
                        });
                        
                        // If this requires an upgrade, show the upgrade prompt
                        if (requiresUpgrade) {
                            // Add a simplified message
                            typeMessage(
                                "Based on your symptoms, I've completed an assessment. Please see the summary below.",
                                true,
                                confidence,
                                triageLevel,
                                null // Don't include care recommendation in the message
                            );
                            
                            // Add a bot message explaining the upgrade
                            setTimeout(() => {
                                typeMessage(
                                    "I've identified a condition that may require further evaluation. To get more insights, you can choose between Premium Access for unlimited symptom checks or a one-time Consultation Report for your current symptoms.",
                                    false
                                );
                                
                                // Show both assessment and upgrade
                                setTimeout(() => {
                                    setUiState(UI_STATES.ASSESSMENT_WITH_UPGRADE);
                                    scrollToBottom();
                                }, 1000);
                            }, 2000);
                        } else {
                            // For non-upgrade assessments, show the full assessment
                            typeMessage(
                                formattedMessage,
                                true,
                                confidence,
                                triageLevel,
                                careRecommendation
                            );
                            
                            // Set UI state to ASSESSMENT
                            setUiState(UI_STATES.ASSESSMENT);
                        }
                    }
                } else {
                    // It's a follow-up question or other response
                    const responseText = response.data.question || response.data.possible_conditions || "Could you tell me more about your symptoms?";
                    typeMessage(responseText, false);
                }
            }, CONFIG.THINKING_DELAY);

        } catch (error) {
            if (!axios.isCancel(error)) {
                if (CONFIG.DEBUG_MODE) {
                    console.error("API error details:", error);
                }
                
                let errorMessage = "I apologize, but I'm having trouble processing your request.";
                
                if (error.response) {
                    // The request was made and the server responded with a status code
                    // that falls out of the range of 2xx
                    if (error.response.status === 429) {
                        errorMessage = "I'm receiving too many requests right now. Please try again in a moment.";
                    } else if (error.response.status >= 500) {
                        errorMessage = "I'm having trouble connecting to my medical knowledge. Please try again shortly.";
                    }
                } else if (error.request) {
                    // The request was made but no response was received
                    errorMessage = "I'm having trouble connecting to my medical database. Please check your internet connection and try again.";
                }
                
                setError(errorMessage);
                setTimeout(() => {
                    typeMessage(errorMessage, false);
                }, CONFIG.THINKING_DELAY);
            }
        } finally {
            setLoading(false);
            // Don't set typing to false here - it will be set in typeMessage when typing is complete
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
                    
                    {/* Show typing indicator */}
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
                    
                    {/* Add loading indicator */}
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

                {/* Add the sticky assessment summary here */}
                {(uiState === UI_STATES.ASSESSMENT || uiState === UI_STATES.ASSESSMENT_WITH_UPGRADE) && latestAssessment && (
                    <AssessmentSummary assessment={latestAssessment} />
                )}

                {/* Show upgrade prompt if in UPGRADE_PROMPT or ASSESSMENT_WITH_UPGRADE state */}
                {(uiState === UI_STATES.UPGRADE_PROMPT || uiState === UI_STATES.ASSESSMENT_WITH_UPGRADE) && (
                    <div className="upgrade-options">
                        <button 
                            className="close-upgrade" 
                            onClick={() => {
                                setUiState(uiState === UI_STATES.ASSESSMENT_WITH_UPGRADE ? UI_STATES.ASSESSMENT : UI_STATES.DEFAULT);
                                if (inputRef.current) {
                                    inputRef.current.focus();
                                }
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
                                    setTimeout(() => {
                                        window.location.href = '/subscribe';
                                    }, 300);
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
                                    setTimeout(() => {
                                        window.location.href = '/one-time-report';
                                    }, 300);
                                }}
                                disabled={loadingSubscription || loadingOneTime}
                            >
                                {loadingOneTime ? 'Processing...' : '📄 Get Consultation Report ($4.99)'}
                            </button>
                        </div>
                    </div>
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
                
                {/* Add the ChatOnboarding component if it exists */}
                {showChatOnboarding && (
                    <div className="chat-onboarding">
                        <h3>Welcome to HealthTracker AI</h3>
                        <p>Describe your symptoms and I'll help you understand what might be going on.</p>
                        <button onClick={() => setShowChatOnboarding(false)}>Got it</button>
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