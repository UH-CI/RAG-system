import React from 'react';
import { CheckCircle, Clock, AlertCircle, File, Settings, Upload, Loader2 } from 'lucide-react';
import type { CreateGroupData, DocumentParsingType, UploadProgress } from '../../types';

interface ConfirmationStepProps {
  groupData: CreateGroupData;
  parsingTypes: DocumentParsingType[];
  uploadProgress: UploadProgress[];
  loading: boolean;
}

const ConfirmationStep: React.FC<ConfirmationStepProps> = ({
  groupData,
  parsingTypes,
  uploadProgress,
  loading,
}) => {
  const selectedParsingType = parsingTypes.find(t => t.id === groupData.parsingType);
  
  const formatFileSize = (bytes: number) => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  const getProgressIcon = (status: UploadProgress['status']) => {
    switch (status) {
      case 'completed':
        return <CheckCircle className="w-4 h-4 text-green-500" />;
      case 'uploading':
        return <Loader2 className="w-4 h-4 text-blue-500 animate-spin" />;
      case 'error':
        return <AlertCircle className="w-4 h-4 text-red-500" />;
      default:
        return <Clock className="w-4 h-4 text-gray-400" />;
    }
  };

  return (
    <div className="space-y-6">
      <div className="text-center">
        <div className="bg-green-100 rounded-full w-16 h-16 flex items-center justify-center mx-auto mb-4">
          <CheckCircle className="w-8 h-8 text-green-600" />
        </div>
        <h3 className="text-lg font-medium text-gray-900 mb-2">
          {loading ? 'Creating Group...' : 'Review & Create'}
        </h3>
        <p className="text-gray-600">
          {loading 
            ? 'Please wait while we create your group and upload your documents.'
            : 'Review your settings before creating the group.'
          }
        </p>
      </div>

      {!loading && (
        <div className="space-y-4">
          {/* Group Details Summary */}
          <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">
            <h4 className="font-medium text-gray-900 mb-3 flex items-center">
              <File className="w-4 h-4 mr-2" />
              Group Details
            </h4>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-gray-600">Name:</span>
                <span className="font-medium text-gray-900">{groupData.name}</span>
              </div>
              {groupData.description && (
                <div className="flex justify-between">
                  <span className="text-gray-600">Description:</span>
                  <span className="font-medium text-gray-900 text-right max-w-xs">
                    {groupData.description}
                  </span>
                </div>
              )}
            </div>
          </div>

          {/* Documents Summary */}
          <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">
            <h4 className="font-medium text-gray-900 mb-3 flex items-center">
              <Upload className="w-4 h-4 mr-2" />
              Documents ({groupData.documents.length})
            </h4>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-gray-600">Total files:</span>
                <span className="font-medium text-gray-900">{groupData.documents.length}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-600">Total size:</span>
                <span className="font-medium text-gray-900">
                  {formatFileSize(
                    groupData.documents.reduce((total, file) => total + file.size, 0)
                  )}
                </span>
              </div>
            </div>
            
            {groupData.documents.length > 0 && (
              <div className="mt-3 pt-3 border-t border-gray-300">
                <div className="max-h-32 overflow-y-auto space-y-1">
                  {groupData.documents.map((file, index) => (
                    <div key={index} className="flex justify-between text-xs">
                      <span className="text-gray-600 truncate">{file.name}</span>
                      <span className="text-gray-500 ml-2">{formatFileSize(file.size)}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Processing Settings Summary */}
          <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">
            <h4 className="font-medium text-gray-900 mb-3 flex items-center">
              <Settings className="w-4 h-4 mr-2" />
              Processing Configuration
            </h4>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-gray-600">Type:</span>
                <span className="font-medium text-gray-900">
                  {selectedParsingType?.label || groupData.parsingType}
                </span>
              </div>
              {selectedParsingType && (
                <div className="text-gray-600 text-xs">
                  {selectedParsingType.description}
                </div>
              )}
              {groupData.parsingType === 'custom' && groupData.customParsingDescription && (
                <div className="mt-2 p-2 bg-blue-50 border border-blue-200 rounded">
                  <span className="text-xs font-medium text-blue-800">Custom Instructions:</span>
                  <p className="text-xs text-blue-700 mt-1">
                    {groupData.customParsingDescription}
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Upload Progress */}
      {loading && uploadProgress.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-lg p-4">
          <h4 className="font-medium text-gray-900 mb-3 flex items-center">
            <Upload className="w-4 h-4 mr-2" />
            Upload Progress
          </h4>
          <div className="space-y-3">
            {uploadProgress.map((progress, index) => (
              <div key={index} className="space-y-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center space-x-2">
                    {getProgressIcon(progress.status)}
                    <span className="text-sm text-gray-900 truncate">
                      {progress.fileName}
                    </span>
                  </div>
                  <span className="text-xs text-gray-500">
                    {progress.progress}%
                  </span>
                </div>
                
                <div className="w-full bg-gray-200 rounded-full h-2">
                  <div
                    className={`h-2 rounded-full transition-all duration-300 ${
                      progress.status === 'completed'
                        ? 'bg-green-500'
                        : progress.status === 'error'
                        ? 'bg-red-500'
                        : 'bg-blue-500'
                    }`}
                    style={{ width: `${progress.progress}%` }}
                  />
                </div>
                
                {progress.error && (
                  <p className="text-xs text-red-600">{progress.error}</p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Success/Loading State */}
      {loading && (
        <div className="text-center py-4">
          <Loader2 className="w-8 h-8 text-blue-600 animate-spin mx-auto mb-2" />
          <p className="text-sm text-gray-600">
            Creating group and processing documents...
          </p>
        </div>
      )}
    </div>
  );
};

export default ConfirmationStep; 