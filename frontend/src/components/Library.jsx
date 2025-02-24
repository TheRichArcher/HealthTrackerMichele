// Import necessary modules
import React, { useEffect, useState } from 'react';
import axios from 'axios';

const API_BASE_URL = 'https://healthtrackermichele.onrender.com/api';

const Library = () => {
    const [resources, setResources] = useState([]);
    const [error, setError] = useState(null);
    const [isLoading, setIsLoading] = useState(true);

    // Fetch resources from the backend
    useEffect(() => {
        const fetchResources = async () => {
            try {
                const response = await axios.get(`${API_BASE_URL}/library`, {
                    headers: {
                        'Content-Type': 'application/json',
                        // Add authorization header if needed
                        // 'Authorization': `Bearer ${localStorage.getItem('access_token')}`
                    },
                    timeout: 10000 // 10 second timeout
                });

                if (response.data && Array.isArray(response.data.library)) {
                    setResources(response.data.library);
                } else {
                    throw new Error('Invalid response format');
                }
            } catch (err) {
                console.error('Error fetching library resources:', err);
                setError(
                    err.response?.status === 404 
                        ? 'Library resources not found.'
                        : err.response?.status === 401
                        ? 'Please log in to access the library.'
                        : 'Unable to load library resources. Please try again later.'
                );
            } finally {
                setIsLoading(false);
            }
        };

        fetchResources();

        // Cleanup function
        return () => {
            // Cancel any pending requests if component unmounts
            // You can use axios.CancelToken for this if needed
        };
    }, []);

    if (isLoading) {
        return (
            <div className="library-container">
                <h1 className="library-title">Trusted Resource Library</h1>
                <div className="loading-message" role="status">
                    Loading resources...
                </div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="library-container">
                <h1 className="library-title">Trusted Resource Library</h1>
                <div className="error-message" role="alert">
                    {error}
                </div>
            </div>
        );
    }

    return (
        <div className="library-container">
            <h1 className="library-title">Trusted Resource Library</h1>

            {resources.length === 0 ? (
                <p className="no-resources-message" role="status">
                    No resources found in the library.
                </p>
            ) : (
                <ul className="resource-list" role="list">
                    {resources.map((resource, index) => (
                        <li 
                            key={resource.id || index} 
                            className="library-item"
                        >
                            <a 
                                href={resource.url} 
                                target="_blank" 
                                rel="noopener noreferrer" 
                                className="resource-link"
                                aria-label={`Read ${resource.title}`}
                            >
                                <h2 className="resource-title">{resource.title}</h2>
                                {resource.description && (
                                    <p className="resource-description">
                                        {resource.description}
                                    </p>
                                )}
                                {resource.category && (
                                    <span className="resource-category">
                                        {resource.category}
                                    </span>
                                )}
                            </a>
                        </li>
                    ))}
                </ul>
            )}
        </div>
    );
};

export default Library;