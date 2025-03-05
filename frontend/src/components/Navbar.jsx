import React, { useState, useCallback, useEffect, memo } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import '../styles/navbar.css';

const PUBLIC_NAV_ITEMS = [
    { path: '/', label: 'Chat' }
];

const PRIVATE_NAV_ITEMS = [
    { path: '/dashboard', label: 'Dashboard' },
    { path: '/symptom-logger', label: 'Log Symptoms' },
    { path: '/report', label: 'Reports' },
    { path: '/medical-info', label: 'Medical Info' },
    { path: '/library', label: 'Library' }
];

const LogoutModal = memo(({ onConfirm, onCancel }) => (
    <div 
        className="modal-overlay" 
        onClick={onCancel}
        role="dialog"
        aria-labelledby="logout-title"
    >
        <div 
            className="modal-content" 
            onClick={(e) => e.stopPropagation()}
        >
            <h3 id="logout-title">Confirm Logout</h3>
            <p>Are you sure you want to log out?</p>
            <div className="modal-buttons">
                <button 
                    onClick={onConfirm} 
                    className="btn btn-danger"
                    aria-label="Confirm logout"
                >
                    Yes, Logout
                </button>
                <button 
                    onClick={onCancel} 
                    className="btn btn-secondary"
                    aria-label="Cancel logout"
                >
                    Cancel
                </button>
            </div>
        </div>
    </div>
));

LogoutModal.displayName = 'LogoutModal';

const Navbar = () => {
    const [isMenuOpen, setIsMenuOpen] = useState(false);
    const [showLogoutConfirm, setShowLogoutConfirm] = useState(false);
    const { isAuthenticated, logout } = useAuth();
    const navigate = useNavigate();
    const location = useLocation();

    const closeMenu = useCallback(() => {
        setIsMenuOpen(false);
    }, []);

    const handleNavClick = useCallback(() => {
        closeMenu();
    }, [closeMenu]);

    const handleLogoutClick = useCallback(() => {
        setShowLogoutConfirm(true);
        closeMenu();
    }, [closeMenu]);

    const handleLogout = useCallback(async () => {
        try {
            setShowLogoutConfirm(false);
            await logout();
            navigate('/');
        } catch (error) {
            console.error('Logout failed:', error);
        }
    }, [logout, navigate]);

    useEffect(() => {
        closeMenu();
    }, [location.pathname, closeMenu]);

    return (
        <nav className="navbar" role="navigation" aria-label="Main navigation">
            <div className="navbar-container">
                <div className="navbar-brand">
                    <img 
                        src="/doctor-avatar.png" 
                        alt="HealthTracker AI" 
                        className="navbar-avatar"
                        onError={(e) => { e.target.onerror = null; e.target.src = '/default-avatar.png'; }}
                    />
                    <div className="navbar-title">
                        <span className="navbar-name">HealthTracker AI</span>
                        <span className="navbar-role">AI Medical Assistant</span>
                    </div>
                    
                    {/* Add disclaimer for chat pages */}
                    {location.pathname === '/' && (
                        <span className="navbar-disclaimer">
                            For informational purposes only. Not a substitute for professional medical advice.
                        </span>
                    )}
                    
                    <button 
                        className="navbar-burger"
                        aria-label="menu"
                        aria-expanded={isMenuOpen}
                        onClick={() => setIsMenuOpen(!isMenuOpen)}
                    >
                        <span aria-hidden="true" />
                        <span aria-hidden="true" />
                        <span aria-hidden="true" />
                    </button>
                </div>

                <div 
                    className={`navbar-menu ${isMenuOpen ? 'active' : ''}`}
                    aria-hidden={!isMenuOpen}
                >
                    {PUBLIC_NAV_ITEMS.map((item) => (
                        <Link
                            key={item.path}
                            to={item.path}
                            className="nav-button chat-button"
                            onClick={handleNavClick}
                        >
                            {item.label}
                        </Link>
                    ))}

                    {isAuthenticated ? (
                        <>
                            {PRIVATE_NAV_ITEMS.map((item) => (
                                <Link
                                    key={item.path}
                                    to={item.path}
                                    className="nav-button"
                                    onClick={handleNavClick}
                                >
                                    {item.label}
                                </Link>
                            ))}
                            <button
                                onClick={handleLogoutClick}
                                className="nav-button logout-button"
                                aria-label="Logout"
                            >
                                Logout
                            </button>
                        </>
                    ) : (
                        <Link 
                            to="/auth" 
                            className="nav-button sign-in-button"
                            onClick={handleNavClick}
                        >
                            Sign In
                        </Link>
                    )}
                </div>
            </div>

            {showLogoutConfirm && (
                <LogoutModal 
                    onConfirm={handleLogout}
                    onCancel={() => setShowLogoutConfirm(false)}
                />
            )}
        </nav>
    );
};

export default memo(Navbar);