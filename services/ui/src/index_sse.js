import React from 'react';
import ReactDOM from 'react-dom/client';
import './index.css';
import AppSSE from './AppSSE';

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
  <React.StrictMode>
    <AppSSE />
  </React.StrictMode>
);
