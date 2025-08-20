import React, { useState, useEffect, useRef } from "react";
import { X, Check, CheckCircle, Clock, AlertTriangle } from "lucide-react";
import { createCollection, uploadPDFToCollection, uploadFromGoogleDrive, uploadFromWebUrl, extractText, chunkText } from "../services/api";
import GroupNameStep from "./CreateGroupModal/GroupNameStep";
import DocumentUploadStep from "./CreateGroupModal/DocumentUploadStep";
import type { CreateGroupData } from "../types";

interface CreateGroupModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: (collection: any) => void;
}

interface CollectionProgress {
  id: string;
  name: string;
  collectionPath?: string;
  currentStep: number;
  totalSteps: number;
  status: 'idle' | 'creating' | 'uploading' | 'extracting' | 'chunking' | 'completed' | 'error' | 'paused';
  error?: string;
  uploadProgress?: number;
  canContinueInBackground?: boolean;
  startTime?: Date;
  completedSteps: string[];
  stepStatuses: {
    create: 'pending' | 'processing' | 'completed' | 'error';
    upload: 'pending' | 'processing' | 'completed' | 'error';
    extract: 'pending' | 'processing' | 'completed' | 'error';
    chunk: 'pending' | 'processing' | 'completed' | 'error';
  };
}

const STEPS = [
  { id: 1, title: "Collection Information", description: "Name and describe your collection" },
  { id: 2, title: "Upload Documents", description: "Add files to your collection" },
  { id: 3, title: "Chunking Settings", description: "Configure document processing" }
];

const PROCESSING_STEPS = [
  { id: 'create', name: 'Create Collection', description: 'Setting up collection structure' },
  { id: 'upload', name: 'Upload Documents', description: 'Transferring files to server' },
  { id: 'extract', name: 'Extract Text', description: 'Processing documents and extracting content' },
  { id: 'chunk', name: 'Chunk Text', description: 'Breaking content into searchable segments' }
];
// Global state for tracking collections being processed
let globalCollectionProgress: CollectionProgress | null = null;

