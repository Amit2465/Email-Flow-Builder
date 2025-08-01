import { create } from 'zustand';
import { FlowNode, FlowEdge, CampaignFlow } from '../types/flow';
import { Node, Edge, addEdge, applyNodeChanges, applyEdgeChanges, Connection } from '@xyflow/react';

interface FlowStore {
  nodes: Node[];
  edges: Edge[];
  selectedNode: string | null;
  isValidFlow: boolean;
  validationErrors: string[];
  
  // Actions
  setNodes: (nodes: Node[]) => void;
  setEdges: (edges: Edge[]) => void;
  addNode: (node: FlowNode) => void;
  updateNode: (nodeId: string, data: any) => void;
  deleteNode: (nodeId: string) => void;
  setSelectedNode: (nodeId: string | null) => void;
  onNodesChange: (changes: any) => void;
  onEdgesChange: (changes: any) => void;
  onConnect: (connection: Connection) => void;
  validateFlow: () => void;
  exportFlow: () => CampaignFlow;
  importFlow: (flow: CampaignFlow) => void;
}

export const useFlowStore = create<FlowStore>((set, get) => ({
  nodes: [
    {
      id: 'start-1',
      type: 'start',
      position: { x: 400, y: 50 },
      data: { label: 'Campaign Start' },
      deletable: false,
    },
  ],
  edges: [],
  selectedNode: null,
  isValidFlow: false,
  validationErrors: [],

  setNodes: (nodes) => set({ nodes }),
  setEdges: (edges) => set({ edges }),

  addNode: (node) => {
    const newNode: Node = {
      id: node.id,
      type: node.type,
      position: node.position,
      data: node.data,
    };
    set((state) => ({ nodes: [...state.nodes, newNode] }));
    get().validateFlow();
  },

  updateNode: (nodeId, data) => {
    set((state) => ({
      nodes: state.nodes.map((node) =>
        node.id === nodeId ? { ...node, data: { ...node.data, ...data } } : node
      ),
    }));
    get().validateFlow();
  },

  deleteNode: (nodeId) => {
    set((state) => ({
      nodes: state.nodes.filter((node) => node.id !== nodeId),
      edges: state.edges.filter((edge) => edge.source !== nodeId && edge.target !== nodeId),
    }));
    get().validateFlow();
  },

  setSelectedNode: (nodeId) => set({ selectedNode: nodeId }),

  onNodesChange: (changes) => {
    set((state) => ({ nodes: applyNodeChanges(changes, state.nodes) }));
    get().validateFlow();
  },

  onEdgesChange: (changes) => {
    set((state) => ({ edges: applyEdgeChanges(changes, state.edges) }));
    get().validateFlow();
  },

  onConnect: (connection) => {
    const edge: Edge = {
      ...connection,
      id: `${connection.source}-${connection.target}`,
      animated: true,
      style: { stroke: '#1D4ED8', strokeWidth: 2 },
    };
    
    set((state) => ({ edges: addEdge(edge, state.edges) }));
    get().validateFlow();
  },

  validateFlow: () => {
    const { nodes, edges } = get();
    const errors: string[] = [];
    let isValid = true;

    // Check for orphaned nodes (except start)
    const connectedNodes = new Set();
    edges.forEach((edge) => {
      connectedNodes.add(edge.source);
      connectedNodes.add(edge.target);
    });

    nodes.forEach((node) => {
      if (node.id !== 'start-1' && !connectedNodes.has(node.id)) {
        errors.push(`Node "${node.data.label}" is not connected`);
        isValid = false;
      }
    });

    // Check for missing configuration
    nodes.forEach((node) => {
      if (node.type === 'sendEmail' && !node.data.config?.templateId) {
        errors.push(`Email node "${node.data.label}" needs a template`);
        isValid = false;
      }
      if (node.type === 'wait' && !node.data.config?.waitDays) {
        errors.push(`Wait node "${node.data.label}" needs a duration`);
        isValid = false;
      }
    });

    set({ isValidFlow: isValid, validationErrors: errors });
  },

  exportFlow: () => {
    const { nodes, edges } = get();
    return {
      nodes: nodes.map((node) => ({
        id: node.id,
        type: node.type as any,
        position: node.position,
        data: node.data,
      })),
      edges: edges.map((edge) => ({
        id: edge.id,
        source: edge.source,
        target: edge.target,
        type: edge.type,
        animated: edge.animated,
        style: edge.style,
        label: edge.label,
      })),
    };
  },

  importFlow: (flow) => {
    const nodes: Node[] = flow.nodes.map((node) => ({
      id: node.id,
      type: node.type,
      position: node.position,
      data: node.data,
    }));
    
    const edges: Edge[] = flow.edges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      type: edge.type || 'default',
      animated: edge.animated || false,
      style: edge.style || {},
      label: edge.label,
    }));

    set({ nodes, edges });
    get().validateFlow();
  },
}));
