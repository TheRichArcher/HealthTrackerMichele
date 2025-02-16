import React from 'react';
import { useNavigate } from 'react-router-dom';

const Home = () => {
    const navigate = useNavigate();

    return (
        <div className="home-container">
            <h1>Welcome to HealthTrackerAI</h1>
            <p>Your personal health companion—track symptoms, log vitals, and generate insightful reports.</p>

            <div className="cta-buttons">
                <button onClick={() => navigate('/signup')} className="signup-btn" aria-label="Sign Up">
                    Sign Up
                </button>
                <button onClick={() => navigate('/login')} className="login-btn" aria-label="Log In">
                    Log In
                </button>
            </div>
        </div>
    );
};

export default Home;
