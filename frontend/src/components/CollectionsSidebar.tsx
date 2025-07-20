import React, { useState } from 'react';
import { Database, FileText, AlertCircle, RefreshCw, Plus, ChevronDown, ChevronRight, X, CheckCircle, Clock, AlertTriangle, File, FileSearch, Layers, Zap } from 'lucide-react';
import type { Collection } from '../types';

interface CollectionsSidebarProps {
  collections: Collection[];
  loading: boolean;
  error: string | null;
  onRefresh: () => void;
  onCreateGroup: () => void;
}

interface DocumentStep {
  id: string;
  name: string;
  status: 'completed' | 'processing' | 'pending' | 'error';
  icon: React.ComponentType<any>;
  metadata?: Record<string, any>;
}

interface Document {
  id: string;
  filename: string;
  uploadDate: string;
  size: string;
  steps: DocumentStep[];
}

interface CollectionData {
  id: string;
  name: string;
  documents: Document[];
  isExpanded: boolean;
}

const CollectionsSidebar: React.FC<CollectionsSidebarProps> = ({
  collections,
  loading,
  error,
  onRefresh,
  onCreateGroup,
}) => {
  const [selectedDocument, setSelectedDocument] = useState<Document | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);

  // Dummy collection data
  const [collectionsData, setCollectionsData] = useState<CollectionData[]>([
    {
      id: 'collection-1',
      name: 'Research Papers',
      isExpanded: true,
      documents: [
        {
          id: 'doc-1',
          filename: 'Improving CS Performance Spatial Skills.pdf',
          uploadDate: '2025-01-19',
          size: '2.4 MB',
          steps: [
            {
              id: 'upload',
              name: 'Document Upload',
              status: 'completed',
              icon: File,
              metadata: {
                'File Size': '2.4 MB',
                'Upload Date': '2025-01-19 10:30:00',
                'File Type': 'PDF',
                'Pages': 12
              }
            },
            {
              id: 'extract',
              name: 'Text Extraction',
              status: 'completed',
              icon: FileSearch,
              metadata: {
                'Extraction Method': 'PyMuPDF + PDFPlumber',
                'Text Length': '15,234 characters',
                'Tables Found': 3,
                'Images Found': 5,
                'Processing Time': '2.3 seconds'
              }
            },
            {
              id: 'chunk',
              name: 'Text Chunking',
              status: 'completed',
              icon: Layers,
              metadata: {
                'Chunk Size': '1000 tokens',
                'Overlap': '200 tokens',
                'Total Chunks': 18,
                'Chunking Strategy': 'Recursive Character Split'
              }
            },
            {
              id: 'embed',
              name: 'Generate Embeddings',
              status: 'processing',
              icon: Zap,
              metadata: {
                'Model': 'text-embedding-3-small',
                'Dimensions': 1536,
                'Progress': '12/18 chunks',
                'Estimated Time': '2 minutes remaining'
              }
            }
          ]
        },
        {
          id: 'doc-2',
          filename: 'Machine Learning Fundamentals.pdf',
          uploadDate: '2025-01-18',
          size: '3.1 MB',
          steps: [
            {
              id: 'upload',
              name: 'Document Upload',
              status: 'completed',
              icon: File,
              metadata: {
                'File Size': '3.1 MB',
                'Upload Date': '2025-01-18 14:22:00',
                'File Type': 'PDF',
                'Pages': 24
              }
            },
            {
              id: 'extract',
              name: 'Text Extraction',
              status: 'completed',
              icon: FileSearch,
              metadata: {
                'Extraction Method': 'PyMuPDF + PDFPlumber',
                'Text Length': '28,456 characters',
                'Tables Found': 8,
                'Images Found': 12
              }
            },
            {
              id: 'chunk',
              name: 'Text Chunking',
              status: 'completed',
              icon: Layers,
              metadata: {
                'Total Chunks': 32,
                'Chunk Size': '1000 tokens',
                'Overlap': '200 tokens'
              }
            },
            {
              id: 'embed',
              name: 'Generate Embeddings',
              status: 'completed',
              icon: Zap,
              metadata: {
                'Model': 'text-embedding-3-small',
                'Dimensions': 1536,
                'Total Vectors': 32
              }
            }
          ]
        },
        {
          id: 'doc-3',
          filename: 'Data Structures and Algorithms.pdf',
          uploadDate: '2025-01-17',
          size: '4.2 MB',
          steps: [
            {
              id: 'upload',
              name: 'Document Upload',
              status: 'completed',
              icon: File,
              metadata: {
                'File Size': '4.2 MB',
                'Upload Date': '2025-01-17 09:15:00',
                'File Type': 'PDF',
                'Pages': 35
              }
            },
            {
              id: 'extract',
              name: 'Text Extraction',
              status: 'error',
              icon: FileSearch,
              metadata: {
                'Error': 'Corrupted PDF structure detected',
                'Retry Count': 3,
                'Last Attempt': '2025-01-17 09:18:00'
              }
            },
            {
              id: 'chunk',
              name: 'Text Chunking',
              status: 'pending',
              icon: Layers
            },
            {
              id: 'embed',
              name: 'Generate Embeddings',
              status: 'pending',
              icon: Zap
            }
          ]
        }
      ]
    }
  ]);

  const toggleCollection = (collectionId: string) => {
    setCollectionsData(prev => 
      prev.map(collection => 
        collection.id === collectionId 
          ? { ...collection, isExpanded: !collection.isExpanded }
          : collection
      )
    );
  };

  const openDocumentModal = (document: Document) => {
    setSelectedDocument(document);
    setIsModalOpen(true);
  };

  const closeModal = () => {
    setIsModalOpen(false);
    setSelectedDocument(null);
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'completed':
        return <CheckCircle className="w-4 h-4 text-green-500" />;
      case 'processing':
        return <Clock className="w-4 h-4 text-blue-500 animate-pulse" />;
      case 'error':
        return <AlertTriangle className="w-4 h-4 text-red-500" />;
      default:
        return <Clock className="w-4 h-4 text-gray-400" />;
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'completed':
        return 'bg-green-100 text-green-800';
      case 'processing':
        return 'bg-blue-100 text-blue-800';
      case 'error':
        return 'bg-red-100 text-red-800';
      default:
        return 'bg-gray-100 text-gray-800';
    }
  };

  return (
    <div className="w-80 bg-white border-r border-gray-200 flex flex-col h-full">
      {/* Header */}
      <div className="p-6 border-b border-gray-200">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-900">Collections</h2>
          <button
            onClick={onRefresh}
            disabled={loading}
            className="p-2 text-gray-400 hover:text-gray-600 transition-colors disabled:opacity-50"
            title="Refresh collections"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
        
        {/* Create Group Button */}
        <button
          onClick={onCreateGroup}
          className="w-full flex items-center justify-center space-x-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
        >
          <Plus className="w-4 h-4" />
          <span>Create Collection</span>
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        {loading && (
          <div className="p-6 text-center">
            <div className="inline-flex items-center space-x-2 text-gray-500">
              <RefreshCw className="w-4 h-4 animate-spin" />
              <span>Loading...</span>
            </div>
          </div>
        )}

        {error && (
          <div className="p-6">
            <div className="bg-red-50 border border-red-200 rounded-lg p-4">
              <div className="flex items-center space-x-2 text-red-800">
                <AlertCircle className="w-4 h-4" />
                <span className="font-medium">Error</span>
              </div>
              <p className="text-red-700 text-sm mt-1">{error}</p>
              <button
                onClick={onRefresh}
                className="text-red-600 hover:text-red-700 text-sm font-medium mt-2"
              >
                Try again
              </button>
            </div>
          </div>
        )}

        {!loading && !error && (
          <div className="p-4">
            {collectionsData.map((collection) => (
              <div key={collection.id} className="mb-4">
                {/* Collection Header */}
                <button
                  onClick={() => toggleCollection(collection.id)}
                  className="w-full flex items-center justify-between p-3 bg-gray-50 hover:bg-gray-100 rounded-lg transition-colors"
                >
                  <div className="flex items-center space-x-2">
                    {collection.isExpanded ? (
                      <ChevronDown className="w-4 h-4 text-gray-500" />
                    ) : (
                      <ChevronRight className="w-4 h-4 text-gray-500" />
                    )}
                    <Database className="w-4 h-4 text-gray-600" />
                    <span className="font-medium text-gray-900">{collection.name}</span>
                  </div>
                  <span className="text-sm text-gray-500">
                    {collection.documents.length} docs
                  </span>
                </button>

                {/* Documents List */}
                {collection.isExpanded && (
                  <div className="mt-2 ml-4 space-y-1">
                    {collection.documents.map((document) => (
                      <button
                        key={document.id}
                        onClick={() => openDocumentModal(document)}
                        className="w-full text-left p-3 rounded-lg border border-gray-200 hover:border-gray-300 hover:bg-gray-50 transition-colors"
                      >
                        <div className="flex items-center justify-between">
                          <div className="flex items-center space-x-2 flex-1 min-w-0">
                            <FileText className="w-4 h-4 text-gray-500 flex-shrink-0" />
                            <span className="text-sm font-medium text-gray-900 truncate">
                              {document.filename}
                            </span>
                          </div>
                          <div className="flex items-center space-x-2">
                            {getStatusIcon(document.steps[document.steps.length - 1]?.status || 'pending')}
                          </div>
                        </div>
                        <div className="mt-1 text-xs text-gray-500">
                          {document.size} • {document.uploadDate}
                        </div>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="p-4 border-t border-gray-200">
        <div className="text-xs text-gray-500 text-center">
          Chat works across all available collections
        </div>
      </div>

      {/* Modal */}
      {isModalOpen && selectedDocument && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full mx-4 max-h-[80vh] overflow-hidden">
            {/* Modal Header */}
            <div className="flex items-center justify-between p-6 border-b border-gray-200">
              <div>
                <h3 className="text-lg font-semibold text-gray-900">
                  {selectedDocument.filename}
                </h3>
                <p className="text-sm text-gray-500 mt-1">
                  Processing Pipeline Status
                </p>
              </div>
              <button
                onClick={closeModal}
                className="p-2 text-gray-400 hover:text-gray-600 transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Modal Content */}
            <div className="p-6 overflow-y-auto max-h-[60vh]">
              <div className="space-y-4">
                {selectedDocument.steps.map((step, index) => {
                  const Icon = step.icon;
                  return (
                    <div key={step.id} className="border border-gray-200 rounded-lg p-4">
                      <div className="flex items-center justify-between mb-3">
                        <div className="flex items-center space-x-3">
                          <Icon className="w-5 h-5 text-gray-600" />
                          <span className="font-medium text-gray-900">{step.name}</span>
                        </div>
                        <div className="flex items-center space-x-2">
                          {getStatusIcon(step.status)}
                          <span className={`px-2 py-1 rounded-full text-xs font-medium ${getStatusColor(step.status)}`}>
                            {step.status}
                          </span>
                        </div>
                      </div>
                      
                      {step.metadata && (
                        <div className="bg-gray-50 rounded-md p-3">
                          <div className="grid grid-cols-2 gap-2 text-sm">
                            {Object.entries(step.metadata).map(([key, value]) => (
                              <div key={key}>
                                <span className="text-gray-600 font-medium">{key}:</span>
                                <span className="text-gray-900 ml-1">{value}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default CollectionsSidebar;