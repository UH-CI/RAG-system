import { useState, useEffect, useCallback } from 'react';
import { Upload, FileText, MessageSquare, Send, Loader2, CheckCircle, X } from 'lucide-react';
import type { Collection, ChatMessage } from '../types';
import { getCollections, createCollection, uploadPDFFiles, extractTextFromPDFs, chunkExtractedText, askQuestionWithCollections } from '../services/api';

interface FiscalNoteGenerationProps {
  onBack: () => void;
}

interface CollectionOption {
  id: string;
  name: string;
  isNew?: boolean;
}

interface UploadedDocument {
  id: string;
  name: string;
  size: number;
  uploadedAt: Date;
}

export default function FiscalNoteGeneration({ onBack }: FiscalNoteGenerationProps) {
  const [collections, setCollections] = useState<Collection[]>([]);
  const [selectedCollections, setSelectedCollections] = useState<string[]>([]);
  const [uploadedDocuments, setUploadedDocuments] = useState<UploadedDocument[]>([]);
  const [uploadCollectionName, setUploadCollectionName] = useState<string>('fiscal_documents');
  const [availableCollections, setAvailableCollections] = useState<CollectionOption[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [currentMessage, setCurrentMessage] = useState('');
  const [loading, setLoading] = useState(false);
  const [collectionsLoading, setCollectionsLoading] = useState(true);
  const [uploadLoading, setUploadLoading] = useState(false);
  const [dragActive, setDragActive] = useState(false);

  // Load collections on component mount
  const loadCollections = useCallback(async () => {
    setCollectionsLoading(true);
    try {
      const response = await getCollections();
      const collectionsArray: Collection[] = response.collections.map(
        (collection) => ({
          name: collection.name,
        })
      );
      setCollections(collectionsArray);
      
      // Also populate available collections for upload dropdown
      const collectionOptions: CollectionOption[] = collectionsArray.map(col => ({
        id: col.name,
        name: col.name
      }));
      // Add option to create new collection
      collectionOptions.push({ id: 'new', name: 'Create New Collection', isNew: true });
      setAvailableCollections(collectionOptions);
    } catch (err) {
      console.error('Failed to load collections:', err);
    } finally {
      setCollectionsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadCollections();
  }, [loadCollections]);

  // Handle file upload
  const handleFileUpload = useCallback(async (files: FileList | File[]) => {
    const fileArray = Array.from(files);
    const pdfFiles = fileArray.filter(file => file.type === 'application/pdf');
    
    if (pdfFiles.length === 0) {
      alert('Please select PDF files only.');
      return;
    }

    setUploadLoading(true);
    
    try {
      // Step 1: Upload PDF files to backend
      await uploadPDFFiles(uploadCollectionName, pdfFiles, (fileName: string, progress: number) => {
        console.log(`Uploading ${fileName}: ${progress}%`);
      });
      
      // Step 2: Extract text from PDFs
      await extractTextFromPDFs(uploadCollectionName, {
        contains_tables: false, // Assume fiscal documents may contain tables
        contains_images_of_text: false,
        contains_images_of_nontext: false,
      });
      
      // Step 3: Chunk the extracted text
      await chunkExtractedText(uploadCollectionName, {
        chosen_methods: ['pymupdf_extraction_text'],
        identifier: 'fiscal_note',
        chunk_size: 1000,
        chunk_overlap: 200,
        use_ai: false,
      });
      
      // Store uploaded document info locally
      const newDocuments: UploadedDocument[] = pdfFiles.map(file => ({
        id: `doc_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
        name: file.name,
        size: file.size,
        uploadedAt: new Date(),
      }));
      
      setUploadedDocuments(prev => [...prev, ...newDocuments]);
      
      // Add a system message about successful processing
      const uploadMessage: ChatMessage = {
        id: `upload_${Date.now()}`,
        type: 'assistant',
        content: `Successfully uploaded and processed ${pdfFiles.length} PDF document(s) to collection '${uploadCollectionName}': ${pdfFiles.map(f => f.name).join(', ')}. The documents have been extracted and chunked for analysis. You can now ask questions about these documents using the selected collections.`,
        timestamp: new Date(),
      };
      setMessages(prev => [...prev, uploadMessage]);
      
    } catch (err) {
      console.error('Upload failed:', err);
      const errorMsg = err instanceof Error ? err.message : 'Unknown error occurred';
      alert(`Failed to upload and process documents: ${errorMsg}`);
      
      // Add error message to chat
      const errorMessage: ChatMessage = {
        id: `error_${Date.now()}`,
        type: 'assistant',
        content: `Failed to upload and process documents: ${errorMsg}. Please try again.`,
        timestamp: new Date(),
      };
      setMessages(prev => [...prev, errorMessage]);
    } finally {
      setUploadLoading(false);
    }
  }, [uploadCollectionName]);

  // Handle drag and drop
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
    
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFileUpload(e.dataTransfer.files);
    }
  }, [handleFileUpload]);

  // Handle collection selection
  const handleCollectionToggle = useCallback((collectionId: string) => {
    setSelectedCollections(prev => 
      prev.includes(collectionId)
        ? prev.filter(id => id !== collectionId)
        : [...prev, collectionId]
    );
  }, []);

  // Handle sending a message
  const handleSendMessage = useCallback(async () => {
    if (!currentMessage.trim()) return;
    
    const userMessage: ChatMessage = {
      id: `user_${Date.now()}`,
      type: 'user',
      content: currentMessage,
      timestamp: new Date(),
    };

    setMessages(prev => [...prev, userMessage]);
    setCurrentMessage('');
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
      // Create a query that includes information about selected collections
      let queryText = currentMessage;
      if (selectedCollections.length > 0) {
        queryText += `\n\nPlease focus on information from these collections: ${selectedCollections.join(', ')}`;
      }
      if (uploadedDocuments.length > 0) {
        queryText += `\n\nI have uploaded these documents for analysis: ${uploadedDocuments.map(doc => doc.name).join(', ')}`;
      }

      const response = await askQuestionWithCollections(queryText, selectedCollections);
      
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
  }, [currentMessage, selectedCollections, uploadedDocuments]);

  const handleKeyPress = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  }, [handleSendMessage]);

  const removeDocument = useCallback((docId: string) => {
    setUploadedDocuments(prev => prev.filter(doc => doc.id !== docId));
  }, []);

  const formatFileSize = (bytes: number): string => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };
console.log(messages)
  return (
    <div className="h-full flex flex-col bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 px-6 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <button
              onClick={onBack}
              className="text-gray-500 hover:text-gray-700 transition-colors"
            >
              ← Back
            </button>
            <div className="bg-green-600 rounded-lg p-2">
              <FileText className="w-6 h-6 text-white" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-gray-900">Fiscal Note Generation</h1>
              <p className="text-sm text-gray-500">
                Upload documents and analyze using selected collections
              </p>
            </div>
          </div>
        </div>
      </header>

      <div className="flex-1 flex overflow-hidden">
        {/* Left Sidebar - Document Upload & Collections */}
        <div className="w-80 bg-white border-r border-gray-200 flex flex-col">
          {/* Document Upload Section */}
          <div className="p-4 border-b border-gray-200">
            <h3 className="text-sm font-semibold text-gray-900 mb-3">Upload Documents</h3>
            
            {/* Collection Selection for Upload */}
            <div className="mb-4">
              <label className="block text-xs font-medium text-gray-700 mb-2">
                Collection for Upload
              </label>
              <div className="flex space-x-2">
                <select
                  value={uploadCollectionName}
                  onChange={async (e) => {
                    if (e.target.value === 'new') {
                      const newName = prompt('Enter new collection name:');
                      if (newName && newName.trim()) {
                        try {
                          // Create the collection on the backend
                          const result = await createCollection(newName.trim());
                          const sanitizedName = result.collection_name;
                            console.log(sanitizedName)
                          // Update the upload collection name
                          setUploadCollectionName(sanitizedName);
                          
                          // Refresh the collections list to include the new collection
                          await loadCollections();
                          
                          // Add success message to chat
                          const successMessage: ChatMessage = {
                            id: `collection_created_${Date.now()}`,
                            type: 'assistant',
                            content: `✅ Successfully created new collection '${sanitizedName}'. You can now upload documents to this collection.`,
                            timestamp: new Date(),
                          };
                          setMessages(prev => [...prev, successMessage]);
                          
                        } catch (error) {
                          console.error('Failed to create collection:', error);
                          const errorMsg = error instanceof Error ? error.message : 'Unknown error occurred';
                          alert(`Failed to create collection: ${errorMsg}`);
                          
                          // Add error message to chat
                          const errorMessage: ChatMessage = {
                            id: `collection_error_${Date.now()}`,
                            type: 'assistant',
                            content: `❌ Failed to create collection '${newName}': ${errorMsg}`,
                            timestamp: new Date(),
                          };
                          setMessages(prev => [...prev, errorMessage]);
                        }
                      }
                    } else {
                      setUploadCollectionName(e.target.value);
                    }
                  }}
                  className="flex-1 text-xs border border-gray-300 rounded px-2 py-1 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                >
                  <option value="fiscal_documents">fiscal_documents (default)</option>
                  {availableCollections.filter(col => !col.isNew).map((col) => (
                    <option key={col.id} value={col.name}>{col.name}</option>
                  ))}
                  <option value="new">+ Create New Collection</option>
                </select>
              </div>
              <p className="text-xs text-gray-500 mt-1">
                Documents will be uploaded to: <span className="font-medium">{uploadCollectionName}</span>
              </p>
            </div>
            
            <div
              className={`border-2 border-dashed rounded-lg p-4 text-center transition-colors ${
                dragActive
                  ? 'border-blue-500 bg-blue-50'
                  : 'border-gray-300 hover:border-gray-400'
              }`}
              onDragEnter={handleDrag}
              onDragLeave={handleDrag}
              onDragOver={handleDrag}
              onDrop={handleDrop}
            >
              {uploadLoading ? (
                <div className="flex flex-col items-center">
                  <Loader2 className="w-8 h-8 text-blue-600 animate-spin mb-2" />
                  <p className="text-sm text-gray-600">Uploading...</p>
                </div>
              ) : (
                <div className="flex flex-col items-center">
                  <Upload className="w-8 h-8 text-gray-400 mb-2" />
                  <p className="text-sm text-gray-600 mb-2">
                    Drag & drop PDF files here, or{' '}
                    <label className="text-blue-600 hover:text-blue-700 cursor-pointer">
                      browse
                      <input
                        type="file"
                        multiple
                        accept=".pdf"
                        className="hidden"
                        onChange={(e) => e.target.files && handleFileUpload(e.target.files)}
                      />
                    </label>
                  </p>
                  <p className="text-xs text-gray-500">PDF files only</p>
                </div>
              )}
            </div>

            {/* Uploaded Documents List */}
            {uploadedDocuments.length > 0 && (
              <div className="mt-4">
                <h4 className="text-xs font-semibold text-gray-700 mb-2">Uploaded Documents</h4>
                <div className="space-y-2 max-h-32 overflow-y-auto">
                  {uploadedDocuments.map((doc) => (
                    <div key={doc.id} className="flex items-center justify-between bg-gray-50 rounded p-2">
                      <div className="flex items-center space-x-2 flex-1 min-w-0">
                        <FileText className="w-4 h-4 text-gray-500 flex-shrink-0" />
                        <div className="min-w-0 flex-1">
                          <p className="text-xs font-medium text-gray-900 truncate">{doc.name}</p>
                          <p className="text-xs text-gray-500">{formatFileSize(doc.size)}</p>
                        </div>
                      </div>
                      <button
                        onClick={() => removeDocument(doc.id)}
                        className="text-gray-400 hover:text-red-600 transition-colors"
                      >
                        <X className="w-4 h-4" />
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Collections Selection */}
          <div className="flex-1 p-4 overflow-y-auto">
            <h3 className="text-sm font-semibold text-gray-900 mb-3">Select Collections</h3>
            
            {collectionsLoading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="w-6 h-6 text-blue-600 animate-spin" />
              </div>
            ) : collections.length === 0 ? (
              <p className="text-sm text-gray-500 text-center py-8">No collections available</p>
            ) : (
              <div className="space-y-2">
                {collections.map((collection) => (
                  <label
                    key={collection.name}
                    className="flex items-center space-x-3 p-2 rounded-lg hover:bg-gray-50 cursor-pointer"
                  >
                    <input
                      type="checkbox"
                      checked={selectedCollections.includes(collection.name)}
                      onChange={() => handleCollectionToggle(collection.name)}
                      className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                    />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-gray-900">{collection.name}</p>
                      <p className="text-xs text-gray-500">
                      </p>
                    </div>
                    {selectedCollections.includes(collection.name) && (
                      <CheckCircle className="w-4 h-4 text-green-600" />
                    )}
                  </label>
                ))}
              </div>
            )}

            {selectedCollections.length > 0 && (
              <div className="mt-4 p-3 bg-blue-50 rounded-lg">
                <p className="text-xs font-semibold text-blue-900 mb-1">Selected Collections:</p>
                <p className="text-xs text-blue-700">
                  {selectedCollections.map(id => 
                    collections.find(c => c.name === id)?.name || id
                  ).join(', ')}
                </p>
              </div>
            )}
          </div>
        </div>

        {/* Right Side - Chat Interface */}
        <div className="flex-1 flex flex-col">
          {/* Messages Area */}
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {messages.length === 0 ? (
              <div className="flex items-center justify-center h-full">
                <div className="text-center max-w-md">
                  <MessageSquare className="w-12 h-12 text-gray-400 mx-auto mb-4" />
                  <h3 className="text-lg font-semibold text-gray-900 mb-2">Ready for Fiscal Analysis</h3>
                  <p className="text-gray-600 mb-4">
                    Upload PDF documents and select collections to start generating fiscal notes and analysis.
                  </p>
                  <div className="text-sm text-gray-500">
                    <p>• Upload relevant policy documents</p>
                    <p>• Select collections for context</p>
                    <p>• Ask questions about fiscal impact</p>
                  </div>
                </div>
              </div>
            ) : (
              messages.map((message) => (
                <div
                  key={message.id}
                  className={`flex ${message.type === 'user' ? 'justify-end' : 'justify-start'}`}
                >
                  <div
                    className={`max-w-3xl rounded-lg px-4 py-2 ${
                      message.type === 'user'
                        ? 'bg-blue-600 text-white'
                        : 'bg-white border border-gray-200 text-gray-900'
                    }`}
                  >
                    {message.isLoading ? (
                      <div className="flex items-center space-x-2">
                        <Loader2 className="w-4 h-4 animate-spin" />
                        <span className="text-sm">Analyzing...</span>
                      </div>
                    ) : (
                      <>
                        <div className="whitespace-pre-wrap">{message.content}</div>
                        {message.sources && message.sources.length > 0 && (
                          <div className="mt-3 pt-3 border-t border-gray-200">
                            <p className="text-xs font-semibold text-gray-600 mb-2">Sources:</p>
                            <div className="space-y-1">
                              {message.sources.slice(0, 3).map((source, idx) => (
                                <div key={idx} className="text-xs text-gray-600 bg-gray-50 rounded p-2">
                                  <div className="font-medium">{source.metadata?.title || `Source ${idx + 1}`}</div>
                                  <div className="truncate">{source.content ? source.content.substring(0, 100) + '...' : 'No content available'}</div>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                      </>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>

          {/* Message Input */}
          <div className="border-t border-gray-200 p-4 bg-white">
            <div className="flex space-x-3">
              <div className="flex-1">
                <textarea
                  value={currentMessage}
                  onChange={(e) => setCurrentMessage(e.target.value)}
                  onKeyPress={handleKeyPress}
                  placeholder="Ask questions about fiscal impact, budget analysis, or policy implications..."
                  className="w-full resize-none border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  rows={3}
                  disabled={loading}
                />
              </div>
              <button
                onClick={handleSendMessage}
                disabled={loading || !currentMessage.trim()}
                className="bg-blue-600 text-white rounded-lg px-4 py-2 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center space-x-2"
              >
                {loading ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Send className="w-4 h-4" />
                )}
                <span>Send</span>
              </button>
            </div>
            
            {(selectedCollections.length > 0 || uploadedDocuments.length > 0) && (
              <div className="mt-2 flex flex-wrap gap-2 text-xs">
                {uploadedDocuments.length > 0 && (
                  <span className="bg-green-100 text-green-800 px-2 py-1 rounded">
                    {uploadedDocuments.length} document(s) uploaded
                  </span>
                )}
                {selectedCollections.length > 0 && (
                  <span className="bg-blue-100 text-blue-800 px-2 py-1 rounded">
                    {selectedCollections.length} collection(s) selected
                  </span>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
