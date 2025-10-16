import React from 'react';
import VisualizationControls from './VisualizationControls';
import './styles/TraceViewer.css';

const TraceViewer = ({ spec, vizId }) => {
  const traces = spec.data.traces || [];

  const formatDuration = (microseconds) => {
    if (microseconds < 1000) return `${microseconds}µs`;
    if (microseconds < 1000000) return `${(microseconds / 1000).toFixed(2)}ms`;
    return `${(microseconds / 1000000).toFixed(2)}s`;
  };

  const renderSpan = (span, depth = 0) => {
    const hasChildren = span.children && span.children.length > 0;

    return (
      <div key={span.id} className="trace-span" style={{ marginLeft: `${depth * 20}px` }}>
        <div className={`span-info ${span.error ? 'span-error' : ''}`}>
          <span className="span-service">{span.service}</span>
          <span className="span-operation">{span.operation}</span>
          <span className="span-duration">{formatDuration(span.duration)}</span>
          {span.error && <span className="span-error-badge">ERROR</span>}
        </div>
        {span.tags && (
          <div className="span-tags">
            {Object.entries(span.tags).map(([key, value]) => (
              <span key={key} className="span-tag">
                {key}: {value}
              </span>
            ))}
          </div>
        )}
        {hasChildren && (
          <div className="span-children">
            {span.children.map(child => renderSpan(child, depth + 1))}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="trace-viewer">
      <div className="trace-header">
        <h3>{spec.title}</h3>
        <VisualizationControls vizId={vizId} spec={spec} type="trace" />
      </div>

      <div className="trace-metadata">
        {spec.metadata && (
          <>
            <span>Trace ID: {spec.metadata.traceId}</span>
            <span>Service: {spec.metadata.service}</span>
            <span>Spans: {traces.length}</span>
          </>
        )}
      </div>

      <div className="trace-content">
        {traces.map(trace => renderSpan(trace))}
      </div>
    </div>
  );
};

export default TraceViewer;
