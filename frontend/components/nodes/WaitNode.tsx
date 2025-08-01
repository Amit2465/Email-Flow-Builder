import React, { useState } from 'react';
import { Handle, Position } from '@xyflow/react';
import { Clock, Edit3 } from 'lucide-react';
import { useFlowStore } from '../../store/flowStore';

export const WaitNode: React.FC<any> = ({ id, data, selected }) => {
  const { updateNode } = useFlowStore();
  const [isEditing, setIsEditing] = useState(false);
  const [waitDays, setWaitDays] = useState(data.config?.waitDays || 1);

  const handleSave = () => {
    updateNode(id, {
      config: { ...data.config, waitDays: parseInt(waitDays.toString()) }
    });
    setIsEditing(false);
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleSave();
    }
    if (e.key === 'Escape') {
      setWaitDays(data.config?.waitDays || 1);
      setIsEditing(false);
    }
  };

  return (
    <div className={`bg-white rounded-lg shadow-md border-2 transition-all duration-200 min-w-[200px] ${
      selected ? 'border-yellow-500 shadow-lg' : 'border-gray-200 hover:border-gray-300'
    }`}>
      <Handle
        type="target"
        position={Position.Top}
        className="w-3 h-3 bg-yellow-600 border-2 border-white"
      />
      
      <div className="p-4">
        <div className="flex items-center space-x-3 mb-3">
          <div className="w-8 h-8 bg-yellow-100 rounded-lg flex items-center justify-center">
            <Clock className="w-4 h-4 text-yellow-600" />
          </div>
          <div className="flex-1">
            <h3 className="font-semibold text-sm text-gray-900">{data.label}</h3>
            <p className="text-xs text-gray-500">Pause campaign flow</p>
          </div>
          <button
            onClick={() => setIsEditing(!isEditing)}
            className="p-1 hover:bg-gray-100 rounded"
          >
            <Edit3 className="w-3 h-3 text-gray-400" />
          </button>
        </div>
        
        <div className="space-y-2">
          <div className="text-xs text-gray-500">Duration:</div>
          <div className="flex items-center space-x-2">
            {isEditing ? (
              <input
                type="number"
                min="1"
                max="365"
                value={waitDays}
                onChange={(e) => setWaitDays(parseInt(e.target.value) || 1)}
                onBlur={handleSave}
                onKeyDown={handleKeyPress}
                className="w-16 px-2 py-1 text-xs border border-gray-300 rounded focus:outline-none focus:border-yellow-500"
                autoFocus
              />
            ) : (
              <div 
                onClick={() => setIsEditing(true)}
                className="px-2 py-1 text-xs bg-yellow-50 text-yellow-700 border border-yellow-200 rounded cursor-pointer font-medium"
              >
                {waitDays}
              </div>
            )}
            <span className="text-xs text-gray-500">day{waitDays !== 1 ? 's' : ''}</span>
          </div>
        </div>
      </div>

      <Handle
        type="source"
        position={Position.Bottom}
        className="w-3 h-3 bg-yellow-600 border-2 border-white"
      />
    </div>
  );
};
