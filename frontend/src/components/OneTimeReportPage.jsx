import React, { useEffect, useState } from 'react';
import { useLocation } from 'react-router-dom';
import axios from 'axios';
import '../styles/Report.css'; // Reuse styles from Report.css

const API_BASE_URL = 'https://healthtrackermichele.onrender.com';

const OneTimeReportPage = () => {
    const [report, setReport] = useState(null);
    const [error, setError] = useState(null);
    const [loading, setLoading] = useState(true);
    const location = useLocation();

    useEffect(() => {
        const fetchReport = async () => {
            const params = new URLSearchParams(location.search);
            const sessionId = params.get('session_id');
            if (!sessionId) {
                setError('Missing session ID');
                setLoading(false);
                return;
            }

            try {
                console.log('Fetching one-time report for session:', sessionId);
                const response = await axios.get(`${API_BASE_URL}/one-time-report`, {
                    params: { session_id: sessionId },
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    withCredentials: true,
                });
                console.log('One-time report response:', response.data);
                setReport(response.data);
            } catch (err) {
                console.error('Error fetching one-time report:', err.response?.data || err.message);
                setError(err.response?.data?.error || 'Failed to load report. Please try again.');
            } finally {
                setLoading(false);
            }
        };
        fetchReport();
    }, [location]);

    if (loading) {
        return (
            <div className="report-container">
                <h1>Loading Report...</h1>
                <p>Please wait while we retrieve your one-time health report.</p>
            </div>
        );
    }

    if (error) {
        return (
            <div className="report-container">
                <h1>Error</h1>
                <div className="error-message" role="alert">
                    {error}
                </div>
            </div>
        );
    }

    if (!report) {
        return (
            <div className="report-container">
                <h1>No Report Found</h1>
                <p>We couldn’t retrieve your report. Please contact support.</p>
            </div>
        );
    }

    return (
        <div className="report-container">
            <h1>{report.title}</h1>
            <div className="report-content" role="region" aria-label="One-Time Report">
                <div className="report-body">
                    {report.content.split('\n').map((line, index) => (
                        <p key={index}>{line}</p>
                    ))}
                    <p><strong>User ID:</strong> {report.user_id}</p>
                    <p><strong>Payment Date:</strong> {new Date(report.payment_date * 1000).toLocaleString()}</p>
                </div>
                <button
                    onClick={() => window.print()}
                    className="print-button"
                    aria-label="Print report"
                >
                    Print Report
                </button>
            </div>
        </div>
    );
};

export default OneTimeReportPage;