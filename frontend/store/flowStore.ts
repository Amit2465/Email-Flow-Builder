import { create } from 'zustand';
import { FlowNode, FlowEdge, CampaignFlow } from '../types/flow';
import { Node, Edge, addEdge, applyNodeChanges, applyEdgeChanges, Connection } from '@xyflow/react';
import { toast } from 'sonner';

// Helper function to check if there's a wait node in the path between two nodes
const checkForWaitNodeInPath = (startNodeId: string, endNodeId: string, nodes: Node[], edges: Edge[]): boolean => {
  const visited = new Set<string>();
  const hasWaitNode = (currentNodeId: string): boolean => {
    if (visited.has(currentNodeId)) return false;
    visited.add(currentNodeId);
    
    const currentNode = nodes.find(n => n.id === currentNodeId);
    if (!currentNode) return false;
    
    if (currentNode.type === 'wait') return true;
    if (currentNodeId === endNodeId) return false;
    
    // Find all edges from this node
    const outgoingEdges = edges.filter(edge => edge.source === currentNodeId);
    return outgoingEdges.some(edge => hasWaitNode(edge.target));
  };
  
  return hasWaitNode(startNodeId);
};





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
    // Multiple condition nodes are now supported

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
    const { nodes } = get();
    
    // Get the source and target nodes
    const sourceNode = nodes.find(node => node.id === connection.source);
    const targetNode = nodes.find(node => node.id === connection.target);
    
    // Prevent connecting two wait nodes together
    if (sourceNode?.type === 'wait' && targetNode?.type === 'wait') {
      toast.error("Cannot connect two wait nodes directly. Instead, use one wait node with increased time duration.");
      return;
    }
    
    // Warn when connecting two email nodes together
    if (sourceNode?.type === 'sendEmail' && targetNode?.type === 'sendEmail') {
      toast.warning("Both emails will be sent instantly. Consider adding a wait node between them for better timing.");
    }
    
    // Check condition node path restrictions
    if (sourceNode?.type === 'condition') {
      const conditionNode = sourceNode;
      const isNoPath = connection.id?.includes('no'); // Check if this is the "No" output
      
      if (isNoPath) {
        // First node in No path must be a wait node
        if (targetNode?.type !== 'wait') {
          toast.error(`The first node in the "No" path of condition node "${conditionNode.data.label}" must be a wait node. This ensures a proper delay before sending follow-up emails.`);
          return;
        }
      }
    }

    // Prevent campaign start from connecting directly to condition node
    if (sourceNode?.type === 'start' && targetNode?.type === 'condition') {
      toast.error("Campaign start cannot connect directly to a condition node. Add an email node between them to establish the flow.");
      return;
    }

    // Check timeout vs path duration when connecting FROM condition node
    if (sourceNode?.type === 'condition') {
      const conditionNode = sourceNode;
      const isNoPath = connection.sourceHandle?.includes('no'); // Check if this is the "No" output
      
      if (isNoPath) {
        // First node in No path must be a wait node
        if (targetNode?.type !== 'wait') {
          toast.error(`The first node in the "No" path of condition node "${conditionNode.data.label}" must be a wait node. This ensures a proper delay before sending follow-up emails.`);
          return;
        }
      }
      

    }

    // Condition nodes should only connect FROM email nodes (to monitor them)
    if (targetNode?.type === 'condition' && sourceNode?.type !== 'sendEmail') {
      toast.error("Condition nodes can only connect FROM email nodes. This ensures the condition can monitor email engagement.");
      return;
    }



    // Check timeout vs path duration when connecting to condition nodes
    if (targetNode?.type === 'condition') {
      const conditionNode = targetNode;
      const timeoutDuration = conditionNode.data.config?.timeoutDuration || 7;
      const timeoutUnit = conditionNode.data.config?.timeoutUnit || 'days';
      
      // Calculate timeout in minutes for comparison
      let timeoutInMinutes = 0;
      if (timeoutUnit === 'minutes') {
        timeoutInMinutes = timeoutDuration;
      } else if (timeoutUnit === 'hours') {
        timeoutInMinutes = timeoutDuration * 60;
      } else if (timeoutUnit === 'days') {
        timeoutInMinutes = timeoutDuration * 24 * 60;
      }
      
      // Check both Yes and No path durations
      const yesPathDuration = calculatePathDuration(conditionNode.id, 'yes', nodes, edges);
      const noPathDuration = calculatePathDuration(conditionNode.id, 'no', nodes, edges);
      
      let invalidPaths = [];
      if (yesPathDuration > timeoutInMinutes) {
        invalidPaths.push('Yes');
      }
      if (noPathDuration > timeoutInMinutes) {
        invalidPaths.push('No');
      }
      
      if (invalidPaths.length > 0) {
        const pathText = invalidPaths.join(' and ');
        const maxDuration = Math.max(yesPathDuration, noPathDuration);
        const durationText = formatDuration(maxDuration);
        
        toast.error(
          `The "${pathText}" path has ${durationText} of wait time, but your condition timeout is only ${timeoutDuration} ${timeoutUnit}. Please reduce the wait time or increase the timeout.`,
          {
            duration: Infinity,
            action: {
              label: "Close",
              onClick: () => toast.dismiss()
            }
          }
        );
        return;
      }
    }
    
    const edge: Edge = {
      ...connection,
      id: `${connection.source}-${connection.target}`,
      animated: true,
      style: { stroke: '#1D4ED8', strokeWidth: 2 },
    };
    
    // Add the edge first
    set((state) => ({ edges: addEdge(edge, state.edges) }));
    
    // Then validate and remove if invalid
    setTimeout(() => {
    get().validateFlow();
    }, 0);
  },

  validateFlow: () => {
    const { nodes, edges } = get();
    const errors: string[] = [];
    let isValid = true;

    // Check for multiple condition nodes (warning only)
    const conditionNodes = nodes.filter((node) => node.type === "condition")
    // Multiple condition nodes are now supported

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
      if (node.type === "condition") {
        if (!node.data.config?.conditionType) {
          errors.push(`Condition node "${node.data.label}" needs an event selected`)
          isValid = false
        }
        if (node.data.config?.conditionType === "click" && (!node.data.config?.linkUrl || node.data.config.linkUrl.trim() === "")) {
          errors.push(`Condition node "${node.data.label}" needs a link URL when "Link Clicked" is selected`)
          isValid = false
        }

      }
    });

    // Check for invalid wait-to-wait connections
    edges.forEach((edge) => {
      const sourceNode = nodes.find(node => node.id === edge.source);
      const targetNode = nodes.find(node => node.id === edge.target);
      
      if (sourceNode?.type === 'wait' && targetNode?.type === 'wait') {
        errors.push(`Cannot connect wait node "${sourceNode.data.label}" directly to wait node "${targetNode.data.label}". Instead, use one wait node with increased time duration.`);
        isValid = false;
      }
      
      // Warn about email-to-email connections
      if (sourceNode?.type === 'sendEmail' && targetNode?.type === 'sendEmail') {
        errors.push(`Email node "${sourceNode.data.label}" connects directly to email node "${targetNode.data.label}". Both emails will be sent instantly. Consider adding a wait node between them.`);
      }
      
      // Check condition node path restrictions
      if (sourceNode?.type === 'condition') {
        const conditionNode = sourceNode;
        const isNoPath = edge.id.includes('no'); // Check if this is the "No" output
        
        if (isNoPath) {
          // First node in No path must be a wait node
          if (targetNode?.type !== 'wait') {
            errors.push(`The first node in the "No" path of condition node "${conditionNode.data.label}" must be a wait node. This ensures a proper delay before sending follow-up emails.`);
            isValid = false;
          }
        }
      }

      // Prevent campaign start from connecting directly to condition node
      if (sourceNode?.type === 'start' && targetNode?.type === 'condition') {
        errors.push(`Campaign start cannot connect directly to condition node "${targetNode.data.label}". Add an email node between them to establish the flow.`);
        isValid = false;
      }

      // Condition nodes should only connect FROM email nodes (to monitor them)
      if (targetNode?.type === 'condition' && sourceNode?.type !== 'sendEmail') {
        errors.push(`Condition node "${targetNode.data.label}" can only connect FROM email nodes. This ensures the condition can monitor email engagement.`);
        isValid = false;
      }
    });

    // Check if all branches end with an end node
    const endNodes = nodes.filter(node => node.type === 'end');
    const nodesWithOutgoingConnections = new Set();
    
    edges.forEach((edge) => {
      nodesWithOutgoingConnections.add(edge.source);
    });

    // Calculate minimum required end nodes based on condition nodes
    let minRequiredEndNodes = 1; // At least one end node for basic flow
    if (conditionNodes.length > 0) {
      // Each condition node creates 2 branches (Yes/No), so we need at least 2 end nodes per condition
      minRequiredEndNodes = conditionNodes.length * 2;
    }

    if (endNodes.length < minRequiredEndNodes) {
      errors.push(`You have ${conditionNodes.length} condition node(s) but only ${endNodes.length} end node(s). You need at least ${minRequiredEndNodes} end nodes to handle all branches.`);
      isValid = false;
    }



    // Find nodes that have outgoing connections but don't connect to an end node
    const nodesWithoutEndConnection = nodes.filter(node => {
      if (node.type === 'end') return false; // Skip end nodes themselves
      if (!nodesWithOutgoingConnections.has(node.id)) return false; // Skip nodes without outgoing connections
      
      // Check if this node's path leads to an end node
      const visited = new Set();
      const hasPathToEnd = (nodeId: string): boolean => {
        if (visited.has(nodeId)) return false;
        visited.add(nodeId);
        
        const currentNode = nodes.find(n => n.id === nodeId);
        if (!currentNode) return false;
        
        if (currentNode.type === 'end') return true;
        
        // Find all edges from this node
        const outgoingEdges = edges.filter(edge => edge.source === nodeId);
        return outgoingEdges.some(edge => hasPathToEnd(edge.target));
      };
      
      return !hasPathToEnd(node.id);
    });

    if (nodesWithoutEndConnection.length > 0) {
      const nodeLabels = nodesWithoutEndConnection.map(node => node.data.label).join(', ');
      errors.push(`The following nodes do not connect to an end node: ${nodeLabels}. All branches must end with an end node.`);
      isValid = false;
    }

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
