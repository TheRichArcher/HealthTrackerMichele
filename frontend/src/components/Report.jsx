import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { getLocalStorageItem } from '../utils/utils';
import '../styles/Report.css';  // ✅ Fixed import path

const Report = () => {
    const navigate = useNavigate();
    const [symptoms, setSymptoms] = useState('');
    const [timeline, setTimeline] = useState('');
    const [reportContent, setReportContent] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

    const userId = getLocalStorageItem("user_id");

    useEffect(() => {
        if (!userId) {
            navigate('/auth');  // ✅ Fixed: Changed from '/login' to '/auth'
        }
    }, [userId, navigate]);

    const handleSubmit = async (e) => {
        e.preventDefault();

        if (!userId) {
            setError('User session expired. Please log in.');
            return;
        }

        if (!symptoms.trim()) {
            setError('Please enter at least one symptom.');
            return;
        }

        setLoading(true);
        setError(null);

        try {
            const response = await axios.post(
                'https://healthtrackerai.pythonanywhere.com/api/reports',
                { 
                    user_id: userId,
                    symptoms: symptoms.split(',').map(s => s.trim()), 
                    timeline 
                }
            );

            setReportContent(response.data.report);
        } catch (err) {
            console.error('Error generating report:', err);
            setError('Failed to generate report. Please try again.');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="report-container">
            <h1>Generate Your Health Report</h1>
            <form onSubmit={handleSubmit}>
                <div className="form-group">
                    <label htmlFor="symptoms">Enter your symptoms (comma-separated):</label>
                    <input
                        type="text"
                        id="symptoms"
                        value={symptoms}
                        onChange={(e) => setSymptoms(e.target.value)}
                        placeholder="e.g., fever, headache, fatigue"
                    />
                </div>
                <div className="form-group">
                    <label htmlFor="timeline">Provide a brief timeline (optional):</label>
                    <textarea
                        id="timeline"
                        value={timeline}
                        onChange={(e) => setTimeline(e.target.value)}
                        placeholder="e.g., started feeling unwell 3 days ago, fever appeared yesterday"
                    />
                </div>
                <button type="submit" disabled={loading}>
                    {loading ? 'Generating...' : 'Submit'}
                </button>
            </form>

            {loading && <p>Loading...</p>}
            {error && <p className="error">{error}</p>}

            {reportContent && (
                <div className="report-content">
                    <h2>Generated Report</h2>
                    <pre>{reportContent}</pre>
                </div>
            )}
        </div>
    );
};

export default Report;