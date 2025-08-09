import React from 'react';
import { Settings, FileText, Image, Camera, Wrench } from 'lucide-react';
import type { CreateGroupData, DocumentParsingType } from '../../types';

interface ParsingTypeStepProps {
  groupData: CreateGroupData;
  onUpdate: (updates: Partial<CreateGroupData>) => void;
  parsingTypes: DocumentParsingType[];
}

const ParsingTypeStep: React.FC<ParsingTypeStepProps> = ({ 
  groupData, 
  onUpdate, 
  parsingTypes 
}) => {
  const getParsingIcon = (type: string) => {
    switch (type) {
      case 'text':
        return FileText;
      case 'image_text':
        return Camera;
      case 'image_nontext':
        return Image;
      case 'custom':
        return Wrench;
      default:
        return FileText;
    }
  };

  const handleParsingTypeChange = (type: string) => {
    onUpdate({ 
      parsingType: type,
      // Clear custom description if switching away from custom
      ...(type !== 'custom' && { customParsingDescription: '' })
    });
  };

  return (
    <div className="space-y-6">
      <div className="text-center">
        <div className="bg-purple-100 rounded-full w-16 h-16 flex items-center justify-center mx-auto mb-4">
          <Settings className="w-8 h-8 text-purple-600" />
        </div>
        <h3 className="text-lg font-medium text-gray-900 mb-2">Document Processing</h3>
        <p className="text-gray-600">
          Choose how your documents should be processed and analyzed.
        </p>
      </div>

      <div className="space-y-3">
        {parsingTypes.map((type) => {
          const Icon = getParsingIcon(type.id);
          const isSelected = groupData.parsingType === type.id;
          
          return (
            <div key={type.id}>
              <label 
                className={`flex items-start space-x-4 p-4 border rounded-lg cursor-pointer transition-all ${
                  isSelected 
                    ? 'border-blue-500 bg-blue-50' 
                    : 'border-gray-200 hover:border-gray-300'
                }`}
              >
                <input
                  type="radio"
                  name="parsingType"
                  value={type.id}
                  checked={isSelected}
                  onChange={() => handleParsingTypeChange(type.id)}
                  className="mt-1"
                />
                
                <div className="flex items-start space-x-3 flex-1">
                  <div className={`p-2 rounded-lg ${
                    isSelected ? 'bg-blue-100' : 'bg-gray-100'
                  }`}>
                    <Icon className={`w-5 h-5 ${
                      isSelected ? 'text-blue-600' : 'text-gray-600'
                    }`} />
                  </div>
                  
                  <div className="flex-1">
                    <h4 className={`font-medium ${
                      isSelected ? 'text-blue-900' : 'text-gray-900'
                    }`}>
                      {type.label}
                    </h4>
                    <p className={`text-sm mt-1 ${
                      isSelected ? 'text-blue-700' : 'text-gray-600'
                    }`}>
                      {type.description}
                    </p>
                  </div>
                </div>
              </label>

              {/* Custom description field for custom parsing type */}
              {type.id === 'custom' && isSelected && (
                <div className="ml-8 mt-3">
                  <label htmlFor="customDescription" className="block text-sm font-medium text-gray-700 mb-2">
                    Custom Processing Instructions *
                  </label>
                  <textarea
                    id="customDescription"
                    value={groupData.customParsingDescription || ''}
                    onChange={(e) => onUpdate({ customParsingDescription: e.target.value })}
                    placeholder="Describe how these documents should be processed. For example: 'Extract key metrics from financial reports', 'Identify product names and prices from catalogs', 'Focus on research methodology and conclusions'..."
                    rows={4}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                    maxLength={1000}
                  />
                  <p className="text-xs text-gray-500 mt-1">
                    {(groupData.customParsingDescription || '').length}/1000 characters
                  </p>
                  
                  {/* Helper text */}
                  <div className="mt-3 p-3 bg-blue-50 border border-blue-200 rounded-lg">
                    <h5 className="text-sm font-medium text-blue-800 mb-1">Tips for custom instructions:</h5>
                    <ul className="text-xs text-blue-700 space-y-1">
                      <li>• Be specific about what information to extract</li>
                      <li>• Mention any special formatting or structure</li>
                      <li>• Include examples if helpful</li>
                      <li>• Specify what to ignore if relevant</li>
                    </ul>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Preview of selected type */}
      <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">
        <h4 className="font-medium text-gray-900 mb-2">Selected Processing Method</h4>
        <div className="flex items-center space-x-3">
          {(() => {
            const selectedType = parsingTypes.find(t => t.id === groupData.parsingType);
            const Icon = getParsingIcon(groupData.parsingType);
            return selectedType ? (
              <>
                <Icon className="w-5 h-5 text-gray-600" />
                <div>
                  <p className="font-medium text-gray-900">{selectedType.label}</p>
                  <p className="text-sm text-gray-600">{selectedType.description}</p>
                  {groupData.parsingType === 'custom' && groupData.customParsingDescription && (
                    <p className="text-sm text-blue-700 mt-1 font-medium">
                      Custom: {groupData.customParsingDescription.slice(0, 100)}
                      {groupData.customParsingDescription.length > 100 ? '...' : ''}
                    </p>
                  )}
                </div>
              </>
            ) : null;
          })()}
        </div>
      </div>
    </div>
  );
};

export default ParsingTypeStep; 