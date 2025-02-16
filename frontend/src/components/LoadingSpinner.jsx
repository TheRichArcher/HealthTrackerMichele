import React, { memo } from 'react';
import '../styles/LoadingSpinner.css';

const LoadingSpinner = memo(({ message = 'Loading...' }) => (
    <div className="loading-spinner">
        <div className="spinner"></div>
        <p>{message}</p>
    </div>
));

LoadingSpinner.displayName = 'LoadingSpinner';

export default LoadingSpinner;