import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { useAuth } from './AuthProvider';
import UpgradePrompt from './UpgradePrompt';
import '../styles/Chat.css';
import '../styles/shared.css';

const Chat = () => {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [error, setError] = useState(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [assessmentCompleted, setAssessmentCompleted] = useState(false);
  const messagesEndRef = useRef(null);
  const navigate = useNavigate();
  const { isAuthenticated, subscriptionTier } = useAuth();

  // Initialize chat with welcome message
  useEffect(() => {
    const savedMessages = localStorage.getItem('healthtracker_chat_messages');
    if (savedMessages) {
      try {
        const parsedMessages = JSON.parse(savedMessages);
        setMessages(parsedMessages);
        
        // Check if there's an assessment in the saved messages
        const hasAssessment = parsedMessages.some(msg => 
          msg.sender === 'bot' && 
          typeof msg.text === 'object' && 
          msg.text.is_assessment === true
        );
        setAssessmentCompleted(hasAssessment);
      } catch (e) {
        console.error('Failed to parse saved messages:', e);
        initializeChat();
      }
    } else {
      initializeChat();
    }
  }, []);

  // Save messages to localStorage whenever they change
  useEffect(() => {
    if (messages.length > 0) {
      localStorage.setItem('healthtracker_chat_messages', JSON.stringify(messages));
    }
  }, [messages]);

  // Scroll to bottom whenever messages change
  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const initializeChat = () => {
    const welcomeMessage = {
      text: "Hi, I'm Michele—your AI medical assistant. Think of me as that doctor you absolutely trust, here to listen, guide, and help you make sense of your symptoms. While I can't replace a real doctor, I can give you insights, ask the right questions, and help you feel more in control of your health.\n\nYou can start by describing your symptoms like:\n• \"I've had a headache for two days\"\n• \"My throat is sore and I have a fever\"\n• \"I have a rash on my arm that's itchy\"",
      sender: 'bot',
      timestamp: new Date().toISOString()
    };
    setMessages([welcomeMessage]);
  };

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const handleInputChange = (e) => {
    setInput(e.target.value);
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  const resetConversation = async () => {
    setIsAnalyzing(true);
    setError(null);
    
    try {
      const token = localStorage.getItem('access_token');
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      
      const response = await axios.post(
        `${import.meta.env.VITE_API_URL || '/api'}/symptoms/reset`,
        {},
        { headers }
      );
      
      if (response.data && response.data.response) {
        setMessages([{
          text: response.data.response,
          sender: 'bot',
          timestamp: new Date().toISOString()
        }]);
        setAssessmentCompleted(false);
      } else {
        initializeChat();
      }
    } catch (err) {
      console.error('Error resetting conversation:', err);
      setError('Failed to reset conversation. Please try again.');
      initializeChat();
    } finally {
      setIsAnalyzing(false);
    }
  };

  const handleSendMessage = async () => {
    if (!input.trim() || isAnalyzing) return;
    
    const userMessage = {
      text: input.trim(),
      sender: 'user',
      timestamp: new Date().toISOString()
    };
    
    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setIsTyping(true);
    setIsAnalyzing(true);
    setError(null);
    
    try {
      // Convert messages to the format expected by the API
      const conversationHistory = messages.map(msg => ({
        message: typeof msg.text === 'object' ? JSON.stringify(msg.text) : msg.text,
        isBot: msg.sender === 'bot'
      }));
      
      const token = localStorage.getItem('access_token');
      const headers = token ? { Authorization: `Bearer ${token}` } : {};
      
      const response = await axios.post(
        `${import.meta.env.VITE_API_URL || '/api'}/symptoms/analyze`,
        {
          symptom: userMessage.text,
          conversation_history: conversationHistory
        },
        { headers }
      );
      
      if (response.data && response.data.response) {
        const botResponse = response.data.response;
        
        // Check if the response is an assessment
        if (typeof botResponse === 'object' && botResponse.is_assessment) {
          setAssessmentCompleted(true);
          
          // Add the assessment to messages
          setMessages(prev => [...prev, {
            text: botResponse,
            sender: 'bot',
            timestamp: new Date().toISOString()
          }]);
        } else {
          // Regular text response
          setMessages(prev => [...prev, {
            text: botResponse,
            sender: 'bot',
            timestamp: new Date().toISOString()
          }]);
        }
      }
    } catch (err) {
      console.error('Error analyzing symptoms:', err);
      setError('Failed to analyze symptoms. Please try again.');
      
      setMessages(prev => [...prev, {
        text: "I'm sorry, I couldn't process your request. Please try again.",
        sender: 'bot',
        timestamp: new Date().toISOString(),
        isError: true
      }]);
    } finally {
      setIsTyping(false);
      setIsAnalyzing(false);
    }
  };

  const handleDismissUpgrade = () => {
    // Find the last assessment message and update it
    const updatedMessages = [...messages];
    for (let i = updatedMessages.length - 1; i >= 0; i--) {
      const msg = updatedMessages[i];
      if (msg.sender === 'bot' && typeof msg.text === 'object' && msg.text.is_assessment) {
        // Clone the message and remove requires_upgrade flag
        const updatedMsg = {
          ...msg,
          text: {
            ...msg.text,
            requires_upgrade: false
          }
        };
        updatedMessages[i] = updatedMsg;
        break;
      }
    }
    setMessages(updatedMessages);
    localStorage.setItem('healthtracker_chat_messages', JSON.stringify(updatedMessages));
  };

  const renderMessage = (message, index) => {
    const { text, sender, isError } = message;
    
    // Handle assessment messages (objects)
    if (sender === 'bot' && typeof text === 'object' && text.is_assessment) {
      const isPremiumUser = subscriptionTier === 'paid' || subscriptionTier === 'one_time';
      const requiresUpgrade = text.requires_upgrade && !isPremiumUser;
      
      // Extract assessment details
      const condition = text.possible_conditions || 'Unknown condition';
      const commonName = condition.match(/\((.*?)\)/) ? condition.match(/\((.*?)\)/)[1] : '';
      const medicalTerm = condition.replace(/\s*\(.*?\)\s*/, '');
      
      // Determine if it's a mild case
      const isMildCase = (text.triage_level || '').toUpperCase() === 'MILD';
      
      if (requiresUpgrade || (text.requires_upgrade && !isPremiumUser)) {
        return (
          <UpgradePrompt
            key={index}
            condition={medicalTerm}
            commonName={commonName}
            isMildCase={isMildCase}
            requiresUpgrade={requiresUpgrade}
            confidence={text.confidence}
            triageLevel={text.triage_level}
            recommendation={text.care_recommendation}
            onDismiss={handleDismissUpgrade}
          />
        );
      }
      
      // Regular assessment display for premium users or non-upgrade-required cases
      return (
        <div className="message-row" key={index}>
          <div className="avatar-container">
            <img src="/doctor-avatar.png" alt="AI Assistant" />
          </div>
          <div className="message bot assessment-message">
            <span className="assessment-indicator">Assessment</span>
            <div className="message-content">
              <p>I've identified <strong>{condition}</strong> as a possible condition.</p>
              {text.confidence && <p>Confidence: <strong>{text.confidence}%</strong></p>}
              {text.triage_level && <p>Severity: <strong>{text.triage_level}</strong></p>}
              {text.care_recommendation && (
                <p>Recommendation: <strong>{text.care_recommendation}</strong></p>
              )}
            </div>
          </div>
        </div>
      );
    }
    
    // Regular text messages
    return (
      <div className={`message-row ${sender}`} key={index}>
        <div className="avatar-container">
          <img 
            src={sender === 'bot' ? "/doctor-avatar.png" : "/user-avatar.png"} 
            alt={sender === 'bot' ? "AI Assistant" : "User"} 
          />
        </div>
        <div className={`message ${sender} ${isError ? 'error' : ''}`}>
          <div className="message-content">
            {typeof text === 'string' ? (
              text.split('\n').map((line, i) => (
                <p key={i}>{line}</p>
              ))
            ) : (
              <p>Error: Unable to display message</p>
            )}
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="chat-container">
      <div className="reset-button-container">
        <button 
          className="reset-button" 
          onClick={resetConversation}
          disabled={isAnalyzing}
        >
          Reset Conversation
        </button>
      </div>
      
      <div className="messages-container">
        {messages.map(renderMessage)}
        
        {isTyping && (
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
          <div className="error-message">
            {error}
          </div>
        )}
        
        <div ref={messagesEndRef} />
      </div>
      
      <div className="chat-input-container">
        <div className="chat-input-wrapper">
          <textarea
            className="chat-input"
            value={input}
            onChange={handleInputChange}
            onKeyPress={handleKeyPress}
            placeholder="Describe your symptoms..."
            disabled={isAnalyzing}
          />
          <button
            className="send-button"
            onClick={handleSendMessage}
            disabled={!input.trim() || isAnalyzing}
          >
            {isAnalyzing ? 'Analyzing...' : 'Send'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default Chat;