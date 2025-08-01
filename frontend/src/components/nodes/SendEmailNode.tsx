"use client"

import type React from "react"
import { useEffect } from "react"
import { Handle, Position } from "@xyflow/react"
import { Mail } from "lucide-react"
import { useFlowStore } from "../../store/flowStore"

export const SendEmailNode: React.FC<any> = ({ id, data, selected }) => {
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

  // Get subject from config and truncate if too long
  const subject = data.config?.subject || "No subject"
  const truncatedSubject = subject.length > 15 ? `${subject.substring(0, 15)}...` : subject

  return (
    <div
      className={`bg-blue-100 text-blue-800 rounded shadow-sm border transition-all duration-200 min-w-[120px] cursor-pointer ${
        selected ? "border-blue-400 shadow-md" : "border-blue-200"
      }`}
      onClick={handleNodeClick}
    >
      <Handle
        type="target"
        position={Position.Top}
        className="w-2 h-2 bg-blue-600 border border-white"
        isConnectable={1}
      />

      <div className="p-2">
        <div className="flex items-center space-x-2 mb-1">
          <div className="w-5 h-5 bg-blue-200 rounded flex items-center justify-center">
            <Mail className="w-3 h-3 text-blue-700" />
          </div>
          <div className="flex-1">
            <h3 className="font-medium text-xs">{data.label}</h3>
          </div>
        </div>
        <div className="text-xs text-blue-600 font-medium truncate" title={subject}>
          {truncatedSubject}
        </div>
      </div>

      <Handle
        type="source"
        position={Position.Bottom}
        className="w-2 h-2 bg-blue-600 border border-white"
        isConnectable={1}
      />
    </div>
  )
}
