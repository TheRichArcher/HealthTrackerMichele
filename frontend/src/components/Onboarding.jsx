import React, { useEffect, useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { getLocalStorageItem } from '../utils/utils';
import '../styles/Onboarding.css';

const Onboarding = () => {
  const navigate = useNavigate();
  const chatRef = useRef(null);
  const [messages, setMessages] = useState([
    { role: 'bot', content: "Welcome to HealthTrackerAI! What brings you into the office today?" },
  ]);
  const [input, setInput] = useState("");
  const [vitals, setVitals] = useState({
    age: "", weight: "", height: "", temperature: "", heartRate: "",
    respiratoryRate: "", oxygenSaturation: "", waistCircumference: "",
    symptoms: "", medications: "",
  });
  const [unitSystem, setUnitSystem] = useState("Imperial");
  const [error, setError] = useState(null);
  const [isLoading, setIsLoading] = useState(false);

  const userId = getLocalStorageItem("user_id");

  useEffect(() => {
    if (!userId) {
      navigate('/auth');  // ✅ Fixed: Changed from '/login' to '/auth'
    }
  }, [userId, navigate]);

  useEffect(() => {
    chatRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const toggleUnitSystem = () => {
    setUnitSystem(prevUnit => prevUnit === "Imperial" ? "Metric" : "Imperial");
  };

  const sendMessage = async () => {
    if (!input.trim()) {
      setError("Please enter a valid message.");
      return;
    }
    setMessages(prev => [...prev, { role: 'user', content: input }]);
    setIsLoading(true);
    setError(null);

    try {
      const response = await axios.post(
        'https://healthtrackerai.pythonanywhere.com/api/onboarding',
        { user_id: userId, initial_symptom: input }
      );
      setMessages(prev => [...prev, { role: 'bot', content: response.data.response }]);
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
    const { age, weight, height, temperature, heartRate, respiratoryRate, oxygenSaturation, waistCircumference, symptoms, medications } = vitals;
    if (!age || !weight || !height || !temperature || !heartRate || !symptoms || !medications) {
      setError("Please fill in all required fields before submitting.");
      return;
    }

    setError(null);
    try {
      const response = await axios.post(
        'https://healthtrackerai.pythonanywhere.com/api/vitals',
        { user_id: userId, ...vitals }
      );
      setMessages(prev => [...prev, { role: 'bot', content: "Vitals submitted successfully!" }]);
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
            <div key={index} ref={chatRef} className={msg.role === 'bot' ? 'message bot' : 'message user'}>
              <strong>{msg.role === 'bot' ? 'Bot:' : 'You:'}</strong> {msg.content}
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
            <input type="number" name="age" placeholder="Age" value={vitals.age} onChange={handleVitalsChange} />
            <input type="number" name="weight" placeholder={`Weight (${unitSystem === "Imperial" ? "lbs" : "kg"})`} value={vitals.weight} onChange={handleVitalsChange} />
            <input type="text" name="height" placeholder={`Height (${unitSystem === "Imperial" ? "ft/in" : "cm"})`} value={vitals.height} onChange={handleVitalsChange} />
            <input type="number" name="temperature" placeholder={`Temperature (${unitSystem === "Imperial" ? "°F" : "°C"})`} value={vitals.temperature} onChange={handleVitalsChange} />
            <input type="number" name="heartRate" placeholder="Heart Rate (BPM)" value={vitals.heartRate} onChange={handleVitalsChange} />
            <input type="number" name="respiratoryRate" placeholder="Respiratory Rate (breaths/min)" value={vitals.respiratoryRate} onChange={handleVitalsChange} />
            <input type="number" name="oxygenSaturation" placeholder="Oxygen Saturation (%)" value={vitals.oxygenSaturation} onChange={handleVitalsChange} />
            <input type="number" name="waistCircumference" placeholder={`Waist Circumference (${unitSystem === "Imperial" ? "in" : "cm"})`} value={vitals.waistCircumference} onChange={handleVitalsChange} />
            <input type="text" name="symptoms" placeholder="Symptoms" value={vitals.symptoms} onChange={handleVitalsChange} />
            <input type="text" name="medications" placeholder="Medications" value={vitals.medications} onChange={handleVitalsChange} />
          </div>
          <button type="button" onClick={submitVitals}>Submit Vitals</button>
        </form>
      </div>
    </div>
  );
};

export default Onboarding;