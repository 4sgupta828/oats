import React, { useCallback, useMemo, useEffect, useState } from 'react';
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  MarkerType,
} from 'reactflow';
import ELK from 'elkjs/lib/elk.bundled.js';
import 'reactflow/dist/style.css';
import VisualizationControls from './VisualizationControls';
import './styles/TopologyViewer.css';

const elk = new ELK();

// ELK layout options for better spacing and hierarchy
const elkOptions = {
  'elk.algorithm': 'layered',
  'elk.layered.spacing.nodeNodeBetweenLayers': '200', // Increased spacing between layers
  'elk.spacing.nodeNode': '120', // Increased horizontal spacing
  'elk.direction': 'DOWN',
  'elk.edgeRouting': 'SPLINES', // Changed to SPLINES for smoother, less overlapping edges
  'elk.layered.nodePlacement.strategy': 'NETWORK_SIMPLEX',
  'elk.layered.crossingMinimization.strategy': 'LAYER_SWEEP', // Minimize edge crossings
  'elk.layered.spacing.edgeNodeBetweenLayers': '50', // Space between edges and nodes
  'elk.spacing.edgeEdge': '20', // Space between parallel edges
  'elk.spacing.edgeNode': '40', // Space between edges and nodes
  'elk.layered.thoroughness': '10', // More thorough layout computation
  'elk.separateConnectedComponents': 'true' // Keep disconnected components separate
};

const TopologyViewer = ({ spec, vizId }) => {
  const [layoutedNodes, setLayoutedNodes] = useState([]);
  const [layoutedEdges, setLayoutedEdges] = useState([]);

  // Transform spec nodes and edges to ReactFlow format
  const { initialNodes, initialEdges } = useMemo(() => {
    const nodes = spec.data.nodes.map((node) => ({
      id: node.id,
      data: {
        label: (
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontWeight: 'bold', fontSize: '14px', marginBottom: '4px' }}>
              {node.label}
            </div>
            <div style={{ fontSize: '11px', opacity: 0.8 }}>
              {node.type}
            </div>
            {node.status && (
              <div style={{ fontSize: '10px', marginTop: '4px', textTransform: 'uppercase' }}>
                {node.status}
              </div>
            )}
          </div>
        ),
        type: node.type,
        metadata: node.metadata,
        annotation: spec.data.annotations?.[node.id]
      },
      position: { x: 0, y: 0 }, // Will be calculated by ELK
      style: {
        backgroundColor: getNodeColor(node.status),
        border: spec.data.highlights?.includes(node.id) ? '3px solid #ff0000' : '1px solid #888',
        borderRadius: '8px',
        padding: '14px 20px',
        color: '#fff',
        minWidth: '180px',
        minHeight: '100px',
        boxShadow: '0 4px 6px rgba(0, 0, 0, 0.3)'
      },
      type: 'default'
    }));

    const edges = spec.data.edges.map((edge, index) => ({
      id: edge.id || `${edge.source}-${edge.target}-${index}`,
      source: edge.source,
      target: edge.target,
      label: edge.label,
      markerEnd: {
        type: MarkerType.ArrowClosed,
        color: '#888'
      },
      style: { stroke: '#888', strokeWidth: 2 },
      type: 'default', // Using default bezier curves for better edge separation
      labelStyle: { fill: '#fff', fontSize: 11 },
      labelBgStyle: { fill: '#2c2c2c', opacity: 0.9 }
    }));

    return { initialNodes: nodes, initialEdges: edges };
  }, [spec]);

  // Use ELK to calculate layout
  useEffect(() => {
    const getLayoutedElements = async () => {
      const graph = {
        id: 'root',
        layoutOptions: elkOptions,
        children: initialNodes.map(node => ({
          id: node.id,
          width: 180, // Increased width for better spacing
          height: 100  // Increased height for better spacing
        })),
        edges: initialEdges.map(edge => ({
          id: edge.id,
          sources: [edge.source],
          targets: [edge.target]
        }))
      };

      try {
        const layoutedGraph = await elk.layout(graph);

        const layoutedNodes = initialNodes.map(node => {
          const layoutedNode = layoutedGraph.children?.find(n => n.id === node.id);
          return {
            ...node,
            position: {
              x: layoutedNode?.x || 0,
              y: layoutedNode?.y || 0
            }
          };
        });

        setLayoutedNodes(layoutedNodes);
        setLayoutedEdges(initialEdges);
      } catch (error) {
        console.error('Layout error:', error);
        // Fallback to simple grid layout
        setLayoutedNodes(initialNodes.map((node, index) => ({
          ...node,
          position: {
            x: (index % 3) * 350,
            y: Math.floor(index / 3) * 200
          }
        })));
        setLayoutedEdges(initialEdges);
      }
    };

    if (initialNodes.length > 0) {
      getLayoutedElements();
    }
  }, [initialNodes, initialEdges]);

  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);

  // Update nodes and edges when layout is complete
  useEffect(() => {
    if (layoutedNodes.length > 0) {
      setNodes(layoutedNodes);
    }
  }, [layoutedNodes, setNodes]);

  useEffect(() => {
    if (layoutedEdges.length > 0) {
      setEdges(layoutedEdges);
    }
  }, [layoutedEdges, setEdges]);

  const onNodeClick = useCallback((_event, node) => {
    console.log('Node clicked:', node);
    // TODO: Show node details in modal/sidebar
  }, []);

  return (
    <div className="topology-viewer">
      <div className="topology-header">
        <h3>{spec.title}</h3>
        <VisualizationControls vizId={vizId} spec={spec} type="topology" />
      </div>
      <div style={{ height: '800px', backgroundColor: '#1e1e1e' }}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeClick={onNodeClick}
          fitView
          fitViewOptions={{ padding: 0.3, minZoom: 0.4, maxZoom: 1.2 }}
          attributionPosition="bottom-left"
          minZoom={0.1}
          maxZoom={2}
          defaultEdgeOptions={{
            animated: false,
            style: { strokeWidth: 2, stroke: '#888' }
          }}
        >
          <Background color="#555" gap={16} />
          <Controls />
          <MiniMap
            nodeColor={(node) => node.style?.backgroundColor || '#2196f3'}
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
