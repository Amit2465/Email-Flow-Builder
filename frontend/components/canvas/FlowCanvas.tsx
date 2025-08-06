import React, { useCallback, useRef } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useReactFlow,
  ReactFlowProvider,
} from '@xyflow/react';
import { v4 as uuidv4 } from 'uuid';
import { ZoomOut } from 'lucide-react';
import { useFlowStore } from '../../store/flowStore';
import { StartNode } from '../nodes/StartNode';
import { SendEmailNode } from '../nodes/SendEmailNode';
import { WaitNode } from '../nodes/WaitNode';
import { ConditionNode } from '../nodes/ConditionNode';

const nodeTypes = {
  start: StartNode,
  sendEmail: SendEmailNode,
  wait: WaitNode,
  condition: ConditionNode,
};

const FlowCanvasInner: React.FC = () => {
  const reactFlowWrapper = useRef<HTMLDivElement>(null);
  const { screenToFlowPosition, zoomOut } = useReactFlow();
  
  const {
    nodes,
    edges,
    onNodesChange,
    onEdgesChange,
    onConnect,
    addNode,
    setSelectedNode,
  } = useFlowStore();

  const onDragOver = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
  }, []);

  const onDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault();

      const type = event.dataTransfer.getData('application/reactflow');
      
      if (typeof type === 'undefined' || !type) {
        return;
      }

      const position = screenToFlowPosition({
        x: event.clientX,
        y: event.clientY,
      });

      const newNode = {
        id: `${type}-${uuidv4()}`,
        type: type as any,
        position,
        data: {
          label: getNodeLabel(type),
          config: getDefaultConfig(type),
        },
      };

      addNode(newNode);
    },
    [screenToFlowPosition, addNode]
  );

  const getNodeLabel = (type: string): string => {
    switch (type) {
      case 'sendEmail':
        return 'Send Email';
      case 'wait':
        return 'Wait';
      case 'condition':
        return 'Condition Check';
      default:
        return type;
    }
  };

  const getDefaultConfig = (type: string): any => {
    switch (type) {
      case 'sendEmail':
        return { templateId: '' };
      case 'wait':
        return { waitDays: 1 };
      case 'condition':
        return { conditionType: 'open' };
      default:
        return {};
    }
  };

  const onNodeClick = useCallback(
    (event: React.MouseEvent, node: any) => {
      setSelectedNode(node.id);
    },
    [setSelectedNode]
  );

  const onPaneClick = useCallback(() => {
    setSelectedNode(null);
  }, [setSelectedNode]);

  return (
    <div className="flex-1 bg-gray-50" ref={reactFlowWrapper}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onDrop={onDrop}
        onDragOver={onDragOver}
        onNodeClick={onNodeClick}
        onPaneClick={onPaneClick}
        nodeTypes={nodeTypes}
        fitView={false}
        defaultViewport={{ x: 0, y: 0, zoom: 0.8 }}
        defaultEdgeOptions={{
          animated: true,
          style: { stroke: '#1D4ED8', strokeWidth: 2 },
        }}
        className="bg-gray-50"
      >
        <Background
          color="#E5E7EB"
          gap={20}
          size={1}
          variant="dots"
        />
        <Controls
          className="bg-white border border-gray-200 rounded-lg shadow-sm"
          showInteractive={false}
        />
        
        {/* Custom Zoom Out Button */}
        <div className="absolute top-4 right-4 z-10">
          <button
            onClick={() => zoomOut({ duration: 300 })}
            className="p-2 bg-white border border-gray-200 rounded-lg shadow-sm hover:bg-gray-50 transition-colors"
            title="Zoom Out"
          >
            <ZoomOut className="w-4 h-4 text-gray-600" />
          </button>
        </div>
        
        <MiniMap
          className="bg-white border border-gray-200 rounded-lg shadow-sm"
          nodeColor="#E5E7EB"
          nodeStrokeWidth={2}
          zoomable
          pannable
        />
      </ReactFlow>
    </div>
  );
};

export const FlowCanvas: React.FC = () => {
  return (
    <ReactFlowProvider>
      <FlowCanvasInner />
    </ReactFlowProvider>
  );
};
