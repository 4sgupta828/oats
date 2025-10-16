import React, { useEffect, useRef, useState } from 'react';
import mermaid from 'mermaid';
import VisualizationControls from './VisualizationControls';
import './styles/MermaidViewer.css';

const MermaidViewer = ({ spec, vizId }) => {
  const mermaidRef = useRef(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    // Initialize mermaid with dark theme
    mermaid.initialize({
      startOnLoad: false,
      theme: spec.data.theme || 'dark',
      themeVariables: {
        primaryColor: '#4488ff',
        primaryTextColor: '#fff',
        primaryBorderColor: '#666',
        lineColor: '#888',
        secondaryColor: '#2c2c2c',
        tertiaryColor: '#1e1e1e',
        background: '#1e1e1e',
        mainBkg: '#2c2c2c',
        secondBkg: '#1e1e1e',
        textColor: '#fff',
        fontSize: '16px',
      },
      darkMode: true,
      securityLevel: 'strict',
      fontFamily: 'Arial, sans-serif'
    });

    // Render the diagram
    if (mermaidRef.current && spec.data.diagram) {
      try {
        // Clear previous content
        mermaidRef.current.innerHTML = '';

        // Generate unique ID for this diagram
        const diagramId = `mermaid-${vizId}`;

        // Render diagram
        mermaid.render(diagramId, spec.data.diagram).then(({ svg }) => {
          if (mermaidRef.current) {
            mermaidRef.current.innerHTML = svg;
          }
        }).catch(err => {
          console.error('Mermaid rendering error:', err);
          setError(err.message);
        });
      } catch (err) {
        console.error('Mermaid error:', err);
        setError(err.message);
      }
    }
  }, [spec.data.diagram, spec.data.theme, vizId]);

  return (
    <div className="mermaid-viewer">
      <div className="mermaid-header">
        <h3>{spec.title}</h3>
        <VisualizationControls vizId={vizId} spec={spec} type="mermaid" />
      </div>

      {error ? (
        <div className="mermaid-error">
          <strong>Error rendering diagram:</strong>
          <pre>{error}</pre>
          <details>
            <summary>Diagram source:</summary>
            <pre>{spec.data.diagram}</pre>
          </details>
        </div>
      ) : (
        <div
          ref={mermaidRef}
          className="mermaid-content"
          style={{
            backgroundColor: '#1e1e1e',
            padding: '20px',
            borderRadius: '8px',
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'center',
            minHeight: '300px'
          }}
        />
      )}
    </div>
  );
};

export default MermaidViewer;
