"use client"

import type React from "react"
import { useEffect } from "react"
import { Handle, Position } from "@xyflow/react"
import { Circle } from "lucide-react"
import { useFlowStore } from "../../store/flowStore"

export const EmptyNode: React.FC<any> = ({ id, data, selected }) => {
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
      className={`bg-gray-100 text-gray-700 px-2 py-1.5 rounded shadow-sm border cursor-pointer min-w-[100px] ${
        selected ? "border-gray-400 shadow-md" : "border-gray-200"
      }`}
      onClick={handleNodeClick}
    >
      <Handle
        type="target"
        position={Position.Top}
        className="w-2 h-2 bg-gray-600 border border-white"
        isConnectable={1}
      />

      <div className="flex items-center space-x-1.5">
        <div className="w-4 h-4 bg-gray-200 rounded-full flex items-center justify-center">
          <Circle className="w-2.5 h-2.5 text-gray-600" />
        </div>
        <div>
          <h3 className="font-medium text-xs leading-tight">{data.label}</h3>
        </div>
      </div>
    </div>
  )
}
