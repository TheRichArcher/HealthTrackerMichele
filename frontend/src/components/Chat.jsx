import React, { useState, useRef, useEffect, useCallback, memo } from 'react';
import axios from 'axios';
import PropTypes from 'prop-types';
import { debounce } from 'lodash';
import '../styles/Chat.css';

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
    THINKING_DELAY: 1000,
    API_TIMEOUT: 10000,
    API_URL: '/api/symptoms/analyze', // Use relative URL for same-origin deployment
    RESET_URL: '/api/symptoms/reset',
    MAX_MESSAGE_LENGTH: 1000,
    MIN_MESSAGE_LENGTH: 1, // Changed from 3 to 1 to allow short responses
    SCROLL_DEBOUNCE_DELAY: 100,
    LOCAL_STORAGE_KEY: 'healthtracker_chat_messages',
    DEBUG_MODE: process.env.NODE_ENV === 'development',
    MIN_CONFIDENCE_THRESHOLD: 85, // Minimum confidence required for assessment
    MESSAGE_DELAY: 1000 // Delay between sequential messages
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

    // Determine confidence class
    let confidenceClass = '';
    if (confidence) {
        if (confidence >= CONFIG.MIN_CONFIDENCE_THRESHOLD) {
            confidenceClass = 'confidence-high';
        } else if (confidence >= 70) {
            confidenceClass = 'confidence-medium';
        } else {
            confidenceClass = 'confidence-low';
        }
    }

    return (
        <div className={`message-row ${sender === 'user' ? 'user' : ''}`}>
            <div className="avatar-container">
                {avatarContent}
            </div>
            <div className={`message ${sender} ${text.includes('?') && sender === 'bot' ? 'follow-up-question' : ''}`}>
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
                                className={`assessment-item confidence ${confidenceClass}`}
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
                        onClick={() => {
                            // Add a brief delay before retrying for a more natural feel
                            setTimeout(() => onRetry(index), 500);
                        }}
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
    
    // Determine confidence class
    let confidenceClass = '';
    if (assessment.confidence) {
        if (assessment.confidence >= CONFIG.MIN_CONFIDENCE_THRESHOLD) {
            confidenceClass = 'confidence-high';
        } else if (assessment.confidence >= 70) {
            confidenceClass = 'confidence-medium';
        } else {
            confidenceClass = 'confidence-low';
        }
    }
    
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
                    <span className={confidenceClass}> - {assessment.confidence}% confidence</span>
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
    
    // Track previously asked questions to avoid repetition
    const [askedQuestions, setAskedQuestions] = useState([]);
    
    // Unified UI state
    const [uiState, setUiState] = useState(UI_STATES.DEFAULT);
    
    // Loading states for upgrade buttons
    const [loadingSubscription, setLoadingSubscription] = useState(false);
    const [loadingOneTime, setLoadingOneTime] = useState(false);
    
    // Add state for the latest assessment to keep it visible
    const [latestAssessment, setLatestAssessment] = useState(null);
    
    // Add state for showing the onboarding component
    const [showChatOnboarding, setShowChatOnboarding] = useState(false);
    
    // Track if user has declined an upgrade
    const [hasDeclinedUpgrade, setHasDeclinedUpgrade] = useState(false);

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

    // Optimized scrollToBottom with debounce
    const debouncedScrollToBottom = useCallback(
        debounce(() => {
            if (messagesEndRef.current) {
                messagesEndRef.current.scrollIntoView({ behavior: "smooth" });
            }
        }, CONFIG.SCROLL_DEBOUNCE_DELAY),
        []
    );

    // Immediate scroll function for when we need it right away
    const scrollToBottomImmediate = useCallback(() => {
        if (messagesEndRef.current) {
            messagesEndRef.current.scrollIntoView({ behavior: "auto" });
        }
    }, []);

    // Scroll when messages change
    useEffect(() => {
        debouncedScrollToBottom();
    }, [messages, debouncedScrollToBottom]);

    // Scroll when typing state changes
    useEffect(() => {
        debouncedScrollToBottom();
    }, [typing, debouncedScrollToBottom]);

    useEffect(() => {
        return () => {
            if (abortControllerRef.current) {
                abortControllerRef.current.abort();
            }
            debouncedScrollToBottom.cancel();
        };
    }, [debouncedScrollToBottom]);

    const validateInput = useCallback((input) => {
        if (!input.trim()) return "Please enter a message";
        if (input.length > CONFIG.MAX_MESSAGE_LENGTH) {
            return "Message is too long";
        }
        return null;
    }, []);

    // Simplified message function - no character-by-character typing
    const addBotMessage = useCallback((message, isAssessment = false, confidence = null, triageLevel = null, careRecommendation = null) => {
        // Show thinking indicator
        setTyping(true);
        setIsTypingComplete(false);
        
        // Calculate a realistic thinking delay based on message length
        const wordCount = message.split(/\s+/).length;
        // Base delay between 1-3 seconds, with diminishing returns for very long messages
        const thinkingDelay = Math.min(1000 + (wordCount * 30), 3000);
        
        setTimeout(() => {
            // Add the complete message at once
            setMessages(prev => [...prev, {
                sender: 'bot',
                text: message,
                isAssessment,
                confidence,
                triageLevel,
                careRecommendation
            }]);
            
            // Increment bot message counter for non-assessment messages
            if (!isAssessment) {
                setBotMessageCount(prev => prev + 1);
            }
            
            setTyping(false);
            setIsTypingComplete(true);
            
            // Ensure message is visible
            debouncedScrollToBottom();
            
            // Focus input after message is complete
            if (inputRef.current) {
                inputRef.current.focus();
            }
        }, thinkingDelay);
        
        return thinkingDelay; // Return the delay for sequential messaging
    }, [debouncedScrollToBottom]);

    // New function for sequential messaging
    const addSequentialBotMessages = useCallback((messages, startDelay = 0) => {
        let currentDelay = startDelay;
        
        messages.forEach((messageData) => {
            setTimeout(() => {
                const { message, isAssessment, confidence, triageLevel, careRecommendation } = messageData;
                const messageDelay = addBotMessage(message, isAssessment, confidence, triageLevel, careRecommendation);
                // No need to add the message delay here since we're controlling the sequence manually
            }, currentDelay);
            
            currentDelay += CONFIG.MESSAGE_DELAY;
        });
    }, [addBotMessage]);

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
            setAskedQuestions([]); // Reset asked questions
            setError(null);
            setInputError(null);
            setIsTypingComplete(true);
            setLoadingSubscription(false);
            setLoadingOneTime(false);
            setLatestAssessment(null); // Reset the latest assessment
            setUiState(UI_STATES.DEFAULT); // Reset UI state
            setHasDeclinedUpgrade(false); // Reset upgrade decline state
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
            setAskedQuestions([]); // Reset asked questions
            setIsTypingComplete(true);
            setLoadingSubscription(false);
            setLoadingOneTime(false);
            setLatestAssessment(null); // Reset the latest assessment
            setUiState(UI_STATES.DEFAULT); // Reset UI state
            setHasDeclinedUpgrade(false); // Reset upgrade decline state
            localStorage.setItem(CONFIG.LOCAL_STORAGE_KEY, JSON.stringify([WELCOME_MESSAGE]));
        } finally {
            setResetting(false);
        }
    };

    // Generate a unique follow-up question that hasn't been asked before
    const generateUniqueFollowUpQuestion = useCallback((response, conditionName = "") => {
        // Get a follow-up question from the API or create a generic one
        let followUpQuestion = response.data.question || "";
        
        // If the question has already been asked, or no question was provided
        if (!followUpQuestion || askedQuestions.includes(followUpQuestion)) {
            // Create a unique follow-up question based on symptoms and what we've already asked
            const symptoms = response.data.symptoms || [];
            const possibleQuestions = [
                "When did your symptoms first start?",
                "Have you noticed any patterns or triggers that make your symptoms worse?",
                "Have you tried any treatments or medications for your symptoms?",
                "Does anyone in your family have a history of similar symptoms?",
                "Have you experienced these symptoms before?",
                "Are your symptoms constant or do they come and go?",
                "On a scale of 1-10, how would you rate the severity of your symptoms?",
                "Have you noticed any other symptoms that might be related?"
            ];
            
            // Filter out questions we've already asked
            const availableQuestions = possibleQuestions.filter(q => !askedQuestions.includes(q));
            
            if (symptoms.length > 0 && availableQuestions.length > 0) {
                // Pick a random symptom and a random question
                const symptom = symptoms[Math.floor(Math.random() * symptoms.length)];
                const questionTemplate = availableQuestions[Math.floor(Math.random() * availableQuestions.length)];
                
                // Customize the question with the symptom if applicable
                if (questionTemplate.includes("symptoms")) {
                    followUpQuestion = questionTemplate.replace("symptoms", `${symptom}`);
                } else {
                    followUpQuestion = questionTemplate;
                }
            } else if (availableQuestions.length > 0) {
                // Just pick a random question if no symptoms are available
                followUpQuestion = availableQuestions[Math.floor(Math.random() * availableQuestions.length)];
            } else {
                // If we've exhausted all questions, create a generic one
                followUpQuestion = "Could you tell me more about your symptoms?";
            }
        }
        
        // Add this question to the list of asked questions
        setAskedQuestions(prev => [...prev, followUpQuestion]);
        
        return `I have some possible insights about your condition${conditionName ? ` (possibly ${conditionName})` : ""}, but I need a bit more information to be certain. ${followUpQuestion}`;
    }, [askedQuestions]);

    // Enhanced scrollToAssessment function to ensure the assessment is visible
    const scrollToAssessment = useCallback(() => {
        if (messagesContainerRef.current) {
            // Find all assessment message elements
            const messageElements = messagesContainerRef.current.querySelectorAll('.message.bot');
            
            // Find the element containing the assessment (looking for the one with condition name)
            let targetElement = null;
            for (let i = messageElements.length - 1; i >= 0; i--) {
                if (messageElements[i].textContent.includes("most likely condition") || 
                    messageElements[i].textContent.includes("Urinary Tract Infection") ||
                    messageElements[i].textContent.includes("completed an assessment")) {
                    targetElement = messageElements[i];
                    break;
                }
            }
            
            // If we found the target element, scroll to it
            if (targetElement) {
                targetElement.scrollIntoView({
                    behavior: 'smooth',
                    block: 'start'
                });
            } else {
                // Fallback: scroll to a position that shows the assessment summary
                const scrollHeight = messagesContainerRef.current.scrollHeight;
                const clientHeight = messagesContainerRef.current.clientHeight;
                const scrollPosition = Math.max(0, scrollHeight - clientHeight - 300);
                
                messagesContainerRef.current.scrollTo({
                    top: scrollPosition,
                    behavior: 'smooth'
                });
            }
        }
    }, []);

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
                addBotMessage(
                    "Based on your symptoms, I've identified a condition that may require further evaluation. To get more insights, you can choose between Premium Access for unlimited symptom checks or a one-time Consultation Report for your current symptoms.",
                    false
                );
                
                // Show upgrade prompt after the explanation
                setTimeout(() => {
                    setUiState(UI_STATES.UPGRADE_PROMPT);
                    debouncedScrollToBottom();
                }, 500);
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
        if (uiState === UI_STATES.DEFAULT && messageCount > CONFIG.MAX_FREE_MESSAGES && hasDeclinedUpgrade) {
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
                debouncedScrollToBottom();
            }, 1000);
            
            // Don't continue with API call if we're showing a secondary prompt
            if (!retryMessage) setUserInput('');
            return;
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
        scrollToBottomImmediate();

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
                const isAssessment = response.data.is_assessment === true;
                const requiresUpgrade = response.data.requires_upgrade === true;
                
                // Get confidence level
                const confidence = response.data.confidence || 
                                  (response.data.assessment?.conditions && 
                                   response.data.assessment.conditions[0]?.confidence) || 0;
                
                // Only treat as assessment if confidence is high enough
                const isConfidentAssessment = isAssessment && confidence >= CONFIG.MIN_CONFIDENCE_THRESHOLD;
                
                // Get condition name for context in follow-up questions
                let conditionName = "";
                if (response.data.assessment?.conditions && response.data.assessment.conditions.length > 0) {
                    conditionName = response.data.assessment.conditions[0].name;
                }
                
                // Add detailed logging
                if (CONFIG.DEBUG_MODE) {
                    console.log("API response analysis:", {
                        isAssessment,
                        requiresUpgrade,
                        confidence,
                        isConfidentAssessment,
                        conditionName,
                        responseData: response.data
                    });
                }
                
                // If we have a response but no question or assessment, generate a follow-up
                if (!response.data.question && !isAssessment && !response.data.error) {
                    const followUpMessage = "I need more details to be certain. Can you tell me more about your symptoms?";
                    addBotMessage(followUpMessage, false);
                    return;
                }
                
                if (isConfidentAssessment) {
                    // It's a final assessment with conditions and high confidence
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
                        
                        // Only now check if upgrade is required - AFTER confirming high confidence
                        if (requiresUpgrade) {
                            // Add sequential messages for a smoother experience
                            addSequentialBotMessages([
                                {
                                    message: "Based on your symptoms, I've completed an assessment.",
                                    isAssessment: true
                                },
                                {
                                    // Add the actual assessment with condition name and confidence BEFORE the upgrade message
                                    message: `The most likely condition is ${conditions[0].name} (${conditions[0].confidence}% confidence).`,
                                    isAssessment: true,
                                    confidence: conditions[0].confidence
                                },
                                {
                                    message: careRecommendation || "Consider consulting with a healthcare provider for proper evaluation.",
                                    isAssessment: true,
                                    triageLevel: triageLevel,
                                    careRecommendation: careRecommendation
                                },
                                {
                                    message: "To get more detailed insights, you can choose between Premium Access for unlimited symptom checks or a one-time Consultation Report for your current symptoms.",
                                    isAssessment: false
                                }
                            ]);
                            
                            // Show both assessment and upgrade after a delay
                            setTimeout(() => {
                                setUiState(UI_STATES.ASSESSMENT_WITH_UPGRADE);
                                
                                // Schedule multiple attempts to scroll to the right position
                                const scrollTimes = [100, 300, 600, 1000, 1500];
                                scrollTimes.forEach(time => {
                                    setTimeout(scrollToAssessment, time);
                                });
                            }, 4000); // Increased delay to account for sequential messages
                        } else {
                            // Regular assessment without upgrade - split into sequential messages
                            addSequentialBotMessages([
                                {
                                    message: "Based on your symptoms, I've completed an assessment.",
                                    isAssessment: true
                                },
                                {
                                    message: `The most likely condition is ${conditions[0].name} (${conditions[0].confidence}% confidence).`,
                                    isAssessment: true,
                                    confidence: conditions[0].confidence
                                },
                                {
                                    message: careRecommendation,
                                    isAssessment: true,
                                    triageLevel: triageLevel,
                                    careRecommendation: careRecommendation
                                },
                                {
                                    message: disclaimer,
                                    isAssessment: true
                                }
                            ]);
                            
                            // Set UI state to ASSESSMENT
                            setTimeout(() => {
                                setUiState(UI_STATES.ASSESSMENT);
                                
                                // Schedule multiple attempts to scroll to the right position
                                const scrollTimes = [100, 300, 600, 1000];
                                scrollTimes.forEach(time => {
                                    setTimeout(scrollToAssessment, time);
                                });
                            }, 1000);
                        }
                    } else {
                        // Unstructured assessment
                        const formattedMessage = response.data.possible_conditions || "Based on your symptoms, I can provide an assessment.";
                        triageLevel = response.data.triage_level;
                        careRecommendation = response.data.care_recommendation;
                        
                        // Update the latest assessment for the sticky summary
                        setLatestAssessment({
                            condition: "Assessment",
                            confidence: confidence,
                            recommendation: careRecommendation
                        });
                        
                        // Only now check if upgrade is required - AFTER confirming high confidence
                        if (requiresUpgrade) {
                            // Add sequential messages for a smoother experience
                            addSequentialBotMessages([
                                {
                                    message: "Based on your symptoms, I've completed an assessment.",
                                    isAssessment: true
                                },
                                {
                                    // Add assessment details before upgrade prompt
                                    message: formattedMessage,
                                    isAssessment: true,
                                    confidence: confidence,
                                    triageLevel: triageLevel,
                                    careRecommendation: careRecommendation
                                },
                                {
                                    message: "To get more detailed insights, you can choose between Premium Access for unlimited symptom checks or a one-time Consultation Report for your current symptoms.",
                                    isAssessment: false
                                }
                            ]);
                            
                            // Show both assessment and upgrade after a delay
                            setTimeout(() => {
                                setUiState(UI_STATES.ASSESSMENT_WITH_UPGRADE);
                                
                                // Schedule multiple attempts to scroll to the right position
                                const scrollTimes = [100, 300, 600, 1000, 1500];
                                scrollTimes.forEach(time => {
                                    setTimeout(scrollToAssessment, time);
                                });
                            }, 4000); // Increased delay to account for sequential messages
                        } else {
                            // For non-upgrade assessments, show the full assessment
                            addBotMessage(
                                formattedMessage,
                                true,
                                confidence,
                                triageLevel,
                                careRecommendation
                            );
                            
                            // Set UI state to ASSESSMENT
                            setUiState(UI_STATES.ASSESSMENT);
                            
                            // Schedule multiple attempts to scroll to the right position
                            setTimeout(() => {
                                const scrollTimes = [100, 300, 600, 1000];
                                scrollTimes.forEach(time => {
                                    setTimeout(scrollToAssessment, time);
                                });
                            }, 1000);
                        }
                    }
                } else if (isAssessment) {
                    // It's an assessment but confidence is too low - ALWAYS ask more questions
                    // regardless of whether the server says upgrade is required
                    
                    // Check if the response contains a follow-up question
                    if (response.data.question) {
                        addBotMessage(response.data.question, false);
                    } else {
                        // Generate a unique follow-up question
                        const followUpMessage = generateUniqueFollowUpQuestion(response, conditionName);
                        addBotMessage(followUpMessage, false);
                    }
                    
                    // Log this situation for debugging
                    if (CONFIG.DEBUG_MODE && requiresUpgrade) {
                        console.warn("Server requested upgrade but confidence is too low. Asking more questions instead.");
                    }
                } else {
                    // It's a follow-up question or other response
                    const responseText = response.data.question || response.data.possible_conditions || "Could you tell me more about your symptoms?";
                    addBotMessage(responseText, false);
                    
                    // Add this question to asked questions to avoid repetition
                    if (response.data.question) {
                        setAskedQuestions(prev => [...prev, response.data.question]);
                    }
                }
            }, CONFIG.THINKING_DELAY);

        } catch (error) {
            if (!axios.isCancel(error)) {
                if (CONFIG.DEBUG_MODE) {
                    console.error("API error details:", error);
                }
                
                let errorMessage = "I apologize, but I'm having trouble processing your request.";
                
                if (error.response) {
                    // Check if this is actually a valid response with requires_upgrade=false
                    // that was incorrectly caught as an error
                    if (error.response.data && error.response.status === 200) {
                        // This is actually a valid response, not an error
                        // Process it normally
                        const response = error.response;
                        
                        // Log the response for debugging
                        if (CONFIG.DEBUG_MODE) {
                            console.log("Valid response caught in error handler:", response.data);
                        }
                        
                        // Process the response as normal
                        setTimeout(() => {
                            // Re-use the same processing logic as the success path
                            const isAssessment = response.data.is_assessment === true;
                            const requiresUpgrade = response.data.requires_upgrade === true;
                            const confidence = response.data.confidence || 
                                             (response.data.assessment?.conditions && 
                                              response.data.assessment.conditions[0]?.confidence) || 0;
                            const isConfidentAssessment = isAssessment && confidence >= CONFIG.MIN_CONFIDENCE_THRESHOLD;
                            
                            // For now, just add a simple follow-up question
                            addBotMessage(response.data.possible_conditions || "Could you tell me more about your symptoms?", false);
                        }, CONFIG.THINKING_DELAY);
                        
                        return;
                    }
                    
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
                    addBotMessage(errorMessage, false);
                }, CONFIG.THINKING_DELAY);
            }
        } finally {
            setLoading(false);
            // Don't set typing to false here - it will be set in addBotMessage when typing is complete
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
                    
                    {/* Add the sticky assessment summary here - INSIDE the messages container */}
                    {(uiState === UI_STATES.ASSESSMENT || uiState === UI_STATES.ASSESSMENT_WITH_UPGRADE) && latestAssessment && (
                        <AssessmentSummary assessment={latestAssessment} />
                    )}
                    
                    {/* Show upgrade prompt if in UPGRADE_PROMPT or ASSESSMENT_WITH_UPGRADE state - INSIDE the messages container */}
                    {(uiState === UI_STATES.UPGRADE_PROMPT || uiState === UI_STATES.ASSESSMENT_WITH_UPGRADE) && (
                        <div className="upgrade-options">
                            <button 
                                className="close-upgrade" 
                                onClick={() => {
                                    setUiState(uiState === UI_STATES.ASSESSMENT_WITH_UPGRADE ? UI_STATES.ASSESSMENT : UI_STATES.DEFAULT);
                                    setHasDeclinedUpgrade(true); // Track that user has declined upgrade
                                    if (inputRef.current) {
                                        inputRef.current.focus();
                                    }
                                }}
                                aria-label="Dismiss upgrade prompt"
                            >
                                ✖
                            </button>
                            <div className="upgrade-message">
                                <h3>
                                    Based on your symptoms, 
                                    {latestAssessment ? 
                                        ` I've identified ${latestAssessment.condition} as a possible condition that may require further evaluation.` : 
                                        ` I've identified a condition that may require further evaluation.`}
                                </h3>
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
    typingSpeed: 30,
    thinkingDelay: CONFIG.THINKING_DELAY
};

export default Chat;