import { useState, useEffect, useCallback } from 'react';
import { MessageSquare, AlertCircle, Loader2, FileText } from 'lucide-react';
import CollectionsSidebar from './components/CollectionsSidebar';
import ChatInterface from './components/ChatInterface';
import CreateGroupModal from './components/CreateGroupModal';
import FiscalNoteGeneration from './components/FiscalNoteGeneration';
import type { Collection, ChatMessage } from './types';
import { getCollections, askQuestion } from './services/api';

type AppView = 'chat' | 'fiscal-note';

function App() {
  const [currentView, setCurrentView] = useState<AppView>('chat');
  const [collections, setCollections] = useState<Collection[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [collectionsLoading, setCollectionsLoading] = useState(true);
  const [collectionsError, setCollectionsError] = useState<string | null>(null);
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);

  // Load collections on app start
  const loadCollections = useCallback(async () => {
    setCollectionsLoading(true);
    setCollectionsError(null);
    
    try {
      const response = await getCollections();
      
      // Transform the backend response to our Collection type
      const collectionsArray: Collection[] = Object.entries(response.collections).map(
        ([collectionName, totalCollections]) => ({
          name: collectionName,
          total_collections: totalCollections,
          status: "active",
        })
      );
      
      setCollections(collectionsArray);
      
      // Auto-select functionality is no longer needed since chat works across all collections
    } catch (err) {
      setCollectionsError(err instanceof Error ? err.message : 'Failed to load collections');
    } finally {
      setCollectionsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadCollections();
  }, [loadCollections]);

  // Handle sending a message
  const handleSendMessage = useCallback(async (messageText: string) => {
    const userMessage: ChatMessage = {
      id: `user_${Date.now()}`,
      type: 'user',
      content: messageText,
      timestamp: new Date(),
    };

    // Add user message
    setMessages(prev => [...prev, userMessage]);
    setLoading(true);

    // Add loading message
    const loadingMessage: ChatMessage = {
      id: `loading_${Date.now()}`,
      type: 'assistant',
      content: '',
      timestamp: new Date(),
      isLoading: true,
    };

    setMessages(prev => [...prev, loadingMessage]);

    try {
      const response = await askQuestion(messageText);
      
      // Remove loading message and add real response
      setMessages(prev => {
        const withoutLoading = prev.filter(msg => msg.id !== loadingMessage.id);
        const assistantMessage: ChatMessage = {
          id: `assistant_${Date.now()}`,
          type: 'assistant',
          content: response.answer,
          timestamp: new Date(),
          sources: response.sources,
        };
        return [...withoutLoading, assistantMessage];
      });
    } catch (err) {
      // Remove loading message and show error
      setMessages(prev => prev.filter(msg => msg.id !== loadingMessage.id));
      
      // Add error message to chat
      const errorMessage: ChatMessage = {
        id: `error_${Date.now()}`,
        type: 'assistant',
        content: `Sorry, I encountered an error: ${err instanceof Error ? err.message : 'Unknown error'}`,
        timestamp: new Date(),
      };
      setMessages(prev => [...prev, errorMessage]);
    } finally {
      setLoading(false);
    }
  }, []);

  // Handle collection selection
  // const handleCollectionSelect = useCallback((collectionId: string) => {
  //   setSelectedCollection(collectionId);
  //   // Don't clear messages when switching collections since chat works across all collections
  // }, []); // This function is no longer needed

  // Handle create group modal
  const handleCreateGroup = useCallback(() => {
    setIsCreateModalOpen(true);
  }, []);

  const handleCreateModalClose = useCallback(() => {
    setIsCreateModalOpen(false);
  }, []);

  const handleCreateSuccess = useCallback(() => {
    // Refresh collections to include the new group
    loadCollections();
  }, []);

  return (
    <div className="h-screen bg-gray-100 flex overflow-hidden">
      {/* Sidebar */}
      <CollectionsSidebar
        collections={collections}
        loading={collectionsLoading}
        error={collectionsError}
        onRefresh={loadCollections}
        onCreateGroup={handleCreateGroup}
      />

      {/* Main Content */}
      <div className="flex-1 flex flex-col">
        {/* Header */}
        <header className="bg-white border-b border-gray-200 px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <div className={`rounded-lg p-2 ${
                currentView === 'chat' ? 'bg-blue-600' : 'bg-green-600'
              }`}>
                {currentView === 'chat' ? (
                  <MessageSquare className="w-6 h-6 text-white" />
                ) : (
                  <FileText className="w-6 h-6 text-white" />
                )}
              </div>
              <div>
                <h1 className="text-xl font-bold text-gray-900">
                  {currentView === 'chat' ? 'Document Chat' : 'Fiscal Note Generation'}
                </h1>
                <p className="text-sm text-gray-500">
                  {currentView === 'chat'
                    ? 'Ask questions across all your document collections'
                    : 'Upload documents and analyze using selected collections'
                  }
                </p>
              </div>
            </div>
            
            {/* Navigation */}
            <div className="flex items-center space-x-4">
              <nav className="flex space-x-1">
                <button
                  onClick={() => setCurrentView('chat')}
                  className={`px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                    currentView === 'chat'
                      ? 'bg-blue-100 text-blue-700'
                      : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100'
                  }`}
                >
                  <MessageSquare className="w-4 h-4 inline mr-2" />
                  Chat
                </button>
                <button
                  onClick={() => setCurrentView('fiscal-note')}
                  className={`px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                    currentView === 'fiscal-note'
                      ? 'bg-green-100 text-green-700'
                      : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100'
                  }`}
                >
                  <FileText className="w-4 h-4 inline mr-2" />
                  Fiscal Note
                </button>
              </nav>
              
              {/* Status Indicator */}
              <div className="flex items-center space-x-2">
              {collectionsLoading && (
                <div className="flex items-center space-x-2 text-gray-500">
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span className="text-sm">Loading...</span>
                </div>
              )}
              
              {!collectionsLoading && collections.length > 0 && (
                <div className="flex items-center space-x-2 text-green-600">
                  <div className="w-2 h-2 bg-green-400 rounded-full"></div>
                  <span className="text-sm">Connected</span>
                </div>
              )}
              
              {collectionsError && (
                <div className="flex items-center space-x-2 text-red-600">
                  <AlertCircle className="w-4 h-4" />
                  <span className="text-sm">Connection Error</span>
                </div>
              )}
              </div>
            </div>
          </div>
        </header>

        {/* Main Content */}
        <div className="flex-1 overflow-hidden">
          {currentView === 'fiscal-note' ? (
            <FiscalNoteGeneration onBack={() => setCurrentView('chat')} />
          ) : (
            collectionsLoading ? (
            <div className="flex items-center justify-center h-full">
              <div className="text-center">
                <Loader2 className="w-8 h-8 text-blue-600 animate-spin mx-auto mb-4" />
                <p className="text-gray-600">Loading collections...</p>
              </div>
            </div>
          ) : collectionsError ? (
            <div className="flex items-center justify-center h-full">
              <div className="text-center max-w-md">
                <AlertCircle className="w-12 h-12 text-red-500 mx-auto mb-4" />
                <h3 className="text-lg font-semibold text-gray-900 mb-2">Connection Error</h3>
                <p className="text-gray-600 mb-4">{collectionsError}</p>
                <button
                  onClick={loadCollections}
                  className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
                >
                  Try Again
                </button>
              </div>
            </div>
          ) : collections.length === 0 ? (
            <div className="flex items-center justify-center h-full">
              <div className="text-center max-w-md">
                <MessageSquare className="w-12 h-12 text-gray-400 mx-auto mb-4" />
                <h3 className="text-lg font-semibold text-gray-900 mb-2">No Collections Found</h3>
                <p className="text-gray-600 mb-4">
                  No document collections are available. Make sure the backend has collections with documents.
                </p>
                <button
                  onClick={loadCollections}
                  className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
                >
                  Refresh
                </button>
              </div>
            </div>
          ) : (
              <ChatInterface
                messages={messages}
                onSendMessage={handleSendMessage}
                loading={loading}
              />
            )
          )}
        </div>
      </div>

      {/* Create Group Modal */}
      <CreateGroupModal
        isOpen={isCreateModalOpen}
        onClose={handleCreateModalClose}
        onSuccess={handleCreateSuccess}
      />
    </div>
  );
}

export default App;
