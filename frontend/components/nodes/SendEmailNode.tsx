import React, { useState } from 'react';
import { Handle, Position } from '@xyflow/react';
import { Mail, Edit3 } from 'lucide-react';
import { useFlowStore } from '../../store/flowStore';

export const SendEmailNode: React.FC<any> = ({ id, data, selected }) => {
  const { updateNode } = useFlowStore();
  const [isEditing, setIsEditing] = useState(false);
  const [templateId, setTemplateId] = useState(data.config?.templateId || '');

  const handleSave = () => {
    updateNode(id, {
      config: { ...data.config, templateId }
    });
    setIsEditing(false);
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleSave();
    }
    if (e.key === 'Escape') {
      setTemplateId(data.config?.templateId || '');
      setIsEditing(false);
    }
  };

  return (
    <div className={`bg-white rounded-lg shadow-md border-2 transition-all duration-200 min-w-[220px] ${
      selected ? 'border-blue-500 shadow-lg' : 'border-gray-200 hover:border-gray-300'
    }`}>
      <Handle
        type="target"
        position={Position.Top}
        className="w-3 h-3 bg-blue-600 border-2 border-white"
      />
      
      <div className="p-4">
        <div className="flex items-center space-x-3 mb-3">
          <div className="w-8 h-8 bg-blue-100 rounded-lg flex items-center justify-center">
            <Mail className="w-4 h-4 text-blue-600" />
          </div>
          <div className="flex-1">
            <h3 className="font-semibold text-sm text-gray-900">{data.label}</h3>
            <p className="text-xs text-gray-500">Send email template</p>
          </div>
          <button
            onClick={() => setIsEditing(!isEditing)}
            className="p-1 hover:bg-gray-100 rounded"
          >
            <Edit3 className="w-3 h-3 text-gray-400" />
          </button>
        </div>
        
        <div className="space-y-2">
          <div className="text-xs text-gray-500">Template ID:</div>
          {isEditing ? (
            <input
              type="text"
              value={templateId}
              onChange={(e) => setTemplateId(e.target.value)}
              onBlur={handleSave}
              onKeyDown={handleKeyPress}
              className="w-full px-2 py-1 text-xs border border-gray-300 rounded focus:outline-none focus:border-blue-500"
              placeholder="Enter template ID"
              autoFocus
            />
          ) : (
            <div 
              onClick={() => setIsEditing(true)}
              className={`px-2 py-1 text-xs rounded cursor-pointer ${
                templateId 
                  ? 'bg-blue-50 text-blue-700 border border-blue-200' 
                  : 'bg-gray-50 text-gray-400 border border-dashed border-gray-300'
              }`}
            >
              {templateId || 'Click to set template'}
            </div>
          )}
        </div>
      </div>

      <Handle
        type="source"
        position={Position.Bottom}
        className="w-3 h-3 bg-blue-600 border-2 border-white"
      />
    </div>
  );
};
