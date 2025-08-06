"use client"

import type React from "react"
import { useCallback, useRef, useEffect } from "react"
import { ReactFlow, Background, Controls, MiniMap, useReactFlow, ReactFlowProvider } from "@xyflow/react"
import { v4 as uuidv4 } from "uuid"
import { ZoomOut } from "lucide-react"
import { useFlowStore } from "../../store/flowStore"
import { StartNode } from "../nodes/StartNode"
import { SendEmailNode } from "../nodes/SendEmailNode"
import { WaitNode } from "../nodes/WaitNode"
import { ConditionNode } from "../nodes/ConditionNode"
import { EndNode } from "../nodes/EndNode"

const nodeTypes = {
  start: StartNode,
  sendEmail: SendEmailNode,
  wait: WaitNode,
  condition: ConditionNode,
  end: EndNode,
}

const FlowCanvasInner: React.FC = () => {
  const reactFlowWrapper = useRef<HTMLDivElement>(null)
  const { screenToFlowPosition, zoomOut } = useReactFlow()

  const {
    nodes,
    edges,
    selectedEdge,
    selectedNode, // Add this line
    onNodesChange,
    onEdgesChange,
    onConnect,
    addNode,
    setSelectedNode,
    setSelectedEdge,
    deleteEdge,
  } = useFlowStore()

  // Handle delete key for edges
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (selectedEdge && (e.key === "Delete" || e.key === "Backspace")) {
        e.preventDefault()
        deleteEdge(selectedEdge)
      }
    }

    document.addEventListener("keydown", handleKeyDown)
    return () => document.removeEventListener("keydown", handleKeyDown)
  }, [selectedEdge, deleteEdge])

  const onDragOver = useCallback((event: React.DragEvent) => {
    event.preventDefault()
    event.dataTransfer.dropEffect = "move"
  }, [])

  const onDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault()

      const type = event.dataTransfer.getData("application/reactflow")

      if (typeof type === "undefined" || !type) {
        return
      }

      const position = screenToFlowPosition({
        x: event.clientX,
        y: event.clientY,
      })

      const newNode = {
        id: `${type}-${uuidv4()}`,
        type: type as any,
        position,
        data: {
          label: getNodeLabel(type),
          config: getDefaultConfig(type),
        },
      }

      addNode(newNode)
    },
    [screenToFlowPosition, addNode],
  )

  const getNodeLabel = (type: string): string => {
    switch (type) {
      case "sendEmail":
        return "Send Email"
      case "wait":
        return "Wait"
      case "condition":
        return "Condition Check"
      case "end":
        return "Campaign End"
      default:
        return type
    }
  }

  const getDefaultConfig = (type: string): any => {
    switch (type) {
      case "sendEmail":
        return { subject: "", body: "", links: [] }
      case "wait":
        return { waitDuration: 1, waitUnit: "days" }
      case "condition":
        return { conditionType: "open" }
      case "end":
        return {}
      default:
        return {}
    }
  }

  const onNodeClick = useCallback(
    (event: React.MouseEvent, node: any) => {
      setSelectedNode(node.id)
    },
    [setSelectedNode],
  )

  const onEdgeClick = useCallback(
    (event: React.MouseEvent, edge: any) => {
      setSelectedEdge(edge.id)
    },
    [setSelectedEdge],
  )

  const onPaneClick = useCallback(() => {
    setSelectedNode(null)
    setSelectedEdge(null)
  }, [setSelectedNode, setSelectedEdge])

  return (
    <div className="flex-1 bg-white" ref={reactFlowWrapper}>
      <ReactFlow
        nodes={nodes}
        edges={edges.map((edge) => ({
          ...edge,
          style: {
            ...edge.style,
            stroke: selectedEdge === edge.id ? "#EF4444" : "#1D4ED8",
            strokeWidth: selectedEdge === edge.id ? 3 : 2,
          },
        }))}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onDrop={onDrop}
        onDragOver={onDragOver}
        onNodeClick={onNodeClick}
        onEdgeClick={onEdgeClick}
        onPaneClick={onPaneClick}
        nodeTypes={nodeTypes}
        fitView={false}
        defaultViewport={{ x: 0, y: 0, zoom: 0.8 }}
        defaultEdgeOptions={{
          animated: true,
          style: { stroke: "#1D4ED8", strokeWidth: 2 },
        }}
        className="bg-white"
      >
        <Background color="#E5E7EB" gap={16} size={1} variant="lines" />
        <Controls className="bg-white border border-gray-200 rounded-lg shadow-sm" showInteractive={false} />
        
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
        
        {!selectedNode && (
          <MiniMap
            className="bg-white border border-gray-200 rounded-lg shadow-sm"
            nodeColor="#E5E7EB"
            nodeStrokeWidth={2}
            zoomable
            pannable
          />
        )}
      </ReactFlow>
    </div>
  )
}

export const FlowCanvas: React.FC = () => {
  return (
    <ReactFlowProvider>
      <FlowCanvasInner />
    </ReactFlowProvider>
  )
}
