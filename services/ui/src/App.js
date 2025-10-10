import React, { useState, useEffect, useRef } from 'react';
import './App.css'; // We will create this CSS file next

function App() {
  const [goal, setGoal] = useState('');
  const [messages, setMessages] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef(null);

  // Effect to scroll to the bottom of the messages when new ones are added
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Initial greeting message
  useEffect(() => {
    setMessages([
      { sender: 'agent', text: 'Welcome to the OATS SRE Co-Pilot. Please enter your goal to begin an investigation.' }
    ]);
  }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!goal.trim() || isLoading) return;

    // Add user's message to the display
    const userMessage = { sender: 'user', text: goal };
    setMessages(prevMessages => [...prevMessages, userMessage]);
    setIsLoading(true);
    setGoal('');

    try {
      // The '/api' prefix is handled by our Nginx proxy
      const response = await fetch('/api/investigate', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ goal }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || 'An unknown error occurred.');
      }

      // Add agent's confirmation message to the display
      const agentResponse = { sender: 'agent', text: `${data.message}\n\nTo see the agent's progress, run:\n\