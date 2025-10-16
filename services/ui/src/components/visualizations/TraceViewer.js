import React, { useState } from 'react';
import VisualizationControls from './VisualizationControls';
import './styles/TraceViewer.css';

const TraceViewer = ({ spec, vizId }) => {
  const [selectedSpan, setSelectedSpan] = useState(null);

  // Support both old format (traces array) and new format (spans array with traceId and duration)
  const { spans, traceId, duration } = spec.data.spans ? spec.data : {
    spans: spec.data.traces || [],
    traceId: spec.metadata?.traceId || 'unknown',
    duration: Math.max(...(spec.data.traces || []).map(t => (t.startTime || 0) + (t.duration || 0)))
  };

  // Build span hierarchy
  const buildSpanTree = () => {
    if (!spans || spans.length === 0) return [];

    const spanMap = {};
    spans.forEach(span => {
      spanMap[span.spanId || span.id] = { ...span, children: [] };
    });

    const rootSpans = [];
    spans.forEach(span => {
      const spanId = span.spanId || span.id;
      const parentId = span.parentId;

      if (parentId && spanMap[parentId]) {
        spanMap[parentId].children.push(spanMap[spanId]);
      } else {
        rootSpans.push(spanMap[spanId]);
      }
    });

    return rootSpans;
  };

  const renderSpan = (span, depth = 0) => {
    const spanId = span.spanId || span.id;
    const startPercent = duration > 0 ? ((span.startTime || 0) / duration) * 100 : 0;
    const widthPercent = duration > 0 ? ((span.duration || 0) / duration) * 100 : 100;
    const isSelected = selectedSpan?.spanId === spanId || selectedSpan?.id === spanId;

    return (
      <div key={spanId} className="trace-span-container">
        <div
          className={`trace-span trace-span-depth-${depth} ${span.error ? 'trace-span-error' : ''} ${isSelected ? 'trace-span-selected' : ''}`}
          onClick={() => setSelectedSpan(span)}
        >
          <div className="trace-span-label" style={{ paddingLeft: `${depth * 20}px`, width: '30%' }}>
            <span className="trace-span-service">{span.service}</span>
            <span className="trace-span-operation">{span.operation}</span>
            <span className="trace-span-duration">{span.duration}ms</span>
          </div>
          <div className="trace-span-timeline" style={{ width: '70%' }}>
            <div
              className="trace-span-bar"
              style={{
                left: `${startPercent}%`,
                width: `${widthPercent}%`,
                backgroundColor: span.error ? '#ff4444' : '#4488ff'
              }}
              title={`${span.service}: ${span.operation} (${span.duration}ms)`}
            />
          </div>
        </div>
        {span.children && span.children.map(child => renderSpan(child, depth + 1))}
      </div>
    );
  };

  const spanTree = buildSpanTree();

  return (
    <div className="trace-viewer">
      <div className="trace-header">
        <div>
          <h3>{spec.title}</h3>
          <div className="trace-info">
            <span>Trace ID: <code>{traceId}</code></span>
            <span>Total Duration: <strong>{duration}ms</strong></span>
            <span>Spans: {spans?.length || 0}</span>
          </div>
        </div>
        <VisualizationControls vizId={vizId} spec={spec} type="trace" />
      </div>

      <div className="trace-content">
        <div className="trace-timeline-header">
          <div className="trace-timeline-labels" style={{ width: '30%' }}>
            Service / Operation
          </div>
          <div className="trace-timeline-scale" style={{ width: '70%' }}>
            <div className="trace-timeline-ticks">
              {[0, 25, 50, 75, 100].map(pct => (
                <span key={pct} style={{ left: `${pct}%` }}>
                  {Math.round(duration * pct / 100)}ms
                </span>
              ))}
            </div>
          </div>
        </div>

        <div className="trace-spans">
          {spanTree.length > 0 ? spanTree.map(span => renderSpan(span)) : (
            <div className="trace-empty">No trace data available</div>
          )}
        </div>
      </div>

      {selectedSpan && (
        <div className="trace-span-details">
          <h4>Span Details</h4>
          <button
            className="close-button"
            onClick={() => setSelectedSpan(null)}
          >
            ✕
          </button>
          <div className="span-detail-row">
            <strong>Service:</strong> {selectedSpan.service}
          </div>
          <div className="span-detail-row">
            <strong>Operation:</strong> {selectedSpan.operation}
          </div>
          <div className="span-detail-row">
            <strong>Duration:</strong> {selectedSpan.duration}ms
          </div>
          <div className="span-detail-row">
            <strong>Start:</strong> +{selectedSpan.startTime || 0}ms
          </div>
          {selectedSpan.error && (
            <div className="span-detail-row error">
              <strong>Error:</strong> Yes
            </div>
          )}
          {selectedSpan.tags && (
            <div className="span-detail-tags">
              <strong>Tags:</strong>
              <pre>{JSON.stringify(selectedSpan.tags, null, 2)}</pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default TraceViewer;
