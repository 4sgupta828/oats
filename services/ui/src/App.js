import React, { useState, useEffect, useRef } from 'react';
import { io } from 'socket.io-client';
import './App.css';

// Helper to format different message types from the agent
const formatAgentPayload = (message) => {
  try {
    // Agent messages are sent as strings, so we parse them first
    const data = typeof message === 'string' ? JSON.parse(message) : message;
    const { type, payload } = data;

    switch (type) {
      case 'thought':
        return `🧠 Thought: ${payload}`;
      case 'action':
        return `▶️ Action: ${payload.tool} with params ${JSON.stringify(payload.params)}`;
      case 'observation':
        // Basic formatting for observation strings
        return `👀 Observation:\n${payload.substring(0, 1000)}${payload.length > 1000 ? '...' : ''}`;
      case 'finish':
        // Handle both old string format and new object format
        if (typeof payload === 'string') {
          return `✅ Investigation Complete: ${payload}`;
        } else {
          // New format with comprehensive completion data
          const lines = [
            `✅ Investigation Complete!`,
            ``,
            `📊 Summary:`,
            payload.execution_summary || payload.completion_reason,
            ``,
            `📈 Turns Completed: ${payload.turns_completed}`,
          ];

          if (payload.final_results_file) {
            lines.push(``);
            lines.push(`📁 Full results saved to:`);
            lines.push(payload.final_results_file);
          }

          return lines.join('\n');
        }
      case 'status':
        return `ℹ️ Status: ${payload}`;
      case 'error':
        return `🔥 Error: ${payload}`;
      default:
        return JSON.stringify(payload, null, 2);
    }
  } catch (error) {
    // If parsing fails, it might be a simple status string
    return `ℹ️ Status: ${message}`;
  }
};


function App() {
  const [goal, setGoal] = useState('');
  const [messages, setMessages] = useState([]);
  const [isConnected, setIsConnected] = useState(false);
  const [isInvestigating, setIsInvestigating] = useState(false);
  const messagesEndRef = useRef(null);
  const socketRef = useRef(null);

  useEffect(() => {
    // Establish WebSocket connection when the component mounts.
    // The empty URL connects to the same host that serves the page.
    // Our Nginx proxy will route this to the backend.
    const socket = io();
    socketRef.current = socket;

    socket.on('connect', () => {
      console.log('Connected to backend.');
      setIsConnected(true);
    });

    socket.on('disconnect', () => {
      console.log('Disconnected from backend.');
      setIsConnected(false);
    });

    socket.on('agent_message', (message) => {
      console.log('Received message from agent:', message);
      const formattedText = formatAgentPayload(message);
      setMessages(prevMessages => [...prevMessages, { sender: 'agent', text: formattedText }]);

      // If the message indicates completion, allow new investigations
      const data = typeof message === 'string' ? JSON.parse(message) : message;
      if (data.type === 'finish') {
        setIsInvestigating(false);
      }
    });

    // Clean up the connection when the component unmounts
    return () => {
      socket.disconnect();
    };
  }, []);

  // Effect to scroll to the bottom of the messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!goal.trim() || !isConnected || isInvestigating) return;

    const userMessage = { sender: 'user', text: goal };
    setMessages(prevMessages => [userMessage]); // Clear previous messages for a new investigation
    setIsInvestigating(true);

    // Send the goal to the backend via WebSocket
    socketRef.current.emit('start_investigation', { goal });
    setGoal('');
  };

  return (
    <div className="App">
      <header className="App-header">
        <h1>OATS SRE Co-Pilot</h1>
        <div className={`connection-status ${isConnected ? 'connected' : ''}`}>
          {isConnected ? '● Connected' : '○ Disconnected'}
        </div>
      </header>
      <div className="message-container">
        {messages.map((msg, index) => (
          <div key={index} className={`message ${msg.sender}`}>
            <div className="sender-label">{msg.sender === 'user' ? 'You' : 'Agent'}</div>
            {msg.text.split('\n').map((line, i) => <p key={i}>{line}</p>)}
          </div>
        ))}
        {isInvestigating && messages[messages.length - 1]?.sender === 'agent' && (
          <div className="spinner"></div>
        )}
        <div ref={messagesEndRef} />
      </div>
      <footer className="App-footer">
        <form onSubmit={handleSubmit} className="input-form">
          <input
            type="text"
            value={goal}
            onChange={(e) => setGoal(e.target.value)}
            placeholder={isInvestigating ? "Investigation in progress..." : "e.g., Diagnose high latency in the payment-service"}
            disabled={!isConnected || isInvestigating}
          />
          <button type="submit" disabled={!isConnected || isInvestigating}>
            {isInvestigating ? 'Running...' : 'Start Investigation'}
          </button>
        </form>
      </footer>
    </div>
  );
}

export default App;