// utils.jsx
import React from 'react';

// Local Storage Functions with optimized JSON handling
export const setLocalStorageItem = (key, value) => {
    try {
        // Only stringify if value isn't already a string
        const serializedValue = typeof value === 'string' ? value : JSON.stringify(value);
        localStorage.setItem(key, serializedValue);
    } catch (err) {
        console.error(`Error setting localStorage for key "${key}":`, err);
    }
};

export const getLocalStorageItem = (key) => {
    try {
        const item = localStorage.getItem(key);
        if (!item) return null;

        // Try parsing as JSON, return as-is if parsing fails (handles primitive strings)
        try {
            return JSON.parse(item);
        } catch {
            return item;
        }
    } catch (err) {
        console.error(`Error accessing localStorage for key "${key}":`, err);
        return null;
    }
};

export const removeLocalStorageItem = (key) => {
    try {
        localStorage.removeItem(key);
    } catch (err) {
        console.error(`Error removing localStorage for key "${key}":`, err);
    }
};

export const clearLocalStorage = () => {
    try {
        localStorage.clear();
    } catch (err) {
        console.error('Error clearing localStorage:', err);
    }
};

export default {
    setLocalStorageItem,
    getLocalStorageItem,
    removeLocalStorageItem,
    clearLocalStorage
};