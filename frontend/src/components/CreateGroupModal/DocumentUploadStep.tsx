import React, { useCallback, useState } from 'react';
import { Upload, File, X, AlertCircle } from 'lucide-react';
import type { CreateGroupData } from '../../types';

interface DocumentUploadStepProps {
  groupData: CreateGroupData;
  onUpdate: (updates: Partial<CreateGroupData>) => void;
}

const DocumentUploadStep: React.FC<DocumentUploadStepProps> = ({ groupData, onUpdate }) => {
  const [dragActive, setDragActive] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleFiles = useCallback((files: FileList | null) => {
    if (!files) return;

    const fileArray = Array.from(files);
    const validFiles: File[] = [];
    let hasError = false;

    // Validate files
    fileArray.forEach(file => {
      // Check file size (50MB limit)
      if (file.size > 50 * 1024 * 1024) {
        setError(`File "${file.name}" is too large. Maximum size is 50MB.`);
        hasError = true;
        return;
      }

      // Check file type (basic validation)
      const validExtensions = [
        '.pdf', '.doc', '.docx', '.txt', '.rtf',
        '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff',
        '.ppt', '.pptx', '.xls', '.xlsx'
      ];
      
      const hasValidExtension = validExtensions.some(ext => 
        file.name.toLowerCase().endsWith(ext)
      );
      
      if (!hasValidExtension) {
        setError(`File "${file.name}" has an unsupported format.`);
        hasError = true;
        return;
      }

      validFiles.push(file);
    });

    if (!hasError && validFiles.length > 0) {
      setError(null);
      // Add to existing documents, avoiding duplicates
      const existingNames = groupData.documents.map(f => f.name);
      const newFiles = validFiles.filter(f => !existingNames.includes(f.name));
      onUpdate({ documents: [...groupData.documents, ...newFiles] });
    }
  }, [groupData.documents, onUpdate]);

  const handleDrag = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    handleFiles(e.dataTransfer.files);
  }, [handleFiles]);

  const handleInputChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    handleFiles(e.target.files);
    // Reset input value to allow re-uploading the same file
    e.target.value = '';
  }, [handleFiles]);

  const removeFile = useCallback((index: number) => {
    const newDocuments = groupData.documents.filter((_, i) => i !== index);
    onUpdate({ documents: newDocuments });
  }, [groupData.documents, onUpdate]);

  const formatFileSize = (bytes: number) => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  return (
    <div className="space-y-6">
      <div className="text-center">
        <div className="bg-green-100 rounded-full w-16 h-16 flex items-center justify-center mx-auto mb-4">
          <Upload className="w-8 h-8 text-green-600" />
        </div>
        <h3 className="text-lg font-medium text-gray-900 mb-2">Upload Documents</h3>
        <p className="text-gray-600">
          Add the documents you want to include in this group.
        </p>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <div className="flex items-center space-x-2 text-red-800">
            <AlertCircle className="w-4 h-4" />
            <span className="font-medium">Upload Error</span>
          </div>
          <p className="text-red-700 text-sm mt-1">{error}</p>
        </div>
      )}

      {/* Upload Area */}
      <div
        className={`border-2 border-dashed rounded-lg p-8 text-center transition-colors ${
          dragActive
            ? 'border-blue-400 bg-blue-50'
            : 'border-gray-300 hover:border-gray-400'
        }`}
        onDragEnter={handleDrag}
        onDragLeave={handleDrag}
        onDragOver={handleDrag}
        onDrop={handleDrop}
      >
        <Upload className="w-12 h-12 text-gray-400 mx-auto mb-4" />
        <h4 className="text-lg font-medium text-gray-900 mb-2">
          Drop files here or click to browse
        </h4>
        <p className="text-gray-600 mb-4">
          Supports PDF, Word, PowerPoint, Excel, text files, and images
        </p>
        <p className="text-sm text-gray-500 mb-4">
          Maximum file size: 50MB each
        </p>
        
        <input
          type="file"
          multiple
          onChange={handleInputChange}
          className="hidden"
          id="file-upload"
          accept=".pdf,.doc,.docx,.txt,.rtf,.jpg,.jpeg,.png,.gif,.bmp,.tiff,.ppt,.pptx,.xls,.xlsx"
        />
        <label
          htmlFor="file-upload"
          className="inline-flex items-center px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 cursor-pointer transition-colors"
        >
          Choose Files
        </label>
      </div>

      {/* File List */}
      {groupData.documents.length > 0 && (
        <div>
          <h4 className="font-medium text-gray-900 mb-3">
            Selected Files ({groupData.documents.length})
          </h4>
          <div className="space-y-2 max-h-60 overflow-y-auto">
            {groupData.documents.map((file, index) => (
              <div
                key={`${file.name}-${index}`}
                className="flex items-center justify-between p-3 bg-gray-50 rounded-lg border"
              >
                <div className="flex items-center space-x-3 flex-1 min-w-0">
                  <File className="w-5 h-5 text-gray-500 flex-shrink-0" />
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-gray-900 truncate">
                      {file.name}
                    </p>
                    <p className="text-xs text-gray-500">
                      {formatFileSize(file.size)}
                    </p>
                  </div>
                </div>
                <button
                  onClick={() => removeFile(index)}
                  className="p-1 text-gray-400 hover:text-red-600 transition-colors"
                  title="Remove file"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            ))}
          </div>
          
          <div className="mt-3 text-sm text-gray-600">
            Total size: {formatFileSize(
              groupData.documents.reduce((total, file) => total + file.size, 0)
            )}
          </div>
        </div>
      )}

      {groupData.documents.length === 0 && (
        <div className="text-center py-4">
          <p className="text-gray-500">No files selected yet</p>
        </div>
      )}
    </div>
  );
};

export default DocumentUploadStep; 