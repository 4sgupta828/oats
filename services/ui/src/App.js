import React, { useState, useEffect, useRef } from 'react';
import './App.css';
import AgentMessage from './components/AgentMessage';
import FeedbackModal from './components/FeedbackModal';
import ResetModal from './components/ResetModal';
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
        fullLength: eventData.observation_length,
        artifactPath: eventData.artifact_path,
        artifactType: eventData.artifact_type
      };

    case 'tool_failed':
      return {
        type: 'error',
        content: `❌ Tool '${eventData.tool}' failed:\n${eventData.observation || eventData.error_message || 'Unknown error'}`,
        isTruncated: eventData.observation_truncated,
        fullLength: eventData.observation_length,
        artifactPath: eventData.artifact_path,
        artifactType: eventData.artifact_type
      };

    case 'execution_paused':
      return {
        type: 'pause',
        summary: eventData.reason || 'Agent paused - awaiting user input',
        turnsCompleted: event.turn
      };

    case 'execution_failed':
      return {
        type: 'error',
        content: `🔴 Execution failed: ${eventData.reason || eventData.error}`
      };

    case 'execution_aborted':
      return {
        type: 'error',
        content: `🛑 Execution aborted: ${eventData.reason || 'User stopped execution'}`
      };

    case 'execution_stopped':
      return {
        type: 'error',
        content: `🛑 Execution stopped: ${eventData.reason || 'User stopped execution'}`
      };

    case 'interrupt_received':
      const interruptType = eventData.type || 'unknown';
      return {
        type: 'status',
        content: `⚠️ Interrupt received (${interruptType})`
      };

    case 'feedback_injected':
      return {
        type: 'status',
        content: `💬 User guidance: ${eventData.message || 'Feedback provided - agent continuing with guidance...'}`
      };

    case 'user_interrupt':
      return {
        type: 'status',
        content: `⏸️ Agent paused - feedback received`
      };

    case 'user_feedback_received':
      const feedbackData = eventData.feedback_data || {};
      return {
        type: 'status',
        content: `💬 Feedback: ${feedbackData.guidance || 'User provided guidance'}`
      };

    case 'user_prompt_requested':
      console.log('[DEBUG] user_prompt_requested event received:', event);
      const formatted = {
        type: 'user_prompt',
        question: eventData.question || 'Please provide input',
        turn: event.turn
      };
      console.log('[DEBUG] Formatted user_prompt message:', formatted);
      return formatted;

    case 'context_summarized':
      return {
        type: 'status',
        content: `📝 Context summarized: ${eventData.turns_summarized || 0} turns condensed, ${eventData.facts_count || 0} facts preserved`
      };

    case 'execution_continued':
      return {
        type: 'status',
        content: `🔄 Investigation continued with refined goal (${eventData.previous_turns || 0} previous turns)`
      };

    default:
      console.log('[DEBUG] Unknown event type:', event.type);
      return null;
  }
};

