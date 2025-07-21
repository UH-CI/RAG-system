import React, { useState, useCallback } from 'react';
import { X, ArrowLeft, ArrowRight, CheckCircle } from 'lucide-react';
import type { CreateGroupData, CreateGroupStep, DocumentParsingType, UploadProgress } from '../types';
import { createCollection, uploadDocuments } from '../services/api';
import GroupNameStep from './CreateGroupModal/GroupNameStep';
import DocumentUploadStep from './CreateGroupModal/DocumentUploadStep';
import ParsingTypeStep from './CreateGroupModal/ParsingTypeStep';
import ConfirmationStep from './CreateGroupModal/ConfirmationStep';

interface CreateGroupModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

const STEPS: CreateGroupStep[] = [
  { id: 1, title: 'Group Details', description: 'Name your group and add a description' },
  { id: 2, title: 'Upload Documents', description: 'Add documents to your group' },
  { id: 3, title: 'Parsing Configuration', description: 'Choose how documents should be processed' },
  { id: 4, title: 'Review & Create', description: 'Review your settings and create the group' },
];

const PARSING_TYPES: DocumentParsingType[] = [
  {
    id: 'text',
    label: 'Text Documents',
    description: 'PDF, Word, TXT files with readable text content',
  },
  {
    id: 'image_text',
    label: 'Images with Text',
    description: 'Screenshots, scanned documents, images containing text (OCR will be applied)',
  },
  {
    id: 'image_nontext',
    label: 'Images without Text',
    description: 'Photos, diagrams, charts, visual content without readable text',
  },
  {
    id: 'custom',
    label: 'Custom Processing',
    description: 'Specify custom instructions for how documents should be processed',
  },
];

