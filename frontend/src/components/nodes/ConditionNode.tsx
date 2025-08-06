"use client"

import type React from "react"
import { useState, useEffect } from "react"
import { Handle, Position } from "@xyflow/react"
import { HelpCircle, Edit3, Check, X } from "lucide-react"
import { useFlowStore } from "../../store/flowStore"

export const ConditionNode: React.FC<any> = ({ id, data, selected }) => {
  const { updateNode, deleteNode } = useFlowStore()
  const [isEditing, setIsEditing] = useState(false)
  const [conditionType, setConditionType] = useState(data.config?.conditionType || "open")

  const conditionOptions = [
    { value: "open", label: "Email Opened" },
    { value: "click", label: "Link Clicked" },
  ]

  const handleSave = () => {
    updateNode(id, {
      config: { ...data.config, conditionType },
    })
    setIsEditing(false)
  }

  const handleCancel = () => {
    setConditionType(data.config?.conditionType || "open")
    setIsEditing(false)
  }

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      handleSave()
    }
    if (e.key === "Escape") {
      handleCancel()
    }
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

  const selectedOption = conditionOptions.find((opt) => opt.value === (data.config?.conditionType || "open"))

  return (
    <div
      className={`bg-purple-100 text-purple-800 rounded shadow-sm border cursor-pointer transition-all duration-200 min-w-[120px] relative ${
        selected ? "border-purple-400 shadow-md" : "border-purple-200"
      }`}
    >
      <Handle
        type="target"
        position={Position.Top}
        className="w-2 h-2 bg-purple-600 border border-white"
        isConnectable={1}
      />

      <div className="p-1.5">
        <div className="flex items-center space-x-1.5 mb-1.5">
          <div className="w-4 h-4 bg-purple-200 rounded flex items-center justify-center">
            <HelpCircle className="w-2.5 h-2.5 text-purple-700" />
          </div>
          <div className="flex-1">
            <h3 className="font-medium text-xs">{data.label}</h3>
          </div>
          {!isEditing && (
            <button onClick={() => setIsEditing(true)} className="p-0.5 hover:bg-purple-200 rounded">
              <Edit3 className="w-2 h-2 text-purple-600" />
            </button>
          )}
        </div>

        <div className="space-y-1.5">
          <div className="text-xs text-purple-600">Condition:</div>
          {isEditing ? (
            <div className="space-y-1">
              <select
                value={conditionType}
                onChange={(e) => setConditionType(e.target.value)}
                onKeyDown={handleKeyPress}
                className="w-full px-1.5 py-0.5 text-xs border border-purple-300 rounded focus:outline-none focus:border-purple-500"
                autoFocus
              >
                {conditionOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              <div className="flex items-center space-x-1">
                <button
                  onClick={handleSave}
                  className="flex items-center justify-center w-4 h-4 bg-green-500 hover:bg-green-600 text-white rounded text-xs"
                >
                  <Check className="w-2.5 h-2.5" />
                </button>
                <button
                  onClick={handleCancel}
                  className="flex items-center justify-center w-4 h-4 bg-red-500 hover:bg-red-600 text-white rounded text-xs"
                >
                  <X className="w-2.5 h-2.5" />
                </button>
              </div>
            </div>
          ) : (
            <div
              onClick={() => setIsEditing(true)}
              className="px-1.5 py-0.5 text-xs bg-purple-200 text-purple-800 border border-purple-300 rounded cursor-pointer"
            >
              {selectedOption?.label}
            </div>
          )}
        </div>
      </div>

      {/* Yes Handle */}
      <Handle
        type="source"
        position={Position.Bottom}
        id="yes"
        style={{ left: "25%" }}
        className="w-2 h-2 bg-green-600 border border-white"
        isConnectable={1}
      />

      {/* No Handle */}
      <Handle
        type="source"
        position={Position.Bottom}
        id="no"
        style={{ left: "75%" }}
        className="w-2 h-2 bg-red-600 border border-white"
        isConnectable={1}
      />

      {/* Labels for Yes/No */}
      <div className="absolute -bottom-5 left-0 right-0 flex justify-between px-1.5">
        <span className="text-xs text-green-600 font-medium">Yes</span>
        <span className="text-xs text-red-600 font-medium">No</span>
      </div>
    </div>
  )
}
