import React, { useState, useCallback, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { getLocalStorageItem, setLocalStorageItem } from "../utils/utils";
import debounce from 'lodash/debounce';
import '../styles/SymptomLogger.css';

// Validation constants
const VALIDATION_RULES = {
    respiratoryRate: { min: 8, max: 40, label: 'Respiratory rate' },
    oxygenSaturation: { min: 50, max: 100, label: 'Oxygen saturation' },
    waistCircumference: { min: 20, max: 200, label: 'Waist circumference' },
    intensity: { min: 1, max: 10, label: 'Intensity' }
};

// Initial form state
const initialFormState = {
    symptom: "",
    onsetDate: new Date().toISOString().split('T')[0],
    relatedSymptoms: "",
    intensity: 5,
    respiratoryRate: "",
    oxygenSaturation: "",
    waistCircumference: ""
};

// Loading Spinner Component
const LoadingSpinner = () => (
    <div className="spinner-overlay">
        <div className="spinner"></div>
    </div>
);

// Error Boundary Component
class ErrorBoundary extends React.Component {
    state = { hasError: false };

    static getDerivedStateFromError(error) {
        return { hasError: true };
    }

    render() {
        if (this.state.hasError) {
            return (
                <div className="error-boundary">
                    <h2>Something went wrong</h2>
                    <button onClick={() => window.location.reload()}>
                        Refresh Page
                    </button>
                </div>
            );
        }
        return this.props.children;
    }
}

const SymptomLogger = () => {
    const [formData, setFormData] = useState(initialFormState);
    const [logStatus, setLogStatus] = useState(null);
    const [errors, setErrors] = useState({});
    const [isLoading, setIsLoading] = useState(false);
    const [lastEntry, setLastEntry] = useState(null);

    const { isAuthenticated, checkAuth } = useAuth();
    const navigate = useNavigate();
    const userId = getLocalStorageItem("user_id");

    // Load last entry on mount
    useEffect(() => {
        const savedEntry = getLocalStorageItem("lastSymptomEntry");
        if (savedEntry) {
            const parsedEntry = JSON.parse(savedEntry);
            setLastEntry(parsedEntry);
            setFormData(prev => ({
                ...prev,
                ...parsedEntry,
                onsetDate: new Date().toISOString().split('T')[0]
            }));
        }
    }, []);

    // Auto-clear success message
    useEffect(() => {
        if (logStatus) {
            const timer = setTimeout(() => setLogStatus(null), 3000);
            return () => clearTimeout(timer);
        }
    }, [logStatus]);

    // Redirect if not authenticated
    useEffect(() => {
        if (!isAuthenticated) {
            navigate('/auth');
        }
    }, [isAuthenticated, navigate]);

    // Debounced validation
    const debouncedValidation = useCallback(
        debounce((value, id) => {
            const rules = VALIDATION_RULES[id];
            if (!rules) return;

            const numValue = Number(value);
            if (value && (numValue < rules.min || numValue > rules.max)) {
                setErrors(prev => ({
                    ...prev,
                    [id]: `${rules.label} must be between ${rules.min} and ${rules.max}`
                }));
            } else {
                setErrors(prev => ({ ...prev, [id]: null }));
            }
        }, 300),
        []
    );

    // Handle input changes
    const handleInputChange = useCallback((e) => {
        const { id, value, type } = e.target;

        setFormData(prev => ({ ...prev, [id]: value }));

        if (type === 'number' || id === 'intensity') {
            debouncedValidation(value, id);
        } else {
            setErrors(prev => ({ ...prev, [id]: null }));
        }
    }, [debouncedValidation]);

    // Form validation
    const validateForm = useCallback(() => {
        const newErrors = {};

        if (!userId) {
            newErrors.general = "User session not found. Please log in.";
        }

        if (!formData.symptom.trim()) {
            newErrors.symptom = "Please provide a symptom description.";
        }

        Object.entries(VALIDATION_RULES).forEach(([field, rules]) => {
            if (formData[field]) {
                const numValue = Number(formData[field]);
                if (numValue < rules.min || numValue > rules.max) {
                    newErrors[field] = `${rules.label} must be between ${rules.min} and ${rules.max}`;
                }
            }
        });

        setErrors(newErrors);
        return Object.keys(newErrors).length === 0;
    }, [userId, formData]);

    // Handle form reset
    const handleReset = useCallback(() => {
        setFormData({
            ...initialFormState,
            onsetDate: new Date().toISOString().split('T')[0]
        });
        setErrors({});
        setLogStatus("Form reset successfully!");
    }, []);

    // Handle restore last entry
    const handleRestore = useCallback(() => {
        if (lastEntry) {
            setFormData({
                ...lastEntry,
                onsetDate: new Date().toISOString().split('T')[0]
            });
            setErrors({});
            setLogStatus("Last entry restored!");
        }
    }, [lastEntry]);

    // Handle form submission
    const handleSubmit = async (event) => {
        event.preventDefault();

        if (!validateForm()) {
            return;
        }

        setIsLoading(true);
        setLogStatus(null);

        try {
            const response = await fetch(
                "https://healthtrackerai.pythonanywhere.com/api/symptoms/",
                {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "Authorization": `Bearer ${getLocalStorageItem('access_token')}`
                    },
                    body: JSON.stringify({
                        user_id: userId,
                        symptom: formData.symptom.trim(),
                        notes: formData.relatedSymptoms.trim(),
                        intensity: formData.intensity,
                        respiratory_rate: formData.respiratoryRate,
                        oxygen_saturation: formData.oxygenSaturation,
                        waist_circumference: formData.waistCircumference,
                    }),
                }
            );

            if (!response.ok) {
                if (response.status === 401) {
                    await checkAuth();
                    throw new Error("Session expired. Please log in again.");
                }
                const errorData = await response.json();
                throw new Error(errorData.error || "Failed to log the symptom.");
            }

            setLocalStorageItem("lastSymptomEntry", JSON.stringify(formData));
            setLastEntry(formData);
            setLogStatus("✅ Symptom logged successfully!");
            setErrors({});

            handleReset();
            window.scrollTo({ top: 0, behavior: 'smooth' });
        } catch (err) {
            setErrors({ general: err.message });
            if (err.message.includes("session expired")) {
                navigate('/auth');
            }
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="symptom-logger-container">
            <h1 className="header">Log Your Symptom</h1>

            {(logStatus || errors.general) && (
                <div 
                    className={`message ${errors.general ? 'error' : 'success'}`}
                    role={errors.general ? 'alert' : 'status'}
                >
                    {errors.general || logStatus}
                </div>
            )}

            <form onSubmit={handleSubmit} className="form">
                <div className={`form-group ${errors.symptom ? 'error' : ''}`}>
                    <label htmlFor="symptom">Symptom:</label>
                    <input
                        type="text"
                        id="symptom"
                        value={formData.symptom}
                        onChange={handleInputChange}
                        placeholder="e.g., fever, headache, etc."
                        required
                        disabled={isLoading}
                        aria-invalid={!!errors.symptom}
                        aria-describedby={errors.symptom ? "symptom-error" : undefined}
                    />
                    {errors.symptom && (
                        <span className="error-message" id="symptom-error">
                            {errors.symptom}
                        </span>
                    )}
                </div>

                <div className={`form-group ${errors.onsetDate ? 'error' : ''}`}>
                    <label htmlFor="onsetDate">Onset Date:</label>
                    <input
                        type="date"
                        id="onsetDate"
                        value={formData.onsetDate}
                        onChange={handleInputChange}
                        max={new Date().toISOString().split('T')[0]}
                        required
                        disabled={isLoading}
                    />
                </div>

                <div className={`form-group ${errors.relatedSymptoms ? 'error' : ''}`}>
                    <label htmlFor="relatedSymptoms">Notes:</label>
                    <textarea
                        id="relatedSymptoms"
                        value={formData.relatedSymptoms}
                        onChange={handleInputChange}
                        placeholder="Additional notes about your symptoms..."
                        disabled={isLoading}
                        rows="3"
                    />
                </div>

                <div className={`form-group ${errors.intensity ? 'error' : ''}`}>
                    <label htmlFor="intensity">
                        Intensity: <span className="intensity-value">{formData.intensity}</span>
                    </label>
                    <input
                        type="range"
                        id="intensity"
                        min={VALIDATION_RULES.intensity.min}
                        max={VALIDATION_RULES.intensity.max}
                        value={formData.intensity}
                        onChange={handleInputChange}
                        disabled={isLoading}
                    />
                    <div className="range-labels">
                        <span>Mild</span>
                        <span>Severe</span>
                    </div>
                </div>

                <div className={`form-group ${errors.respiratoryRate ? 'error' : ''}`}>
                    <label htmlFor="respiratoryRate">
                        Respiratory Rate (breaths/min):
                    </label>
                    <input
                        type="number"
                        id="respiratoryRate"
                        value={formData.respiratoryRate}
                        onChange={handleInputChange}
                        placeholder={`${VALIDATION_RULES.respiratoryRate.min}-${VALIDATION_RULES.respiratoryRate.max}`}
                        disabled={isLoading}
                        min={VALIDATION_RULES.respiratoryRate.min}
                        max={VALIDATION_RULES.respiratoryRate.max}
                    />
                    {errors.respiratoryRate && (
                        <span className="error-message">
                            {errors.respiratoryRate}
                        </span>
                    )}
                </div>

                <div className={`form-group ${errors.oxygenSaturation ? 'error' : ''}`}>
                    <label htmlFor="oxygenSaturation">
                        Oxygen Saturation (%):
                    </label>
                    <input
                        type="number"
                        id="oxygenSaturation"
                        value={formData.oxygenSaturation}
                        onChange={handleInputChange}
                        placeholder={`${VALIDATION_RULES.oxygenSaturation.min}-${VALIDATION_RULES.oxygenSaturation.max}`}
                        disabled={isLoading}
                        min={VALIDATION_RULES.oxygenSaturation.min}
                        max={VALIDATION_RULES.oxygenSaturation.max}
                    />
                    {errors.oxygenSaturation && (
                        <span className="error-message">
                            {errors.oxygenSaturation}
                        </span>
                    )}
                </div>

                <div className={`form-group ${errors.waistCircumference ? 'error' : ''}`}>
                    <label htmlFor="waistCircumference">
                        Waist Circumference (cm):
                    </label>
                    <input
                        type="number"
                        id="waistCircumference"
                        value={formData.waistCircumference}
                        onChange={handleInputChange}
                        placeholder={`${VALIDATION_RULES.waistCircumference.min}-${VALIDATION_RULES.waistCircumference.max}`}
                        disabled={isLoading}
                        min={VALIDATION_RULES.waistCircumference.min}
                        max={VALIDATION_RULES.waistCircumference.max}
                    />
                    {errors.waistCircumference && (
                        <span className="error-message">
                            {errors.waistCircumference}
                        </span>
                    )}
                </div>

                <div className="button-group">
                    <button 
                        type="submit" 
                        disabled={isLoading || Object.keys(errors).length > 0} 
                        className={`submit-button ${isLoading ? 'loading' : ''}`}
                    >
                        {isLoading ? "Logging..." : "Log Symptom"}
                    </button>
                    <button 
                        type="button"
                        onClick={handleReset}
                        className="reset-button"
                        disabled={isLoading}
                    >
                        Reset Form
                    </button>
                    {lastEntry && (
                        <button 
                            type="button"
                            onClick={handleRestore}
                            className="restore-button"
                            disabled={isLoading}
                        >
                            Restore Last Entry
                        </button>
                    )}
                </div>
            </form>

            {isLoading && <LoadingSpinner />}
        </div>
    );
};

// Export wrapped component with error boundary
export default function SymptomLoggerWithErrorBoundary() {
    return (
        <ErrorBoundary>
            <SymptomLogger />
        </ErrorBoundary>
    );
}