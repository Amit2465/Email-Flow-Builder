import React from 'react';
import { NodeTemplate } from '../../types/flow';

interface DraggableNodeCardProps {
  template: NodeTemplate;
}

export const DraggableNodeCard: React.FC<DraggableNodeCardProps> = ({ template }) => {
  const onDragStart = (event: React.DragEvent) => {
    event.dataTransfer.setData('application/reactflow', template.type);
    event.dataTransfer.effectAllowed = 'move';
  };

  const getCategoryColor = (category: string) => {
    switch (category) {
      case 'action':
        return 'bg-blue-50 border-blue-200 text-blue-700';
      case 'logic':
        return 'bg-purple-50 border-purple-200 text-purple-700';
      case 'timing':
        return 'bg-yellow-50 border-yellow-200 text-yellow-700';
      default:
        return 'bg-gray-50 border-gray-200 text-gray-700';
    }
  };

  return (
    <div
      draggable
      onDragStart={onDragStart}
      className={`p-4 rounded-lg border-2 border-dashed cursor-grab hover:shadow-md transition-all duration-200 hover:scale-105 ${getCategoryColor(template.category)}`}
    >
      <div className="flex items-start space-x-3">
        <div className="text-2xl">{template.icon}</div>
        <div className="flex-1 min-w-0">
          <h3 className="font-medium text-sm">{template.label}</h3>
          <p className="text-xs opacity-80 mt-1 line-clamp-2">
            {template.description}
          </p>
          <div className="flex items-center mt-2">
            <span className="text-xs font-medium px-2 py-1 rounded-full bg-white/50">
              {template.category}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};
