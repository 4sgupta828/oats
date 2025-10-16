import React, { useState, useMemo } from 'react';
import { Virtuoso } from 'react-virtuoso';
import VisualizationControls from './VisualizationControls';
import './styles/LogViewer.css';

const LogViewer = ({ spec, vizId }) => {
  const [filters, setFilters] = useState({
    levels: { ERROR: true, WARN: true, INFO: true, DEBUG: true },
    search: '',
    timeRange: null,
    traceId: ''
  });

  const logs = useMemo(() => {
    return spec.data.logs || [];
  }, [spec.data.logs]);

  const filteredLogs = useMemo(() => {
    return logs.filter(log => {
      // Handle different log formats (string vs object)
      const logObj = typeof log === 'string' ? { level: 'INFO', message: log, timestamp: new Date().toISOString() } : log;
      const logLevel = (logObj.level || 'INFO').toUpperCase();

      // Filter by level
      if (!filters.levels[logLevel]) return false;

      // Filter by search
      if (filters.search && !logObj.message.toLowerCase().includes(filters.search.toLowerCase())) {
        return false;
      }

      // Filter by trace ID
      if (filters.traceId && logObj.trace_id !== filters.traceId) {
        return false;
      }

      // Filter by time range
      if (filters.timeRange && logObj.timestamp) {
        const logTime = new Date(logObj.timestamp).getTime();
        if (logTime < filters.timeRange.start || logTime > filters.timeRange.end) {
          return false;
        }
      }

      return true;
    });
  }, [logs, filters]);

  const isHighlighted = (log) => {
    if (!spec.data.highlights?.timeRange || !log.timestamp) return false;
    const logTime = new Date(log.timestamp).getTime();
    const start = new Date(spec.data.highlights.timeRange.start).getTime();
    const end = new Date(spec.data.highlights.timeRange.end).getTime();
    return logTime >= start && logTime <= end;
  };

  const toggleLevel = (level) => {
    setFilters({
      ...filters,
      levels: { ...filters.levels, [level]: !filters.levels[level] }
    });
  };

  const renderLogLine = (index) => {
    const log = filteredLogs[index];
    const logObj = typeof log === 'string' ? { level: 'INFO', message: log, timestamp: new Date().toISOString() } : log;
    const highlighted = isHighlighted(logObj);

    return (
      <div key={index} className={`log-line log-${logObj.level?.toLowerCase() || 'info'} ${highlighted ? 'log-highlighted' : ''}`}>
        {logObj.timestamp && <span className="log-timestamp">{logObj.timestamp}</span>}
        <span className={`log-level log-level-${logObj.level?.toLowerCase() || 'info'}`}>
          {logObj.level || 'INFO'}
        </span>
        {logObj.source && <span className="log-source">{logObj.source}</span>}
        {logObj.trace_id && (
          <span className="log-trace-id" title="Trace ID">
            🔍 {logObj.trace_id}
          </span>
        )}
        <span className="log-message">{logObj.message}</span>
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
        <div className="log-level-filters">
          {Object.keys(filters.levels).map(level => (
            <label key={level} className={`level-filter level-${level.toLowerCase()}`}>
              <input
                type="checkbox"
                checked={filters.levels[level]}
                onChange={() => toggleLevel(level)}
              />
              <span>{level}</span>
              <span className="level-count">
                ({spec.data.summary?.[level.toLowerCase()] || logs.filter(l => {
                  const logObj = typeof l === 'string' ? { level: 'INFO' } : l;
                  return (logObj.level || 'INFO').toUpperCase() === level;
                }).length})
              </span>
            </label>
          ))}
        </div>

        <div className="log-search-container">
          <input
            type="text"
            placeholder="Search logs..."
            value={filters.search}
            onChange={(e) => setFilters({ ...filters, search: e.target.value })}
            className="log-search"
          />
          <input
            type="text"
            placeholder="Filter by Trace ID..."
            value={filters.traceId}
            onChange={(e) => setFilters({ ...filters, traceId: e.target.value })}
            className="log-trace-filter"
          />
        </div>

        <div className="log-stats">
          Showing <strong>{filteredLogs.length}</strong> / {logs.length} logs
        </div>
      </div>

      {spec.data.highlights?.timeRange && (
        <div className="log-highlight-notice">
          Highlighted: {spec.data.highlights.timeRange.reason}
        </div>
      )}

      <div className="log-content" style={{ height: '600px', backgroundColor: '#1e1e1e' }}>
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
