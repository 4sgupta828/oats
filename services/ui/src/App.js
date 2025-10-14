import React, { useState, useEffect, useRef } from 'react';
import { io } from 'socket.io-client';
import './App.css';
import AgentMessage from './components/AgentMessage';
import { useSSE } from './hooks/useSSE';

// Feature detection: Use SSE if backend supports it, fallback to WebSocket
const USE_SSE = process.env.REACT_APP_USE_SSE === 'true';

const formatAgentPayload = (message) => {
  try {
    const data = typeof message === 'string' ? JSON.parse(message) : message;
    const { type, payload } = data;

    // Return structured data instead of plain text
    switch (type) {
      case 'thought':
        return { type: 'thought', content: payload };
      case 'action':
        return {
          type: 'action',
          tool: payload.tool,
          params: payload.params
        };
      case 'observation':
        return {
          type: 'observation',
          content: payload,
          isLarge: payload.length > 1000
        };
      case 'finish':
        return {
          type: 'finish',
          summary: payload.execution_summary || payload.completion_reason,
          turnsCompleted: payload.turns_completed,
          resultsFile: payload.final_results_file
        };
      case 'status':
        return { type: 'status', content: payload };
      case 'error':
        return { type: 'error', content: payload };
      default:
        return { type: 'unknown', content: JSON.stringify(payload, null, 2) };
    }
  } catch (error) {
    return { type: 'status', content: message };
  }
};

// Format SSE events to match WebSocket format
const formatSSEEvent = (event) => {
  const eventData = event.data || {};

  switch (event.type) {
    case 'turn_started':
      return { type: 'status', content: `Starting turn ${event.turn}...` };

    case 'llm_called':
      return { type: 'status', content: 'AI is reasoning...' };

    case 'llm_response_success':
      const strategize = eventData.strategize || {};
      return {
        type: 'thought',
        content: strategize.reasoning || 'AI completed reasoning'
      };

    case 'tool_started':
      return {
        type: 'action',
        tool: eventData.tool_name,
        params: eventData.parameters
      };

    case 'tool_success':
      return {
        type: 'observation',
        content: eventData.observation || 'Tool executed successfully',
        isLarge: eventData.observation_length > 1000
      };

    case 'tool_failed':
      return {
        type: 'error',
        content: `Tool failed: ${eventData.error_message}`
      };

    case 'execution_completed':
      return {
        type: 'finish',
        summary: eventData.completion_reason || 'Goal completed',
        turnsCompleted: eventData.turns_completed
      };

    case 'execution_failed':
      return {
        type: 'error',
        content: `Execution failed: ${eventData.reason || eventData.error}`
      };

    default:
      return null;
  }
};

function App() {
  const [goal, setGoal] = useState('');
  const [messages, setMessages] = useState([]);
  const [isConnected, setIsConnected] = useState(false);
  const [isInvestigating, setIsInvestigating] = useState(false);
  const messagesEndRef = useRef(null);
  const socketRef = useRef(null);

  // Get backend URL from environment variable
  const backendUrl = process.env.REACT_APP_BACKEND_URL || 'http://localhost:8000';

  // Use SSE hook if enabled
  const sseHook = useSSE(USE_SSE ? backendUrl : null);

  // Process SSE events
  useEffect(() => {
    if (!USE_SSE || !sseHook.events) return;

    sseHook.events.forEach(event => {
      const formatted = formatSSEEvent(event);
      if (formatted) {
        setMessages(prev => {
          // Avoid duplicates
          const isDuplicate = prev.some(msg =>
            msg.sender === 'agent' &&
            JSON.stringify(msg.data) === JSON.stringify(formatted)
          );
          if (!isDuplicate) {
            return [...prev, { sender: 'agent', data: formatted }];
          }
          return prev;
        });
      }
    });
  }, [sseHook.events]);

  // Update connection status from SSE
  useEffect(() => {
    if (USE_SSE) {
      setIsConnected(sseHook.isConnected);
      setIsInvestigating(sseHook.isExecuting);
    }
  }, [sseHook.isConnected, sseHook.isExecuting]);

  useEffect(() => {
    // Skip WebSocket setup if using SSE
    if (USE_SSE) {
      setIsConnected(true);
      return;
    }

    console.log('Connecting to backend:', backendUrl);

    const socket = io(backendUrl, {
      reconnection: true,
      reconnectionAttempts: 10,
      reconnectionDelay: 1000,
      reconnectionDelayMax: 5000,
      timeout: 20000,
      transports: ['polling', 'websocket']
    });

    socketRef.current = socket;

    socket.on('connect', () => {
      console.log('Connected to backend');
      setIsConnected(true);
    });

    socket.on('disconnect', (reason) => {
      console.log('Disconnected from backend:', reason);
      setIsConnected(false);

      // Show error message about disconnection
      setMessages(prev => [...prev, {
        sender: 'agent',
        data: {
          type: 'error',
          content: `Connection lost: ${reason}. Attempting to reconnect...`
        }
      }]);
    });

    socket.on('reconnect', (attemptNumber) => {
      console.log('Reconnected to backend after', attemptNumber, 'attempts');
      setMessages(prev => [...prev, {
        sender: 'agent',
        data: {
          type: 'status',
          content: 'Connection restored!'
        }
      }]);
    });

    socket.on('reconnect_attempt', (attemptNumber) => {
      console.log('Reconnection attempt', attemptNumber);
    });

    socket.on('reconnect_failed', () => {
      console.error('Failed to reconnect to backend');
      setMessages(prev => [...prev, {
        sender: 'agent',
        data: {
          type: 'error',
          content: 'Failed to reconnect to backend. Please refresh the page.'
        }
      }]);
      setIsInvestigating(false);
    });

    socket.on('connect_error', (error) => {
      console.error('Connection error:', error);
    });

    socket.on('agent_message', (message) => {
      const formattedData = formatAgentPayload(message);
      setMessages(prev => [...prev, { sender: 'agent', data: formattedData }]);
      if (formattedData.type === 'finish') {
        setIsInvestigating(false);
      }
    });

    return () => socket.disconnect();
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!goal.trim() || !isConnected || isInvestigating) return;

    setMessages([{ sender: 'user', text: goal }]);
    setGoal('');

    if (USE_SSE) {
      // Use SSE
      try {
        await sseHook.startExecution(goal.trim());
      } catch (error) {
        setMessages(prev => [...prev, {
          sender: 'agent',
          data: { type: 'error', content: `Failed to start execution: ${error.message}` }
        }]);
      }
    } else {
      // Use WebSocket
      setIsInvestigating(true);
      socketRef.current.emit('start_investigation', { goal });
    }
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
          {USE_SSE && <span className="transport-type"> (SSE)</span>}
          {!USE_SSE && <span className="transport-type"> (WebSocket)</span>}
        </div>
      </header>
      <div className="message-container">
        {messages.map((msg, index) => (
          <div key={index} className={`message ${msg.sender === 'user' ? 'user-message' : 'agent-message'}`}>
            <div className="sender-label">{msg.sender === 'user' ? 'You' : 'Agent'}</div>
            {msg.sender === 'user' ? (
              <div className="user-message-content">{msg.text}</div>
            ) : (
              <AgentMessage message={msg.data} />
            )}
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