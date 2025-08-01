"use client"

import type React from "react"
import { ChevronLeft, ChevronRight, Mail, Clock, HelpCircle, Circle, Square } from "lucide-react"
import { nodeTemplates } from "../../data/nodeTemplates"

interface NodePaletteProps {
  isCollapsed: boolean
  onToggleCollapse: () => void
}

export const NodePalette: React.FC<NodePaletteProps> = ({ isCollapsed, onToggleCollapse }) => {
  return (
    <div
      className={`bg-white border-r border-gray-200 h-full flex flex-col transition-all duration-300 ${
        isCollapsed ? "w-16" : "w-80"
      }`}
    >
      {/* Header */}
      <div className="p-4 border-b border-gray-100 flex items-center justify-between">
        {!isCollapsed && (
          <div>
            <h2 className="font-semibold text-gray-900">Workflow Components</h2>
            <p className="text-sm text-gray-500 mt-1">Drag components to build your campaign</p>
          </div>
        )}
        <button onClick={onToggleCollapse} className="p-2 hover:bg-gray-100 rounded-lg transition-colors">
          {isCollapsed ? (
            <ChevronRight className="w-4 h-4 text-gray-600" />
          ) : (
            <ChevronLeft className="w-4 h-4 text-gray-600" />
          )}
        </button>
      </div>

      {!isCollapsed && (
        <>
          {/* Node Cards */}
          <div className="flex-1 overflow-y-auto p-3">
            <div className="space-y-2">
              {nodeTemplates.map((template) => (
                <div
                  key={template.type}
                  draggable
                  onDragStart={(event) => {
                    event.dataTransfer.setData("application/reactflow", template.type)
                    event.dataTransfer.effectAllowed = "move"
                  }}
                  className={`px-3 py-2 rounded-md border cursor-grab hover:shadow-sm transition-all duration-200 ${
                    template.type === "sendEmail"
                      ? "bg-blue-50 border-blue-200 text-blue-700 hover:bg-blue-100"
                      : template.type === "wait"
                        ? "bg-yellow-50 border-yellow-200 text-yellow-700 hover:bg-yellow-100"
                        : template.type === "condition"
                          ? "bg-purple-50 border-purple-200 text-purple-700 hover:bg-purple-100"
                          : template.type === "empty"
                            ? "bg-gray-50 border-gray-200 text-gray-700 hover:bg-gray-100"
                            : "bg-red-50 border-red-200 text-red-700 hover:bg-red-100"
                  }`}
                >
                  <div className="flex items-center space-x-3">
                    <div className="flex-shrink-0">
                      {template.type === "sendEmail" && <Mail className="w-4 h-4" />}
                      {template.type === "wait" && <Clock className="w-4 h-4" />}
                      {template.type === "condition" && <HelpCircle className="w-4 h-4" />}
                      {template.type === "empty" && <Circle className="w-4 h-4" />}
                      {template.type === "end" && <Square className="w-4 h-4" />}
                    </div>
                    <div className="flex-1 min-w-0">
                      <h3 className="font-medium text-sm truncate">{template.label}</h3>
                      <p className="text-xs opacity-75 truncate">{template.description}</p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </>
      )}

      {isCollapsed && (
        <div className="flex-1 flex flex-col items-center pt-4 space-y-3">
          {nodeTemplates.map((template) => (
            <div
              key={template.type}
              draggable
              onDragStart={(event) => {
                event.dataTransfer.setData("application/reactflow", template.type)
                event.dataTransfer.effectAllowed = "move"
              }}
              className={`w-10 h-10 rounded-lg border-2 border-dashed flex items-center justify-center cursor-grab hover:shadow-sm transition-all ${
                template.type === "sendEmail"
                  ? "bg-blue-50 border-blue-300 hover:bg-blue-100 hover:border-blue-400"
                  : template.type === "wait"
                    ? "bg-yellow-50 border-yellow-300 hover:bg-yellow-100 hover:border-yellow-400"
                    : template.type === "condition"
                      ? "bg-purple-50 border-purple-300 hover:bg-purple-100 hover:border-purple-400"
                      : template.type === "empty"
                        ? "bg-gray-50 border-gray-300 hover:bg-gray-100 hover:border-gray-400"
                        : "bg-red-50 border-red-300 hover:bg-red-100 hover:border-red-400"
              }`}
              title={template.label}
            >
              {template.type === "sendEmail" && <Mail className="w-4 h-4 text-blue-600" />}
              {template.type === "wait" && <Clock className="w-4 h-4 text-yellow-600" />}
              {template.type === "condition" && <HelpCircle className="w-4 h-4 text-purple-600" />}
              {template.type === "empty" && <Circle className="w-4 h-4 text-gray-600" />}
              {template.type === "end" && <Square className="w-4 h-4 text-red-600" />}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
