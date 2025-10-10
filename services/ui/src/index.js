import React from 'react';
import ReactDOM from 'react-dom/client';

// Import the global stylesheet we created earlier
import './index.css';

// Import the main App component (we will create this next)
import App from './App';

// Find the <div id="root"> in our public/index.html file
const root = ReactDOM.createRoot(document.getElementById('root'));

// Render our main App component inside that div
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);