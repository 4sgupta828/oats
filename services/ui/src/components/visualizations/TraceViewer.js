import React, { useState } from 'react';
import VisualizationControls from './VisualizationControls';
import './styles/TraceViewer.css';

const TraceViewer = ({ spec, vizId }) => {
  const [selectedSpan, setSelectedSpan] = useState(null);

  // Support both old format (traces array) and new format (spans array with traceId and duration)
  // Also handle snake_case field names from the JSON
  const rawSpans = spec.data.spans || spec.data.traces || [];
  const traceId = spec.data.trace_id || spec.data.traceId || spec.metadata?.trace_id || spec.metadata?.traceId || 'unknown';

  // Calculate total duration from spans
  const calculateDuration = () => {
    if (rawSpans.length === 0) return 0;
    const maxEndTime = Math.max(...rawSpans.map(s => {
      const startTime = s.start_time || s.startTime || 0;
      const duration = s.duration_ms || s.duration || 0;
      // Convert ISO timestamp strings to milliseconds offset if needed
      if (typeof s.start_time === 'string') {
        const rootTime = new Date(rawSpans[0].start_time || rawSpans[0].startTime).getTime();
        const thisTime = new Date(s.start_time || s.startTime).getTime();
        return (thisTime - rootTime) + duration;
      }
      return startTime + duration;
    }));
    return maxEndTime;
  };

  const duration = spec.data.duration || spec.data.total_duration_ms || calculateDuration();

  // Normalize span data to handle both snake_case and camelCase
  const normalizeSpan = (span) => ({
    ...span,
    spanId: span.span_id || span.spanId || span.id,
    parentSpanId: span.parent_span_id || span.parentSpanId || span.parentId,
    startTime: (() => {
      // Handle ISO timestamp strings by calculating offset from root span
      if (typeof span.start_time === 'string' && rawSpans.length > 0) {
        const rootTime = new Date(rawSpans[0].start_time || rawSpans[0].startTime).getTime();
        const thisTime = new Date(span.start_time || span.startTime).getTime();
        return thisTime - rootTime;
      }
      return span.start_time || span.startTime || 0;
    })(),
    duration: span.duration_ms || span.duration || 0,
    isError: span.status === 'error' || span.error === true,
    service: span.service || 'unknown',
    operation: span.operation || 'unknown'
  });

  const spans = rawSpans.map(normalizeSpan);

  // Build span hierarchy
  const buildSpanTree = () => {
    if (!spans || spans.length === 0) return [];

    const spanMap = {};
    spans.forEach(span => {
      spanMap[span.spanId] = { ...span, children: [] };
    });

    const rootSpans = [];
    spans.forEach(span => {
      const spanId = span.spanId;
      const parentId = span.parentSpanId;

      if (parentId && spanMap[parentId]) {
        spanMap[parentId].children.push(spanMap[spanId]);
      } else {
        rootSpans.push(spanMap[spanId]);
      }
    });

    return rootSpans;
  };

  const renderSpan = (span, depth = 0) => {
    const spanId = span.spanId;
    const startPercent = duration > 0 ? (span.startTime / duration) * 100 : 0;
    const widthPercent = duration > 0 ? (span.duration / duration) * 100 : 100;
    const isSelected = selectedSpan?.spanId === spanId;

    return (
      <div key={spanId} className="trace-span-container">
        <div
          className={`trace-span trace-span-depth-${depth} ${span.isError ? 'trace-span-error' : ''} ${isSelected ? 'trace-span-selected' : ''}`}
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
                backgroundColor: span.isError ? '#ff4444' : '#4488ff'
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
            <strong>Start:</strong> +{selectedSpan.startTime}ms
          </div>
          {selectedSpan.isError && (
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
