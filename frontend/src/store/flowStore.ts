import { create } from "zustand"
import type { FlowNode, CampaignFlow } from "../types/flow"
import { type Node, type Edge, addEdge, applyNodeChanges, applyEdgeChanges, type Connection } from "@xyflow/react"
import { toast } from "sonner"

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
  nodes: Node[]
  edges: Edge[]
  selectedNode: string | null
  selectedEdge: string | null
  isValidFlow: boolean
  validationErrors: string[]
  contactFile: File | null

  // Actions
  setNodes: (nodes: Node[]) => void
  setEdges: (edges: Edge[]) => void
  addNode: (node: FlowNode) => void
  updateNode: (nodeId: string, data: any) => void
  deleteNode: (nodeId: string) => void
  deleteEdge: (edgeId: string) => void
  setSelectedNode: (nodeId: string | null) => void
  setSelectedEdge: (edgeId: string | null) => void
  onNodesChange: (changes: any) => void
  onEdgesChange: (changes: any) => void
  onConnect: (connection: Connection) => void
  validateFlow: () => void
  exportFlow: () => CampaignFlow
  importFlow: (flow: CampaignFlow) => void
  resetFlow: () => void
  setContactFile: (file: File | null) => void
  
  // Campaign save API
  saveCampaign: () => Promise<any>
}

