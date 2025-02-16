// Import necessary modules
import React, { useEffect, useState } from 'react';
import axios from 'axios';

const Library = () => {
    const [resources, setResources] = useState([]);
    const [error, setError] = useState(null);
    const [isLoading, setIsLoading] = useState(true);

    // Fetch resources from the backend
    useEffect(() => {
        const fetchResources = async () => {
            try {
                const response = await axios.get('https://healthtrackerai.pythonanywhere.com/api/library');
                setResources(response.data.library);
            } catch (err) {
                console.error('Error fetching library resources:', err);
                setError('Unable to load library resources. Please check your connection and try again.');
            } finally {
                setIsLoading(false);
            }
        };

        fetchResources();
    }, []);

    return (
        <div className="library-container">
            <h1 className="library-title">Trusted Resource Library</h1>

            {isLoading && <p className="loading-message">Loading resources...</p>}
            {error && <p className="error-message">{error}</p>}

            {!isLoading && !error && resources.length === 0 && (
                <p className="no-resources-message">No resources found in the library.</p>
            )}

            <ul className="resource-list">
                {resources.map((resource, index) => (
                    <li key={index} className="library-item">
                        <a 
                            href={resource.url} 
                            target="_blank" 
                            rel="noopener noreferrer" 
                            className="resource-link"
                            aria-label={`Read ${resource.title}`}
                        >
                            {resource.title}
                        </a>
                    </li>
                ))}
            </ul>
        </div>
    );
};

export default Library;
