import React, { useEffect, useState, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { getLocalStorageItem } from '../utils/utils';
import '../styles/Onboarding.css';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'https://healthtrackerai.pythonanywhere.com/api';

const INITIAL_VITALS = {
    age: "",
    weight: "",
    height: "",
    temperature: "",
    heartRate: "",
    respiratoryRate: "",
    oxygenSaturation: "",
    waistCircumference: "",
    symptoms: "",
    medications: ""
};

const VITAL_FIELDS = {
    age: { type: 'number', label: 'Age', unit: 'years' },
    weight: { type: 'number', label: 'Weight', imperialUnit: 'lbs', metricUnit: 'kg' },
    height: { type: 'number', label: 'Height', imperialUnit: 'inches', metricUnit: 'cm' },
    temperature: { type: 'number', label: 'Temperature', imperialUnit: '°F', metricUnit: '°C' },
    heartRate: { type: 'number', label: 'Heart Rate', unit: 'bpm' },
    respiratoryRate: { type: 'number', label: 'Respiratory Rate', unit: 'breaths/min' },
    oxygenSaturation: { type: 'number', label: 'Oxygen Saturation', unit: '%' },
    waistCircumference: { type: 'number', label: 'Waist Circumference', imperialUnit: 'inches', metricUnit: 'cm' },
    symptoms: { type: 'text', label: 'Current Symptoms', placeholder: 'Describe your symptoms' },
    medications: { type: 'text', label: 'Current Medications', placeholder: 'List your medications' }
};

const Onboarding = () => {
    const navigate = useNavigate();
    const chatRef = useRef(null);
    const [messages, setMessages] = useState([
        { sender: 'bot', text: "Welcome to HealthTrackerAI! What brings you into the office today?" }
    ]);
    const [input, setInput] = useState("");
    const [vitals, setVitals] = useState(INITIAL_VITALS);
    const [unitSystem, setUnitSystem] = useState("Imperial");
    const [error, setError] = useState(null);
    const [isLoading, setIsLoading] = useState(false);
    const [submitSuccess, setSubmitSuccess] = useState(false);

    const userId = getLocalStorageItem("user_id");

    useEffect(() => {
        if (!userId) {
            navigate('/auth');
            return;
        }
    }, [userId, navigate]);

    const scrollToBottom = useCallback(() => {
        chatRef.current?.scrollIntoView({ behavior: "smooth" });
    }, []);

    useEffect(() => {
        scrollToBottom();
    }, [messages, scrollToBottom]);

    const toggleUnitSystem = useCallback(() => {
        setUnitSystem(prev => (prev === "Imperial" ? "Metric" : "Imperial"));
    }, []);

    const sendMessage = async () => {
        if (!input.trim()) {
            setError("Please enter a valid message.");
            return;
        }

        setMessages(prev => [...prev, { sender: 'user', text: input }]);
        setIsLoading(true);
        setError(null);

        try {
            const response = await axios.post(
                `${API_BASE_URL}/onboarding`,
                { 
                    user_id: userId, 
                    initial_symptom: input 
                },
                {
                    headers: {
                        'Authorization': `Bearer ${getLocalStorageItem('access_token')}`
                    }
                }
            );
            setMessages(prev => [...prev, { sender: 'bot', text: response.data.response }]);
        } catch (err) {
            console.error("Error:", err);
            setError("An error occurred while sending your message. Please try again.");
        } finally {
            setIsLoading(false);
            setInput("");
        }
    };

    const handleVitalsChange = useCallback((e) => {
        const { name, value } = e.target;
        setVitals(prev => ({ ...prev, [name]: value }));
        setError(null);
    }, []);

    const validateVitals = useCallback(() => {
        const requiredFields = ["age", "weight", "height", "temperature", "heartRate"];
        const missingFields = requiredFields.filter(field => !vitals[field]);
        
        if (missingFields.length > 0) {
            setError(`Please fill in the following required fields: ${missingFields.join(", ")}`);
            return false;
        }
        return true;
    }, [vitals]);

    const submitVitals = async () => {
        if (!validateVitals()) return;

        setIsLoading(true);
        setError(null);

        try {
            await axios.post(
                `${API_BASE_URL}/vitals`,
                { 
                    user_id: userId,
                    unit_system: unitSystem,
                    ...vitals 
                },
                {
                    headers: {
                        'Authorization': `Bearer ${getLocalStorageItem('access_token')}`
                    }
                }
            );
            setSubmitSuccess(true);
            setMessages(prev => [...prev, { 
                sender: 'bot', 
                text: "Vitals submitted successfully! You can now proceed to the dashboard." 
            }]);
            setTimeout(() => navigate('/dashboard'), 2000);
        } catch (err) {
            console.error("Error submitting vitals:", err);
            setError("An error occurred while submitting your vitals. Please try again.");
        } finally {
            setIsLoading(false);
        }
    };

    const handleKeyPress = (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    };

    return (
        <div className="onboarding-container">
            <div className="chat-section">
                <h2>Chat with HealthTrackerAI</h2>
                <div className="messages">
                    {messages.map((msg, index) => (
                        <div 
                            key={index} 
                            className={`message ${msg.sender}`}
                            ref={index === messages.length - 1 ? chatRef : null}
                        >
                            <span className="message-sender">
                                {msg.sender === 'bot' ? 'HealthTracker AI:' : 'You:'}
                            </span>
                            <span className="message-text">{msg.text}</span>
                        </div>
                    ))}
                </div>
                <div className="input-section">
                    <input
                        type="text"
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        onKeyPress={handleKeyPress}
                        placeholder="Type your response here..."
                        disabled={isLoading}
                        aria-label="Message input"
                    />
                    <button 
                        onClick={sendMessage} 
                        disabled={isLoading}
                        aria-label="Send message"
                    >
                        {isLoading ? "Sending..." : "Send"}
                    </button>
                </div>
                {error && <p className="error" role="alert">{error}</p>}
            </div>

            <div className="vitals-section">
                <h3>Enter Your Vitals</h3>
                <button 
                    onClick={toggleUnitSystem}
                    className="unit-toggle"
                    aria-label="Toggle unit system"
                >
                    Switch to {unitSystem === "Imperial" ? "Metric" : "Imperial"} Units
                </button>
                <form onSubmit={(e) => e.preventDefault()}>
                    <div className="vitals-grid">
                        {Object.entries(VITAL_FIELDS).map(([name, field]) => (
                            <div key={name} className="vital-field">
                                <label htmlFor={name}>{field.label}</label>
                                <input
                                    id={name}
                                    type={field.type}
                                    name={name}
                                    value={vitals[name]}
                                    onChange={handleVitalsChange}
                                    placeholder={field.placeholder || `Enter ${field.label}`}
                                    aria-label={field.label}
                                />
                                {field.unit && <span className="unit">{field.unit}</span>}
                                {(field.imperialUnit || field.metricUnit) && (
                                    <span className="unit">
                                        {unitSystem === "Imperial" ? field.imperialUnit : field.metricUnit}
                                    </span>
                                )}
                            </div>
                        ))}
                    </div>
                    <button 
                        type="button" 
                        onClick={submitVitals}
                        disabled={isLoading || submitSuccess}
                        className="submit-button"
                    >
                        {isLoading ? "Submitting..." : "Submit Vitals"}
                    </button>
                </form>
            </div>
        </div>
    );
};

export default Onboarding;