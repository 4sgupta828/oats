import React, { useState, useEffect } from 'react';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';
import './ArtifactViewer.css';

const ArtifactViewer = ({ artifactPath, artifactType, backendUrl }) => {
  const [isOpen, setIsOpen] = useState(false);
  const [content, setContent] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchArtifact = async () => {
    if (!artifactPath) return;

    setLoading(true);
    setError(null);

    try {
      const response = await fetch(`${backendUrl}/api/v1/artifacts/${artifactPath}`);

      if (!response.ok) {
        throw new Error(`Failed to fetch artifact: ${response.statusText}`);
      }

      const text = await response.text();
      setContent(text);
    } catch (err) {
      setError(err.message);
      console.error('Error fetching artifact:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleClick = () => {
    if (!isOpen && !content) {
      fetchArtifact();
    }
    setIsOpen(!isOpen);
  };

  const renderContent = () => {
    if (loading) {
      return <div className="artifact-loading">Loading artifact...</div>;
    }

    if (error) {
      return <div className="artifact-error">Error: {error}</div>;
    }

    if (!content) {
      return <div className="artifact-empty">No content available</div>;
    }

    // Render based on artifact type
    switch (artifactType) {
      case 'json':
        try {
          const jsonData = JSON.parse(content);
          return (
            <SyntaxHighlighter
              language="json"
              style={vscDarkPlus}
              customStyle={{
                margin: 0,
                padding: '16px',
                fontSize: '0.9rem',
                borderRadius: '4px',
                maxHeight: '600px',
                overflow: 'auto'
              }}
            >
              {JSON.stringify(jsonData, null, 2)}
            </SyntaxHighlighter>
          );
        } catch (e) {
          // Fall back to plain text if JSON parsing fails
          return renderPlainText();
        }

      case 'code':
        const language = detectLanguage(artifactPath);
        return (
          <SyntaxHighlighter
            language={language}
            style={vscDarkPlus}
            customStyle={{
              margin: 0,
              padding: '16px',
              fontSize: '0.9rem',
              borderRadius: '4px',
              maxHeight: '600px',
              overflow: 'auto'
            }}
            showLineNumbers={true}
          >
            {content}
          </SyntaxHighlighter>
        );

      case 'markdown':
        return (
          <div className="artifact-markdown">
            <pre>{content}</pre>
          </div>
        );

      case 'logs':
        return renderLogs();

      case 'metrics':
        return renderMetrics();

      case 'traces':
        return renderTraces();

      case 'yaml':
        return (
          <SyntaxHighlighter
            language="yaml"
            style={vscDarkPlus}
            customStyle={{
              margin: 0,
              padding: '16px',
              fontSize: '0.9rem',
              borderRadius: '4px',
              maxHeight: '600px',
              overflow: 'auto'
            }}
          >
            {content}
          </SyntaxHighlighter>
        );

      case 'table':
        return renderTable();

      default:
        return renderPlainText();
    }
  };

  const renderPlainText = () => (
    <pre className="artifact-text">{content}</pre>
  );

  const renderLogs = () => {
    const lines = content.split('\n');
    return (
      <div className="artifact-logs">
        {lines.map((line, index) => {
          const logLevel = detectLogLevel(line);
          return (
            <div key={index} className={`log-line log-${logLevel}`}>
              {line}
            </div>
          );
        })}
      </div>
    );
  };

  const renderMetrics = () => {
    try {
      const data = JSON.parse(content);
      return (
        <div className="artifact-metrics">
          <table>
            <thead>
              <tr>
                <th>Metric</th>
                <th>Value</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(data).map(([key, value]) => (
                <tr key={key}>
                  <td>{key}</td>
                  <td>{typeof value === 'object' ? JSON.stringify(value) : value}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    } catch (e) {
      return renderPlainText();
    }
  };

  const renderTraces = () => {
    try {
      const data = JSON.parse(content);
      return (
        <div className="artifact-traces">
          <SyntaxHighlighter
            language="json"
            style={vscDarkPlus}
            customStyle={{
              margin: 0,
              padding: '16px',
              fontSize: '0.9rem',
              borderRadius: '4px',
              maxHeight: '600px',
              overflow: 'auto'
            }}
          >
            {JSON.stringify(data, null, 2)}
          </SyntaxHighlighter>
        </div>
      );
    } catch (e) {
      return renderPlainText();
    }
  };

  const renderTable = () => {
    try {
      const lines = content.split('\n');
      const headers = lines[0].split(',');
      const rows = lines.slice(1).map(line => line.split(','));

      return (
        <div className="artifact-table">
          <table>
            <thead>
              <tr>
                {headers.map((header, i) => (
                  <th key={i}>{header.trim()}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => (
                <tr key={i}>
                  {row.map((cell, j) => (
                    <td key={j}>{cell.trim()}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    } catch (e) {
      return renderPlainText();
    }
  };

  const detectLanguage = (filename) => {
    const ext = filename.split('.').pop().toLowerCase();
    const languageMap = {
      'py': 'python',
      'js': 'javascript',
      'ts': 'typescript',
      'java': 'java',
      'go': 'go',
      'rs': 'rust',
      'cpp': 'cpp',
      'c': 'c',
      'rb': 'ruby',
      'php': 'php'
    };
    return languageMap[ext] || 'text';
  };

  const detectLogLevel = (line) => {
    const lowerLine = line.toLowerCase();
    if (lowerLine.includes('error') || lowerLine.includes('err')) return 'error';
    if (lowerLine.includes('warn') || lowerLine.includes('warning')) return 'warning';
    if (lowerLine.includes('info')) return 'info';
    if (lowerLine.includes('debug')) return 'debug';
    return 'default';
  };

  const getArtifactIcon = () => {
    switch (artifactType) {
      case 'json': return '📄';
      case 'code': return '💻';
      case 'logs': return '📋';
      case 'metrics': return '📊';
      case 'traces': return '🔍';
      case 'markdown': return '📝';
      case 'table': return '📊';
      case 'yaml': return '⚙️';
      default: return '📎';
    }
  };

  const getArtifactLabel = () => {
    const filename = artifactPath ? artifactPath.split('/').pop() : 'artifact';
    return `${getArtifactIcon()} ${filename}`;
  };

  return (
    <div className="artifact-viewer">
      <button
        className="artifact-toggle"
        onClick={handleClick}
        title={`Click to ${isOpen ? 'hide' : 'view'} artifact`}
      >
        <span className="artifact-toggle-icon">{isOpen ? '▼' : '▶'}</span>
        <span className="artifact-label">{getArtifactLabel()}</span>
        <span className="artifact-type-badge">{artifactType}</span>
      </button>

      {isOpen && (
        <div className="artifact-panel">
          <div className="artifact-header">
            <span className="artifact-path">{artifactPath}</span>
            <button
              className="artifact-close"
              onClick={() => setIsOpen(false)}
              title="Close"
            >
              ✕
            </button>
          </div>
          <div className="artifact-content">
            {renderContent()}
          </div>
        </div>
      )}
    </div>
  );
};

export default ArtifactViewer;
