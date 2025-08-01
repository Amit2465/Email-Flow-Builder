"use client"

import type React from "react"
import { useEffect } from "react"
import { Handle, Position } from "@xyflow/react"
import { Play, FileText, AlertCircle } from "lucide-react"
import { useFlowStore } from "../../store/flowStore"

export const StartNode: React.FC<any> = ({ id, data, selected }) => {
  const { setSelectedNode, deleteNode, contactFile } = useFlowStore()

  const handleNodeClick = () => {
    setSelectedNode(id)
  }

  // Handle delete key press (but start node shouldn't be deletable)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (selected && (e.key === "Delete" || e.key === "Backspace")) {
        e.preventDefault()
        // Start node cannot be deleted
        console.log("Start node cannot be deleted")
      }
    }

    if (selected) {
      document.addEventListener("keydown", handleKeyDown)
      return () => document.removeEventListener("keydown", handleKeyDown)
    }
  }, [selected, id, deleteNode])

  return (
    <div
      className={`bg-green-100 text-green-800 px-2 py-1.5 rounded shadow-sm border cursor-pointer min-w-[140px] ${
        selected ? "border-green-400 shadow-md" : "border-green-200"
      }`}
      onClick={handleNodeClick}
    >
      <div className="flex items-center space-x-1.5 mb-1">
        <div className="w-4 h-4 bg-green-200 rounded-full flex items-center justify-center">
          <Play className="w-2.5 h-2.5 text-green-700" />
        </div>
        <div className="flex-1">
          <h3 className="font-medium text-xs leading-tight">{data.label}</h3>
        </div>
      </div>

      {/* File status indicator */}
      <div className="flex items-center space-x-1 mt-1">
        {contactFile ? (
          <>
            <FileText className="w-3 h-3 text-green-600" />
            <span className="text-xs text-green-600 truncate" title={contactFile.name}>
              {contactFile.name.length > 12 ? `${contactFile.name.substring(0, 12)}...` : contactFile.name}
            </span>
          </>
        ) : (
          <>
            <AlertCircle className="w-3 h-3 text-orange-600" />
            <span className="text-xs text-orange-600">No file uploaded</span>
          </>
        )}
      </div>

      <Handle
        type="source"
        position={Position.Bottom}
        className="w-2 h-2 bg-green-600 border border-white"
        isConnectable={1}
      />
    </div>
  )
}