function App() {
  const [goal, setGoal] = useState('');
  const [messages, setMessages] = useState([]);
  const [isFeedbackModalOpen, setIsFeedbackModalOpen] = useState(false);
  const [isResetModalOpen, setIsResetModalOpen] = useState(false);
  const [resetGoal, setResetGoal] = useState('');
  const [executionPaused, setExecutionPaused] = useState(false);
  const messagesEndRef = useRef(null);

  // Get backend URL from environment variable
  const backendUrl = process.env.REACT_APP_BACKEND_URL || 'http://localhost:8000';

  // Use SSE hook
  const sseHook = useSSE(backendUrl);

  // Process SSE events
  useEffect(() => {
    if (!sseHook.events) return;

    sseHook.events.forEach(event => {
      console.log('[DEBUG] Processing event:', event.type, event);

      // Check if execution is paused
      if (event.type === 'execution_paused') {
        setExecutionPaused(true);
      }

      const formatted = formatSSEEvent(event);
      console.log('[DEBUG] Formatted result:', formatted);
      if (formatted) {
        setMessages(prev => {
          // Avoid duplicates
          const isDuplicate = prev.some(msg =>
            msg.sender === 'agent' &&
            JSON.stringify(msg.data) === JSON.stringify(formatted)
          );
          console.log('[DEBUG] Is duplicate?', isDuplicate);
          if (!isDuplicate) {
            console.log('[DEBUG] Adding message to UI:', formatted);
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

    // If execution is paused, Enter key triggers Continue
    if (executionPaused) {
      handleContinue();
      return;
    }

    // Otherwise, start new execution
    setMessages([{ sender: 'user', text: goal }]);
    setGoal('');
    setExecutionPaused(false);

    try {
      await sseHook.startExecution(goal.trim());
    } catch (error) {
      setMessages(prev => [...prev, {
        sender: 'agent',
        data: { type: 'error', content: `Failed to start execution: ${error.message}` }
      }]);
    }
  };

  const handleContinue = async () => {
    if (!goal.trim()) return;

    setMessages(prev => [...prev, { sender: 'user', text: `▶️ Continue: ${goal}` }]);
    setGoal('');
    setExecutionPaused(false);

    try {
      await sseHook.continueExecution(goal.trim());
    } catch (error) {
      setMessages(prev => [...prev, {
        sender: 'agent',
        data: { type: 'error', content: `Failed to continue execution: ${error.message}` }
      }]);
    }
  };

  const handleResetClick = () => {
    // Open modal to get new goal
    setIsResetModalOpen(true);
    setResetGoal('');
  };

  const handleResetSubmit = async (newGoal) => {
    if (!newGoal.trim()) return;

    try {
      // Clear messages to start fresh
      setMessages([{ sender: 'user', text: `🔄 Reset with new goal: ${newGoal}` }]);
      setGoal('');
      setExecutionPaused(false);

      await sseHook.resetExecution(newGoal.trim());
    } catch (error) {
      setMessages(prev => [...prev, {
        sender: 'agent',
        data: { type: 'error', content: `Failed to reset execution: ${error.message}` }
      }]);
    }
  };

  const handleFeedbackSubmit = async (feedbackText) => {
    try {
      await sseHook.submitFeedback('feedback', feedbackText);
      // Add user feedback message to UI
      setMessages(prev => [...prev, {
        sender: 'user',
        text: `💬 Feedback provided: ${feedbackText}`
      }]);
    } catch (error) {
      throw error; // Let modal handle the error
    }
  };

  const handleUserPromptResponse = async (turnNumber, response) => {
    if (!sseHook.executionId) {
      throw new Error('No active execution');
    }

    try {
      const apiUrl = `${backendUrl}/api/v1/executions/${sseHook.executionId}/feedback`;
      const requestBody = {
        turn_number: turnNumber,
        interrupt_type: 'user_prompt_response',
        message: response
      };

      const res = await fetch(apiUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestBody)
      });

      if (!res.ok) {
        const errorData = await res.json().catch(() => ({ detail: 'Unknown error' }));
        throw new Error(errorData.detail || `HTTP ${res.status}`);
      }

      // Add user response message to UI
      setMessages(prev => [...prev, {
        sender: 'user',
        text: `💬 Response: ${response}`
      }]);
    } catch (error) {
      console.error('Failed to submit user prompt response:', error);
      throw error;
    }
  };

  return (
    <div className="App">
      <header className="App-header">
        <div>
          <h1>OATS Framework</h1>
          <p className="subtitle">Observe · Adapt · TakeAction · Synthesize</p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <div className={`connection-status ${sseHook.isConnected ? 'connected' : ''}`}>
            {sseHook.isConnected ? '● Connected' : '○ Ready'}
            <span className="transport-type"> (SSE)</span>
            {sseHook.executionId && (
              <span className="execution-id"> | Execution: {sseHook.executionId.slice(0, 8)}...</span>
            )}
          </div>
          {sseHook.executionId && (
            <button
              className="reset-button-header"
              onClick={handleResetClick}
              disabled={sseHook.isExecuting}
              title="Start fresh with a new goal"
            >
              🔄 Reset
            </button>
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
              <AgentMessage
                message={msg.data}
                backendUrl={backendUrl}
                onUserPromptResponse={handleUserPromptResponse}
              />
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
          placeholder={
            sseHook.isExecuting
              ? "Analysis in progress..."
              : executionPaused
              ? "Refine goal or add context..."
              : "Describe your infrastructure issue..."
          }
          disabled={sseHook.isExecuting}
        />
        {!sseHook.isExecuting ? (
          <div className="input-controls">
            <button
              type="submit"
              className={executionPaused ? "continue-button" : "submit-button"}
              disabled={sseHook.isExecuting || (executionPaused && !goal.trim())}
              title={executionPaused ? "Continue with refined/additional context (press Enter)" : "Start analysis"}
            >
              {executionPaused ? '▶️ Continue' : 'Start Analysis'}
            </button>
          </div>
        ) : (
          <div className="execution-controls">
            <button
              type="button"
              className="abort-button"
              onClick={sseHook.stopExecution}
              title="Stop the agent immediately"
            >
              🛑 Abort
            </button>
            <button
              type="button"
              className="feedback-button"
              onClick={() => setIsFeedbackModalOpen(true)}
              title="Provide guidance to the agent"
            >
              💬 Provide Feedback
            </button>
          </div>
        )}
      </form>

      <FeedbackModal
        isOpen={isFeedbackModalOpen}
        onClose={() => setIsFeedbackModalOpen(false)}
        onSubmit={handleFeedbackSubmit}
      />

      <ResetModal
        isOpen={isResetModalOpen}
        onClose={() => setIsResetModalOpen(false)}
        onSubmit={handleResetSubmit}
      />
    </div>
  );
}

export default App;
