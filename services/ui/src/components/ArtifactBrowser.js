import React, { useState, useEffect } from 'react';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';
import VisualizationViewer from './visualizations/VisualizationViewer';
import './ArtifactBrowser.css';

const ArtifactBrowser = ({ isOpen, onClose, backendUrl }) => {
  const [currentPath, setCurrentPath] = useState('');
  const [entries, setEntries] = useState([]);
  const [breadcrumbs, setBreadcrumbs] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [selectedFile, setSelectedFile] = useState(null);
  const [fileContent, setFileContent] = useState(null);
  const [fileLoading, setFileLoading] = useState(false);
  const [fileError, setFileError] = useState(null);

  // Fetch directory contents
  const fetchDirectory = async (path) => {
    setLoading(true);
    setError(null);
    setSelectedFile(null);

    try {
      const encodedPath = path ? encodeURIComponent(path) : '';
      const url = `${backendUrl}/api/v1/browse/${encodedPath}`;
      const response = await fetch(url);

      if (!response.ok) {
        throw new Error(`Failed to browse directory: ${response.statusText}`);
      }

      const data = await response.json();
      setCurrentPath(data.path);
      setEntries(data.entries);
      setBreadcrumbs(data.breadcrumbs);
    } catch (err) {
      setError(err.message);
      console.error('Error browsing directory:', err);
    } finally {
      setLoading(false);
    }
  };

  // Load root directory on mount
  useEffect(() => {
    if (isOpen) {
      fetchDirectory('');
    }
  }, [isOpen]);

  // Handle directory navigation
  const handleNavigate = (path) => {
    fetchDirectory(path);
  };

  // Fetch file content
  const fetchFileContent = async (filePath) => {
    setFileLoading(true);
    setFileError(null);

    try {
      const response = await fetch(`${backendUrl}/api/v1/artifacts/${filePath}`);

      if (!response.ok) {
        throw new Error(`Failed to fetch file: ${response.statusText}`);
      }

      const text = await response.text();
      setFileContent(text);
    } catch (err) {
      setFileError(err.message);
      console.error('Error fetching file:', err);
    } finally {
      setFileLoading(false);
    }
  };

  // Handle file selection
  const handleFileClick = (entry) => {
    if (entry.is_directory) {
      handleNavigate(entry.path);
    } else {
      setSelectedFile(entry);
      setFileContent(null);
      fetchFileContent(entry.path);
    }
  };

  // Handle close
  const handleClose = () => {
    setSelectedFile(null);
    onClose();
  };

  // Get icon for file type
  const getFileIcon = (entry) => {
    if (entry.is_directory) {
      return '📁';
    }

    switch (entry.type) {
      case 'json': return '📄';
      case 'code': return '💻';
      case 'logs': return '📋';
      case 'markdown': return '📝';
      case 'yaml': return '⚙️';
      case 'image': return '🖼️';
      case 'table': return '📊';
      case 'visualization': return '📊';
      default: return '📎';
    }
  };

  // Format file size
  const formatSize = (bytes) => {
    if (!bytes) return '-';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  // Detect language from filename
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
      'sh': 'bash',
      'sql': 'sql',
      'yaml': 'yaml',
      'yml': 'yaml',
      'json': 'json',
      'md': 'markdown',
    };
    return languageMap[ext] || 'text';
  };

  // Render file content based on type
  const renderFileContent = () => {
    if (fileLoading) {
      return <div className="file-content-loading">Loading file...</div>;
    }

    if (fileError) {
      return <div className="file-content-error">Error: {fileError}</div>;
    }

    if (!fileContent) {
      return <div className="file-content-empty">No content</div>;
    }

    const fileType = selectedFile.type;
    const fileName = selectedFile.name;

    // Handle different file types
    switch (fileType) {
      case 'json':
        try {
          const jsonData = JSON.parse(fileContent);

          // Check if it's a visualization spec
          if (jsonData.type && ['topology', 'timeseries', 'mermaid', 'logs', 'trace'].includes(jsonData.type)) {
            return <VisualizationViewer spec={jsonData} artifactPath={selectedFile.path} />;
          }

          // Regular JSON
          return (
            <SyntaxHighlighter
              language="json"
              style={vscDarkPlus}
              customStyle={{
                margin: 0,
                fontSize: '0.9rem',
                borderRadius: '4px',
              }}
            >
              {JSON.stringify(jsonData, null, 2)}
            </SyntaxHighlighter>
          );
        } catch (e) {
          // Fall back to plain text if JSON parsing fails
          return <pre className="file-content-text">{fileContent}</pre>;
        }

      case 'code':
        const language = detectLanguage(fileName);
        return (
          <SyntaxHighlighter
            language={language}
            style={vscDarkPlus}
            customStyle={{
              margin: 0,
              fontSize: '0.9rem',
              borderRadius: '4px',
            }}
            showLineNumbers={true}
          >
            {fileContent}
          </SyntaxHighlighter>
        );

      case 'yaml':
        return (
          <SyntaxHighlighter
            language="yaml"
            style={vscDarkPlus}
            customStyle={{
              margin: 0,
              fontSize: '0.9rem',
              borderRadius: '4px',
            }}
          >
            {fileContent}
          </SyntaxHighlighter>
        );

      case 'markdown':
        return (
          <div className="file-content-markdown">
            <pre>{fileContent}</pre>
          </div>
        );

      case 'logs':
        const lines = fileContent.split('\n');
        return (
          <div className="file-content-logs">
            {lines.map((line, index) => (
              <div key={index} className="log-line">
                {line}
              </div>
            ))}
          </div>
        );

      case 'image':
        return (
          <div className="file-content-image">
            <img
              src={`${backendUrl}/api/v1/artifacts/${selectedFile.path}`}
              alt={fileName}
              style={{ maxWidth: '100%', height: 'auto' }}
            />
          </div>
        );

      case 'table':
        try {
          const csvLines = fileContent.split('\n');
          const headers = csvLines[0].split(',');
          const rows = csvLines.slice(1).map(line => line.split(','));

          return (
            <div className="file-content-table">
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
          return <pre className="file-content-text">{fileContent}</pre>;
        }

      default:
        return <pre className="file-content-text">{fileContent}</pre>;
    }
  };

  // Handle download
  const handleDownload = () => {
    if (!selectedFile) return;

    const apiUrl = `${backendUrl}/api/v1/artifacts/${selectedFile.path}`;
    const filename = selectedFile.name;

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

  if (!isOpen) return null;

  return (
    <div className="artifact-browser-overlay" onClick={handleClose}>
      <div className="artifact-browser-modal" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="artifact-browser-header">
          <h2>📁 Browse Artifacts</h2>
          <button className="artifact-browser-close" onClick={handleClose}>✕</button>
        </div>

        {/* Breadcrumb Navigation */}
        <div className="artifact-browser-breadcrumb">
          {breadcrumbs.map((crumb, index) => (
            <React.Fragment key={index}>
              {index > 0 && <span className="breadcrumb-separator">/</span>}
              <button
                className={`breadcrumb-item ${crumb.path === currentPath ? 'active' : ''}`}
                onClick={() => handleNavigate(crumb.path)}
              >
                {crumb.name}
              </button>
            </React.Fragment>
          ))}
        </div>

        {/* Main Content */}
        <div className="artifact-browser-content">
          {/* Left Panel - Directory Listing */}
          <div className="artifact-browser-listing">
            {loading && <div className="browser-loading">Loading...</div>}

            {error && <div className="browser-error">Error: {error}</div>}

            {!loading && !error && entries.length === 0 && (
              <div className="browser-empty">No files found</div>
            )}

            {!loading && !error && entries.length > 0 && (
              <div className="file-list">
                {entries.map((entry, index) => (
                  <div
                    key={index}
                    className={`file-entry ${selectedFile?.path === entry.path ? 'selected' : ''} ${entry.is_directory ? 'directory' : 'file'}`}
                    onClick={() => handleFileClick(entry)}
                  >
                    <span className="file-icon">{getFileIcon(entry)}</span>
                    <span className="file-name">{entry.name}</span>
                    <span className="file-size">{formatSize(entry.size)}</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Right Panel - File Viewer */}
          {selectedFile && (
            <div className="artifact-browser-viewer">
              <div className="viewer-header">
                <div className="viewer-file-info">
                  <span className="viewer-filename">{selectedFile.name}</span>
                  <span className="viewer-filesize">{formatSize(selectedFile.size)}</span>
                </div>
                <div className="viewer-actions">
                  <button
                    className="viewer-download"
                    onClick={handleDownload}
                    title="Download file"
                  >
                    ⬇ Download
                  </button>
                  <button
                    className="viewer-close"
                    onClick={() => {
                      setSelectedFile(null);
                      setFileContent(null);
                    }}
                    title="Close preview"
                  >
                    ✕
                  </button>
                </div>
              </div>
              <div className="viewer-content">
                {renderFileContent()}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default ArtifactBrowser;
