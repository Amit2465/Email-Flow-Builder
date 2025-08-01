"use client"

import { useState } from "react"
import { TopBar } from "./components/layout/TopBar"
import { NodePalette } from "./components/sidebar/NodePalette"
import { FlowCanvas } from "./components/canvas/FlowCanvas"
import { PropertyPanel } from "./components/properties/PropertyPanel"
import { useFlowStore } from "./store/flowStore"
import "@xyflow/react/dist/style.css"

function App() {
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
    </div>
  )
}

export default App
