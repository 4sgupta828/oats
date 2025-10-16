import React, { useCallback, useMemo } from 'react';
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  MarkerType,
} from 'reactflow';
import 'reactflow/dist/style.css';
import VisualizationControls from './VisualizationControls';
import './styles/TopologyViewer.css';

const TopologyViewer = ({ spec, vizId }) => {
  // Transform spec nodes to ReactFlow format
  const initialNodes = useMemo(() => {
    return spec.data.nodes.map(node => ({
      id: node.id,
      data: {
        label: node.label,
        type: node.type,
        metadata: node.metadata,
        annotation: spec.data.annotations?.[node.id]
      },
      position: node.position,
      style: {
        backgroundColor: getNodeColor(node.status),
        border: spec.data.highlights?.includes(node.id) ? '3px solid #ff0000' : '1px solid #888',
        borderRadius: '8px',
        padding: '10px',
        color: '#fff'
      },
      type: 'default'
    }));
  }, [spec]);

  const initialEdges = useMemo(() => {
    return spec.data.edges.map(edge => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      label: edge.label,
      markerEnd: {
        type: MarkerType.ArrowClosed,
      },
      style: { stroke: '#888' },
      type: 'smoothstep'
    }));
  }, [spec]);

  const [nodes, , onNodesChange] = useNodesState(initialNodes);
  const [edges, , onEdgesChange] = useEdgesState(initialEdges);

  const onNodeClick = useCallback((event, node) => {
    console.log('Node clicked:', node);
    // TODO: Show node details in modal/sidebar
  }, []);

  return (
    <div className="topology-viewer">
      <div className="topology-header">
        <h3>{spec.title}</h3>
        <VisualizationControls vizId={vizId} spec={spec} type="topology" />
      </div>
      <div style={{ height: '600px', backgroundColor: '#1e1e1e' }}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeClick={onNodeClick}
          fitView
          attributionPosition="bottom-left"
        >
          <Background color="#555" gap={16} />
          <Controls />
          <MiniMap
            nodeColor={(node) => node.style.backgroundColor}
            maskColor="rgba(0, 0, 0, 0.6)"
          />
        </ReactFlow>
      </div>
    </div>
  );
};

function getNodeColor(status) {
  switch (status) {
    case 'healthy': return '#4caf50';
    case 'degraded': return '#ff9800';
    case 'unhealthy': return '#f44336';
    default: return '#2196f3';
  }
}

export default TopologyViewer;
