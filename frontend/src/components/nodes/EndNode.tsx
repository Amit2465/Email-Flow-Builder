"use client"

import type React from "react"
import { useEffect } from "react"
import { Handle, Position } from "@xyflow/react"
import { Square } from "lucide-react"
import { useFlowStore } from "../../store/flowStore"

export const EndNode: React.FC<any> = ({ id, data, selected }) => {
  const { setSelectedNode, deleteNode } = useFlowStore()

  const handleNodeClick = () => {
    setSelectedNode(id)
  }

  // Handle delete key press
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (selected && (e.key === "Delete" || e.key === "Backspace")) {
        e.preventDefault()
        deleteNode(id)
      }
    }

    if (selected) {
      document.addEventListener("keydown", handleKeyDown)
      return () => document.removeEventListener("keydown", handleKeyDown)
    }
  }, [selected, id, deleteNode])

  return (
    <div
      className={`bg-red-100 text-red-800 px-2 py-1.5 rounded shadow-sm border cursor-pointer min-w-[100px] ${
        selected ? "border-red-400 shadow-md" : "border-red-200"
      }`}
      onClick={handleNodeClick}
    >
      <div className="flex items-center space-x-1.5">
        <div className="w-4 h-4 bg-red-200 rounded-full flex items-center justify-center">
          <Square className="w-2.5 h-2.5 text-red-700" />
        </div>
        <div>
          <h3 className="font-medium text-xs leading-tight">{data.label}</h3>
        </div>
      </div>
      <Handle type="target" position={Position.Top} className="w-2 h-2 bg-red-600 border border-white" />
    </div>
  )
}
