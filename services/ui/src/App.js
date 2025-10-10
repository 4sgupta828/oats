import React, { useState, useEffect, useRef } from 'react';
import './App.css';

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
    const currentGoal = goal;
    setGoal('');

    try {
      // The proxy in package.json forwards requests to the backend API on port 8000
      const response = await fetch('/investigate', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ goal: currentGoal }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || 'An unknown error occurred.');
      }

      // Add agent's confirmation message to the display
      const agentResponse = {
        sender: 'agent',
        text: `${data.message}\n\nTo see the agent's progress, check the logs or wait for updates.`
      };
      setMessages(prevMessages => [...prevMessages, agentResponse]);

    } catch (error) {
      // Handle errors and display them to the user
      const errorMessage = {
        sender: 'agent',
        text: `Error: ${error.message || 'Failed to start investigation. Please try again.'}`
      };
      setMessages(prevMessages => [...prevMessages, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="App">
      <header className="App-header">
        <h1>OATS SRE Co-Pilot</h1>
      </header>

      <div className="message-container">
        {messages.map((msg, index) => (
          <div
            key={index}
            className={`message ${msg.sender === 'user' ? 'user-message' : 'agent-message'}`}
          >
            <div className="sender-label">
              {msg.sender === 'user' ? 'You' : 'Agent'}
            </div>
            <p>{msg.text}</p>
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      <form onSubmit={handleSubmit} className="input-form">
        <input
          type="text"
          value={goal}
          onChange={(e) => setGoal(e.target.value)}
          placeholder="Enter your investigation goal..."
          disabled={isLoading}
          className="goal-input"
        />
        <button type="submit" disabled={isLoading || !goal.trim()} className="submit-button">
          {isLoading ? 'Processing...' : 'Submit'}
        </button>
      </form>
    </div>
  );
}

export default App;
