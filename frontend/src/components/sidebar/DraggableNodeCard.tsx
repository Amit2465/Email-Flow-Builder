"use client"

import type React from "react"
import { Mail, Clock, HelpCircle, Square } from "lucide-react"
import type { NodeTemplate } from "../../types/flow"

interface DraggableNodeCardProps {
  template: NodeTemplate
}

export const DraggableNodeCard: React.FC<DraggableNodeCardProps> = ({ template }) => {
  const onDragStart = (event: React.DragEvent) => {
    event.dataTransfer.setData("application/reactflow", template.type)
    event.dataTransfer.effectAllowed = "move"
  }

  const getIcon = (type: string) => {
    switch (type) {
      case "sendEmail":
        return <Mail className="w-4 h-4" />
      case "wait":
        return <Clock className="w-4 h-4" />
      case "condition":
        return <HelpCircle className="w-4 h-4" />
      case "end":
        return <Square className="w-4 h-4" />

      default:
        return <Mail className="w-4 h-4" />
    }
  }

  const getCategoryColor = (category: string) => {
    switch (category) {
      case "action":
        return "bg-blue-50 border-blue-200 text-blue-700 hover:bg-blue-100"
      case "logic":
        return "bg-purple-50 border-purple-200 text-purple-700 hover:bg-purple-100"
      case "timing":
        return "bg-yellow-50 border-yellow-200 text-yellow-700 hover:bg-yellow-100"
      default:
        return "bg-gray-50 border-gray-200 text-gray-700 hover:bg-gray-100"
    }
  }

  return (
    <div
      draggable
      onDragStart={onDragStart}
      className={`px-3 py-2 rounded-md border cursor-grab hover:shadow-sm transition-all duration-200 ${getCategoryColor(template.category)}`}
    >
      <div className="flex items-center space-x-3">
        <div className="flex-shrink-0">{getIcon(template.type)}</div>
        <div className="flex-1 min-w-0">
          <h3 className="font-medium text-sm truncate">{template.label}</h3>
          <p className="text-xs opacity-75 truncate">{template.description}</p>
        </div>
      </div>
    </div>
  )
}
