import { create } from "zustand"
import type { FlowNode, CampaignFlow } from "../types/flow"
import { type Node, type Edge, addEdge, applyNodeChanges, applyEdgeChanges, type Connection } from "@xyflow/react"

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
    get().validateFlow()
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
    const { edges } = get()

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

    set((state) => ({ edges: addEdge(edge, state.edges) }))
    get().validateFlow()
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
        if (!node.data.config?.subject || node.data.config.subject.trim() === "") {
          errors.push(`Email node "${node.data.label}" needs a subject`)
          isValid = false
        }
        if (!node.data.config?.body || node.data.config.body.trim() === "") {
          errors.push(`Email node "${node.data.label}" needs a body`)
          isValid = false
        }
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
      }
    })

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
}))
