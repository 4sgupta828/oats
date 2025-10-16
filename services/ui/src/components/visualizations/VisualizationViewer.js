import React from 'react';
import TopologyViewer from './TopologyViewer';
import TimeSeriesViewer from './TimeSeriesViewer';
import MermaidViewer from './MermaidViewer';
import LogViewer from './LogViewer';
import TraceViewer from './TraceViewer';
import './styles/VisualizationViewer.css';

const VisualizationViewer = ({ spec, artifactPath }) => {
  const vizId = `viz-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;

  const renderVisualization = () => {
    switch (spec.type) {
      case 'topology':
        return <TopologyViewer spec={spec} vizId={vizId} />;
      case 'timeseries':
        return <TimeSeriesViewer spec={spec} vizId={vizId} />;
      case 'mermaid':
        return <MermaidViewer spec={spec} vizId={vizId} />;
      case 'logs':
        return <LogViewer spec={spec} vizId={vizId} />;
      case 'trace':
        return <TraceViewer spec={spec} vizId={vizId} />;
      default:
        return (
          <div className="viz-error">
            Unknown visualization type: {spec.type}
          </div>
        );
    }
  };

  return (
    <div id={vizId} className="visualization-container">
      {renderVisualization()}
    </div>
  );
};

export default VisualizationViewer;
