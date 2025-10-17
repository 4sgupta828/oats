import React, { useEffect, useRef, useState } from 'react';
import mermaid from 'mermaid';
import VisualizationControls from './VisualizationControls';
import './styles/MermaidViewer.css';

// Initialize mermaid once outside the component
let mermaidInitialized = false;

const MermaidViewer = ({ spec, vizId }) => {
  const [error, setError] = useState(null);
  const [svgContent, setSvgContent] = useState('');
  const [isRendering, setIsRendering] = useState(true);

  useEffect(() => {
    // Initialize mermaid only once
    if (!mermaidInitialized) {
      mermaid.initialize({
        startOnLoad: false,
        theme: 'dark',
        themeVariables: {
          primaryColor: '#4488ff',
          primaryTextColor: '#fff',
          primaryBorderColor: '#666',
          lineColor: '#888',
          secondaryColor: '#2c2c2c',
          tertiaryColor: '#1e1e1e',
        },
        darkMode: true,
        securityLevel: 'loose', // Changed from 'strict' to 'loose' for better compatibility
        fontFamily: 'Arial, sans-serif',
        logLevel: 'error',
        // Configuration for specific diagram types
        flowchart: {
          useMaxWidth: true,
          htmlLabels: true,
          curve: 'basis'
        },
        sequence: {
          useMaxWidth: true,
          wrap: true,
          width: 150
        },
        gantt: {
          useMaxWidth: true,
          leftPadding: 75,
          gridLineStartPadding: 10,
          fontSize: 12,
          sectionFontSize: 14,
          numberSectionStyles: 4
        }
      });
      mermaidInitialized = true;
    }

    // Render the diagram
    const renderDiagram = async () => {
      if (!spec.data.diagram) {
        return;
      }

      try {
        setError(null);
        setIsRendering(true);
        setSvgContent('');

        // Generate unique ID for this diagram
        const diagramId = `mermaid-${vizId}-${Date.now()}`;

        // Clean the diagram text (remove leading/trailing whitespace)
        let cleanDiagram = spec.data.diagram.trim();

        // Fix: State diagrams don't support HTML in transition labels or complex multi-line labels
        if (cleanDiagram.startsWith('stateDiagram')) {
          // For state diagrams, simplify transition labels by removing everything after first <br/>
          // This handles multiple <br/> tags on the same line
          cleanDiagram = cleanDiagram.replace(/: ([^:<\n]+)<br\/>.*$/gm, ': $1');
          // Also remove any remaining <br/> tags just in case
          cleanDiagram = cleanDiagram.replace(/<br\/>/g, '');
        }

        // Render diagram to get SVG string
        const { svg } = await mermaid.render(diagramId, cleanDiagram);

        // Set the SVG content via state - React will handle it safely
        setSvgContent(svg);
        setIsRendering(false);
      } catch (err) {
        console.error('Mermaid rendering error:', err);
        setError(err.message || err.toString());
        setIsRendering(false);
      }
    };

    renderDiagram();
  }, [spec.data.diagram, vizId]);

  return (
    <div className="mermaid-viewer">
      <div className="mermaid-header">
        <h3>{spec.title}</h3>
        <VisualizationControls vizId={vizId} spec={spec} type="mermaid" />
      </div>

      {error ? (
        <div className="mermaid-error">
          <strong>Error rendering diagram:</strong>
          <pre style={{ color: '#ff6b6b', marginTop: '10px' }}>{error}</pre>
          <details style={{ marginTop: '15px' }}>
            <summary style={{ cursor: 'pointer', color: '#4488ff' }}>
              Show diagram source
            </summary>
            <pre style={{
              marginTop: '10px',
              padding: '12px',
              backgroundColor: '#2c2c2c',
              borderRadius: '4px',
              overflow: 'auto',
              fontSize: '12px'
            }}>
              {spec.data.diagram}
            </pre>
          </details>
        </div>
      ) : (
        <div
          className="mermaid-content"
          style={{
            backgroundColor: '#1e1e1e',
            padding: '20px',
            borderRadius: '8px',
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'center',
            minHeight: '300px',
            position: 'relative'
          }}
        >
          {isRendering ? (
            <div style={{ color: '#888', fontSize: '14px' }}>
              Rendering diagram...
            </div>
          ) : (
            <div dangerouslySetInnerHTML={{ __html: svgContent }} />
          )}
        </div>
      )}
    </div>
  );
};

export default MermaidViewer;