const CreateGroupModal: React.FC<CreateGroupModalProps> = ({ isOpen, onClose, onSuccess }) => {
  const modalRef = useRef<HTMLDivElement>(null);
  const [currentStep, setCurrentStep] = useState(1);
  const [stepLoading, setStepLoading] = useState(false);
  const [collectionProgress, setCollectionProgress] = useState<CollectionProgress | null>(
    globalCollectionProgress
  );
  
  // Form state
  const [groupData, setGroupData] = useState<CreateGroupData>({
    name: '',
    description: '',
    documents: [],
    parsingType: 'text',
    chunkSize: 1000,
    chunkOverlap: 200,
    useAI: false,
    uploadMethod: 'file'
  });

  // Upload method states
  const [uploadMethod, setUploadMethod] = useState<'file' | 'drive' | 'web'>('file');
  const [driveLink, setDriveLink] = useState<string>("");
  const [recursive, setRecursive] = useState<boolean>(false);
  const [webUrl, setWebUrl] = useState<string>("");
  
  // Text extraction settings
  const [extractTables, setExtractTables] = useState<boolean>(false);
  const [extractImagesWithText, setExtractImagesWithText] = useState<boolean>(false);
  const [extractImagesWithoutText, setExtractImagesWithoutText] = useState<boolean>(false);
  const [extractionText, setExtractionText] = useState<string>("");
  const [nullIsOkay, setNullIsOkay] = useState<boolean>(false);
  const [numWorkers, setNumWorkers] = useState<number>(1);
  const [numLevelsDeep, setNumLevelsDeep] = useState<number>(1);
  
  // Chunking settings
  const [chunkingMethod, setChunkingMethod] = useState<'paragraph' | 'fixed' | 'semantic'>('paragraph');
  const [chunkSize, setChunkSize] = useState<number>(1000);
  const [chunkOverlap, setChunkOverlap] = useState<number>(100);
  const [useAI, setUseAI] = useState<boolean>(false);
  const [contextPrompt, setContextPrompt] = useState<string>("");

  // Handle outside click to close modal
  useEffect(() => {
    const handleOutsideClick = (event: MouseEvent) => {
      if (modalRef.current && !modalRef.current.contains(event.target as Node)) {
        // Don't close if processing
        if (!stepLoading && (!collectionProgress || collectionProgress.status === 'completed' || collectionProgress.status === 'error')) {
          onClose();
        }
      }
    };

    if (isOpen) {
      document.addEventListener('mousedown', handleOutsideClick);
    }

    return () => {
      document.removeEventListener('mousedown', handleOutsideClick);
    };
  }, [isOpen, onClose, collectionProgress, stepLoading]);

  // Reset form when modal opens (unless resuming)
  useEffect(() => {
    if (isOpen && !collectionProgress) {
      setCurrentStep(1);
      setGroupData({
        name: '',
        description: '',
        documents: [],
        parsingType: 'text',
        chunkSize: 1000,
        chunkOverlap: 200,
        useAI: false,
        uploadMethod: 'file'
      });
      setStepLoading(false);
    }
  }, [isOpen, collectionProgress]);

  // Sync with global progress state
  useEffect(() => {
    setCollectionProgress(globalCollectionProgress);
  }, [isOpen]);

  const updateCollectionProgress = (progress: CollectionProgress | null) => {
    setCollectionProgress(progress);
    globalCollectionProgress = progress;
  };

  const updateGroupData = (updates: Partial<CreateGroupData>) => {
    setGroupData(prev => ({ ...prev, ...updates }));
  };

  // Step validation
  const isStepValid = (step: number): boolean => {
    switch (step) {
      case 1:
        return groupData.name.trim().length > 0;
      case 2:
        if (uploadMethod === 'file') {
          return groupData.documents.length > 0;
        } else if (uploadMethod === 'drive') {
          return driveLink.trim().length > 0;
        } else if (uploadMethod === 'web') {
          return webUrl.trim().length > 0;
        }
        return false;
      case 3:
        return true; // Chunking settings have defaults
      default:
        return false;
    }
  };

  const canProceedToStep = (step: number): boolean => {
    for (let i = 1; i < step; i++) {
      if (!isStepValid(i)) return false;
    }
    return true;
  };

  // Step 1 -> 2: Create Collection
  const handleCreateCollection = async () => {
    if (!isStepValid(1)) return;

    setStepLoading(true);
    
    const initialProgress: CollectionProgress = {
      id: Date.now().toString(),
      name: groupData.name,
      currentStep: 1,
      totalSteps: 4,
      status: 'creating',
      startTime: new Date(),
      completedSteps: [],
      stepStatuses: {
        create: 'processing',
        upload: 'pending',
        extract: 'pending',
        chunk: 'pending'
      }
    };
    
    updateCollectionProgress(initialProgress);

    try {
      const { collection_path } = await createCollection(groupData.name);

      updateCollectionProgress({
        ...initialProgress,
        collectionPath: collection_path,
        status: 'idle',
        completedSteps: ['create'],
        stepStatuses: {
          create: 'completed',
          upload: 'pending',
          extract: 'pending',
          chunk: 'pending'
        }
      });

      // Move to next step
      setCurrentStep(2);
    } catch (error) {
      console.error("Error creating collection:", error);
      updateCollectionProgress({
        ...initialProgress,
        status: 'error',
        error: error instanceof Error ? error.message : 'Failed to create collection',
        stepStatuses: {
          create: 'error',
          upload: 'pending',
          extract: 'pending',
          chunk: 'pending'
        }
      });
    } finally {
      setStepLoading(false);
    }
  };

  // Step 2 -> 3: Upload Documents
  const handleUploadDocuments = async () => {
    if (!isStepValid(2) || !collectionProgress?.collectionPath) return;

    setStepLoading(true);
    
    updateCollectionProgress({
      ...collectionProgress,
      status: 'uploading',
      stepStatuses: {
        ...collectionProgress.stepStatuses,
        upload: 'processing'
      }
    });

    try {
      // Upload documents based on method
      if (uploadMethod === 'file' && groupData.documents.length > 0) {
        await uploadPDFToCollection(groupData.documents, collectionProgress.collectionPath);
      } else if (uploadMethod === 'drive' && driveLink) {
        await uploadFromGoogleDrive(driveLink, collectionProgress.collectionPath, recursive);
      } else if (uploadMethod === 'web' && webUrl) {
        await uploadFromWebUrl(webUrl, collectionProgress.collectionPath, extractionText, nullIsOkay, numWorkers, numLevelsDeep);
      }

      updateCollectionProgress({
        ...collectionProgress,
        status: 'idle',
        completedSteps: ['create', 'upload'],
        stepStatuses: {
          ...collectionProgress.stepStatuses,
          upload: 'completed'
        }
      });

      // Move to next step
      setCurrentStep(3);
    } catch (error) {
      console.error("Error uploading documents:", error);
      updateCollectionProgress({
        ...collectionProgress,
        status: 'error',
        error: error instanceof Error ? error.message : 'Failed to upload documents',
        stepStatuses: {
          ...collectionProgress.stepStatuses,
          upload: 'error'
        }
      });
    } finally {
      setStepLoading(false);
    }
  };

  // Step 3: Process Documents (Extract + Chunk)
  const handleProcessDocuments = async () => {
    if (!collectionProgress?.collectionPath) return;

    setStepLoading(true);
    
    try {
      // Step 1: Text extraction
      updateCollectionProgress({
        ...collectionProgress,
        status: 'extracting',
        stepStatuses: {
          ...collectionProgress.stepStatuses,
          extract: 'processing'
        }
      });

      await extractText(
        collectionProgress.collectionPath,
        extractTables,
        extractImagesWithText,
        extractImagesWithoutText
      );

      updateCollectionProgress({
        ...collectionProgress,
        status: 'chunking',
        completedSteps: ['create', 'upload', 'extract'],
        stepStatuses: {
          ...collectionProgress.stepStatuses,
          extract: 'completed',
          chunk: 'processing'
        }
      });

      // Step 2: Chunking
      await chunkText(
        collectionProgress.collectionPath,
        chunkingMethod,
        chunkSize,
        chunkOverlap,
        useAI,
        contextPrompt
      );

      updateCollectionProgress({
        ...collectionProgress,
        status: 'completed',
        completedSteps: ['create', 'upload', 'extract', 'chunk'],
        stepStatuses: {
          create: 'completed',
          upload: 'completed',
          extract: 'completed',
          chunk: 'completed'
        }
      });

      // Success callback with collection info
      onSuccess({
        name: groupData.name,
        path: collectionProgress.collectionPath,
        num_documents: uploadMethod === 'file' ? groupData.documents.length : 0
      });

      // Clear global progress after success
      setTimeout(() => {
        updateCollectionProgress(null);
        onClose();
      }, 2000);

    } catch (error) {
      console.error("Error processing documents:", error);
      updateCollectionProgress({
        ...collectionProgress,
        status: 'error',
        error: error instanceof Error ? error.message : 'Failed to process documents',
        stepStatuses: {
          ...collectionProgress.stepStatuses,
          extract: collectionProgress.status === 'extracting' ? 'error' : collectionProgress.stepStatuses.extract,
          chunk: collectionProgress.status === 'chunking' ? 'error' : collectionProgress.stepStatuses.chunk
        }
      });
    } finally {
      setStepLoading(false);
    }
  };

  const handleNext = async () => {
    if (!isStepValid(currentStep)) return;

    if (currentStep === 1) {
      // Create collection before moving to step 2
      await handleCreateCollection();
    } else if (currentStep === 2) {
      // Upload documents before moving to step 3
      await handleUploadDocuments();
    } else if (currentStep === 3) {
      // Process documents (final step)
      await handleProcessDocuments();
    }
  };

  const handlePrevious = () => {
    if (currentStep > 1 && !stepLoading) {
      setCurrentStep(prev => prev - 1);
    }
  };

  const handleStepClick = (step: number) => {
    if (canProceedToStep(step) && !stepLoading) {
      setCurrentStep(step);
    }
  };

  const handleClose = () => {
    if (stepLoading || (collectionProgress && 
        collectionProgress.status !== 'completed' && 
        collectionProgress.status !== 'error' &&
        collectionProgress.status !== 'idle')) {
      // Ask for confirmation
      if (window.confirm('Processing is in progress. Close anyway? The process will continue in the background.')) {
        updateCollectionProgress(collectionProgress ? {
          ...collectionProgress,
          canContinueInBackground: true
        } : null);
        onClose();
      }
    } else {
      onClose();
    }
  };

  const renderStepContent = () => {
    switch (currentStep) {
      case 1:
        return (
          <GroupNameStep
            groupData={groupData}
            onUpdate={updateGroupData}
          />
        );
      case 2:
        return (
          <div className="space-y-6">
            <div className="text-center">
              <div className="bg-green-100 rounded-full w-16 h-16 flex items-center justify-center mx-auto mb-4">
                <Clock className="w-8 h-8 text-green-600" />
              </div>
              <h3 className="text-lg font-medium text-gray-900 mb-2">Upload Documents</h3>
              <p className="text-gray-600">
                Choose how to add documents to your collection.
              </p>
            </div>

            {/* Upload method selection */}
            <div className="flex space-x-4 mb-4">
              <button
                type="button"
                className={`flex items-center px-4 py-2 rounded-md ${uploadMethod === 'file' ? 'bg-blue-50 text-blue-700 border border-blue-200' : 'bg-white border border-gray-300'}`}
                onClick={() => setUploadMethod('file')}
              >
                File Upload
              </button>
              <button
                type="button"
                className={`flex items-center px-4 py-2 rounded-md ${uploadMethod === 'drive' ? 'bg-blue-50 text-blue-700 border border-blue-200' : 'bg-white border border-gray-300'}`}
                onClick={() => setUploadMethod('drive')}
              >
                Google Drive
              </button>
              <button
                type="button"
                className={`flex items-center px-4 py-2 rounded-md ${uploadMethod === 'web' ? 'bg-blue-50 text-blue-700 border border-blue-200' : 'bg-white border border-gray-300'}`}
                onClick={() => setUploadMethod('web')}
              >
                Web URL
              </button>
            </div>

            {uploadMethod === 'file' && (
              <DocumentUploadStep
                groupData={groupData}
                onUpdate={updateGroupData}
              />
            )}

            {uploadMethod === 'drive' && (
              <div className="space-y-4">
                <div className="space-y-2">
                  <label htmlFor="drive-link" className="block text-sm font-medium text-gray-700">
                    Google Drive Folder Link
                  </label>
                  <input
                    id="drive-link"
                    type="url"
                    value={driveLink}
                    onChange={(e) => setDriveLink(e.target.value)}
                    placeholder="https://drive.google.com/drive/folders/..."
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>
                <div className="flex items-center">
                  <input
                    id="recursive-checkbox"
                    type="checkbox"
                    checked={recursive}
                    onChange={(e) => setRecursive(e.target.checked)}
                    className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded"
                  />
                  <label htmlFor="recursive-checkbox" className="ml-2 block text-sm text-gray-700">
                    Process subfolders recursively
                  </label>
                </div>
              </div>
            )}

            {uploadMethod === 'web' && (
              <div className="space-y-2">
                <label htmlFor="web-url" className="block text-sm font-medium text-gray-700">
                  Website URL
                </label>
                <input
                  id="web-url"
                  type="url"
                  value={webUrl}
                  onChange={(e) => setWebUrl(e.target.value)}
                  placeholder="https://example.com"
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                <p className="text-xs text-gray-500 mt-1">
                  The system will crawl and extract content from the provided URL.
                </p>
                <div className="space-y-2">
                  <label htmlFor="extraction-prompt" className="block text-sm font-medium text-gray-700">
                    Extraction Prompt
                  </label>
                  <textarea
                    id="extraction-prompt"
                    value={extractionText}
                    onChange={(e) => setExtractionText(e.target.value)}
                    placeholder="Enter a prompt for the system to extract content from the web page..."
                    rows={3}
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>
                <div className="flex items-center">
                  <input
                    id="null-is-okay"
                    type="checkbox"
                    checked={nullIsOkay}
                    onChange={(e) => setNullIsOkay(e.target.checked)}
                    className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded"
                  />
                  <label htmlFor="null-is-okay" className="ml-2 block text-sm text-gray-700">
                    Allow null values
                  </label>
                </div>
                <div className="space-y-2">
                  <label htmlFor="num-workers" className="block text-sm font-medium text-gray-700">
                    Number of Workers
                  </label>
                  <input
                    id="num-workers"
                    type="number"
                    value={numWorkers}
                    onChange={(e) => setNumWorkers(parseInt(e.target.value) || 0)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                    min="1"
                    max="10"
                  />
                </div>
                <div className="space-y-2">
                  <label htmlFor="num-levels-deep" className="block text-sm font-medium text-gray-700">
                    Number of Levels Deep
                  </label>
                  <input
                    id="num-levels-deep"
                    type="number"
                    value={numLevelsDeep}
                    onChange={(e) => setNumLevelsDeep(parseInt(e.target.value) || 0)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                    min="1"
                    max="10"
                  />
                </div>
              </div>
            )}
          </div>
        );
      case 3:
        return (
          <div className="space-y-6">
            <div className="text-center">
              <div className="bg-purple-100 rounded-full w-16 h-16 flex items-center justify-center mx-auto mb-4">
                <CheckCircle className="w-8 h-8 text-purple-600" />
              </div>
              <h3 className="text-lg font-medium text-gray-900 mb-2">Chunking Settings</h3>
              <p className="text-gray-600">
                Configure how documents should be processed and chunked.
              </p>
            </div>

            {/* Text extraction settings */}
            <div className="space-y-4">
              <h4 className="font-medium text-gray-900">Text Extraction Options</h4>
              <div className="p-4 bg-gray-50 rounded-md space-y-3">
                <div className="flex items-center">
                  <input
                    id="extract-tables"
                    type="checkbox"
                    checked={extractTables}
                    onChange={(e) => setExtractTables(e.target.checked)}
                    className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded"
                  />
                  <label htmlFor="extract-tables" className="ml-2 block text-sm text-gray-700">
                    Extract tables
                  </label>
                </div>
                <div className="flex items-center">
                  <input
                    id="extract-images-with-text"
                    type="checkbox"
                    checked={extractImagesWithText}
                    onChange={(e) => setExtractImagesWithText(e.target.checked)}
                    className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded"
                  />
                  <label htmlFor="extract-images-with-text" className="ml-2 block text-sm text-gray-700">
                    Extract images with text
                  </label>
                </div>
                <div className="flex items-center">
                  <input
                    id="extract-images-without-text"
                    type="checkbox"
                    checked={extractImagesWithoutText}
                    onChange={(e) => setExtractImagesWithoutText(e.target.checked)}
                    className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded"
                  />
                  <label htmlFor="extract-images-without-text" className="ml-2 block text-sm text-gray-700">
                    Extract images without text
                  </label>
                </div>
              </div>
            </div>

            {/* Chunking settings */}
            <div className="space-y-4">
              <h4 className="font-medium text-gray-900">Chunking Method</h4>
              <div className="flex space-x-4">
                <div className="flex items-center">
                  <input
                    id="method-paragraph"
                    type="radio"
                    checked={chunkingMethod === 'paragraph'}
                    onChange={() => setChunkingMethod('paragraph')}
                    className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300"
                  />
                  <label htmlFor="method-paragraph" className="ml-2 block text-sm text-gray-700">
                    Paragraph
                  </label>
                </div>
                <div className="flex items-center">
                  <input
                    id="method-fixed"
                    type="radio"
                    checked={chunkingMethod === 'fixed'}
                    onChange={() => setChunkingMethod('fixed')}
                    className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300"
                  />
                  <label htmlFor="method-fixed" className="ml-2 block text-sm text-gray-700">
                    Fixed Size
                  </label>
                </div>
                <div className="flex items-center">
                  <input
                    id="method-semantic"
                    type="radio"
                    checked={chunkingMethod === 'semantic'}
                    onChange={() => setChunkingMethod('semantic')}
                    className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300"
                  />
                  <label htmlFor="method-semantic" className="ml-2 block text-sm text-gray-700">
                    Semantic
                  </label>
                </div>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <label htmlFor="chunk-size" className="block text-sm font-medium text-gray-700">
                  Chunk Size (characters)
                </label>
                <input
                  id="chunk-size"
                  type="number"
                  value={chunkSize}
                  onChange={(e) => setChunkSize(parseInt(e.target.value) || 0)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  min="100"
                  max="10000"
                />
              </div>
              <div className="space-y-2">
                <label htmlFor="chunk-overlap" className="block text-sm font-medium text-gray-700">
                  Chunk Overlap (characters)
                </label>
                <input
                  id="chunk-overlap"
                  type="number"
                  value={chunkOverlap}
                  onChange={(e) => setChunkOverlap(parseInt(e.target.value) || 0)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  min="0"
                  max={chunkSize - 1}
                />
              </div>
            </div>

            <div className="flex items-center mb-2">
              <input
                id="use-ai"
                type="checkbox"
                checked={useAI}
                onChange={(e) => setUseAI(e.target.checked)}
                className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded"
              />
              <label htmlFor="use-ai" className="ml-2 block text-sm text-gray-700">
                Use AI for context enrichment
              </label>
            </div>

            {useAI && (
              <div className="space-y-2">
                <label htmlFor="context-prompt" className="block text-sm font-medium text-gray-700">
                  Context Prompt
                </label>
                <textarea
                  id="context-prompt"
                  value={contextPrompt}
                  onChange={(e) => setContextPrompt(e.target.value)}
                  placeholder="Enter a prompt for the AI to generate additional context for each chunk..."
                  rows={3}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
            )}
          </div>
        );
      default:
        return null;
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 flex items-center justify-center bg-black bg-opacity-50 z-50 overflow-auto py-10">
      <div 
        ref={modalRef}
        className="bg-white rounded-lg shadow-xl w-full max-w-4xl max-h-[90vh] overflow-y-auto relative"
      >
        <div className="p-6">
          {/* Header */}
          <div className="flex justify-between items-center border-b pb-4 mb-6">
            <h2 className="text-2xl font-bold">Create Collection</h2>
            <button 
              onClick={handleClose}
              className="p-1 rounded-full hover:bg-gray-100"
              aria-label="Close"
            >
              <X size={24} />
            </button>
          </div>

          {/* Progress Steps */}
          <div className="flex items-center justify-between mb-8">
            {STEPS.map((step, index) => (
              <div key={step.id} className="flex items-center">
                <button
                  onClick={() => handleStepClick(step.id)}
                  disabled={!canProceedToStep(step.id) || stepLoading}
                  className={`flex items-center justify-center w-10 h-10 rounded-full text-sm font-medium ${
                    currentStep === step.id
                      ? 'bg-blue-600 text-white'
                      : currentStep > step.id
                      ? 'bg-green-500 text-white'
                      : canProceedToStep(step.id)
                      ? 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                      : 'bg-gray-100 text-gray-400 cursor-not-allowed'
                  }`}
                >
                  {currentStep > step.id ? (
                    <Check size={16} />
                  ) : (
                    step.id
                  )}
                </button>
                <div className="ml-3 min-w-0 flex-1">
                  <p className={`text-sm font-medium ${
                    currentStep >= step.id ? 'text-gray-900' : 'text-gray-500'
                  }`}>
                    {step.title}
                  </p>
                  <p className="text-xs text-gray-500">{step.description}</p>
                </div>
                {index < STEPS.length - 1 && (
                  <div className={`flex-1 h-0.5 mx-4 ${
                    currentStep > step.id ? 'bg-green-500' : 'bg-gray-200'
                  }`} />
                )}
              </div>
            ))}
          </div>

          {/* Collection Progress Display */}
          {collectionProgress && (
            <div className="mb-6 p-4 bg-blue-50 border border-blue-200 rounded-lg">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center space-x-3">
                  {collectionProgress.status === 'completed' ? (
                    <CheckCircle className="w-5 h-5 text-green-500" />
                  ) : collectionProgress.status === 'error' ? (
                    <AlertTriangle className="w-5 h-5 text-red-500" />
                  ) : (
                    <Clock className="w-5 h-5 text-blue-500 animate-pulse" />
                  )}
                  <div>
                    <h4 className="font-medium text-gray-900">{collectionProgress.name}</h4>
                    <p className="text-sm text-gray-600">
                      {collectionProgress.status === 'creating' && 'Creating collection...'}
                      {collectionProgress.status === 'uploading' && 'Uploading documents...'}
                      {collectionProgress.status === 'extracting' && 'Extracting text from documents...'}
                      {collectionProgress.status === 'chunking' && 'Breaking content into chunks...'}
                      {collectionProgress.status === 'completed' && 'Collection created successfully!'}
                      {collectionProgress.status === 'error' && `Error: ${collectionProgress.error}`}
                      {collectionProgress.status === 'paused' && 'Processing paused. You can close this modal.'}
                    </p>
                  </div>
                </div>
                <div className={`px-2 py-1 rounded-full text-xs font-medium ${
                  collectionProgress.status === 'completed' ? 'bg-green-100 text-green-800' :
                  collectionProgress.status === 'error' ? 'bg-red-100 text-red-800' :
                  'bg-blue-100 text-blue-800'
                }`}>
                  Step {collectionProgress.currentStep}/{collectionProgress.totalSteps}
                </div>
              </div>

              {/* Processing Steps Progress */}
              <div className="space-y-2">
                {PROCESSING_STEPS.map((step) => {
                  const stepStatus = collectionProgress.stepStatuses[step.id as keyof typeof collectionProgress.stepStatuses];
                  const isCompleted = stepStatus === 'completed';
                  const isProcessing = stepStatus === 'processing';
                  const isError = stepStatus === 'error';

                  return (
                    <div
                      key={step.id}
                      className={`flex items-center p-2 rounded-md ${
                        isCompleted ? 'bg-green-50 border border-green-200' :
                        isProcessing ? 'bg-blue-50 border border-blue-200' :
                        isError ? 'bg-red-50 border border-red-200' :
                        'bg-gray-50 border border-gray-200'
                      }`}
                    >
                      <div className="flex items-center space-x-3 flex-1">
                        {isCompleted ? (
                          <CheckCircle className="w-4 h-4 text-green-500" />
                        ) : isProcessing ? (
                          <Clock className="w-4 h-4 text-blue-500 animate-pulse" />
                        ) : isError ? (
                          <AlertTriangle className="w-4 h-4 text-red-500" />
                        ) : (
                          <div className="w-4 h-4 rounded-full border-2 border-gray-300" />
                        )}
                        <div>
                          <p className={`text-sm font-medium ${
                            isCompleted ? 'text-green-800' :
                            isProcessing ? 'text-blue-800' :
                            isError ? 'text-red-800' :
                            'text-gray-600'
                          }`}>
                            {step.name}
                          </p>
                          <p className={`text-xs ${
                            isCompleted ? 'text-green-600' :
                            isProcessing ? 'text-blue-600' :
                            isError ? 'text-red-600' :
                            'text-gray-500'
                          }`}>
                            {step.description}
                          </p>
                        </div>
                      </div>
                      {isCompleted && (
                        <span className="text-xs text-green-600 font-medium">✓ Done</span>
                      )}
                      {isProcessing && (
                        <span className="text-xs text-blue-600 font-medium">In Progress</span>
                      )}
                      {isError && (
                        <span className="text-xs text-red-600 font-medium">✗ Error</span>
                      )}
                    </div>
                  );
                })}
              </div>

              {/* Background processing notice */}
              {collectionProgress.canContinueInBackground && (
                <div className="mt-3 p-2 bg-yellow-50 border border-yellow-200 rounded-md">
                  <p className="text-xs text-yellow-800">
                    Processing continues in the background. You can safely close this modal.
                  </p>
                </div>
              )}

              {/* Elapsed time */}
              {collectionProgress.startTime && (
                <div className="mt-3 text-xs text-gray-500">
                  Started {new Date(collectionProgress.startTime).toLocaleTimeString()}
                </div>
              )}
            </div>
          )}

          {/* Step Content */}
          <div className="mb-6">
            {renderStepContent()}
          </div>

          {/* Footer */}
          <div className="flex justify-between items-center pt-4 border-t">
            {stepLoading ? (
              // Loading state footer
              <div className="flex justify-between items-center w-full">
                <div className="text-sm text-gray-600">
                  Processing... Please wait or close to continue in background
                </div>
              </div>
            ) : collectionProgress?.status === 'completed' ? (
              // Completed mode footer
              <div className="flex justify-between items-center w-full">
                <div className="flex items-center space-x-2 text-green-600">
                  <CheckCircle className="w-4 h-4" />
                  <span className="text-sm font-medium">Collection created successfully!</span>
                </div>
                <button
                  onClick={onClose}
                  className="px-4 py-2 bg-green-600 text-white rounded-md hover:bg-green-700"
                >
                  Done
                </button>
              </div>
            ) : collectionProgress?.status === 'error' ? (
              // Error mode footer
              <div className="flex justify-between items-center w-full">
                <div className="flex items-center space-x-2 text-red-600">
                  <AlertTriangle className="w-4 h-4" />
                  <span className="text-sm font-medium">Error occurred</span>
                </div>
                <div className="flex space-x-2">
                  <button
                    onClick={() => updateCollectionProgress(null)}
                    className="px-4 py-2 border border-gray-300 rounded-md hover:bg-gray-50"
                  >
                    Reset
                  </button>
                  <button
                    onClick={onClose}
                    className="px-4 py-2 bg-red-600 text-white rounded-md hover:bg-red-700"
                  >
                    Close
                  </button>
                </div>
              </div>
            ) : (
              // Normal step navigation footer
              <>
                <button
                  onClick={handlePrevious}
                  disabled={currentStep === 1 || stepLoading}
                  className="px-4 py-2 border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  Previous
                </button>

                <div className="flex space-x-2">
                  {currentStep < STEPS.length ? (
                    <button
                      onClick={handleNext}
                      disabled={!isStepValid(currentStep) || stepLoading}
                      className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      Next
                    </button>
                  ) : (
                    <button
                      onClick={handleNext}
                      disabled={stepLoading || !isStepValid(currentStep)}
                      className="px-4 py-2 bg-green-600 text-white rounded-md hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center"
                    >
                      {stepLoading ? (
                        <>
                          <Clock className="w-4 h-4 mr-2 animate-pulse" />
                          {currentStep === 1 ? 'Creating...' : 
                           currentStep === 2 ? 'Uploading...' : 
                           'Processing...'}
                        </>
                      ) : (
                        currentStep === 3 ? 'Create Collection' : 'Next'
                      )}
                    </button>
                  )}
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default CreateGroupModal;