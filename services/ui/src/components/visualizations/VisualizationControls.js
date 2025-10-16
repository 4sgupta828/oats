import React from 'react';
import html2canvas from 'html2canvas';
import { saveAs } from 'file-saver';
import { useVisualizationStore } from '../../store/visualizationStore';

const VisualizationControls = ({ vizId, spec, type }) => {
  const { pinnedVisualizations, pinVisualization, unpinVisualization } = useVisualizationStore();
  const isPinned = pinnedVisualizations.some(v => v.id === vizId);

  const handlePin = () => {
    if (isPinned) {
      unpinVisualization(vizId);
    } else {
      pinVisualization({
        id: vizId,
        spec,
        type,
        timestamp: new Date().toISOString()
      });
    }
  };

  const handleScreenshot = async () => {
    try {
      const element = document.getElementById(vizId);
      if (!element) {
        console.error('Visualization element not found');
        return;
      }

      const canvas = await html2canvas(element, {
        backgroundColor: '#1e1e1e',
        scale: 2
      });

      canvas.toBlob((blob) => {
        if (blob) {
          saveAs(blob, `${spec.title.replace(/\s+/g, '_')}_${Date.now()}.png`);
        }
      });
    } catch (err) {
      console.error('Screenshot failed:', err);
    }
  };

  const handleDownloadData = () => {
    try {
      const dataStr = JSON.stringify(spec.data, null, 2);
      const blob = new Blob([dataStr], { type: 'application/json' });
      saveAs(blob, `${spec.title.replace(/\s+/g, '_')}_${Date.now()}.json`);
    } catch (err) {
      console.error('Download failed:', err);
    }
  };

  return (
    <div className="viz-controls">
      <button
        className={`viz-control-btn ${isPinned ? 'pinned' : ''}`}
        onClick={handlePin}
        title={isPinned ? 'Unpin visualization' : 'Pin visualization'}
      >
        {isPinned ? '📌' : '📍'}
      </button>
      <button
        className="viz-control-btn"
        onClick={handleScreenshot}
        title="Take screenshot"
      >
        📷
      </button>
      <button
        className="viz-control-btn"
        onClick={handleDownloadData}
        title="Download data"
      >
        ⬇️
      </button>
    </div>
  );
};

export default VisualizationControls;
