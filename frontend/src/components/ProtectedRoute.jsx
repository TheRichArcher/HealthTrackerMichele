import React, { useState, useEffect } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import LoadingSpinner from './LoadingSpinner';

const ProtectedRoute = ({ children }) => {
    const { isAuthenticated, isLoading } = useAuth();
    const location = useLocation();
    const [showLoading, setShowLoading] = useState(false);

    useEffect(() => {
        let timer;
        if (isLoading) {
            timer = setTimeout(() => setShowLoading(true), 200);
        } else {
            setShowLoading(false);
        }
        return () => clearTimeout(timer);
    }, [isLoading]);

    if (isLoading && showLoading) {
        return <LoadingSpinner message="Verifying authentication..." />;
    }

    if (!isAuthenticated && !isLoading) {
        return <Navigate to="/auth" state={{ from: location.pathname }} replace />;
    }

    return children;
};

export default ProtectedRoute;