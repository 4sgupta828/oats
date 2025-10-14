import React, { useState, useEffect, useRef } from 'react';
import './App.css';
import AgentMessage from './components/AgentMessage';
import { useSSE } from './hooks/useSSE';

// Format SSE events to UI-friendly format
const formatSSEEvent = (event) => {
  const eventData = event.data || {};

  switch (event.type) {
    case 'turn_started':
      return { type: 'status', content: `🔄 Starting turn ${event.turn}...` };

    case 'llm_called':
      return { type: 'status', content: '🤔 AI is reasoning...' };

    case 'llm_response_success':
      const strategize = eventData.strategize || {};
      const reflect = eventData.reflect || {};
      const action = eventData.action || {};

      // Create rich thought content
      let thoughtContent = strategize.reasoning || 'AI completed reasoning';

      // Add reflection insight if available
      if (reflect.insight) {
        thoughtContent += `\n\n💡 Insight: ${reflect.insight}`;
      }

      // Add action preview
      if (action.tool && action.tool !== 'finish') {
        thoughtContent += `\n\n⚡ Next action: ${action.tool}`;
      }

      return {
        type: 'thought',
        content: thoughtContent,
        rawResponse: eventData.raw_response,
        rawResponseTruncated: eventData.raw_response_truncated
      };

    case 'tool_started':
      return {
        type: 'action',
        tool: eventData.tool || eventData.tool_name,
        params: eventData.params || eventData.parameters || eventData.tool_params
      };

    case 'tool_success':
      return {
        type: 'observation',
        content: eventData.observation || 'Tool executed successfully',
        isLarge: eventData.observation_length > 1000,
        isTruncated: eventData.observation_truncated,
        fullLength: eventData.observation_length
      };

    case 'tool_failed':
      return {
        type: 'error',
        content: `❌ Tool '${eventData.tool}' failed:\n${eventData.observation || eventData.error_message || 'Unknown error'}`,
        isTruncated: eventData.observation_truncated,
        fullLength: eventData.observation_length
      };

    case 'execution_completed':
      return {
        type: 'finish',
        summary: eventData.reason || eventData.completion_reason || 'Goal completed',
        turnsCompleted: event.turn
      };

    case 'execution_failed':
      return {
        type: 'error',
        content: `🔴 Execution failed: ${eventData.reason || eventData.error}`
      };

    default:
      return null;
  }
};

function App() {
  const [goal, setGoal] = useState('');
  const [messages, setMessages] = useState([]);
  const messagesEndRef = useRef(null);

  // Get backend URL from environment variable
  const backendUrl = process.env.REACT_APP_BACKEND_URL || 'http://localhost:8000';

  // Use SSE hook
  const sseHook = useSSE(backendUrl);

  // Process SSE events
  useEffect(() => {
    if (!sseHook.events) return;

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

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!goal.trim() || sseHook.isExecuting) return;

    setMessages([{ sender: 'user', text: goal }]);
    setGoal('');

    try {
      await sseHook.startExecution(goal.trim());
    } catch (error) {
      setMessages(prev => [...prev, {
        sender: 'agent',
        data: { type: 'error', content: `Failed to start execution: ${error.message}` }
      }]);
    }
  };

  return (
    <div className="App">
      <header className="App-header">
        <div>
          <h1>OATS Framework</h1>
          <p className="subtitle">Observe · Adapt · TakeAction · Synthesize</p>
        </div>
        <div className={`connection-status ${sseHook.isConnected ? 'connected' : ''}`}>
          {sseHook.isConnected ? '● Connected' : '○ Ready'}
          <span className="transport-type"> (SSE)</span>
          {sseHook.executionId && (
            <span className="execution-id"> | Execution: {sseHook.executionId.slice(0, 8)}...</span>
          )}
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

        {sseHook.isExecuting && messages.length > 0 && messages[messages.length - 1]?.sender === 'agent' && (
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
          placeholder={sseHook.isExecuting ? "Analysis in progress..." : "Describe your infrastructure issue..."}
          disabled={sseHook.isExecuting}
        />
        <button
          type="submit"
          className="submit-button"
          disabled={sseHook.isExecuting}
        >
          {sseHook.isExecuting ? 'Analyzing...' : 'Start Analysis'}
        </button>
        {sseHook.isExecuting && (
          <button
            type="button"
            className="interrupt-button"
            onClick={sseHook.stopExecution}
          >
            Stop
          </button>
        )}
      </form>
    </div>
  );
}

export default App;
