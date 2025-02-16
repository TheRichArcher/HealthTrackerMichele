import React, { useState, useMemo, memo, useCallback, useEffect } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import '../styles/navbar.css';

// Navigation items split into public and private
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

/** Logout Confirmation Modal */
const LogoutModal = memo(({ onConfirm, onCancel }) => (
    <div 
        className="modal-overlay" 
        onClick={onCancel}
        role="dialog"
        aria-labelledby="logout-title"
        aria-describedby="logout-description"
    >
        <div 
            className="modal-content" 
            onClick={e => e.stopPropagation()}
        >
            <h3 id="logout-title">Confirm Logout</h3>
            <p id="logout-description">Are you sure you want to log out?</p>
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

/** Navbar Links */
const NavbarLink = memo(({ to, children, onClick, className }) => {
    const location = useLocation();
    const isActive = useMemo(() => location.pathname === to, [location.pathname, to]);

    return (
        <Link 
            to={to} 
            className={`nav-link ${isActive ? 'active' : ''} ${className || ''}`}
            aria-current={isActive ? 'page' : undefined}
            onClick={onClick}
        >
            {children}
        </Link>
    );
});

NavbarLink.displayName = 'NavbarLink';

/** Main Navbar */
const Navbar = () => {
    const [isMenuOpen, setIsMenuOpen] = useState(false);
    const [showLogoutConfirm, setShowLogoutConfirm] = useState(false);
    const { isAuthenticated, logout } = useAuth();
    const navigate = useNavigate();
    const location = useLocation();

    /** Toggle Mobile Menu */
    const toggleMenu = useCallback(() => {
        setIsMenuOpen(prev => !prev);
    }, []);

    /** Close Menu */
    const closeMenu = useCallback(() => {
        setIsMenuOpen(false);
    }, []);

    /** Close Menu on Navigation */
    const handleNavClick = useCallback(() => {
        closeMenu();
    }, [closeMenu]);

    /** Show Logout Confirmation */
    const handleLogoutClick = useCallback(() => {
        setShowLogoutConfirm(true);
        closeMenu();
    }, [closeMenu]);

    /** Handle Logout */
    const handleLogout = useCallback(async () => {
        try {
            setShowLogoutConfirm(false);
            await logout();
            navigate('/');
        } catch (error) {
            console.error('Logout failed:', error);
        }
    }, [logout, navigate]);

    /** Close Modal on ESC Key */
    const handleKeyDown = useCallback((e) => {
        if (e.key === 'Escape') {
            setShowLogoutConfirm(false);
        }
    }, []);

    /** Add/Remove Keyboard Listener */
    useEffect(() => {
        if (showLogoutConfirm) {
            window.addEventListener('keydown', handleKeyDown);
        }
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [showLogoutConfirm, handleKeyDown]);

    /** Close Menu on Route Change */
    useEffect(() => {
        closeMenu();
    }, [location.pathname, closeMenu]);

    return (
        <nav className="navbar" role="navigation" aria-label="Main navigation">
            <div className="navbar-container">
                <div className="navbar-brand">
                    <Link to="/" className="logo" onClick={closeMenu}>
                        HealthTracker AI
                    </Link>
                </div>

                <div 
                    className={`navbar-menu ${isMenuOpen ? 'active' : ''}`}
                    aria-hidden={!isMenuOpen}
                >
                    {/* Public Navigation Items */}
                    {PUBLIC_NAV_ITEMS.map(({ path, label }) => (
                        <NavbarLink 
                            key={path} 
                            to={path}
                            onClick={handleNavClick}
                        >
                            {label}
                        </NavbarLink>
                    ))}

                    {/* Authentication-dependent Items */}
                    {isAuthenticated ? (
                        <>
                            {PRIVATE_NAV_ITEMS.map(({ path, label }) => (
                                <NavbarLink 
                                    key={path} 
                                    to={path}
                                    onClick={handleNavClick}
                                >
                                    {label}
                                </NavbarLink>
                            ))}
                            <button
                                onClick={handleLogoutClick}
                                className="logout-button"
                                aria-label="Logout"
                            >
                                Logout
                            </button>
                        </>
                    ) : (
                        <NavbarLink 
                            to="/auth"
                            onClick={handleNavClick}
                            className="login-button"
                        >
                            Sign In
                        </NavbarLink>
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