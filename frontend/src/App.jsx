import React, { Suspense, Component } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate, Link } from 'react-router-dom';
import AuthProvider from './components/AuthProvider'; // Default import
import { useAuth } from './components/AuthProvider'; // Named import

// Component Imports
import Chat from './components/Chat';
import MedicalInfo from './components/MedicalInfo';
import Library from './components/Library';
import Dashboard from './components/Dashboard';
import Onboarding from './components/Onboarding';
import SymptomLogger from './components/SymptomLogger';
import Report from './components/Report';
import AuthPage from './components/AuthPage';
import SubscriptionPage from './components/SubscriptionPage';
import OneTimeReportPage from './components/OneTimeReportPage';
import Navbar from './components/Navbar';
import LoadingSpinner from './components/LoadingSpinner';

// Styles
import './styles/App.css';
import './styles/Chat.css';
import './styles/navbar.css';
import './styles/shared.css';

// Error Boundary Component
class ErrorBoundary extends Component {
    state = { hasError: false, error: null };

    static getDerivedStateFromError(error) {
        return { hasError: true, error };
    }

    componentDidCatch(error, errorInfo) {
        console.error('ErrorBoundary caught an error:', error, errorInfo);
    }

    render() {
        if (this.state.hasError) {
            return (
                <div className="error-container">
                    <h1>Something went wrong.</h1>
                    <p>{this.state.error?.message || 'An unexpected error occurred.'}</p>
                    <p>Please try refreshing the page or logging in again.</p>
                    <Link to="/auth">Go to Login</Link>
                </div>
            );
        }
        return this.props.children;
    }
}

// PrivateRoute Wrapper (now using useAuth directly)
const PrivateRouteWrapper = ({ children }) => {
    const { isAuthenticated, isLoading } = useAuth(); // Safe to use here since wrapped by AuthProvider

    if (isLoading) {
        return <LoadingSpinner message="Checking authentication..." />;
    }

    if (!isAuthenticated) {
        return <Navigate to="/auth" replace />;
    }

    return children;
};

// Main App Component
const App = () => {
    return (
        <div className="app-container">
            <ErrorBoundary>
                <Navbar />
                <main className="app-main">
                    <Suspense fallback={<LoadingSpinner message="Loading..." />}>
                        <Routes>
                            {/* Public Routes */}
                            <Route path="/" element={<Chat />} />
                            <Route path="/auth" element={<AuthPage />} />
                            <Route path="/library" element={<Library />} />

                            {/* Protected Routes */}
                            <Route 
                                path="/dashboard" 
                                element={
                                    <PrivateRouteWrapper>
                                        <Dashboard />
                                    </PrivateRouteWrapper>
                                } 
                            />
                            <Route 
                                path="/symptom-logger" 
                                element={
                                    <PrivateRouteWrapper>
                                        <SymptomLogger />
                                    </PrivateRouteWrapper>
                                } 
                            />
                            <Route 
                                path="/report" 
                                element={
                                    <PrivateRouteWrapper>
                                        <Report />
                                    </PrivateRouteWrapper>
                                } 
                            />
                            <Route 
                                path="/onboarding" 
                                element={
                                    <PrivateRouteWrapper>
                                        <Onboarding />
                                    </PrivateRouteWrapper>
                                } 
                            />
                            <Route 
                                path="/medical-info" 
                                element={
                                    <PrivateRouteWrapper>
                                        <MedicalInfo />
                                    </PrivateRouteWrapper>
                                } 
                            />
                            <Route 
                                path="/subscription" 
                                element={
                                    <PrivateRouteWrapper>
                                        <SubscriptionPage />
                                    </PrivateRouteWrapper>
                                } 
                            /> 
                            <Route 
                                path="/one-time-report" 
                                element={
                                    <PrivateRouteWrapper>
                                        <OneTimeReportPage />
                                    </PrivateRouteWrapper>
                                } 
                            /> 
                            <Route 
                                path="/success" 
                                element={
                                    <PrivateRouteWrapper>
                                        <SubscriptionPage />
                                    </PrivateRouteWrapper>
                                } 
                            /> 
                            <Route 
                                path="/cancel" 
                                element={<div>Payment cancelled. <Link to="/subscription">Try again</Link></div>} 
                            /> 

                            {/* Redirects - Direct to AuthPage instead of redirecting */}
                            <Route path="/login" element={<AuthPage />} />
                            <Route path="/signup" element={<AuthPage initialMode="signup" />} />
                            <Route path="*" element={<Navigate to="/" replace />} />
                        </Routes>
                    </Suspense>
                </main>
            </ErrorBoundary>
        </div>
    );
};

// Wrapper that provides context
const AppWrapper = () => (
    <Router>
        <AuthProvider>
            <App />
        </AuthProvider>
    </Router>
);

export default AppWrapper;