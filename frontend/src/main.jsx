import React from 'react';
import ReactDOM from 'react-dom/client';
import AppWrapper from './App'; // Import the AppWrapper from App.jsx

// Mount the React app to the root div
const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
  <React.StrictMode>
    <AppWrapper />
  </React.StrictMode>
);