const CreateGroupModal: React.FC<CreateGroupModalProps> = ({
  isOpen,
  onClose,
  onSuccess,
}) => {
  const [currentStep, setCurrentStep] = useState(1);
  const [groupData, setGroupData] = useState<CreateGroupData>({
    name: '',
    description: '',
    documents: [],
    parsingType: 'text',
    customParsingDescription: '',
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [uploadProgress, setUploadProgress] = useState<UploadProgress[]>([]);

  const resetModal = useCallback(() => {
    setCurrentStep(1);
    setGroupData({
      name: '',
      description: '',
      documents: [],
      parsingType: 'text',
      customParsingDescription: '',
    });
    setLoading(false);
    setError(null);
    setUploadProgress([]);
  }, []);

  const handleClose = useCallback(() => {
    if (!loading) {
      resetModal();
      onClose();
    }
  }, [loading, resetModal, onClose]);

  const handleNext = useCallback(() => {
    if (currentStep < STEPS.length) {
      setCurrentStep(prev => prev + 1);
      setError(null);
    }
  }, [currentStep]);

  const handlePrevious = useCallback(() => {
    if (currentStep > 1) {
      setCurrentStep(prev => prev - 1);
      setError(null);
    }
  }, [currentStep]);

  const updateGroupData = useCallback((updates: Partial<CreateGroupData>) => {
    setGroupData(prev => ({ ...prev, ...updates }));
  }, []);

  const handleProgressUpdate = useCallback((fileName: string, progress: number) => {
    setUploadProgress(prev => 
      prev.map(item => 
        item.fileName === fileName 
          ? { ...item, progress, status: progress === 100 ? 'completed' : 'uploading' }
          : item
      )
    );
  }, []);

  const handleCreateGroup = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      // Step 1: Create the group
      const createResponse = await createCollection(groupData.name);
      const collectionName = createResponse.collection_name;

      // Step 2: Initialize upload progress
      const initialProgress: UploadProgress[] = groupData.documents.map(file => ({
        fileName: file.name,
        progress: 0,
        status: 'pending',
      }));
      setUploadProgress(initialProgress);

      // Step 3: Upload documents
      await uploadDocuments(
        collectionName,
        groupData.documents,
        groupData.parsingType,
        groupData.customParsingDescription,
        handleProgressUpdate
      );

      // Success!
      onSuccess();
      handleClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create group');
    } finally {
      setLoading(false);
    }
  }, [groupData, onSuccess, handleClose, handleProgressUpdate]);

  const canProceed = useCallback(() => {
    switch (currentStep) {
      case 1:
        return groupData.name.trim().length > 0;
      case 2:
        return groupData.documents.length > 0;
      case 3:
        return groupData.parsingType === 'custom' 
          ? (groupData.customParsingDescription?.trim().length ?? 0) > 0
          : true;
      case 4:
        return true;
      default:
        return false;
    }
  }, [currentStep, groupData]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full max-h-[90vh] overflow-hidden">
        {/* Header */}
        <div className="border-b border-gray-200 p-6">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-xl font-semibold text-gray-900">Create New Group</h2>
              <p className="text-sm text-gray-500 mt-1">
                Step {currentStep} of {STEPS.length}: {STEPS[currentStep - 1]?.title || 'Unknown Step'}
              </p>
            </div>
            <button
              onClick={handleClose}
              disabled={loading}
              className="text-gray-400 hover:text-gray-600 transition-colors disabled:opacity-50"
            >
              <X className="w-6 h-6" />
            </button>
          </div>

          {/* Progress Bar */}
          <div className="mt-4">
            <div className="flex items-center space-x-2">
              {STEPS.map((step, index) => (
                <React.Fragment key={step.id}>
                  <div className={`flex items-center justify-center w-8 h-8 rounded-full text-sm font-medium ${
                    index + 1 < currentStep
                      ? 'bg-green-500 text-white'
                      : index + 1 === currentStep
                      ? 'bg-blue-500 text-white'
                      : 'bg-gray-200 text-gray-600'
                  }`}>
                    {index + 1 < currentStep ? (
                      <CheckCircle className="w-4 h-4" />
                    ) : (
                      step.id
                    )}
                  </div>
                  {index < STEPS.length - 1 && (
                    <div className={`flex-1 h-1 rounded ${
                      index + 1 < currentStep ? 'bg-green-500' : 'bg-gray-200'
                    }`} />
                  )}
                </React.Fragment>
              ))}
            </div>
          </div>
        </div>

        {/* Content */}
        <div className="p-6 flex-1 overflow-y-auto max-h-96">
          {error && (
            <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg">
              <p className="text-red-800 text-sm">{error}</p>
            </div>
          )}

          {currentStep === 1 && (
            <GroupNameStep
              groupData={groupData}
              onUpdate={updateGroupData}
            />
          )}

          {currentStep === 2 && (
            <DocumentUploadStep
              groupData={groupData}
              onUpdate={updateGroupData}
            />
          )}

          {currentStep === 3 && (
            <ParsingTypeStep
              groupData={groupData}
              onUpdate={updateGroupData}
              parsingTypes={PARSING_TYPES}
            />
          )}

          {currentStep === 4 && (
            <ConfirmationStep
              groupData={groupData}
              parsingTypes={PARSING_TYPES}
              uploadProgress={uploadProgress}
              loading={loading}
            />
          )}
        </div>

        {/* Footer */}
        <div className="border-t border-gray-200 p-6">
          <div className="flex items-center justify-between">
            <button
              onClick={handlePrevious}
              disabled={currentStep === 1 || loading}
              className="flex items-center space-x-2 px-4 py-2 text-gray-600 hover:text-gray-800 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <ArrowLeft className="w-4 h-4" />
              <span>Previous</span>
            </button>

            <div className="flex items-center space-x-3">
              {currentStep < STEPS.length ? (
                <button
                  onClick={handleNext}
                  disabled={!canProceed() || loading}
                  className="flex items-center space-x-2 px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <span>Next</span>
                  <ArrowRight className="w-4 h-4" />
                </button>
              ) : (
                <button
                  onClick={handleCreateGroup}
                  disabled={!canProceed() || loading}
                  className="flex items-center space-x-2 px-6 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {loading ? 'Creating...' : 'Create Group'}
                </button>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default CreateGroupModal; 