import React, { useState, useEffect } from 'react';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';
import './ArtifactViewer.css';

const ArtifactViewer = ({ artifacts, backendUrl, executionId }) => {
  // Support both old single artifact and new multiple artifacts format
  const artifactList = artifacts || [];

  if (artifactList.length === 0) {
    return null;
  }

  // Defensive deduplication: Remove duplicate artifacts by path
  const uniqueArtifacts = [];
  const seenPaths = new Set();

  for (const artifact of artifactList) {
    if (!seenPaths.has(artifact.path)) {
      seenPaths.add(artifact.path);
      uniqueArtifacts.push(artifact);
    }
  }

  const dedupedArtifactList = uniqueArtifacts;

  const handleDownloadAll = () => {
    if (dedupedArtifactList.length === 1) {
      // If only one artifact, just download it directly
      handleDownload(dedupedArtifactList[0].path);
    } else {
      // Download as ZIP
      const zipUrl = `${backendUrl}/api/v1/executions/${executionId}/artifacts/download`;
      window.open(zipUrl, '_blank');
    }
  };

  const handleDownload = (artifactPath) => {
    const apiUrl = `${backendUrl}/api/v1/artifacts/${artifactPath}`;
    const filename = artifactPath.split('/').pop();

    fetch(apiUrl)
      .then(response => response.blob())
      .then(blob => {
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
      })
      .catch(err => console.error('Download failed:', err));
  };

  return (
    <div className="artifacts-container">
      <div className="artifacts-header">
        <span className="artifacts-count">
          {dedupedArtifactList.length} Artifact{dedupedArtifactList.length > 1 ? 's' : ''}
        </span>
        {dedupedArtifactList.length > 0 && (
          <button
            className="download-all-button"
            onClick={handleDownloadAll}
            title={dedupedArtifactList.length === 1 ? 'Download artifact' : 'Download all artifacts as ZIP'}
          >
            ⬇ Download {dedupedArtifactList.length > 1 ? 'All' : ''}
          </button>
        )}
      </div>
      <div className="artifacts-list">
        {dedupedArtifactList.map((artifact, index) => (
          <SingleArtifactViewer
            key={`${artifact.path}-${index}`}
            artifact={artifact}
            backendUrl={backendUrl}
            onDownload={() => handleDownload(artifact.path)}
          />
        ))}
      </div>
    </div>
  );
};

const SingleArtifactViewer = ({ artifact, backendUrl, onDownload }) => {
  const [isOpen, setIsOpen] = useState(false);
  const [content, setContent] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const artifactPath = artifact.path;
  const artifactType = artifact.type;

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

      case 'image':
        return (
          <div className="artifact-image">
            <img
              src={`${backendUrl}/api/v1/artifacts/${artifactPath}`}
              alt={artifactPath}
              style={{ maxWidth: '100%', height: 'auto' }}
            />
          </div>
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
      'tsx': 'typescript',
      'jsx': 'javascript',
      'java': 'java',
      'go': 'go',
      'rs': 'rust',
      'cpp': 'cpp',
      'c': 'c',
      'h': 'c',
      'rb': 'ruby',
      'php': 'php',
      'scala': 'scala',
      'kt': 'kotlin',
      'swift': 'swift',
      'cs': 'csharp',
      'sh': 'bash',
      'sql': 'sql'
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
      case 'image': return '🖼️';
      case 'pdf': return '📕';
      case 'archive': return '📦';
      case 'script': return '📜';
      case 'sql': return '🗄️';
      default: return '📎';
    }
  };

  const getArtifactLabel = () => {
    const filename = artifactPath ? artifactPath.split('/').pop() : 'artifact';
    return `${getArtifactIcon()} ${filename}`;
  };

  return (
    <div className="artifact-viewer">
      <div className="artifact-toggle-row">
        <button
          className="artifact-toggle"
          onClick={handleClick}
          title={`Click to ${isOpen ? 'hide' : 'view'} artifact`}
        >
          <span className="artifact-toggle-icon">{isOpen ? '▼' : '▶'}</span>
          <span className="artifact-label">{getArtifactLabel()}</span>
          <span className="artifact-type-badge">{artifactType}</span>
        </button>
        <button
          className="artifact-download-button"
          onClick={(e) => {
            e.stopPropagation();
            onDownload();
          }}
          title="Download artifact"
        >
          ⬇
        </button>
      </div>

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
