import React, { useState } from 'react';
import { Handle, Position } from '@xyflow/react';
import { HelpCircle, Edit3 } from 'lucide-react';
import { useFlowStore } from '../../store/flowStore';

export const ConditionNode: React.FC<any> = ({ id, data, selected }) => {
  const { updateNode } = useFlowStore();
  const [isEditing, setIsEditing] = useState(false);
  const [conditionType, setConditionType] = useState(data.config?.conditionType || 'open');

  const conditionOptions = [
    { value: 'open', label: 'Email Opened' },
    { value: 'click', label: 'Link Clicked' },
    { value: 'purchase', label: 'Purchase Made' },
  ];

  const handleSave = () => {
    updateNode(id, {
      config: { ...data.config, conditionType }
    });
    setIsEditing(false);
  };

  const selectedOption = conditionOptions.find(opt => opt.value === conditionType);

  return (
    <div className={`bg-white rounded-lg shadow-md border-2 transition-all duration-200 min-w-[240px] ${
      selected ? 'border-purple-500 shadow-lg' : 'border-gray-200 hover:border-gray-300'
    }`}>
      <Handle
        type="target"
        position={Position.Top}
        className="w-3 h-3 bg-purple-600 border-2 border-white"
      />
      
      <div className="p-4">
        <div className="flex items-center space-x-3 mb-3">
          <div className="w-8 h-8 bg-purple-100 rounded-lg flex items-center justify-center">
            <HelpCircle className="w-4 h-4 text-purple-600" />
          </div>
          <div className="flex-1">
            <h3 className="font-semibold text-sm text-gray-900">{data.label}</h3>
            <p className="text-xs text-gray-500">Branch based on behavior</p>
          </div>
          <button
            onClick={() => setIsEditing(!isEditing)}
            className="p-1 hover:bg-gray-100 rounded"
          >
            <Edit3 className="w-3 h-3 text-gray-400" />
          </button>
        </div>
        
        <div className="space-y-2">
          <div className="text-xs text-gray-500">Condition:</div>
          {isEditing ? (
            <select
              value={conditionType}
              onChange={(e) => setConditionType(e.target.value)}
              onBlur={handleSave}
              className="w-full px-2 py-1 text-xs border border-gray-300 rounded focus:outline-none focus:border-purple-500"
              autoFocus
            >
              {conditionOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          ) : (
            <div 
              onClick={() => setIsEditing(true)}
              className="px-2 py-1 text-xs bg-purple-50 text-purple-700 border border-purple-200 rounded cursor-pointer"
            >
              {selectedOption?.label}
            </div>
          )}
        </div>
      </div>

      {/* Yes Handle */}
      <Handle
        type="source"
        position={Position.Bottom}
        id="yes"
        style={{ left: '25%' }}
        className="w-3 h-3 bg-green-600 border-2 border-white"
      />
      
      {/* No Handle */}
      <Handle
        type="source"
        position={Position.Bottom}
        id="no"
        style={{ left: '75%' }}
        className="w-3 h-3 bg-red-600 border-2 border-white"
      />
      
      {/* Labels for Yes/No */}
      <div className="absolute -bottom-6 left-0 right-0 flex justify-between px-4">
        <span className="text-xs text-green-600 font-medium">Yes</span>
        <span className="text-xs text-red-600 font-medium">No</span>
      </div>
    </div>
  );
};
