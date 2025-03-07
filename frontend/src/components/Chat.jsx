// Chat.jsx
import React, { useState, useRef, useEffect, useCallback, memo } from 'react';
import PropTypes from 'prop-types';
import { debounce } from 'lodash';
import UpgradePrompt from './UpgradePrompt'; // Import the existing component
import '../styles/Chat.css';

// Add this at the top of Chat.jsx, right after the imports
console.log("CHAT.JSX LOADED AT", new Date().toISOString());

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

const Message = memo(({ message, onRetry, index }) => {
    // Regular message handling (removed upgrade prompt handling as it's now a separate component)
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
                {isAssessment && (
                    <div className="assessment-indicator">Assessment</div>
                )}
                <div className="message-content">
                    {text.split('\n').map((line, i) => (
                        <p key={i}>{line}</p>
                    ))}
                </div>
                {/* Show metrics if this is an assessment */}
                {sender === 'bot' && isAssessment && (confidence || careRecommendation || triageLevel) && (
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
        sender: PropTypes.string,
        text: PropTypes.string,
        confidence: PropTypes.number,
        careRecommendation: PropTypes.string,
        isAssessment: PropTypes.bool,
        triageLevel: PropTypes.string,
        isAssessmentSummary: PropTypes.bool
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

    // Track if the last message was an upgrade prompt to prevent duplicates
    const [lastMessageWasUpgradePrompt, setLastMessageWasUpgradePrompt] = useState(false);

    // Track API retry attempts
    const [apiRetryCount, setApiRetryCount] = useState(0);
    const MAX_API_RETRIES = 3;

    const messagesEndRef = useRef(null);
    const abortControllerRef = useRef(null);
    const chatContainerRef = useRef(null);
    const inputRef = useRef(null);
    const messagesContainerRef = useRef(null);

    // Helper function to ensure upgrade prompt is shown for certain conditions
    const ensureUpgradePromptForCondition = useCallback((responseData, conditionName) => {
        // Check if this is an infectious disease case
        const isInfectiousDisease = 
            conditionName?.toLowerCase().includes('infectious') || 
            responseData.possible_conditions?.toLowerCase().includes('infectious') ||
            responseData.possible_conditions?.toLowerCase().includes('fever') ||
            responseData.possible_conditions?.toLowerCase().includes('viral') ||
            responseData.possible_conditions?.toLowerCase().includes('bacterial');
        
        if (isInfectiousDisease && CONFIG.DEBUG_MODE) {
            console.log("Detected infectious disease case, ensuring upgrade prompt is displayed", {
                conditionName,
                possibleConditions: responseData.possible_conditions
            });
        }
        
        // Always return true to ensure upgrade prompt is shown
        return true;
    }, []);

    // Handle continue with free version - improved as per developer feedback
    const handleContinueFree = useCallback(() => {
        // Reset UI state completely
        setUiState(UI_STATES.DEFAULT);
        setLoading(false);
        setTyping(false);
        setHasDeclinedUpgrade(true); // Prevent immediate re-prompting
        setLastMessageWasUpgradePrompt(false); // Reset upgrade prompt tracking
        
        // Add a message acknowledging their choice to continue with free version
        addBotMessage(
            "You can continue using the free version for this assessment. Feel free to ask me more questions about managing your condition at home.",
            false
        );
        
        // Focus on input field after a short delay to ensure the DOM has updated
        setTimeout(() => {
            if (inputRef.current) {
                inputRef.current.focus();
            }
        }, 100);
    }, []);

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
        if (CONFIG.DEBUG_MODE) {
            console.log("Messages updated:", messages);
        }
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
            await fetch(CONFIG.RESET_URL, {
                method: 'POST'
            });
            
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
            setLastMessageWasUpgradePrompt(false); // Reset upgrade prompt tracking
            setApiRetryCount(0); // Reset API retry count
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
            setLastMessageWasUpgradePrompt(false); // Reset upgrade prompt tracking
            setApiRetryCount(0); // Reset API retry count
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

        // Reset upgrade prompt tracking when user sends a new message
        setLastMessageWasUpgradePrompt(false);

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

        // Create an AbortController for fetch
        const controller = new AbortController();
        abortControllerRef.current = controller;

        try {
            // Prepare conversation history with proper formatting
            const conversationHistory = messages
                .filter(msg => msg.text && msg.text.trim() !== "") // Filter out empty messages and special messages
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

            // Use fetch API instead of axios
            const response = await fetch(CONFIG.API_URL, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(enhancedRequest),
                signal: controller.signal
            });

            // Check if the response is ok
            if (!response.ok) {
                throw new Error(`API returned status code ${response.status}`);
            }

            // Parse the response
            const responseData = await response.json();

            // Reset API retry count on successful response
            setApiRetryCount(0);

            // Debug logging
            if (CONFIG.DEBUG_MODE) {
                console.log("Raw API response:", responseData);
                console.log("Requires upgrade:", responseData.requires_upgrade);
                console.log("Is assessment:", responseData.is_assessment);
                console.log("Upgrade suggestion:", responseData.upgrade_suggestion);
                console.log("API Response Structure:", {
                    isAssessment: responseData.is_assessment,
                    requiresUpgrade: responseData.requires_upgrade,
                    upgradeSuggestion: responseData.upgrade_suggestion,
                    confidence: responseData.confidence,
                    hasAssessmentObject: !!responseData.assessment,
                    hasConditions: !!(responseData.assessment?.conditions),
                    careRecommendation: responseData.care_recommendation,
                    possibleConditions: responseData.possible_conditions,
                    triageLevel: responseData.triage_level || responseData.assessment?.triage_level
                });
            }

            setTimeout(() => {
                // Check if this is a question or assessment
                const isAssessment = responseData.is_assessment === true;
                const requiresUpgrade = responseData.requires_upgrade === true;
                const upgradeSuggestion = responseData.upgrade_suggestion === true;
                
                // Get confidence level
                const confidence = responseData.confidence || 
                                  (responseData.assessment?.conditions && 
                                   responseData.assessment.conditions[0]?.confidence) || 0;
                
                // Only treat as assessment if confidence is high enough
                const isConfidentAssessment = isAssessment && confidence >= CONFIG.MIN_CONFIDENCE_THRESHOLD;
                
                // Get condition name for context in follow-up questions
                let conditionName = "";
                let commonName = null;
                
                if (responseData.assessment?.conditions && responseData.assessment.conditions.length > 0) {
                    conditionName = responseData.assessment.conditions[0].name;
                    // Extract common name if available
                    commonName = responseData.assessment.conditions[0].common_name || null;
                }
                
                // Get triage level
                let triageLevel = responseData.triage_level || 
                                 (responseData.assessment?.triage_level) || 
                                 'UNKNOWN';
                
                // Check if this is a mild case (at-home care)
                const isMildCase = triageLevel?.toLowerCase() === 'mild';
                
                // If no common_name is provided, try to map common conditions
                if (!commonName) {
                    // Expanded mapping for common conditions
                    const commonNameMap = {
                        // Respiratory conditions
                        "Upper Respiratory Infection": "Common Cold",
                        "Acute Rhinosinusitis": "Sinus Infection",
                        "Acute Pharyngitis": "Sore Throat",
                        "Acute Bronchitis": "Chest Cold",
                        "Pneumonia": "Lung Infection",
                        "Influenza": "Flu",
                        "Rhinitis": "Runny Nose",
                        
                        // Neurological conditions
                        "Neurological condition": "Migraine",
                        "Cephalalgia": "Headache",
                        "Tension Cephalalgia": "Tension Headache",
                        "Cluster Cephalalgia": "Cluster Headache",
                        "Vertigo": "Dizziness",
                        
                        // Gastrointestinal conditions
                        "Gastroenteritis": "Stomach Flu",
                        "Gastroesophageal Reflux Disease": "Acid Reflux",
                        "Irritable Bowel Syndrome": "IBS",
                        "Acute Gastritis": "Stomach Inflammation",
                        "Constipation": "Constipation",
                        "Diarrhea": "Diarrhea",
                        
                        // Skin conditions
                        "Dermatitis": "Skin Rash",
                        "Urticaria": "Hives",
                        "Contact Dermatitis": "Contact Rash",
                        "Eczema": "Eczema",
                        "Psoriasis": "Psoriasis",
                        "Cellulitis": "Skin Infection",
                        
                        // Ear, nose, throat
                        "Otitis Media": "Ear Infection",
                        "Otitis Externa": "Swimmer's Ear",
                        "Tonsillitis": "Tonsil Infection",
                        "Laryngitis": "Voice Box Inflammation",
                        
                        // Other common conditions
                        "Conjunctivitis": "Pink Eye",
                        "Urinary Tract Infection": "UTI",
                        "Hypertension": "High Blood Pressure",
                        "Hyperlipidemia": "High Cholesterol",
                        "Diabetes Mellitus": "Diabetes",
                        "Anxiety Disorder": "Anxiety",
                        "Major Depressive Disorder": "Depression",
                        "Insomnia": "Sleep Disorder"
                    };
                    
                    // Check if we have a mapping for this condition
                    commonName = commonNameMap[conditionName] || null;
                }
                
                // Add specific debug logging for condition name handling
                if (CONFIG.DEBUG_MODE) {
                    console.log("Condition name processing:", {
                        medicalTerm: conditionName,
                        providedCommonName: responseData.assessment?.conditions?.[0]?.common_name,
                        mappedCommonName: commonName,
                        finalCommonName: commonName,
                        triageLevel: triageLevel,
                        isMildCase: isMildCase
                    });
                }
                
                // Add specific logging for infectious disease cases
                if (conditionName.toLowerCase().includes("infectious") || 
                    conditionName.toLowerCase().includes("infection") ||
                    responseData.possible_conditions?.toLowerCase().includes("infectious")) {
                    console.log("Infectious disease case detected:", {
                        conditionName,
                        commonName,
                        responseData,
                        uiState
                    });
                }
                
                // Add detailed logging
                if (CONFIG.DEBUG_MODE) {
                    console.log("API response analysis:", {
                        isAssessment,
                        requiresUpgrade,
                        upgradeSuggestion,
                        confidence,
                        isConfidentAssessment,
                        conditionName,
                        commonName,
                        triageLevel,
                        isMildCase,
                        responseData
                    });
                }
                
                // If we have a response but no question or assessment, generate a follow-up
                if (!responseData.question && !isAssessment && !responseData.error) {
                    const followUpMessage = "I need more details to be certain. Can you tell me more about your symptoms?";
                    addBotMessage(followUpMessage, false);
                    return;
                }
                
                if (isConfidentAssessment) {
                    // Add debug logging to help identify issues
                    if (CONFIG.DEBUG_MODE) {
                        console.log("Processing confident assessment:", {
                            isAssessment,
                            requiresUpgrade,
                            upgradeSuggestion,
                            confidence,
                            triageLevel,
                            isMildCase,
                            conditionName,
                            commonName,
                            responseData
                        });
                    }

                    // It's a final assessment with conditions and high confidence
                    let careRecommendation = null;

                    if (responseData.assessment?.conditions) {
                        const conditions = responseData.assessment.conditions;
                        careRecommendation = responseData.assessment.care_recommendation || responseData.care_recommendation;

                        // Update the latest assessment for reference
                        if (conditions && conditions.length > 0) {
                            conditionName = conditions[0].name;
                            setLatestAssessment({
                                condition: conditionName,
                                commonName: commonName,
                                confidence: conditions[0].confidence,
                                recommendation: careRecommendation,
                                triageLevel: triageLevel
                            });
                        }
                        
                        // Create display name with both common and medical terms
                        const displayName = commonName ? 
                            `${commonName} (${conditionName})` : 
                            conditionName;
                        
                        // Step 1: Bot assessment message (looks natural in chat)
                        addBotMessage(
                            `🩺 The most likely condition is **${displayName}** (**${confidence}% confidence**).\n\n${careRecommendation || ""}`,
                            true,
                            confidence,
                            triageLevel,
                            careRecommendation
                        );

                        // Step 2: Always show upgrade prompt after assessment
                        // Different messaging for mild vs. moderate/severe cases
                        setTimeout(() => {
                            // Only send upgrade message if the last message wasn't already an upgrade prompt
                            if (!lastMessageWasUpgradePrompt) {
                                if (isMildCase) {
                                    addBotMessage(
                                        `🔍 While you can manage this condition at home, Premium Access gives you deeper insights, symptom tracking, and doctor-ready reports if you'd like more detailed information.`,
                                        false
                                    );
                                } else {
                                    addBotMessage(
                                        `🔍 For a more comprehensive understanding of your condition, I recommend upgrading. Premium Access lets you track symptoms over time, while the Consultation Report gives you a detailed breakdown for your doctor. Which option works best for you?`,
                                        false
                                    );
                                }
                                setLastMessageWasUpgradePrompt(true);
                            }
                            
                            // Step 3: ALWAYS set upgrade prompt state after assessment
                            setTimeout(() => {
                                // Set UI state to upgrade prompt
                                setUiState(UI_STATES.UPGRADE_PROMPT);
                                
                                // Reset the flag when user interacts again
                                const resetUpgradePromptFlag = () => {
                                    setLastMessageWasUpgradePrompt(false);
                                };
                                
                                // Add event listener to reset flag on user input
                                inputRef.current?.addEventListener('focus', resetUpgradePromptFlag, { once: true });
                                
                                // Ensure everything is visible with multiple scroll attempts
                                setTimeout(() => {
                                    if (messagesEndRef.current) {
                                        messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
                                    }
                                }, 100);
                                
                                // Backup scroll attempts to ensure visibility
                                setTimeout(() => {
                                    if (messagesEndRef.current) {
                                        messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
                                    }
                                }, 300);
                                
                                setTimeout(() => {
                                    if (messagesEndRef.current) {
                                        messagesEndRef.current.scrollIntoView({ behavior: 'auto' });
                                    }
                                }, 600);
                            }, 500);
                        }, 500);
                    } else {
                        // Unstructured assessment handling (similar pattern as above)
                        const formattedMessage = responseData.possible_conditions || "Based on your symptoms, I can provide an assessment.";
                        careRecommendation = responseData.care_recommendation;
                        
                        // Try to extract common name from possible conditions if available
                        let commonName = null;
                        if (responseData.common_condition_name) {
                            commonName = responseData.common_condition_name;
                        }
                        
                        // Update the latest assessment for the sticky summary
                        setLatestAssessment({
                            condition: "Assessment",
                            commonName: commonName,
                            confidence: confidence,
                            recommendation: careRecommendation,
                            triageLevel: triageLevel
                        });
                        
                        // Create display message with common name if available
                        const displayMessage = commonName ? 
                            `${formattedMessage} (commonly known as ${commonName})` : 
                            formattedMessage;
                        
                        // Step 1: Bot assessment message
                        addBotMessage(
                            `🩺 ${displayMessage} (**${confidence}% confidence**).\n\n${careRecommendation || ""}`,
                            true,
                            confidence,
                            triageLevel,
                            careRecommendation
                        );
                        
                        // Step 2: Always show upgrade prompt after assessment
                        setTimeout(() => {
                            // Only send upgrade message if the last message wasn't already an upgrade prompt
                            if (!lastMessageWasUpgradePrompt) {
                                // Different messaging for mild vs. moderate/severe cases
                                if (isMildCase) {
                                    addBotMessage(
                                        `🔍 While you can manage this condition at home, Premium Access gives you deeper insights, symptom tracking, and doctor-ready reports if you'd like more detailed information.`,
                                        false
                                    );
                                } else {
                                    addBotMessage(
                                        `🔍 For a more comprehensive understanding of your condition, I recommend upgrading. Premium Access lets you track symptoms over time, while the Consultation Report gives you a detailed breakdown for your doctor. Which option works best for you?`,
                                        false
                                    );
                                }
                                setLastMessageWasUpgradePrompt(true);
                            }
                            
                            // Step 3: ALWAYS set upgrade prompt state after assessment
                            setTimeout(() => {
                                // Set UI state to upgrade prompt
                                setUiState(UI_STATES.UPGRADE_PROMPT);
                                
                                // Reset the flag when user interacts again
                                const resetUpgradePromptFlag = () => {
                                    setLastMessageWasUpgradePrompt(false);
                                };
                                
                                // Add event listener to reset flag on user input
                                inputRef.current?.addEventListener('focus', resetUpgradePromptFlag, { once: true });
                                
                                // Multiple scroll attempts to ensure visibility
                                setTimeout(() => {
                                    if (messagesEndRef.current) {
                                        messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
                                    }
                                }, 100);
                                
                                setTimeout(() => {
                                    if (messagesEndRef.current) {
                                        messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
                                    }
                                }, 300);
                                
                                setTimeout(() => {
                                    if (messagesEndRef.current) {
                                        messagesEndRef.current.scrollIntoView({ behavior: 'auto' });
                                    }
                                }, 600);
                            }, 500);
                        }, 500);
                    }
                } else if (isAssessment) {
                    // It's an assessment but confidence is too low - ALWAYS ask more questions
                    // regardless of whether the server says upgrade is required
                    
                    // Check if the response contains a follow-up question
                    if (responseData.question) {
                        addBotMessage(responseData.question, false);
                    } else {
                        // Generate a unique follow-up question
                        const followUpMessage = generateUniqueFollowUpQuestion({data: responseData}, conditionName);
                        addBotMessage(followUpMessage, false);
                    }
                    
                    // Log this situation for debugging
                    if (CONFIG.DEBUG_MODE && requiresUpgrade) {
                        console.warn("Server requested upgrade but confidence is too low. Asking more questions instead.");
                    }
                } else {
                    // It's a follow-up question or other response
                    const responseText = responseData.question || responseData.possible_conditions || "Could you tell me more about your symptoms?";
                    addBotMessage(responseText, false);
                    
                    // Add this question to asked questions to avoid repetition
                    if (responseData.question) {
                        setAskedQuestions(prev => [...prev, responseData.question]);
                    }
                }
            }, CONFIG.THINKING_DELAY);

        } catch (error) {
            if (error.name !== 'AbortError') {
                if (CONFIG.DEBUG_MODE) {
                    console.error("API error details:", error);
                    console.error("Request that failed:", {
                        messageToSend,
                        apiRetryCount,
                        uiState
                    });
                }
                
                // Check if we should retry
                if (apiRetryCount < MAX_API_RETRIES) {
                    setApiRetryCount(prev => prev + 1);
                    
                    // Show a temporary message
                    setMessages(prev => [...prev, {
                        sender: 'bot',
                        text: "I'm having a brief connection issue. Retrying in a moment...",
                        isTemporary: true
                    }]);
                    
                    // Retry after a delay
                    setTimeout(() => {
                        // Remove the temporary message
                        setMessages(prev => prev.filter(msg => !msg.isTemporary));
                        
                        // Retry the request
                        handleSendMessage(messageToSend);
                    }, 2000); // 2 second delay before retry
                    
                    return;
                }
                
                // If we've reached max retries, show error message
                let errorMessage = "I apologize, but I'm having trouble processing your request.";
                
                if (error.message.includes('status code')) {
                    if (error.message.includes('429')) {
                        errorMessage = "I'm receiving too many requests right now. Please try again in a moment.";
                    } else if (error.message.includes('5')) {
                        errorMessage = "I'm having trouble connecting to my medical knowledge. Please try again shortly.";
                    }
                } else {
                    errorMessage = "I'm having trouble connecting to my medical database. Please check your internet connection and try again.";
                }
                
                setError(errorMessage);
                setTimeout(() => {
                    addBotMessage(errorMessage, false);
                }, CONFIG.THINKING_DELAY);
                
                // Reset retry count after showing error
                setApiRetryCount(0);
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
                className="chat-container" 
                ref={chatContainerRef} 
                role="main" 
                aria-label="Chat interface"
            >
                {/* Replace the chat header with just the reset button container */}
                <div className="reset-button-container">
                    <button 
                        className="reset-button"
                        onClick={handleResetConversation}
                        disabled={loading || resetting}
                        aria-label="Reset conversation"
                    >
                        {resetting ? 'Resetting...' : 'Reset Conversation'}
                    </button>
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
                    
                    {/* Show upgrade prompt as a separate component when in upgrade prompt state */}
                    {uiState === UI_STATES.UPGRADE_PROMPT && latestAssessment && (
                        <UpgradePrompt 
                            key={`upgrade-${latestAssessment.condition}`} // Add key to force re-render
                            condition={latestAssessment.condition || "this condition"}
                            commonName={latestAssessment.commonName || ""}
                            isMildCase={latestAssessment.triageLevel?.toLowerCase() === "mild"}
                            onDismiss={handleContinueFree}
                        />
                    )}
                    
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
                            disabled={loading || resetting || (uiState === UI_STATES.UPGRADE_PROMPT && latestAssessment?.triageLevel?.toLowerCase() !== "mild")}
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
                            disabled={loading || resetting || !userInput.trim() || (uiState === UI_STATES.UPGRADE_PROMPT && latestAssessment?.triageLevel?.toLowerCase() !== "mild")}
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