export const useFlowStore = create<FlowStore>((set, get) => ({
  nodes: [
    {
      id: "start-1",
      type: "start",
      position: { x: 400, y: 50 },
      data: { label: "Campaign Start", config: {} },
      deletable: false,
    },
  ],
  edges: [],
  selectedNode: null,
  selectedEdge: null,
  isValidFlow: false,
  validationErrors: [],
  contactFile: null,

  setNodes: (nodes) => set({ nodes }),
  setEdges: (edges) => set({ edges }),

  addNode: (node) => {
    // Multiple condition nodes are now supported

    const newNode: Node = {
      id: node.id,
      type: node.type,
      position: node.position,
      data: node.data,
    }
    set((state) => ({ nodes: [...state.nodes, newNode] }))
    

    
    get().validateFlow()
  },

  updateNode: (nodeId, data) => {
    set((state) => ({
      nodes: state.nodes.map((node) => (node.id === nodeId ? { ...node, data: { ...node.data, ...data } } : node)),
    }))
    

  },

  deleteNode: (nodeId) => {
    set((state) => ({
      nodes: state.nodes.filter((node) => node.id !== nodeId),
      edges: state.edges.filter((edge) => edge.source !== nodeId && edge.target !== nodeId),
      selectedNode: state.selectedNode === nodeId ? null : state.selectedNode,
    }))
    get().validateFlow()
  },

  deleteEdge: (edgeId) => {
    set((state) => ({
      edges: state.edges.filter((edge) => edge.id !== edgeId),
      selectedEdge: state.selectedEdge === edgeId ? null : state.selectedEdge,
    }))
    get().validateFlow()
  },

  setSelectedNode: (nodeId) => set({ selectedNode: nodeId, selectedEdge: null }),
  setSelectedEdge: (edgeId) => set({ selectedEdge: edgeId, selectedNode: null }),

  onNodesChange: (changes) => {
    set((state) => ({ nodes: applyNodeChanges(changes, state.nodes) }))
    get().validateFlow()
  },

  onEdgesChange: (changes) => {
    set((state) => ({ edges: applyEdgeChanges(changes, state.edges) }))
    get().validateFlow()
  },

  onConnect: (connection) => {
    const { edges, nodes } = get()

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
      const isNoPath = connection.sourceHandle?.includes('no'); // Check if this is the "No" output
      
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

    // Condition nodes should only connect FROM email nodes (to monitor them)
    if (targetNode?.type === 'condition' && sourceNode?.type !== 'sendEmail') {
      toast.error("Condition nodes can only connect FROM email nodes. This ensures the condition can monitor email engagement.");
      return;
    }



    // For condition nodes, allow multiple connections (yes/no)
    // For other nodes, maintain linear flow
    if (!connection.sourceHandle || connection.sourceHandle === "default") {
      // Check if source already has a connection (linear flow for non-condition nodes)
      const existingEdge = edges.find((edge) => edge.source === connection.source)
      if (existingEdge) {
        // Remove existing connection to maintain linear flow
        set((state) => ({
          edges: state.edges.filter((edge) => edge.source !== connection.source),
        }))
      }
    } else {
      // For condition nodes with specific handles (yes/no), check if that specific handle already has a connection
      const existingEdge = edges.find(
        (edge) => edge.source === connection.source && edge.sourceHandle === connection.sourceHandle,
      )
      if (existingEdge) {
        // Remove existing connection for this specific handle
        set((state) => ({
          edges: state.edges.filter(
            (edge) => !(edge.source === connection.source && edge.sourceHandle === connection.sourceHandle),
          ),
        }))
      }
    }

    const edge: Edge = {
      ...connection,
      id: `${connection.source}-${connection.sourceHandle || "default"}-${connection.target}`,
      animated: true,
      style: { stroke: "#1D4ED8", strokeWidth: 2 },
    }

    // Add the edge first
    set((state) => ({ edges: addEdge(edge, state.edges) }))
    
    // Then validate and remove if invalid immediately
    setTimeout(() => {
    get().validateFlow()
    }, 10) // Small delay to ensure state is updated
  },

  validateFlow: () => {
    const { nodes, edges, contactFile } = get()
    const errors: string[] = []
    let isValid = true
    


    // Check if contact file is uploaded
    if (!contactFile) {
      errors.push("Contact file must be uploaded to start the campaign")
      isValid = false
    }

    // Check for multiple condition nodes (warning only)
    const conditionNodes = nodes.filter(node => node.type === 'condition');
    // Multiple condition nodes are now supported

    // Check for orphaned nodes (except start)
    const connectedNodes = new Set()
    edges.forEach((edge) => {
      connectedNodes.add(edge.source)
      connectedNodes.add(edge.target)
    })

    nodes.forEach((node) => {
      if (node.id !== "start-1" && !connectedNodes.has(node.id)) {
        errors.push(`Node "${node.data.label}" is not connected`)
        isValid = false
      }
    })

    // Check for missing configuration
    nodes.forEach((node) => {
      if (node.type === "sendEmail") {
        console.log(`[VALIDATION] Checking email node: ${node.id}`, {
          hasSubject: !!node.data.config?.subject,
          hasBody: !!node.data.config?.body,
          linksCount: node.data.config?.links?.length || 0
        })
        
        if (!node.data.config?.subject || node.data.config.subject.trim() === "") {
          console.warn(`[VALIDATION] Email node "${node.data.label}" missing subject`)
          errors.push(`Email node "${node.data.label}" needs a subject`)
          isValid = false
        }
        if (!node.data.config?.body || node.data.config.body.trim() === "") {
          console.warn(`[VALIDATION] Email node "${node.data.label}" missing body`)
          errors.push(`Email node "${node.data.label}" needs a body`)
          isValid = false
        }
        
        // Log link validation
        const links = node.data.config?.links || []
        const validLinks = links.filter((link: any) => 
          link.text && link.text.trim() !== "" && 
          link.url && link.url.trim() !== ""
        )
        console.log(`[VALIDATION] Email node "${node.data.label}" links:`, {
          total: links.length,
          valid: validLinks.length,
          invalid: links.length - validLinks.length
        })
      }
      if (node.type === "wait") {
        if (!node.data.config?.waitDuration || node.data.config.waitDuration <= 0) {
          errors.push(`Wait node "${node.data.label}" needs a valid duration`)
          isValid = false
        }
        if (!node.data.config?.waitUnit) {
          errors.push(`Wait node "${node.data.label}" needs a time unit selected`)
          isValid = false
        }
      }
      if (node.type === "condition") {
        if (!node.data.config?.conditionType) {
          errors.push(`Condition node "${node.data.label}" needs an event selected`)
          isValid = false
        }
        // Removed targetLink validation since we now use automatic link detection
      }
    })

    // Check that email nodes have links when followed by "Link Clicked" condition nodes
    nodes.forEach((node) => {
      if (node.type === "sendEmail") {
        console.log(`[LINK_VALIDATION] Checking email node: ${node.id} for link requirements`)
        
        // Find all condition nodes that come after this email node
        const outgoingEdges = edges.filter(edge => edge.source === node.id)
        const linkClickConditions = outgoingEdges.filter(edge => {
          const targetNode = nodes.find(n => n.id === edge.target)
          return targetNode?.type === "condition" && 
                 targetNode.data.config?.conditionType === "click"
        })
        
        console.log(`[LINK_VALIDATION] Email node "${node.data.label}" outgoing edges:`, {
          total: outgoingEdges.length,
          linkClickConditions: linkClickConditions.length,
          conditionNodes: linkClickConditions.map(edge => {
            const targetNode = nodes.find(n => n.id === edge.target)
            return targetNode?.data.label
          })
        })

        if (linkClickConditions.length > 0) {
          const emailLinks = node.data.config?.links || []
          const validLinks = emailLinks.filter((link: any) => 
            link.text && link.text.trim() !== "" && 
            link.url && link.url.trim() !== ""
          )
          
          console.log(`[LINK_VALIDATION] Email node "${node.data.label}" link analysis:`, {
            totalLinks: emailLinks.length,
            validLinks: validLinks.length,
            needsLinks: linkClickConditions.length > 0,
            hasValidLinks: validLinks.length > 0
          })

          if (validLinks.length === 0) {
            console.error(`[LINK_VALIDATION] Email node "${node.data.label}" missing links for click tracking`)
            errors.push(`Email node "${node.data.label}" needs at least one link since it's followed by a "Link Clicked" condition node`)
            isValid = false
          }
        }
      }
    })

    // Check for invalid connections
    edges.forEach((edge) => {
      const sourceNode = nodes.find(node => node.id === edge.source);
      const targetNode = nodes.find(node => node.id === edge.target);
      
      console.log(`[CONNECTION_VALIDATION] Checking edge: ${sourceNode?.type} -> ${targetNode?.type} (${edge.label || 'default'})`)
      
      if (sourceNode?.type === 'wait' && targetNode?.type === 'wait') {
        console.error(`[CONNECTION_VALIDATION] Invalid: Wait -> Wait`)
        errors.push(`Cannot connect wait node "${sourceNode.data.label}" directly to wait node "${targetNode.data.label}". Instead, use one wait node with increased time duration.`);
        isValid = false;
      }
      
      // Warn about email-to-email connections
      if (sourceNode?.type === 'sendEmail' && targetNode?.type === 'sendEmail') {
        console.warn(`[CONNECTION_VALIDATION] Warning: Email -> Email`)
        errors.push(`Email node "${sourceNode.data.label}" connects directly to email node "${targetNode.data.label}". Both emails will be sent instantly. Consider adding a wait node between them.`);
      }
      
      // Check condition node path restrictions
      if (sourceNode?.type === 'condition') {
        const conditionNode = sourceNode;
        const isNoPath = edge.label === 'no'; // Check if this is the "No" output
        
        console.log(`[CONNECTION_VALIDATION] Condition node "${conditionNode.data.label}" ${isNoPath ? 'No' : 'Yes'} path -> ${targetNode?.type}`)
        
        if (isNoPath) {
          // First node in No path must be a wait node
          if (targetNode?.type !== 'wait') {
            console.error(`[CONNECTION_VALIDATION] Invalid "No" path: Condition -> ${targetNode?.type}`)
            errors.push(`The "No" path from condition node "${conditionNode.data.label}" must start with a wait node. Currently connected to ${targetNode?.type} node "${targetNode.data.label}".`);
            isValid = false;
          }
        }
      }

      // Prevent campaign start from connecting directly to condition node
      if (sourceNode?.type === 'start' && targetNode?.type === 'condition') {
        console.error(`[CONNECTION_VALIDATION] Invalid: Start -> Condition`)
        errors.push(`Campaign start cannot connect directly to condition node "${targetNode.data.label}". Add an email node between them to establish the flow.`);
        isValid = false;
      }

      // Condition nodes should only connect FROM email nodes or other condition nodes
      if (targetNode?.type === 'condition') {
        const validSourceTypes = ['sendEmail', 'condition'];
        if (!validSourceTypes.includes(sourceNode?.type || '')) {
          console.error(`[CONNECTION_VALIDATION] Invalid source for condition: ${sourceNode?.type}`)
          errors.push(`Condition node "${targetNode.data.label}" can only connect FROM email nodes or other condition nodes. This ensures the condition can monitor email engagement or build on previous conditions.`);
          isValid = false;
        }
      }
    })

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

    set({ isValidFlow: isValid, validationErrors: errors })
  },

  exportFlow: () => {
    const { nodes, edges, contactFile } = get()
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
      contactFile: contactFile
        ? {
            name: contactFile.name,
            size: contactFile.size,
            type: contactFile.type,
            lastModified: contactFile.lastModified,
          }
        : null,
    }
  },

  importFlow: (flow) => {
    const nodes: Node[] = flow.nodes.map((node) => ({
      id: node.id,
      type: node.type,
      position: node.position,
      data: node.data,
    }))

    const edges: Edge[] = flow.edges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      type: edge.type || "default",
      animated: edge.animated || false,
      style: edge.style || {},
      label: edge.label,
    }))

    set({ nodes, edges })
    get().validateFlow()
  },

  resetFlow: () => {
    set({
      nodes: [
        {
          id: "start-1",
          type: "start",
          position: { x: 400, y: 50 },
          data: { label: "Campaign Start", config: {} },
          deletable: false,
        },
      ],
      edges: [],
      selectedNode: null,
      selectedEdge: null,
      isValidFlow: false,
      validationErrors: [],
      contactFile: null,
    })
  },

  setContactFile: (file) => {
    set({ contactFile: file })
    // Update the start node with file info
    if (file) {
      get().updateNode("start-1", {
        config: {
          contactFile: {
            name: file.name,
            size: file.size,
            type: file.type,
            lastModified: file.lastModified,
          },
        },
      })
    } else {
      get().updateNode("start-1", {
        config: {},
      })
    }
    get().validateFlow()
  },



  // Campaign save API
  saveCampaign: async () => {
    try {
      const flowData = get().exportFlow()
      const { contactFile } = get()
      
      // Read contact file content if available
      let contactFileContent = null
      if (contactFile) {
        contactFileContent = await contactFile.text()
      }
      
      const campaignData = {
        campaign: {
          id: `campaign_${Date.now()}`,
          name: "Email Campaign Flow",
          created_at: new Date().toISOString(),
          status: "ready",
        },
        nodes: flowData.nodes.map((node) => ({
          id: node.id,
          type: node.type,
          position: node.position,
          configuration: {
            label: node.data.label,
            ...node.data.config,
          },
        })),
        connections: flowData.edges.map((edge) => ({
          id: edge.id,
          from_node: edge.source,
          to_node: edge.target,
          connection_type: edge.sourceHandle || "default",
          animated: edge.animated || false,
        })),
        workflow: {
          start_node: "start-1",
          total_nodes: flowData.nodes.length,
          total_connections: flowData.edges.length,
        },
        contact_file: contactFile
          ? {
              filename: contactFile.name,
              size: contactFile.size,
              type: contactFile.type,
              content: contactFileContent,
              uploaded_at: new Date(contactFile.lastModified).toISOString(),
            }
          : null,
      }

      // Use ngrok URL for API calls
      const apiUrl = 'http://35.154.124.182:8000/api/campaigns';
      
      const response = await fetch(apiUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(campaignData),
      })

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail || 'Failed to save campaign')
      }

      const result = await response.json()
      return result
    } catch (error) {
      console.error('Error saving campaign:', error)
      throw error
    }
  },
}))
