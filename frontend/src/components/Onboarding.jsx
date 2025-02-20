import React, { useEffect, useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { getLocalStorageItem } from '../utils/utils';
import '../styles/Onboarding.css';

const Onboarding = () => {
  const navigate = useNavigate();
  const chatRef = useRef(null);
  const [messages, setMessages] = useState([
    { sender: 'bot', text: "Welcome to HealthTrackerAI! What brings you into the office today?" }
  ]);
  const [input, setInput] = useState("");
  const [vitals, setVitals] = useState({
    age: "", weight: "", height: "", temperature: "", heartRate: "",
    respiratoryRate: "", oxygenSaturation: "", waistCircumference: "",
    symptoms: "", medications: ""
  });
  const [unitSystem, setUnitSystem] = useState("Imperial");
  const [error, setError] = useState(null);
  const [isLoading, setIsLoading] = useState(false);

  const userId = getLocalStorageItem("user_id");

  useEffect(() => {
    if (!userId) {
      navigate('/auth');
    }
  }, [userId, navigate]);

  useEffect(() => {
    chatRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const toggleUnitSystem = () => {
    setUnitSystem(prevUnit => (prevUnit === "Imperial" ? "Metric" : "Imperial"));
  };

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
        'https://healthtrackerai.pythonanywhere.com/api/onboarding',
        { user_id: userId, initial_symptom: input }
      );
      setMessages(prev => [...prev, { sender: 'bot', text: response.data.response }]);
    } catch (err) {
      console.error("Error:", err);
      setError("An error occurred while sending your message. Please try again.");
    } finally {
      setIsLoading(false);
    }

    setInput("");
  };

  const handleVitalsChange = (e) => {
    setVitals(prev => ({ ...prev, [e.target.name]: e.target.value }));
  };

  const submitVitals = async () => {
    const requiredFields = ["age", "weight", "height", "temperature", "heartRate", "symptoms", "medications"];
    for (const field of requiredFields) {
      if (!vitals[field]) {
        setError("Please fill in all required fields before submitting.");
        return;
      }
    }

    setError(null);
    try {
      await axios.post(
        'https://healthtrackerai.pythonanywhere.com/api/vitals',
        { user_id: userId, ...vitals }
      );
      setMessages(prev => [...prev, { sender: 'bot', text: "Vitals submitted successfully!" }]);
    } catch (err) {
      console.error("Error submitting vitals:", err);
      setError("An error occurred while submitting your vitals. Please try again.");
    }
  };

  return (
    <div className="onboarding-container">
      <div className="chat-section">
        <h2>Chat with HealthTrackerAI</h2>
        <div className="messages">
          {messages.map((msg, index) => (
            <div key={index} ref={chatRef} className={`message ${msg.sender}`}>
              <strong>{msg.sender === 'bot' ? 'Bot:' : 'You:'}</strong> {msg.text}
            </div>
          ))}
        </div>
        <div className="input-section">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Type your response here..."
            disabled={isLoading}
          />
          <button onClick={sendMessage} disabled={isLoading}>
            {isLoading ? "Sending..." : "Send"}
          </button>
        </div>
        {error && <p className="error">{error}</p>}
      </div>

      <div className="vitals-section">
        <h3>Enter Your Vitals</h3>
        <button onClick={toggleUnitSystem}>
          Switch to {unitSystem === "Imperial" ? "Metric" : "Imperial"} Units
        </button>
        <form>
          <div className="vitals-grid">
            {Object.entries(vitals).map(([key, value]) => (
              <input
                key={key}
                type="text"
                name={key}
                placeholder={key.charAt(0).toUpperCase() + key.slice(1)}
                value={value}
                onChange={handleVitalsChange}
              />
            ))}
          </div>
          <button type="button" onClick={submitVitals}>Submit Vitals</button>
        </form>
      </div>
    </div>
  );
};

export default Onboarding;
