import type { NodeTemplate } from "../types/flow"

export const nodeTemplates: NodeTemplate[] = [
  {
    type: "sendEmail",
    label: "Send Email",
    description: "Send an email to the user",
    icon: "📧",
    color: "#1D4ED8",
    category: "action",
  },
  {
    type: "wait",
    label: "Wait",
    description: "Wait for a specified number of days",
    icon: "⏳",
    color: "#F59E0B",
    category: "timing",
  },
  {
    type: "condition",
    label: "Condition",
    description: "Branch based on user behavior",
    icon: "❓",
    color: "#8B5CF6",
    category: "logic",
  },

  {
    type: "end",
    label: "End",
    description: "End the campaign flow",
    icon: "🏁",
    color: "#EF4444",
    category: "action",
  },
]
