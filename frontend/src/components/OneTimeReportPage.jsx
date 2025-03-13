import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import axios from 'axios';
import '../styles/SubscriptionPage.css';
import '../styles/shared.css';

const OneTimeReportPage = () => {
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const [report, setReport] = useState(null);
    const { isAuthenticated } = useAuth();
    const navigate = useNavigate();
    const location = useLocation();

    // Check if user came from a successful payment
    useEffect(() => {
        const sessionId = new URLSearchParams(location.search).get('session_id');
        if (sessionId && isAuthenticated) {
            confirmPurchase(sessionId);
        } else if (isAuthenticated) {
            // If no session ID, initiate purchase
            initiateReportPurchase();
        }
    }, [isAuthenticated, location.search]);

    const initiateReportPurchase = async () => {
        setLoading(true);
        setError(null);
        const token = localStorage.getItem('access_token'); // Changed from jwt_token

        try {
            const response = await axios.post(
                `${import.meta.env.VITE_API_URL || '/api'}/subscription/upgrade`,
                { plan: 'one_time' },
                { headers: { Authorization: `Bearer ${token}` } }
            );
            window.location.href = response.data.checkout_url; // Redirect to Stripe
        } catch (err) {
            setError(err.response?.data?.error || 'Failed to initiate purchase');
            setLoading(false);
        }
    };

    const confirmPurchase = async (sessionId) => {
        setLoading(true);
        setError(null);
        const token = localStorage.getItem('access_token'); // Changed from jwt_token

        try {
            // First confirm the purchase with Stripe
            await axios.post(
                `${import.meta.env.VITE_API_URL || '/api'}/subscription/confirm`,
                { session_id: sessionId },
                { headers: { Authorization: `Bearer ${token}` } }
            );

            // Then generate the report
            await generateReport();
        } catch (err) {
            setError(err.response?.data?.error || 'Failed to confirm purchase');
            setLoading(false);
        }
    };

    const generateReport = async () => {
        const token = localStorage.getItem('access_token'); // Changed from jwt_token
        try {
            // Get conversation history from localStorage
            const conversationHistory = JSON.parse(localStorage.getItem('healthtracker_chat_messages') || '[]')
                .map(msg => ({ message: msg.text, isBot: msg.sender === 'bot' }));
            
            // Extract the user's initial symptom description
            const userSymptoms = conversationHistory.find(msg => !msg.isBot)?.message || '';
            
            const response = await axios.post(
                `${import.meta.env.VITE_API_URL || '/api'}/symptoms/doctor-report`, 
                {
                    symptom: userSymptoms,
                    conversation_history: conversationHistory
                },
                {
                    headers: { Authorization: `Bearer ${token}` }
                }
            );
            
            if (response.data.success) {
                setReport(response.data.doctors_report);
                setLoading(false);
            } else {
                throw new Error(response.data.error || 'Failed to generate report');
            }
        } catch (err) {
            console.error('Error generating report:', err);
            setError('Failed to generate report. Please try again.');
            setLoading(false);
        }
    };

    if (!isAuthenticated) {
        return <div className="subscription-container">Please log in to purchase a report.</div>;
    }

    return (
        <div className="subscription-container">
            <h2>Doctor's Report</h2>
            
            {loading && (
                <div className="loading">
                    <div className="loading-spinner"></div>
                    <p>Generating your report...</p>
                </div>
            )}
            
            {error && <p className="error">{error}</p>}
            
            {report && (
                <div className="report-container">
                    <div className="report-content">
                        {report.split('\n').map((line, i) => (
                            <p key={i}>{line}</p>
                        ))}
                    </div>
                    <button 
                        className="subscription-button"
                        onClick={() => navigate('/')}
                    >
                        Return to Chat
                    </button>
                </div>
            )}
        </div>
    );
};

export default OneTimeReportPage;