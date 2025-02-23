import React, { Suspense } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';  // ✅ Added `useAuth`

// Component Imports
import Chat from './components/Chat';
import MedicalInfo from './components/MedicalInfo';
import Library from './components/Library';
import Dashboard from './components/Dashboard';
import Onboarding from './components/Onboarding';
import SymptomLogger from './components/SymptomLogger';
import Report from './components/Report';
import AuthPage from './components/AuthPage';
import Navbar from './components/Navbar';
import LoadingSpinner from './components/LoadingSpinner';
import ProtectedRoute from './components/ProtectedRoute';

// Styles
import './styles/App.css';
import './styles/navbar.css';
import './styles/Chat.css';

// Protected Route Wrapper
const PrivateRoute = ({ children }) => {
    const { isAuthenticated, isLoading } = useAuth();  // ✅ useAuth now properly imported

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
                                <PrivateRoute>
                                    <Dashboard />
                                </PrivateRoute>
                            } 
                        />
                        <Route 
                            path="/symptom-logger" 
                            element={
                                <PrivateRoute>
                                    <SymptomLogger />
                                </PrivateRoute>
                            } 
                        />
                        <Route 
                            path="/report" 
                            element={
                                <PrivateRoute>
                                    <Report />
                                </PrivateRoute>
                            } 
                        />
                        <Route 
                            path="/onboarding" 
                            element={
                                <PrivateRoute>
                                    <Onboarding />
                                </PrivateRoute>
                            } 
                        />
                        <Route 
                            path="/medical-info" 
                            element={
                                <PrivateRoute>
                                    <MedicalInfo />
                                </PrivateRoute>
                            } 
                        />

                        {/* Redirects */}
                        <Route path="/login" element={<Navigate to="/auth" replace />} />
                        <Route path="/signup" element={<Navigate to="/auth" replace />} />
                        <Route path="*" element={<Navigate to="/" replace />} />
                    </Routes>
                </Suspense>
            </main>
        </div>
    );
};

// App Wrapper with Router and Auth Provider
const AppWrapper = () => (
    <Router>
        <AuthProvider>
            <App />
        </AuthProvider>
    </Router>
);

export default AppWrapper;
