import React, { useState, useEffect, useRef, useCallback } from 'react';
import './App.css';
import AgentMessage from './components/AgentMessage';

// Event-driven architecture components
import { useAgentExecution } from './hooks/useAgentExecution';
import { useEventStream } from './hooks/useEventStream';

const formatEventPayload = (event) => {
  try {
    const data = typeof event.data === 'string' ? JSON.parse(event.data) : event.data;
    
    // Map event types to UI-friendly formats
    switch (event.event) {
      case 'turn_started':
        return { 
          type: 'turn_start', 
          content: `Starting turn ${data.turn}`,
          metadata: { turn: data.turn }
        };
      
      case 'llm_called':
        return { 
          type: 'llm_thinking', 
          content: 'AI is reasoning...',
          metadata: { messages_count: data.data.messages_count }
        };
      
      case 'llm_response_success':
        return { 
          type: 'thought', 
          content: data.data.strategize?.reasoning || 'AI reasoning completed',
          metadata: { 
            turn: data.turn,
            reflect: data.data.reflect,
            strategize: data.data.strategize 
          }
        };
      
      case 'llm_response_failed':
        return { 
          type: 'error', 
          content: `LLM response failed: ${data.data.error_message}`,
          metadata: { turn: data.turn, error: data.data.error_message }
        };
      
      case 'tool_started':
        return { 
          type: 'action', 
          content: `Executing ${data.data.tool_name}...`,
          metadata: { 
            tool: data.data.tool_name,
            params: data.data.parameters,
            turn: data.turn
          }
        };
      
      case 'tool_success':
        return { 
          type: 'observation', 
          content: data.data.observation || 'Tool executed successfully',
          metadata: { 
            tool: data.data.tool_name,
            execution_time: data.data.execution_time_ms,
            turn: data.turn,
            isLarge: (data.data.observation || '').length > 1000
          }
        };
      
      case 'tool_failed':
        return { 
          type: 'error', 
          content: `Tool execution failed: ${data.data.error_message}`,
          metadata: { 
            tool: data.data.tool_name,
            error: data.data.error_message,
            turn: data.turn
          }
        };
      
      case 'execution_completed':
        return { 
          type: 'finish', 
          content: data.data.completion_reason || 'Goal completed',
          metadata: { 
            summary: data.data.completion_reason,
            turns_completed: data.data.turns_completed,
            execution_time: data.data.execution_time_ms
          }
        };
      
      case 'execution_failed':
        return { 
          type: 'error', 
          content: `Execution failed: ${data.data.reason || data.data.error}`,
          metadata: { 
            error: data.data.error,
            reason: data.data.reason,
            traceback: data.data.traceback
          }
        };
      
      case 'llm_requests_input':
        return { 
          type: 'input_request', 
          content: `AI needs input: ${data.data.request_message}`,
          metadata: { 
            request: data.data.request_message,
            escalation_type: data.data.escalation_type
          }
        };
      
      case 'llm_requests_approval':
        return { 
          type: 'approval_request', 
          content: `AI requests approval for: ${data.data.action_description}`,
          metadata: { 
            action: data.data.action_description,
            risk_level: data.data.risk_level,
            escalation_type: data.data.escalation_type
          }
        };
      
      case 'user_feedback_received':
        return { 
          type: 'feedback', 
          content: `User provided ${data.data.feedback_type} feedback`,
          metadata: { 
            feedback_type: data.data.feedback_type,
            feedback_data: data.data.feedback_data
          }
        };
      
      case 'user_interrupt':
        return { 
          type: 'interrupt', 
          content: 'Execution interrupted by user',
          metadata: { reason: data.data.reason }
        };
      
      default:
        return { 
          type: 'unknown', 
          content: `Unknown event: ${event.event}`,
          metadata: { raw_event: event }
        };
    }
  } catch (error) {
    return { 
      type: 'error', 
      content: `Failed to parse event: ${error.message}`,
      metadata: { raw_event: event }
    };
  }
};

