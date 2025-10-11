import React, { useState } from 'react';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';

const AgentMessage = ({ message }) => {
  const [isExpanded, setIsExpanded] = useState(false);

  const renderThought = () => (
    <div className="agent-section thought-section">
      <div className="section-header">
        <span className="section-icon">🧠</span>
        <span className="section-title">Thought</span>
      </div>
      <div className="section-content">{message.content}</div>
    </div>
  );

  const renderAction = () => (
    <div className="agent-section action-section">
      <div className="section-header">
        <span className="section-icon">▶️</span>
        <span className="section-title">Action</span>
      </div>
      <div className="section-content">
        <div className="action-tool">{message.tool}</div>
        <div className="action-params">
          <SyntaxHighlighter
            language="json"
            style={vscDarkPlus}
            customStyle={{
              margin: 0,
              padding: '8px 12px',
              fontSize: '0.85rem',
              borderRadius: '4px'
            }}
          >
            {JSON.stringify(message.params, null, 2)}
          </SyntaxHighlighter>
        </div>
      </div>
    </div>
  );

  const renderObservation = () => {
    const content = message.content || '';
    const lines = content.split('\n');

    // Show less content initially if it's very large, but don't hide command output
    const shouldTruncate = message.isLarge && !isExpanded && lines.length > 20;
    const displayContent = shouldTruncate
      ? lines.slice(0, 20).join('\n') + '\n\n... (truncated, click "Show More" to see all)'
      : content;

    return (
      <div className="agent-section observation-section">
        <div className="section-header">
          <span className="section-icon">👀</span>
          <span className="section-title">Observation</span>
        </div>
        <div className="section-content">
          <pre className="observation-content">{displayContent}</pre>
          {message.isLarge && lines.length > 20 && (
            <button
              className="expand-button"
              onClick={() => setIsExpanded(!isExpanded)}
            >
              {isExpanded ? '▲ Show Less' : '▼ Show More'}
            </button>
          )}
        </div>
      </div>
    );
  };

  const renderFinish = () => (
    <div className="agent-section finish-section">
      <div className="section-header">
        <span className="section-icon">✅</span>
        <span className="section-title">Analysis Complete</span>
      </div>
      <div className="section-content">
        <div className="finish-summary">
          <div className="finish-label">Summary:</div>
          <div>{message.summary}</div>
        </div>
        {message.turnsCompleted && (
          <div className="finish-stat">
            <span className="stat-icon">📈</span>
            Cycles Completed: {message.turnsCompleted}
          </div>
        )}
        {message.resultsFile && (
          <div className="finish-file">
            <span className="stat-icon">📁</span>
            Full results: <code>{message.resultsFile}</code>
          </div>
        )}
      </div>
    </div>
  );

  const renderStatus = () => (
    <div className="agent-section status-section">
      <div className="section-header">
        <span className="section-icon">ℹ️</span>
        <span className="section-title">Status</span>
      </div>
      <div className="section-content">{message.content}</div>
    </div>
  );

  const renderError = () => (
    <div className="agent-section error-section">
      <div className="section-header">
        <span className="section-icon">🔥</span>
        <span className="section-title">Error</span>
      </div>
      <div className="section-content">{message.content}</div>
    </div>
  );

  const renderUnknown = () => (
    <div className="agent-section unknown-section">
      <div className="section-content">
        <pre>{message.content}</pre>
      </div>
    </div>
  );

  // Route to the appropriate renderer based on message type
  switch (message.type) {
    case 'thought':
      return renderThought();
    case 'action':
      return renderAction();
    case 'observation':
      return renderObservation();
    case 'finish':
      return renderFinish();
    case 'status':
      return renderStatus();
    case 'error':
      return renderError();
    default:
      return renderUnknown();
  }
};

export default AgentMessage;
