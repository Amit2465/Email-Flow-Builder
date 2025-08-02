export interface FlowNode {
  id: string
  type: "sendEmail" | "wait" | "condition" | "start" | "end"
  position: { x: number; y: number }
  data: {
    label: string
    description?: string
    config?: {
      templateId?: string
      subject?: string
      body?: string
      waitDays?: number
      waitDuration?: number
      waitUnit?: string
      conditionType?: "open"
      contactFile?: {
        name: string
        size: number
        type: string
        lastModified: number
      }
    }
  }
}

export interface FlowEdge {
  id: string
  source: string
  target: string
  type?: "default" | "yes" | "no"
  animated?: boolean
  style?: Record<string, any>
  label?: string
}

export interface CampaignFlow {
  nodes: FlowNode[]
  edges: FlowEdge[]
  contactFile?: {
    name: string
    size: number
    type: string
    lastModified: number
  } | null
}

export interface NodeTemplate {
  type: "sendEmail" | "wait" | "condition" | "end"
  label: string
  description: string
  icon: string
  color: string
  category: "action" | "logic" | "timing"
}
