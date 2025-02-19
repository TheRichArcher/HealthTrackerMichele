import React, { Suspense } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';

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
import './styles/Chat.css';

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
                                <ProtectedRoute>
                                    <Dashboard />
                                </ProtectedRoute>
                            } 
                        />
                        <Route 
                            path="/symptom-logger" 
                            element={
                                <ProtectedRoute>
                                    <SymptomLogger />
                                </ProtectedRoute>
                            } 
                        />
                        <Route 
                            path="/report" 
                            element={
                                <ProtectedRoute>
                                    <Report />
                                </ProtectedRoute>
                            } 
                        />
                        <Route 
                            path="/onboarding" 
                            element={
                                <ProtectedRoute>
                                    <Onboarding />
                                </ProtectedRoute>
                            } 
                        />
                        <Route 
                            path="/medical-info" 
                            element={
                                <ProtectedRoute>
                                    <MedicalInfo />
                                </ProtectedRoute>
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