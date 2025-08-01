import React, { useState } from 'react';
import { ChevronLeft, ChevronRight, Plus } from 'lucide-react';
import { nodeTemplates } from '../../data/nodeTemplates';
import { NodeTemplate } from '../../types/flow';
import { DraggableNodeCard } from './DraggableNodeCard';

interface NodePaletteProps {
  isCollapsed: boolean;
  onToggleCollapse: () => void;
}

export const NodePalette: React.FC<NodePaletteProps> = ({
  isCollapsed,
  onToggleCollapse,
}) => {
  const [selectedCategory, setSelectedCategory] = useState<string>('all');

  const categories = [
    { id: 'all', label: 'All Nodes', count: nodeTemplates.length },
    { id: 'action', label: 'Actions', count: nodeTemplates.filter(n => n.category === 'action').length },
    { id: 'logic', label: 'Logic', count: nodeTemplates.filter(n => n.category === 'logic').length },
    { id: 'timing', label: 'Timing', count: nodeTemplates.filter(n => n.category === 'timing').length },
  ];

  const filteredNodes = selectedCategory === 'all' 
    ? nodeTemplates 
    : nodeTemplates.filter(node => node.category === selectedCategory);

  return (
    <div className={`bg-white border-r border-gray-200 h-full flex flex-col transition-all duration-300 ${
      isCollapsed ? 'w-16' : 'w-80'
    }`}>
      {/* Header */}
      <div className="p-4 border-b border-gray-100 flex items-center justify-between">
        {!isCollapsed && (
          <div>
            <h2 className="font-semibold text-gray-900">Node Palette</h2>
            <p className="text-sm text-gray-500 mt-1">Drag to add nodes</p>
          </div>
        )}
        <button
          onClick={onToggleCollapse}
          className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
        >
          {isCollapsed ? (
            <ChevronRight className="w-4 h-4 text-gray-600" />
          ) : (
            <ChevronLeft className="w-4 h-4 text-gray-600" />
          )}
        </button>
      </div>

      {!isCollapsed && (
        <>
          {/* Category Filter */}
          <div className="p-4 border-b border-gray-100">
            <div className="space-y-1">
              {categories.map((category) => (
                <button
                  key={category.id}
                  onClick={() => setSelectedCategory(category.id)}
                  className={`w-full text-left px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                    selectedCategory === category.id
                      ? 'bg-blue-50 text-blue-700 border border-blue-200'
                      : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span>{category.label}</span>
                    <span className={`text-xs px-2 py-1 rounded-full ${
                      selectedCategory === category.id
                        ? 'bg-blue-100 text-blue-600'
                        : 'bg-gray-100 text-gray-500'
                    }`}>
                      {category.count}
                    </span>
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* Node Cards */}
          <div className="flex-1 overflow-y-auto p-4">
            <div className="space-y-3">
              {filteredNodes.map((template) => (
                <DraggableNodeCard key={template.type} template={template} />
              ))}
            </div>
          </div>
        </>
      )}

      {isCollapsed && (
        <div className="flex-1 flex flex-col items-center pt-4 space-y-3">
          {nodeTemplates.slice(0, 3).map((template) => (
            <div
              key={template.type}
              className="w-10 h-10 rounded-lg bg-gray-50 border-2 border-dashed border-gray-300 flex items-center justify-center text-lg cursor-pointer hover:bg-gray-100 hover:border-gray-400 transition-all"
              title={template.label}
            >
              {template.icon}
            </div>
          ))}
          <button className="w-10 h-10 rounded-lg bg-blue-50 border-2 border-dashed border-blue-300 flex items-center justify-center text-blue-600 hover:bg-blue-100 hover:border-blue-400 transition-all">
            <Plus className="w-4 h-4" />
          </button>
        </div>
      )}
    </div>
  );
};
