import React, { useState, useCallback } from 'react';
import { setLocalStorageItem, getLocalStorageItem } from '../utils/utils';

const API_BASE_URL = 'https://healthtrackermichele.onrender.com/api';

const MedicalInfo = () => {
  const [formData, setFormData] = useState({
    name: getLocalStorageItem('name') || '',
    age: getLocalStorageItem('age') || '',
    conditions: getLocalStorageItem('conditions') || '',
    medications: getLocalStorageItem('medications') || '',
    allergies: getLocalStorageItem('allergies') || '',
  });

  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const [isLoading, setIsLoading] = useState(false);

  const handleChange = useCallback((e) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
    setError(null);
    setSuccess(null);
  }, []);

  const validateForm = useCallback(() => {
    if (!formData.name.trim()) {
      setError('Name is required.');
      return false;
    }
    if (!formData.age.trim()) {
      setError('Age is required.');
      return false;
    }
    if (isNaN(formData.age) || parseInt(formData.age) <= 0 || parseInt(formData.age) > 120) {
      setError('Please enter a valid age.');
      return false;
    }
    return true;
  }, [formData.name, formData.age]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);

    if (!validateForm()) return;

    setIsLoading(true);

    try {
      // Store in Local Storage
      Object.entries(formData).forEach(([key, value]) => {
        setLocalStorageItem(key, value);
      });

      const accessToken = localStorage.getItem('access_token');
      if (!accessToken) {
        throw new Error('Please log in to save your medical information.');
      }

      // Send to backend
      const response = await fetch(`${API_BASE_URL}/medical-info`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${accessToken}`
        },
        body: JSON.stringify(formData),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.error || 'Failed to submit medical info.');
      }

      setSuccess('Medical information saved successfully.');
    } catch (err) {
      console.error('Error submitting medical info:', err);
      setError(err.message || 'An error occurred while saving your medical information.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="medical-info-container">
      <h1>Medical Information</h1>
      <p className="form-description">
        Please provide your medical history and details below. This information helps us provide better care recommendations.
      </p>

      <form className="medical-info-form" onSubmit={handleSubmit}>
        <div className="form-group">
          <label htmlFor="name">Full Name: *</label>
          <input
            type="text"
            id="name"
            name="name"
            value={formData.name}
            onChange={handleChange}
            required
            disabled={isLoading}
            aria-describedby="name-required"
          />
          <span id="name-required" className="required-field">Required</span>
        </div>

        <div className="form-group">
          <label htmlFor="age">Age: *</label>
          <input
            type="number"
            id="age"
            name="age"
            value={formData.age}
            onChange={handleChange}
            required
            min="1"
            max="120"
            disabled={isLoading}
            aria-describedby="age-required"
          />
          <span id="age-required" className="required-field">Required</span>
        </div>

        <div className="form-group">
          <label htmlFor="conditions">Medical Conditions:</label>
          <textarea
            id="conditions"
            name="conditions"
            value={formData.conditions}
            onChange={handleChange}
            rows="4"
            disabled={isLoading}
            placeholder="List any current or past medical conditions"
          ></textarea>
        </div>

        <div className="form-group">
          <label htmlFor="medications">Current Medications:</label>
          <textarea
            id="medications"
            name="medications"
            value={formData.medications}
            onChange={handleChange}
            rows="4"
            disabled={isLoading}
            placeholder="List any medications you're currently taking"
          ></textarea>
        </div>

        <div className="form-group">
          <label htmlFor="allergies">Allergies:</label>
          <textarea
            id="allergies"
            name="allergies"
            value={formData.allergies}
            onChange={handleChange}
            rows="4"
            disabled={isLoading}
            placeholder="List any known allergies"
          ></textarea>
        </div>

        <button 
          type="submit" 
          className={`submit-button ${isLoading ? 'loading' : ''}`}
          disabled={isLoading}
        >
          {isLoading ? 'Saving...' : 'Save Information'}
        </button>
      </form>

      {error && (
        <div className="error-message" role="alert">
          {error}
        </div>
      )}
      {success && (
        <div className="success-message" role="status">
          {success}
        </div>
      )}
    </div>
  );
};

export default MedicalInfo;