import React, { useState, useMemo } from 'react';
import { Virtuoso } from 'react-virtuoso';
import VisualizationControls from './VisualizationControls';
import './styles/LogViewer.css';

const LogViewer = ({ spec, vizId }) => {
  const [filterText, setFilterText] = useState('');
  const [logLevel, setLogLevel] = useState('all');

  const logs = useMemo(() => {
    return spec.data.logs || [];
  }, [spec.data.logs]);

  const filteredLogs = useMemo(() => {
    let result = logs;

    // Filter by text
    if (filterText) {
      result = result.filter(log =>
        log.message.toLowerCase().includes(filterText.toLowerCase())
      );
    }

    // Filter by log level
    if (logLevel !== 'all') {
      result = result.filter(log => log.level === logLevel);
    }

    return result;
  }, [logs, filterText, logLevel]);

  const getLogLevelClass = (level) => {
    switch (level?.toLowerCase()) {
      case 'error': return 'log-error';
      case 'warn':
      case 'warning': return 'log-warning';
      case 'info': return 'log-info';
      case 'debug': return 'log-debug';
      default: return 'log-default';
    }
  };

  const renderLogLine = (index) => {
    const log = filteredLogs[index];
    return (
      <div key={index} className={`log-line ${getLogLevelClass(log.level)}`}>
        <span className="log-timestamp">{log.timestamp}</span>
        <span className="log-level">[{log.level}]</span>
        <span className="log-message">{log.message}</span>
      </div>
    );
  };

  return (
    <div className="log-viewer">
      <div className="log-header">
        <h3>{spec.title}</h3>
        <VisualizationControls vizId={vizId} spec={spec} type="logs" />
      </div>

      <div className="log-controls">
        <input
          type="text"
          placeholder="Filter logs..."
          value={filterText}
          onChange={(e) => setFilterText(e.target.value)}
          className="log-filter-input"
        />
        <select
          value={logLevel}
          onChange={(e) => setLogLevel(e.target.value)}
          className="log-level-select"
        >
          <option value="all">All Levels</option>
          <option value="error">Error</option>
          <option value="warning">Warning</option>
          <option value="info">Info</option>
          <option value="debug">Debug</option>
        </select>
        <span className="log-count">
          {filteredLogs.length} / {logs.length} logs
        </span>
      </div>

      <div className="log-content" style={{ height: '500px', backgroundColor: '#1e1e1e' }}>
        <Virtuoso
          style={{ height: '100%' }}
          totalCount={filteredLogs.length}
          itemContent={renderLogLine}
        />
      </div>
    </div>
  );
};

export default LogViewer;
