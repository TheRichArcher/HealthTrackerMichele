import React, { useState } from 'react';
import { setLocalStorageItem, getLocalStorageItem } from '../utils/utils'; // ✅ Ensure import

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

  const handleChange = (e) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);

    // Validate required fields
    if (!formData.name.trim() || !formData.age.trim()) {
      setError('Name and age are required fields.');
      return;
    }

    try {
      // Store in Local Storage
      Object.keys(formData).forEach((key) => {
        setLocalStorageItem(key, formData[key]);
      });

      // Send to backend
      const response = await fetch('https://healthtrackerai.pythonanywhere.com/api/medical-info', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(formData),
      });

      if (!response.ok) {
        throw new Error('Failed to submit medical info.');
      }

      setSuccess('Medical info submitted successfully.');
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <div className="medical-info-container">
      <h1>Medical Information</h1>
      <p>Please provide your medical history and details below:</p>
      <form className="medical-info-form" onSubmit={handleSubmit}>
        <label htmlFor="name">Full Name:</label>
        <input type="text" id="name" name="name" value={formData.name} onChange={handleChange} required />

        <label htmlFor="age">Age:</label>
        <input type="number" id="age" name="age" value={formData.age} onChange={handleChange} required />

        <label htmlFor="conditions">Medical Conditions:</label>
        <textarea id="conditions" name="conditions" value={formData.conditions} onChange={handleChange} rows="4"></textarea>

        <label htmlFor="medications">Current Medications:</label>
        <textarea id="medications" name="medications" value={formData.medications} onChange={handleChange} rows="4"></textarea>

        <label htmlFor="allergies">Allergies:</label>
        <textarea id="allergies" name="allergies" value={formData.allergies} onChange={handleChange} rows="4"></textarea>

        <button type="submit">Submit</button>
      </form>

      {error && <p className="error-message">{error}</p>}
      {success && <p className="success-message">{success}</p>}
    </div>
  );
};

export default MedicalInfo;
