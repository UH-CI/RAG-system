import React from 'react';
import { FileText } from 'lucide-react';
import type { CreateGroupData } from '../../types';

interface GroupNameStepProps {
  groupData: CreateGroupData;
  onUpdate: (updates: Partial<CreateGroupData>) => void;
}

const GroupNameStep: React.FC<GroupNameStepProps> = ({ groupData, onUpdate }) => {
  return (
    <div className="space-y-6">
      <div className="text-center">
        <div className="bg-blue-100 rounded-full w-16 h-16 flex items-center justify-center mx-auto mb-4">
          <FileText className="w-8 h-8 text-blue-600" />
        </div>
        <h3 className="text-lg font-medium text-gray-900 mb-2">Name Your Group</h3>
        <p className="text-gray-600">
          Give your document group a descriptive name and optional description.
        </p>
      </div>

      <div className="space-y-4">
        <div>
          <label htmlFor="groupName" className="block text-sm font-medium text-gray-700 mb-2">
            Group Name *
          </label>
          <input
            type="text"
            id="groupName"
            value={groupData.name}
            onChange={(e) => onUpdate({ name: e.target.value })}
            placeholder="e.g., Marketing Materials, Research Papers, Course Documents"
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            maxLength={100}
          />
          <p className="text-xs text-gray-500 mt-1">
            {groupData.name.length}/100 characters
          </p>
        </div>

        <div>
          <label htmlFor="groupDescription" className="block text-sm font-medium text-gray-700 mb-2">
            Description (Optional)
          </label>
          <textarea
            id="groupDescription"
            value={groupData.description || ''}
            onChange={(e) => onUpdate({ description: e.target.value })}
            placeholder="Describe the purpose or content of this group..."
            rows={3}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outli`ne`-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            maxLength={500}
          />
          <p className="text-xs text-gray-500 mt-1">
            {(groupData.description || '').length}/500 characters
          </p>
        </div>
      </div>

    </div>
  );
};

export default GroupNameStep; 