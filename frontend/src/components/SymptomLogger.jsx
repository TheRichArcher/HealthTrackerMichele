import React, { useState, useCallback, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "./AuthProvider"; // Updated import
import { getLocalStorageItem, setLocalStorageItem } from "../utils/utils";
import debounce from 'lodash/debounce';
import axios from 'axios';
import UpgradePrompt from './UpgradePrompt';
import '../styles/SymptomLogger.css';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'https://healthtrackermichele.onrender.com/api';

const VALIDATION_RULES = {
  respiratoryRate: { min: 8, max: 40, label: 'Respiratory rate' },
  oxygenSaturation: { min: 50, max: 100, label: 'Oxygen saturation' },
  waistCircumference: { min: 20, max: 200, label: 'Waist circumference' },
  intensity: { min: 1, max: 10, label: 'Intensity' }
};

const initialFormState = {
  symptom: "",
  onsetDate: new Date().toISOString().split('T')[0],
  relatedSymptoms: "",
  intensity: 5,
  respiratoryRate: "",
  oxygenSaturation: "",
  waistCircumference: ""
};

const SymptomLogger = () => {
  const [formData, setFormData] = useState(initialFormState);
  const [logStatus, setLogStatus] = useState(null);
  const [errors, setErrors] = useState({});
  const [isLoading, setIsLoading] = useState(false);
  const [lastEntry, setLastEntry] = useState(null);
  const [subscriptionTier, setSubscriptionTier] = useState(null);
  const [symptomCount, setSymptomCount] = useState(0);

  const { isAuthenticated, checkAuth } = useAuth();
  const navigate = useNavigate();
  const userId = getLocalStorageItem("user_id");
  const accessToken = getLocalStorageItem("access_token");

  useEffect(() => {
    if (isAuthenticated) {
      const token = accessToken;
      Promise.all([
        axios.get(`${API_BASE_URL}/symptoms/count`, { headers: { Authorization: `Bearer ${token}` } }),
        axios.get(`${API_BASE_URL}/subscription/status`, { headers: { Authorization: `Bearer ${token}` } })
      ])
        .then(([countRes, subRes]) => {
          setSymptomCount(countRes.data.count || 0);
          setSubscriptionTier(subRes.data.subscription_tier);
        })
        .catch(err => console.error('Failed to fetch data:', err));
    }
  }, [isAuthenticated, accessToken]);

  useEffect(() => {
    const savedEntry = getLocalStorageItem("lastSymptomEntry");
    if (savedEntry) {
      try {
        const parsedEntry = JSON.parse(savedEntry);
        setLastEntry(parsedEntry);
        setFormData(prev => ({ ...prev, ...parsedEntry, onsetDate: new Date().toISOString().split('T')[0] }));
      } catch (error) {
        console.error('Error parsing saved entry:', error);
      }
    }
    if (!isAuthenticated) {
      navigate('/auth', { state: { from: { pathname: '/symptom-logger' } } });
    }
  }, [isAuthenticated, navigate]);

  useEffect(() => {
    if (logStatus) {
      const timer = setTimeout(() => setLogStatus(null), 3000);
      return () => clearTimeout(timer);
    }
  }, [logStatus]);

  const debouncedValidation = useCallback(debounce((value, id) => {
    const rules = VALIDATION_RULES[id];
    if (!rules) return;
    const numValue = Number(value);
    if (value && (numValue < rules.min || numValue > rules.max)) {
      setErrors(prev => ({ ...prev, [id]: `${rules.label} must be between ${rules.min} and ${rules.max}` }));
    } else {
      setErrors(prev => ({ ...prev, [id]: null }));
    }
  }, 300), []);

  const handleInputChange = useCallback((e) => {
    const { id, value } = e.target;
    setFormData(prev => ({ ...prev, [id]: value }));
    if (['number', 'range'].includes(e.target.type)) {
      debouncedValidation(value, id);
    } else {
      setErrors(prev => ({ ...prev, [id]: null }));
    }
  }, [debouncedValidation]);

  const validateForm = useCallback(() => {
    const newErrors = {};
    if (!userId || !accessToken) newErrors.general = "User session not found. Please log in.";
    if (!formData.symptom.trim()) newErrors.symptom = "Please provide a symptom description.";
    Object.entries(VALIDATION_RULES).forEach(([field, rules]) => {
      if (formData[field] && (Number(formData[field]) < rules.min || Number(formData[field]) > rules.max)) {
        newErrors[field] = `${rules.label} must be between ${rules.min} and ${rules.max}`;
      }
    });
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  }, [userId, accessToken, formData]);

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!validateForm()) return;

    if (subscriptionTier === 'free' && symptomCount >= 5) {
      setErrors({ general: "Free users are limited to 5 symptom logs. Please upgrade." });
      return;
    }

    setIsLoading(true);
    setLogStatus(null);

    try {
      const response = await fetch(`${API_BASE_URL}/symptoms`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${accessToken}`
        },
        body: JSON.stringify({
          user_id: userId,
          symptom: formData.symptom.trim(),
          notes: formData.relatedSymptoms.trim(),
          intensity: Number(formData.intensity),
          respiratory_rate: formData.respiratoryRate ? Number(formData.respiratoryRate) : null,
          oxygen_saturation: formData.oxygenSaturation ? Number(formData.oxygenSaturation) : null,
          waist_circumference: formData.waistCircumference ? Number(formData.waistCircumference) : null,
        }),
      });

      if (!response.ok) {
        if (response.status === 401) throw new Error("Session expired. Please log in again.");
        const errorData = await response.json();
        throw new Error(errorData.error || "Failed to log the symptom.");
      }

      setLocalStorageItem("lastSymptomEntry", JSON.stringify(formData));
      setLastEntry(formData);
      setSymptomCount(prev => prev + 1);
      setLogStatus("✅ Symptom logged successfully!");
      setFormData({ ...initialFormState, onsetDate: new Date().toISOString().split('T')[0] });
      window.scrollTo({ top: 0, behavior: 'smooth' });
    } catch (err) {
      setErrors({ general: err.message });
      if (err.message.includes("session expired")) {
        navigate('/auth');
      }
    } finally {
      setIsLoading(false);
    }
  };

  const handleDismissUpgrade = useCallback(() => {
    navigate('/dashboard');
  }, [navigate]);

  return (
    <div className="symptom-logger-container">
      <h1 className="header">Log Your Symptom</h1>
      {(logStatus || errors.general) && (
        <div className={`message ${errors.general ? 'error' : 'success'}`} role={errors.general ? 'alert' : 'status'}>
          {errors.general || logStatus}
        </div>
      )}
      <form onSubmit={handleSubmit} className="form">
        <div className={`form-group ${errors.symptom ? 'error' : ''}`}>
          <label htmlFor="symptom">Symptom:</label>
          <input 
            type="text" 
            id="symptom" 
            value={formData.symptom} 
            onChange={handleInputChange} 
            placeholder="e.g., fever" 
            required 
            disabled={isLoading} 
          />
          {errors.symptom && <span className="error-message">{errors.symptom}</span>}
        </div>
        <div className="form-group">
          <label htmlFor="onsetDate">Onset Date:</label>
          <input 
            type="date" 
            id="onsetDate" 
            value={formData.onsetDate} 
            onChange={handleInputChange} 
            max={new Date().toISOString().split('T')[0]} 
            required 
            disabled={isLoading} 
          />
        </div>
        <div className="form-group">
          <label htmlFor="relatedSymptoms">Notes:</label>
          <textarea 
            id="relatedSymptoms" 
            value={formData.relatedSymptoms} 
            onChange={handleInputChange} 
            placeholder="Additional notes..." 
            disabled={isLoading} 
            rows="3" 
          />
        </div>
        <div className={`form-group ${errors.intensity ? 'error' : ''}`}>
          <label htmlFor="intensity">Intensity: <span className="intensity-value">{formData.intensity}</span></label>
          <input 
            type="range" 
            id="intensity" 
            min={1} 
            max={10} 
            value={formData.intensity} 
            onChange={handleInputChange} 
            disabled={isLoading} 
          />
          <div className="range-labels">
            <span>Mild</span>
            <span>Severe</span>
          </div>
        </div>
        <div className={`form-group ${errors.respiratoryRate ? 'error' : ''}`}>
          <label htmlFor="respiratoryRate">Respiratory Rate (breaths/min):</label>
          <input 
            type="number" 
            id="respiratoryRate" 
            value={formData.respiratoryRate} 
            onChange={handleInputChange} 
            placeholder="8-40" 
            disabled={isLoading} 
          />
          {errors.respiratoryRate && <span className="error-message">{errors.respiratoryRate}</span>}
        </div>
        <div className={`form-group ${errors.oxygenSaturation ? 'error' : ''}`}>
          <label htmlFor="oxygenSaturation">Oxygen Saturation (%):</label>
          <input 
            type="number" 
            id="oxygenSaturation" 
            value={formData.oxygenSaturation} 
            onChange={handleInputChange} 
            placeholder="50-100" 
            disabled={isLoading} 
          />
          {errors.oxygenSaturation && <span className="error-message">{errors.oxygenSaturation}</span>}
        </div>
        <div className={`form-group ${errors.waistCircumference ? 'error' : ''}`}>
          <label htmlFor="waistCircumference">Waist Circumference (cm):</label>
          <input 
            type="number" 
            id="waistCircumference" 
            value={formData.waistCircumference} 
            onChange={handleInputChange} 
            placeholder="20-200" 
            disabled={isLoading} 
          />
          {errors.waistCircumference && <span className="error-message">{errors.waistCircumference}</span>}
        </div>
        <div className="button-group">
          <button 
            type="submit" 
            disabled={isLoading || Object.keys(errors).length > 0} 
            className={`submit-button ${isLoading ? 'loading' : ''}`}
          >
            {isLoading ? "Logging..." : "Log Symptom"}
          </button>
          <button 
            type="button" 
            onClick={() => setFormData({ ...initialFormState, onsetDate: new Date().toISOString().split('T')[0] })} 
            className="reset-button" 
            disabled={isLoading}
          >
            Reset Form
          </button>
          {lastEntry && (
            <button 
              type="button" 
              onClick={() => setFormData({ ...lastEntry, onsetDate: new Date().toISOString().split('T')[0] })} 
              className="restore-button" 
              disabled={isLoading}
            >
              Restore Last Entry
            </button>
          )}
        </div>
      </form>
      {subscriptionTier === 'free' && symptomCount >= 5 && (
        <UpgradePrompt
          condition="Symptom Logging"
          commonName="Free Tier Limit"
          isMildCase={true}
          requiresUpgrade={true}
          onDismiss={handleDismissUpgrade}
        />
      )}
    </div>
  );
};

export default SymptomLogger;