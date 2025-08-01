"use client"

import type React from "react"
import { useState, useEffect } from "react"
import { Handle, Position } from "@xyflow/react"
import { Clock, Edit3, Check, X } from "lucide-react"
import { useFlowStore } from "../../store/flowStore"

export const WaitNode: React.FC<any> = ({ id, data, selected }) => {
  const { updateNode, deleteNode } = useFlowStore()
  const [isEditing, setIsEditing] = useState(false)
  const [waitDuration, setWaitDuration] = useState(data.config?.waitDuration || 1)
  const [waitUnit, setWaitUnit] = useState(data.config?.waitUnit || "days")

  const handleSave = () => {
    updateNode(id, {
      config: { ...data.config, waitDuration: Number.parseInt(waitDuration.toString()), waitUnit },
    })
    setIsEditing(false)
  }

  const handleCancel = () => {
    setWaitDuration(data.config?.waitDuration || 1)
    setWaitUnit(data.config?.waitUnit || "days")
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

  const displayDuration = data.config?.waitDuration || 1
  const displayUnit = data.config?.waitUnit || "days"

  return (
    <div
      className={`bg-yellow-100 text-yellow-800 rounded-sm shadow-sm border cursor-pointer transition-all duration-200 w-[130px] h-[60px] ${
        selected ? "border-yellow-400 shadow-md" : "border-yellow-200"
      }`}
    >
      <Handle
        type="target"
        position={Position.Top}
        className="w-2 h-2 bg-yellow-600 border border-white"
        isConnectable={1}
      />

      <div className="p-1.5 h-full flex flex-col justify-center">
        <div className="flex items-center space-x-1.5 mb-1">
          <div className="w-3.5 h-3.5 bg-yellow-200 rounded flex items-center justify-center">
            <Clock className="w-2 h-2 text-yellow-700" />
          </div>
          <div className="flex-1">
            <h3 className="font-medium text-xs">{data.label}</h3>
          </div>
          {!isEditing && (
            <button onClick={() => setIsEditing(true)} className="p-0.5 hover:bg-yellow-200 rounded">
              <Edit3 className="w-1.5 h-1.5 text-yellow-600" />
            </button>
          )}
        </div>

        {isEditing ? (
          <div className="space-y-1">
            <div className="flex items-center space-x-1">
              <input
                type="number"
                min="1"
                max="365"
                value={waitDuration}
                onChange={(e) => setWaitDuration(Number.parseInt(e.target.value) || 1)}
                onKeyDown={handleKeyPress}
                className="w-12 px-1 py-0.5 text-xs border border-yellow-300 rounded focus:outline-none focus:border-yellow-500"
                autoFocus
              />
              <select
                value={waitUnit}
                onChange={(e) => setWaitUnit(e.target.value)}
                onKeyDown={handleKeyPress}
                className="w-16 px-1 py-0.5 text-xs border border-yellow-300 rounded focus:outline-none focus:border-yellow-500"
              >
                <option value="minutes">min</option>
                <option value="hours">hrs</option>
                <option value="days">days</option>
              </select>
            </div>
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
          <div className="flex items-center space-x-1">
            <div className="px-1 py-0.5 text-xs bg-yellow-200 text-yellow-800 border border-yellow-300 rounded font-medium">
              {displayDuration} {displayUnit}
            </div>
          </div>
        )}
      </div>

      <Handle
        type="source"
        position={Position.Bottom}
        className="w-2 h-2 bg-yellow-600 border border-white"
        isConnectable={1}
      />
    </div>
  )
}
