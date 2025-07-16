import React from 'react';
import { Database, FileText, AlertCircle, RefreshCw, Plus } from 'lucide-react';
import type { Collection } from '../types';

interface CollectionsSidebarProps {
  collections: Collection[];
  loading: boolean;
  error: string | null;
  onRefresh: () => void;
  onCreateGroup: () => void;
}

const CollectionsSidebar: React.FC<CollectionsSidebarProps> = ({
  collections,
  loading,
  error,
  onRefresh,
  onCreateGroup,
}) => {
  const getCollectionIcon = () => {
    // Default to FileText, could be customized based on collection name patterns
    return FileText;
  };

  const formatNumber = (num: number) => {
    if (num >= 1000000) {
      return (num / 1000000).toFixed(1) + 'M';
    } else if (num >= 1000) {
      return (num / 1000).toFixed(1) + 'K';
    }
    return num.toString();
  };

  return (
    <div className="w-80 bg-white border-r border-gray-200 flex flex-col h-full">
      {/* Header */}
      <div className="p-6 border-b border-gray-200">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-900">Groups</h2>
          <button
            onClick={onRefresh}
            disabled={loading}
            className="p-2 text-gray-400 hover:text-gray-600 transition-colors disabled:opacity-50"
            title="Refresh collections"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
        
        <div className="flex items-center space-x-2 text-sm text-gray-500">
          <span>{collections.length} Group{collections.length !== 1 ? 's' : ''} available</span>
        </div>
        
        {/* Create Group Button */}
        <button
          onClick={onCreateGroup}
          className="mt-4 w-full flex items-center justify-center space-x-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
        >
          <Plus className="w-4 h-4" />
          <span>Create Group</span>
        </button>
      </div>

      {/* Collections List */}
      <div className="flex-1 overflow-y-auto">
        {loading && (
          <div className="p-6 text-center">
            <div className="inline-flex items-center space-x-2 text-gray-500">
              <RefreshCw className="w-4 h-4 animate-spin" />
              <span>Loading collections...</span>
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
            <p className="text-gray-500">No document collections found</p>
            <button
              onClick={onRefresh}
              className="text-blue-600 hover:text-blue-700 text-sm font-medium mt-2"
            >
              Refresh
            </button>
          </div>
        )}

        {!loading && !error && collections.length > 0 && (
          <div className="p-4 space-y-2">
            {collections.map((collection) => {
              const Icon = getCollectionIcon();
              const isActive = collection.status === 'active';
              
              return (
                <div
                  key={collection.id}
                  className="w-full text-left p-3 rounded-lg border bg-gray-50 border-gray-200 text-gray-700"
                >
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center space-x-2">
                      <Icon className="w-4 h-4 text-gray-500" />
                      <span className="font-medium truncate">{collection.name}</span>
                    </div>
                    <div className={`w-2 h-2 rounded-full ${
                      isActive ? 'bg-green-400' : 'bg-red-400'
                    }`} title={`Status: ${collection.status}`} />
                  </div>
                  
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-gray-500">
                      {formatNumber(collection.count)} documents
                    </span>
                    {!isActive && (
                      <span className="text-xs text-red-600 bg-red-100 px-2 py-1 rounded">
                        {collection.status}
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="p-4 border-t border-gray-200">
        <div className="text-xs text-gray-500 text-center">
          Chat works across all available collections
        </div>
      </div>
    </div>
  );
};

export default CollectionsSidebar; 