function AppSSE() {
  const [goal, setGoal] = useState('');
  const [messages, setMessages] = useState([]);
  const [isConnected, setIsConnected] = useState(false);
  const [isInvestigating, setIsInvestigating] = useState(false);
  const [executionId, setExecutionId] = useState(null);
  const [userInput, setUserInput] = useState('');
  const [pendingApproval, setPendingApproval] = useState(null);
  const messagesEndRef = useRef(null);

  // Get backend URL from environment
  const backendUrl = process.env.REACT_APP_BACKEND_URL || 'http://localhost:8000';

  // Use the new event-driven hooks
  const { 
    events, 
    status, 
    isConnected: streamConnected, 
    error: streamError,
    submitFeedback 
  } = useAgentExecution(executionId);

  // Update connection status based on stream
  useEffect(() => {
    setIsConnected(streamConnected);
    if (streamError) {
      console.error('Stream error:', streamError);
    }
  }, [streamConnected, streamError]);

  // Process events and update messages
  useEffect(() => {
    if (events.length === 0) return;

    const latestEvents = events.slice(-10); // Only process recent events to avoid spam
    
    latestEvents.forEach(event => {
      const formattedData = formatEventPayload(event);
      
      // Check if this is a new message (avoid duplicates)
      const isDuplicate = messages.some(msg => 
        msg.sender === 'agent' && 
        msg.data?.type === formattedData.type &&
        JSON.stringify(msg.data?.metadata) === JSON.stringify(formattedData.metadata)
      );

      if (!isDuplicate) {
        setMessages(prev => [...prev, { sender: 'agent', data: formattedData }]);
      }
    });
  }, [events, messages]);

  // Handle execution status changes
  useEffect(() => {
    if (status === 'completed' || status === 'failed') {
      setIsInvestigating(false);
      setPendingApproval(null);
    } else if (status === 'paused') {
      setIsInvestigating(false);
      // Check if we need to show input/approval UI
      const lastEvent = events[events.length - 1];
      if (lastEvent) {
        const formattedData = formatEventPayload(lastEvent);
        if (formattedData.type === 'input_request') {
          // Show input dialog
        } else if (formattedData.type === 'approval_request') {
          setPendingApproval(formattedData.metadata);
        }
      }
    }
  }, [status, events]);

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!goal.trim() || !isConnected || isInvestigating) return;

    try {
      setMessages([{ sender: 'user', text: goal }]);
      setIsInvestigating(true);
      setExecutionId(null); // Reset execution ID

      const response = await fetch(`${backendUrl}/executions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          goal: goal.trim(),
          max_turns: 15,
          user_id: 'web_user'
        })
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const result = await response.json();
      setExecutionId(result.execution_id);
      console.log('Started execution:', result.execution_id);
      
    } catch (error) {
      console.error('Failed to start execution:', error);
      setMessages(prev => [...prev, {
        sender: 'agent',
        data: {
          type: 'error',
          content: `Failed to start execution: ${error.message}`
        }
      }]);
      setIsInvestigating(false);
    }

    setGoal('');
  };

  const handleUserInput = async () => {
    if (!userInput.trim() || !executionId) return;

    try {
      await submitFeedback(1, 'input', { input: userInput.trim() });
      setMessages(prev => [...prev, {
        sender: 'user',
        text: `Input: ${userInput.trim()}`
      }]);
      setUserInput('');
    } catch (error) {
      console.error('Failed to submit input:', error);
    }
  };

  const handleApproval = async (approved) => {
    if (!executionId || !pendingApproval) return;

    try {
      await submitFeedback(1, 'approval', { 
        approved,
        action: pendingApproval.action,
        risk_level: pendingApproval.risk_level
      });
      setMessages(prev => [...prev, {
        sender: 'user',
        text: `Approval: ${approved ? 'Approved' : 'Rejected'} ${pendingApproval.action}`
      }]);
      setPendingApproval(null);
    } catch (error) {
      console.error('Failed to submit approval:', error);
    }
  };

  const handleInterrupt = async () => {
    if (!executionId) return;

    try {
      await submitFeedback(1, 'interrupt', { reason: 'User requested interruption' });
      setMessages(prev => [...prev, {
        sender: 'user',
        text: 'Interrupted execution'
      }]);
      setIsInvestigating(false);
    } catch (error) {
      console.error('Failed to interrupt execution:', error);
    }
  };

  return (
    <div className="App">
      <header className="App-header">
        <div>
          <h1>OATS Framework - Event-Driven</h1>
          <p className="subtitle">Observe · Adapt · TakeAction · Synthesize</p>
        </div>
        <div className={`connection-status ${isConnected ? 'connected' : ''}`}>
          {isConnected ? '● Connected' : '○ Disconnected'}
          {executionId && <span className="execution-id"> | Execution: {executionId.slice(0, 8)}...</span>}
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
        
        {/* User Input Dialog */}
        {status === 'paused' && events.length > 0 && 
         formatEventPayload(events[events.length - 1]).type === 'input_request' && (
          <div className="input-dialog">
            <div className="input-dialog-content">
              <h3>AI Needs Input</h3>
              <p>{formatEventPayload(events[events.length - 1]).metadata.request}</p>
              <div className="input-form">
                <input
                  type="text"
                  value={userInput}
                  onChange={(e) => setUserInput(e.target.value)}
                  placeholder="Provide input..."
                  onKeyPress={(e) => e.key === 'Enter' && handleUserInput()}
                />
                <button onClick={handleUserInput} disabled={!userInput.trim()}>
                  Submit
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Approval Dialog */}
        {pendingApproval && (
          <div className="approval-dialog">
            <div className="approval-dialog-content">
              <h3>AI Requests Approval</h3>
              <p><strong>Action:</strong> {pendingApproval.action}</p>
              <p><strong>Risk Level:</strong> {pendingApproval.risk_level}</p>
              <div className="approval-buttons">
                <button 
                  className="approve-btn" 
                  onClick={() => handleApproval(true)}
                >
                  Approve
                </button>
                <button 
                  className="reject-btn" 
                  onClick={() => handleApproval(false)}
                >
                  Reject
                </button>
              </div>
            </div>
          </div>
        )}

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
        {isInvestigating && (
          <button 
            type="button" 
            className="interrupt-button" 
            onClick={handleInterrupt}
          >
            Interrupt
          </button>
        )}
      </form>
    </div>
  );
}

export default AppSSE;
