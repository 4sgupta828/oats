import React, { useState, useEffect, useRef } from 'react';
import { io } from 'socket.io-client';
import './App.css';

const formatAgentPayload = (message) => {
  try {
    const data = typeof message === 'string' ? JSON.parse(message) : message;
    const { type, payload } = data;

    switch (type) {
      case 'thought':
        return `🧠 Thought: ${payload}`;
      case 'action':
        return `▶️ Action: ${payload.tool} with params ${JSON.stringify(payload.params)}`;
      case 'observation':
        return `👀 Observation:\n${payload.substring(0, 1000)}${payload.length > 1000 ? '...' : ''}`;
      case 'finish':
        const lines = [
          `✅ OATS Analysis Complete!`, ``, `📊 Summary:`,
          payload.execution_summary || payload.completion_reason, ``,
          `📈 Cycles Completed: ${payload.turns_completed}`,
        ];
        if (payload.final_results_file) {
          lines.push(``, `📁 Full results saved to:`, payload.final_results_file);
        }
        return lines.join('\n');
      case 'status':
        return `ℹ️ Status: ${payload}`;
      case 'error':
        return `🔥 Error: ${payload}`;
      default:
        return JSON.stringify(payload, null, 2);
    }
  } catch (error) {
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
    const socket = io();
    socketRef.current = socket;
    socket.on('connect', () => setIsConnected(true));
    socket.on('disconnect', () => setIsConnected(false));
    socket.on('agent_message', (message) => {
      const formattedText = formatAgentPayload(message);
      setMessages(prev => [...prev, { sender: 'agent', text: formattedText }]);
      const data = typeof message === 'string' ? JSON.parse(message) : message;
      if (data.type === 'finish') {
        setIsInvestigating(false);
      }
    });
    return () => socket.disconnect();
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!goal.trim() || !isConnected || isInvestigating) return;
    setMessages([{ sender: 'user', text: goal }]);
    setIsInvestigating(true);
    socketRef.current.emit('start_investigation', { goal });
    setGoal('');
  };

  return (
    <div className="App">
      <header className="App-header">
        <div>
            <h1>OATS Framework</h1>
            <p className="subtitle">Observe · Adapt · TakeAction · Synthesize</p>
        </div>
        <div className={`connection-status ${isConnected ? 'connected' : ''}`}>
          {isConnected ? '● Connected' : '○ Disconnected'}
        </div>
      </header>
      <div className="message-container">
        {messages.map((msg, index) => (
          <div key={index} className={`message ${msg.sender === 'user' ? 'user-message' : 'agent-message'}`}>
            <div className="sender-label">{msg.sender === 'user' ? 'You' : 'Agent'}</div>
            {msg.text.split('\n').map((line, i) => <p key={i}>{line}</p>)}
          </div>
        ))}
        {isInvestigating && messages.length > 0 && messages[messages.length - 1]?.sender === 'agent' && (
          <div className="spinner"></div>
        )}
        <div ref={messagesEndRef} />
      </div>
      <form onSubmit={handleSubmit} className="input-form">
        <input
          className="goal-input"
          type="text"
          value={goal}
          onChange={(e) => setGoal(e.target.value)}
          placeholder={isInvestigating ? "Analysis in progress..." : "Describe your infrastructure issue..."}
          disabled={!isConnected || isInvestigating}
        />
        <button type="submit" className="submit-button" disabled={!isConnected || isInvestigating}>
          {isInvestigating ? 'Analyzing...' : 'Start Analysis'}
        </button>
      </form>
    </div>
  );
}

export default App;