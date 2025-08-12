import React, { useState, useEffect } from 'react';
import { AlertCircle, RefreshCw, Plus, X, CheckCircle, Clock, AlertTriangle, Database, ChevronRight, ChevronDown, FileText } from 'lucide-react';
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

const CollectionsSidebar: React.FC<CollectionsSidebarProps> = ({
  collections,
  loading,
  error,
  onRefresh,
  onCreateGroup,
}) => {
  const [selectedDocument, setSelectedDocument] = useState<Document | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [expandedCollections, setExpandedCollections] = useState<Set<string>>(new Set());

  const toggleCollection = (collectionName: string) => {
    setExpandedCollections(prev => {
      const newSet = new Set(prev);
      if (newSet.has(collectionName)) {
        newSet.delete(collectionName);
      } else {
        newSet.add(collectionName);
      }
      return newSet;
    });
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

        {!loading && !error && collections.length === 0 && (
          <div className="p-6 text-center">
            <Database className="w-12 h-12 text-gray-300 mx-auto mb-4" />
            <h3 className="text-lg font-medium text-gray-900 mb-2">No Collections</h3>
            <p className="text-gray-500 text-sm mb-4">
              Create your first collection to get started with document analysis.
            </p>
            <button
              onClick={onCreateGroup}
              className="inline-flex items-center space-x-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
            >
              <Plus className="w-4 h-4" />
              <span>Create Collection</span>
            </button>
          </div>
        )}

        {!loading && !error && collections.length > 0 && (
          <div className="p-4">
            <div className="space-y-2">
              {collections.map((collection) => (
                <div key={collection.name} className="border border-gray-200 rounded-lg">
                  {/* Collection Header */}
                  <button
                    onClick={() => toggleCollection(collection.name)}
                    className="w-full flex items-center justify-between p-3 hover:bg-gray-50 rounded-lg transition-colors"
                  >
                    <div className="flex items-center space-x-3 flex-1 min-w-0">
                      {expandedCollections.has(collection.name) ? (
                        <ChevronDown className="w-4 h-4 text-gray-500 flex-shrink-0" />
                      ) : (
                        <ChevronRight className="w-4 h-4 text-gray-500 flex-shrink-0" />
                      )}
                      <Database className="w-4 h-4 text-blue-600 flex-shrink-0" />
                      <div className="flex-1 min-w-0 text-left">
                        <p className="text-sm font-medium text-gray-900 truncate">
                          {collection.name}
                        </p>
                        <p className="text-xs text-gray-500">
                          {collection.num_documents} documents
                        </p>
                      </div>
                    </div>
                    
                    <div className={`px-2 py-1 rounded-full text-xs font-medium ${
                      collection.status === 'active' ? 'bg-green-100 text-green-800' :
                      collection.status === 'processing' ? 'bg-blue-100 text-blue-800' :
                      'bg-gray-100 text-gray-800'
                    }`}>
                      {collection.status || 'active'}
                    </div>
                  </button>

                  {/* Expanded Content */}
                  {expandedCollections.has(collection.name) && (
                    <div className="px-3 pb-3 border-t border-gray-100">
                      <div className="mt-3 space-y-2">
                        <div className="text-xs text-gray-500">
                          <div className="flex justify-between">
                            <span>Documents:</span>
                            <span>{collection.num_documents}</span>
                          </div>
                          {collection.last_updated && (
                            <div className="flex justify-between mt-1">
                              <span>Last updated:</span>
                              <span>{new Date(collection.last_updated).toLocaleDateString()}</span>
                            </div>
                          )}
                          {collection.total_size && (
                            <div className="flex justify-between mt-1">
                              <span>Size:</span>
                              <span>{Math.round(collection.total_size / 1024 / 1024)} MB</span>
                            </div>
                          )}
                        </div>
                        
                        {collection.num_documents > 0 && (
                          <div className="mt-3">
                            <div className="bg-blue-50 border border-blue-200 rounded-md p-2">
                              <div className="flex items-center space-x-2">
                                <CheckCircle className="w-4 h-4 text-blue-600" />
                                <span className="text-xs text-blue-800 font-medium">
                                  Ready for queries
                                </span>
                              </div>
                              <p className="text-xs text-blue-700 mt-1">
                                This collection is available for chat and analysis.
                              </p>
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
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
                {selectedDocument.steps.map((step) => {
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