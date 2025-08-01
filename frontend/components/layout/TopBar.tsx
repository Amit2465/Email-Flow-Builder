import React from 'react';
import { Play, Save, Download, Upload, Settings } from 'lucide-react';
import { useFlowStore } from '../../store/flowStore';

export const TopBar: React.FC = () => {
  const { isValidFlow, validationErrors, exportFlow } = useFlowStore();

  const handleRunFlow = () => {
    if (isValidFlow) {
      const flowData = exportFlow();
      console.log('Exporting flow:', flowData);
      // In a real app, this would trigger the campaign
      alert('Campaign flow exported successfully!');
    } else {
      alert(`Please fix the following errors:\n${validationErrors.join('\n')}`);
    }
  };

  const handleExport = () => {
    const flowData = exportFlow();
    const blob = new Blob([JSON.stringify(flowData, null, 2)], {
      type: 'application/json',
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'email-campaign-flow.json';
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between">
      <div className="flex items-center space-x-4">
        <h1 className="text-xl font-semibold text-gray-900">
          Email Campaign Builder
        </h1>
        <div className="flex items-center space-x-2">
          {!isValidFlow && validationErrors.length > 0 && (
            <div className="flex items-center space-x-1 text-red-600 text-sm">
              <span className="w-2 h-2 bg-red-500 rounded-full"></span>
              <span>{validationErrors.length} error{validationErrors.length > 1 ? 's' : ''}</span>
            </div>
          )}
          {isValidFlow && (
            <div className="flex items-center space-x-1 text-green-600 text-sm">
              <span className="w-2 h-2 bg-green-500 rounded-full"></span>
              <span>Flow valid</span>
            </div>
          )}
        </div>
      </div>

      <div className="flex items-center space-x-3">
        <button className="flex items-center space-x-2 px-3 py-2 text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded-lg transition-colors">
          <Save className="w-4 h-4" />
          <span className="text-sm font-medium">Save</span>
        </button>
        
        <button 
          onClick={handleExport}
          className="flex items-center space-x-2 px-3 py-2 text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded-lg transition-colors"
        >
          <Download className="w-4 h-4" />
          <span className="text-sm font-medium">Export</span>
        </button>

        <button className="flex items-center space-x-2 px-3 py-2 text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded-lg transition-colors">
          <Upload className="w-4 h-4" />
          <span className="text-sm font-medium">Import</span>
        </button>

        <button className="flex items-center space-x-2 px-3 py-2 text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded-lg transition-colors">
          <Settings className="w-4 h-4" />
          <span className="text-sm font-medium">Settings</span>
        </button>

        <button
          onClick={handleRunFlow}
          disabled={!isValidFlow}
          className={`flex items-center space-x-2 px-4 py-2 rounded-lg font-medium transition-all ${
            isValidFlow
              ? 'bg-blue-600 text-white hover:bg-blue-700 shadow-sm hover:shadow-md'
              : 'bg-gray-300 text-gray-500 cursor-not-allowed'
          }`}
        >
          <Play className="w-4 h-4" />
          <span>Run Flow</span>
        </button>
      </div>
    </div>
  );
};
