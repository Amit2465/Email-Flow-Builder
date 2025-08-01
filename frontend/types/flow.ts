export interface FlowNode {
  id: string;
  type: 'sendEmail' | 'wait' | 'condition' | 'start';
  position: { x: number; y: number };
  data: {
    label: string;
    description?: string;
    config?: {
      templateId?: string;
      waitDays?: number;
      conditionType?: 'open' | 'click' | 'purchase';
      conditionValue?: string;
    };
  };
}

export interface FlowEdge {
  id: string;
  source: string;
  target: string;
  type?: 'default' | 'yes' | 'no';
  animated?: boolean;
  style?: Record<string, any>;
  label?: string;
}

export interface CampaignFlow {
  nodes: FlowNode[];
  edges: FlowEdge[];
}

export interface NodeTemplate {
  type: 'sendEmail' | 'wait' | 'condition';
  label: string;
  description: string;
  icon: string;
  color: string;
  category: 'action' | 'logic' | 'timing';
}
