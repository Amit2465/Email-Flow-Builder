import React from 'react';
import { X, Info } from 'lucide-react';
import { useFlowStore } from '../../store/flowStore';

export const PropertyPanel: React.FC = () => {
  const { nodes, selectedNode, setSelectedNode, updateNode } = useFlowStore();
  
  const selectedNodeData = nodes.find(node => node.id === selectedNode);

  if (!selectedNode || !selectedNodeData) return null;

  const handleClose = () => {
    setSelectedNode(null);
  };

  const renderNodeProperties = () => {
    switch (selectedNodeData.type) {
      case 'sendEmail':
        return (
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Email Template ID
              </label>
              <input
                type="text"
                value={selectedNodeData.data.config?.templateId || ''}
                onChange={(e) => updateNode(selectedNode, {
                  config: { ...selectedNodeData.data.config, templateId: e.target.value }
                })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:border-blue-500"
                placeholder="e.g., welcome-email-v2"
              />
            </div>
            <div className="p-3 bg-blue-50 rounded-lg">
              <div className="flex items-start space-x-2">
                <Info className="w-4 h-4 text-blue-600 mt-0.5" />
                <div>
                  <p className="text-sm text-blue-800 font-medium">Template Setup</p>
                  <p className="text-xs text-blue-600 mt-1">
                    Make sure your email template is created in your email service provider
                    and the ID matches exactly.
                  </p>
                </div>
              </div>
            </div>
          </div>
        );
        
      case 'wait':
        return (
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Wait Duration (Days)
              </label>
              <input
                type="number"
                min="1"
                max="365"
                value={selectedNodeData.data.config?.waitDays || 1}
                onChange={(e) => updateNode(selectedNode, {
                  config: { ...selectedNodeData.data.config, waitDays: parseInt(e.target.value) || 1 }
                })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:border-yellow-500"
              />
            </div>
            <div className="p-3 bg-yellow-50 rounded-lg">
              <div className="flex items-start space-x-2">
                <Info className="w-4 h-4 text-yellow-600 mt-0.5" />
                <div>
                  <p className="text-sm text-yellow-800 font-medium">Timing Note</p>
                  <p className="text-xs text-yellow-600 mt-1">
                    Users will wait exactly this many days before proceeding to the next step.
                  </p>
                </div>
              </div>
            </div>
          </div>
        );
        
      case 'condition':
        return (
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Condition Type
              </label>
              <select
                value={selectedNodeData.data.config?.conditionType || 'open'}
                onChange={(e) => updateNode(selectedNode, {
                  config: { ...selectedNodeData.data.config, conditionType: e.target.value }
                })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:border-purple-500"
              >
                <option value="open">Email Opened</option>
              </select>
            </div>
            <div className="p-3 bg-purple-50 rounded-lg">
              <div className="flex items-start space-x-2">
                <Info className="w-4 h-4 text-purple-600 mt-0.5" />
                <div>
                  <p className="text-sm text-purple-800 font-medium">Branching Logic</p>
                  <p className="text-xs text-purple-600 mt-1">
                    Connect the "Yes" output to the path for users who meet the condition,
                    and "No" for those who don't.
                  </p>
                </div>
              </div>
            </div>
          </div>
        );
        
      default:
        return (
          <div className="text-center text-gray-500 py-8">
            <p>No properties available for this node type.</p>
          </div>
        );
    }
  };

  return (
    <div className="w-80 bg-white border-l border-gray-200 flex flex-col">
      <div className="p-4 border-b border-gray-100 flex items-center justify-between">
        <div>
          <h3 className="font-semibold text-gray-900">Properties</h3>
          <p className="text-sm text-gray-500 mt-1">{selectedNodeData.data.label}</p>
        </div>
        <button
          onClick={handleClose}
          className="p-1 hover:bg-gray-100 rounded"
        >
          <X className="w-4 h-4 text-gray-500" />
        </button>
      </div>
      
      <div className="flex-1 p-4 overflow-y-auto">
        {renderNodeProperties()}
      </div>
    </div>
  );
};
