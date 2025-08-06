"use client"

import { useState } from "react"
import { TopBar } from "../src/components/layout/TopBar"
import { NodePalette } from "../src/components/sidebar/NodePalette"
import { FlowCanvas } from "../src/components/canvas/FlowCanvas"
import { PropertyPanel } from "../src/components/properties/PropertyPanel"
import { useFlowStore } from "../src/store/flowStore"
import { Toaster } from "../components/ui/sonner"
import "@xyflow/react/dist/style.css"

export default function Page() {
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false)
  const { selectedNode } = useFlowStore()

  return (
    <div className="h-screen flex flex-col bg-gray-50">
      <TopBar />

      <div className="flex-1 flex overflow-hidden">
        <NodePalette
          isCollapsed={isSidebarCollapsed}
          onToggleCollapse={() => setIsSidebarCollapsed(!isSidebarCollapsed)}
        />

        <FlowCanvas />

        {selectedNode && <PropertyPanel />}
      </div>
      
      <Toaster />
    </div>
  )
}
