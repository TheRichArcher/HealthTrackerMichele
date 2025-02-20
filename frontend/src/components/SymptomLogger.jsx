import React, { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { getLocalStorageItem, setLocalStorageItem } from "../utils/utils";
import debounce from "lodash/debounce";
import "../styles/SymptomLogger.css";

const VALIDATION_RULES = {
    respiratoryRate: { min: 8, max: 40, label: "Respiratory rate" },
    oxygenSaturation: { min: 50, max: 100, label: "Oxygen saturation" },
    waistCircumference: { min: 20, max: 200, label: "Waist circumference" },
    intensity: { min: 1, max: 10, label: "Intensity" },
};

const initialFormState = {
    symptom: "",
    onsetDate: new Date().toISOString().split("T")[0],
    relatedSymptoms: "",
    intensity: 5,
    respiratoryRate: "",
    oxygenSaturation: "",
    waistCircumference: "",
};

const SymptomLogger = () => {
    const [formData, setFormData] = useState(initialFormState);
    const [logStatus, setLogStatus] = useState(null);
    const [errors, setErrors] = useState({});
    const [isLoading, setIsLoading] = useState(false);
    const navigate = useNavigate();
    const { isAuthenticated, checkAuth } = useAuth();
    const userId = getLocalStorageItem("user_id");

    useEffect(() => {
        if (!isAuthenticated) {
            navigate("/auth");
        }
    }, [isAuthenticated, navigate]);

    useEffect(() => {
        if (logStatus) {
            const timer = setTimeout(() => setLogStatus(null), 3000);
            return () => clearTimeout(timer);
        }
    }, [logStatus]);

    const debouncedValidation = useCallback(
        debounce((value, id) => {
            const rules = VALIDATION_RULES[id];
            if (!rules) return;

            const numValue = Number(value);
            if (value && (numValue < rules.min || numValue > rules.max)) {
                setErrors((prev) => ({
                    ...prev,
                    [id]: `${rules.label} must be between ${rules.min} and ${rules.max}`,
                }));
            } else {
                setErrors((prev) => ({ ...prev, [id]: null }));
            }
        }, 300),
        []
    );

    const handleInputChange = (e) => {
        const { id, value } = e.target;
        setFormData((prev) => ({ ...prev, [id]: value }));
        debouncedValidation(value, id);
    };

    const validateForm = () => {
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
    };

    const handleSubmit = async (event) => {
        event.preventDefault();
        if (!validateForm()) return;

        setIsLoading(true);
        setLogStatus(null);

        try {
            const response = await fetch(
                "https://healthtrackerai.pythonanywhere.com/api/symptoms/",
                {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "Authorization": `Bearer ${getLocalStorageItem("access_token")}`,
                    },
                    body: JSON.stringify({ user_id: userId, ...formData }),
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
            setLogStatus("✅ Symptom logged successfully!");
            setErrors({});
            setFormData(initialFormState);
        } catch (err) {
            setErrors({ general: err.message });
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="symptom-logger-container">
            <h1 className="header">Log Your Symptom</h1>
            {logStatus && <div className="message success">{logStatus}</div>}
            {errors.general && <div className="message error">{errors.general}</div>}
            <form onSubmit={handleSubmit} className="form">
                <div className="form-group">
                    <label htmlFor="symptom">Symptom:</label>
                    <input
                        type="text"
                        id="symptom"
                        value={formData.symptom}
                        onChange={handleInputChange}
                        required
                    />
                </div>
                <button type="submit" disabled={isLoading} className="submit-button">
                    {isLoading ? "Logging..." : "Log Symptom"}
                </button>
            </form>
        </div>
    );
};

export default SymptomLogger;
