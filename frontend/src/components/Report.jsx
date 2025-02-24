import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { getLocalStorageItem } from '../utils/utils';
import '../styles/Report.css';

const API_BASE_URL = 'https://healthtrackermichele.onrender.com/api';

const Report = () => {
    const navigate = useNavigate();
    const [formData, setFormData] = useState({
        symptoms: '',
        timeline: ''
    });
    const [reportContent, setReportContent] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

    const userId = getLocalStorageItem("user_id");
    const accessToken = getLocalStorageItem("access_token");

    useEffect(() => {
        if (!userId || !accessToken) {
            navigate('/auth', { 
                state: { from: { pathname: '/report' } },
                replace: true 
            });
        }
    }, [userId, accessToken, navigate]);

    const handleInputChange = useCallback((e) => {
        const { id, value } = e.target;
        setFormData(prev => ({
            ...prev,
            [id]: value
        }));
        setError(null);
    }, []);

    const validateInput = useCallback(() => {
        if (!formData.symptoms.trim()) {
            setError('Please enter at least one symptom.');
            return false;
        }
        return true;
    }, [formData.symptoms]);

    const handleSubmit = async (e) => {
        e.preventDefault();

        if (!userId || !accessToken) {
            setError('User session expired. Please log in.');
            navigate('/auth');
            return;
        }

        if (!validateInput()) return;

        setLoading(true);
        setError(null);

        try {
            const symptoms = formData.symptoms
                .split(',')
                .map(s => s.trim())
                .filter(s => s.length > 0);

            const response = await axios.post(
                `${API_BASE_URL}/reports`,
                { 
                    user_id: userId,
                    symptoms,
                    timeline: formData.timeline.trim()
                },
                {
                    headers: {
                        'Authorization': `Bearer ${accessToken}`,
                        'Content-Type': 'application/json'
                    },
                    timeout: 15000 // 15 second timeout
                }
            );

            if (response.data && response.data.report) {
                setReportContent(response.data.report);
            } else {
                throw new Error('Invalid response format');
            }
        } catch (err) {
            console.error('Error generating report:', err);
            setError(
                err.response?.status === 401 
                    ? 'Session expired. Please log in again.'
                    : err.response?.status === 429
                    ? 'Too many requests. Please try again later.'
                    : 'Failed to generate report. Please try again.'
            );

            if (err.response?.status === 401) {
                navigate('/auth');
            }
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="report-container">
            <h1>Generate Your Health Report</h1>
            <p className="report-description">
                Enter your symptoms and timeline to generate a detailed health report.
            </p>

            <form onSubmit={handleSubmit} className="report-form">
                <div className="form-group">
                    <label htmlFor="symptoms">
                        Symptoms (comma-separated): *
                    </label>
                    <input
                        type="text"
                        id="symptoms"
                        value={formData.symptoms}
                        onChange={handleInputChange}
                        placeholder="e.g., fever, headache, fatigue"
                        disabled={loading}
                        required
                        aria-describedby="symptoms-help"
                    />
                    <small id="symptoms-help" className="help-text">
                        List each symptom separated by commas
                    </small>
                </div>

                <div className="form-group">
                    <label htmlFor="timeline">Timeline (optional):</label>
                    <textarea
                        id="timeline"
                        value={formData.timeline}
                        onChange={handleInputChange}
                        placeholder="e.g., started feeling unwell 3 days ago, fever appeared yesterday"
                        disabled={loading}
                        rows="4"
                        aria-describedby="timeline-help"
                    />
                    <small id="timeline-help" className="help-text">
                        Describe when your symptoms started and how they've changed
                    </small>
                </div>

                <button 
                    type="submit" 
                    className={`submit-button ${loading ? 'loading' : ''}`}
                    disabled={loading}
                >
                    {loading ? (
                        <>
                            <span className="spinner"></span>
                            Generating Report...
                        </>
                    ) : 'Generate Report'}
                </button>
            </form>

            {error && (
                <div className="error-message" role="alert">
                    {error}
                </div>
            )}

            {reportContent && (
                <div className="report-content" role="region" aria-label="Generated Report">
                    <h2>Your Health Report</h2>
                    <div className="report-body">
                        {reportContent.split('\n').map((line, index) => (
                            <p key={index}>{line}</p>
                        ))}
                    </div>
                    <button 
                        onClick={() => window.print()} 
                        className="print-button"
                        aria-label="Print report"
                    >
                        Print Report
                    </button>
                </div>
            )}
        </div>
    );
};

export default Report;