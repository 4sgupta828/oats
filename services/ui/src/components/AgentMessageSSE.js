import React, { useState } from 'react';

const AgentMessageSSE = ({ message }) => {
  const [isExpanded, setIsExpanded] = useState(false);

  const formatToolParams = (params) => {
    if (!params || typeof params !== 'object') return '';
    return Object.entries(params)
      .map(([key, value]) => `${key}: ${JSON.stringify(value)}`)
      .join(', ');
  };

  const formatMetadata = (metadata) => {
    if (!metadata) return null;
    
    return (
      <div className="message-metadata">
        {metadata.turn && <span className="turn-info">Turn {metadata.turn}</span>}
        {metadata.execution_time && <span className="execution-time">{metadata.execution_time}ms</span>}
        {metadata.tool && <span className="tool-info">{metadata.tool}</span>}
        {metadata.error && <span className="error-info">Error: {metadata.error}</span>}
      </div>
    );
  };

  const renderMessageContent = () => {
    switch (message.type) {
      case 'turn_start':
        return (
          <div className="turn-start">
            <div className="turn-header">🔄 {message.content}</div>
            {formatMetadata(message.metadata)}
          </div>
        );

      case 'llm_thinking':
        return (
          <div className="llm-thinking">
            <div className="thinking-header">🧠 {message.content}</div>
            {formatMetadata(message.metadata)}
          </div>
        );

      case 'thought':
        return (
          <div className="thought">
            <div className="thought-header">💭 AI Reasoning</div>
            <div className="thought-content">{message.content}</div>
            {formatMetadata(message.metadata)}
            {message.metadata?.strategize && (
              <button 
                className="expand-button"
                onClick={() => setIsExpanded(!isExpanded)}
              >
                {isExpanded ? 'Hide Details' : 'Show Details'}
              </button>
            )}
            {isExpanded && message.metadata?.strategize && (
              <div className="strategy-details">
                <h4>Strategy:</h4>
                <pre>{JSON.stringify(message.metadata.strategize, null, 2)}</pre>
                {message.metadata.reflect && (
                  <>
                    <h4>Reflection:</h4>
                    <pre>{JSON.stringify(message.metadata.reflect, null, 2)}</pre>
                  </>
                )}
              </div>
            )}
          </div>
        );

      case 'action':
        return (
          <div className="action">
            <div className="action-header">⚡ {message.content}</div>
            {message.metadata?.params && (
              <div className="action-params">
                <strong>Parameters:</strong> {formatToolParams(message.metadata.params)}
              </div>
            )}
            {formatMetadata(message.metadata)}
          </div>
        );

      case 'observation':
        return (
          <div className="observation">
            <div className="observation-header">👀 Observation</div>
            <div className={`observation-content ${message.metadata?.isLarge ? 'large-content' : ''}`}>
              {message.content}
            </div>
            {formatMetadata(message.metadata)}
            {message.metadata?.isLarge && (
              <div className="content-warning">
                Large content truncated for display
              </div>
            )}
          </div>
        );

      case 'finish':
        return (
          <div className="finish">
            <div className="finish-header">✅ {message.content}</div>
            {formatMetadata(message.metadata)}
            {message.metadata?.summary && (
              <div className="execution-summary">
                <h4>Execution Summary:</h4>
                <p>{message.metadata.summary}</p>
                {message.metadata.turns_completed && (
                  <p>Turns completed: {message.metadata.turns_completed}</p>
                )}
                {message.metadata.execution_time && (
                  <p>Execution time: {message.metadata.execution_time}ms</p>
                )}
              </div>
            )}
          </div>
        );

      case 'error':
        return (
          <div className="error">
            <div className="error-header">❌ Error</div>
            <div className="error-content">{message.content}</div>
            {formatMetadata(message.metadata)}
            {message.metadata?.traceback && (
              <button 
                className="expand-button"
                onClick={() => setIsExpanded(!isExpanded)}
              >
                {isExpanded ? 'Hide Traceback' : 'Show Traceback'}
              </button>
            )}
            {isExpanded && message.metadata?.traceback && (
              <div className="traceback">
                <pre>{message.metadata.traceback}</pre>
              </div>
            )}
          </div>
        );

      case 'input_request':
        return (
          <div className="input-request">
            <div className="input-header">❓ AI Needs Input</div>
            <div className="input-content">{message.content}</div>
            {formatMetadata(message.metadata)}
          </div>
        );

      case 'approval_request':
        return (
          <div className="approval-request">
            <div className="approval-header">⚠️ AI Requests Approval</div>
            <div className="approval-content">{message.content}</div>
            {formatMetadata(message.metadata)}
          </div>
        );

      case 'feedback':
        return (
          <div className="feedback">
            <div className="feedback-header">📝 User Feedback</div>
            <div className="feedback-content">{message.content}</div>
            {formatMetadata(message.metadata)}
          </div>
        );

      case 'interrupt':
        return (
          <div className="interrupt">
            <div className="interrupt-header">⏸️ Execution Interrupted</div>
            <div className="interrupt-content">{message.content}</div>
            {formatMetadata(message.metadata)}
          </div>
        );

      default:
        return (
          <div className="unknown">
            <div className="unknown-header">❓ Unknown Event</div>
            <div className="unknown-content">{message.content}</div>
            {formatMetadata(message.metadata)}
            <button 
              className="expand-button"
              onClick={() => setIsExpanded(!isExpanded)}
            >
              {isExpanded ? 'Hide Raw Data' : 'Show Raw Data'}
            </button>
            {isExpanded && message.metadata?.raw_event && (
              <div className="raw-event">
                <pre>{JSON.stringify(message.metadata.raw_event, null, 2)}</pre>
              </div>
            )}
          </div>
        );
    }
  };

  return (
    <div className={`agent-message agent-message-${message.type}`}>
      {renderMessageContent()}
    </div>
  );
};

export default AgentMessageSSE;
