import React from 'react';
import { Link } from 'react-router-dom';
import '../styles/navbar.css';

const Navbar = () => {
    return (
        <nav className="navbar" role="navigation" aria-label="Main navigation">
            <div className="navbar-container">
                <div className="navbar-brand">
                    <Link to="/" className="logo">
                        HealthTracker AI
                    </Link>
                </div>

                <div className="navbar-menu">
                    <Link 
                        to="/" 
                        className="nav-button chat-button"
                        aria-label="Chat"
                    >
                        Chat
                    </Link>
                    <Link 
                        to="/auth" 
                        className="nav-button sign-in-button"
                        aria-label="Sign In"
                    >
                        Sign In
                    </Link>
                </div>
            </div>
        </nav>
    );
};

export default Navbar;