import React from 'react';
import { Handle, Position } from '@xyflow/react';
import { Play } from 'lucide-react';

export const StartNode: React.FC<any> = ({ data }) => {
  return (
    <div className="bg-gradient-to-r from-green-400 to-green-600 text-white px-6 py-4 rounded-lg shadow-lg border-2 border-green-500 min-w-[200px]">
      <div className="flex items-center space-x-3">
        <div className="w-8 h-8 bg-white/20 rounded-full flex items-center justify-center">
          <Play className="w-4 h-4" />
        </div>
        <div>
          <h3 className="font-semibold text-sm">{data.label}</h3>
          <p className="text-xs opacity-90">Campaign entry point</p>
        </div>
      </div>
      
      <Handle
        type="source"
        position={Position.Bottom}
        className="w-3 h-3 bg-green-600 border-2 border-white"
      />
    </div>
  );
};
