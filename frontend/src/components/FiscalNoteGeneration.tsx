import { useState, useEffect, useCallback } from 'react';
import { Upload, FileText, MessageSquare, Send, Loader2, CheckCircle, X, ChevronDown, ChevronRight, Clock, Search, Brain, FileCheck } from 'lucide-react';
import type { Collection, ChatMessage } from '../types';
import { getCollections, uploadPDFFiles, extractTextFromPDFs, chunkExtractedText, chatWithPDF, streamChatWithPDF } from '../services/api';

interface FiscalNoteGenerationProps {
  onBack: () => void;
}



interface UploadedDocument {
  id: string;
  name: string;
  size: number;
  uploadedAt: Date;
}

interface StreamingUpdate {
  type: 'status' | 'subquestions_generated' | 'hypothetical_answers_generated' | 'subquestion_start' | 'subquestion_completed' | 'completed' | 'error';
  message?: string;
  timestamp: string;
  stage?: string;
  subquestion?: string;
  subquestions?: string[];
  hypothetical_answers?: string[];
  answer?: string;
  index?: number;
  total?: number;
  search_results_count?: number;
  response?: any;
  processing_time?: number;
}

interface SubquestionProgress {
  id: string;
  question: string;
  status: 'pending' | 'processing' | 'completed';
  stage: 'waiting' | 'hypothetical' | 'searching' | 'answering' | 'done';
  answer?: string;
  searchResultsCount?: number;
  timestamp?: string;
  expanded: boolean;
}

export default function FiscalNoteGeneration({ onBack }: FiscalNoteGenerationProps) {
  const [collections, setCollections] = useState<Collection[]>([]);
  const [selectedCollections, setSelectedCollections] = useState<string[]>([]);
  const [uploadedDocuments, setUploadedDocuments] = useState<UploadedDocument[]>([]);
  const [sessionId] = useState<string>(() => `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`);
  const [sessionCollectionName] = useState<string>(() => `pdf_session_${sessionId}`);

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [currentMessage, setCurrentMessage] = useState('');
  const [loading, setLoading] = useState(false);
  const [collectionsLoading, setCollectionsLoading] = useState(true);
  const [uploadLoading, setUploadLoading] = useState(false);
  const [dragActive, setDragActive] = useState(false);

  // Streaming state
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingStatus, setStreamingStatus] = useState('');
  const [subquestions, setSubquestions] = useState<SubquestionProgress[]>([]);
  const [hypotheticalAnswers, setHypotheticalAnswers] = useState<string[]>([]);
  const [currentStage, setCurrentStage] = useState('');
  const [processingTime, setProcessingTime] = useState<number | null>(null);
  const [streamingError, setStreamingError] = useState<string | null>(null);

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
      
      // Collections are now loaded for context selection only
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
      // Step 1: Upload PDF files to unique session collection
      await uploadPDFFiles(sessionCollectionName, pdfFiles, (fileName: string, progress: number) => {
        console.log(`Uploading ${fileName}: ${progress}%`);
      });
      
      // Step 2: Extract text from PDFs
      await extractTextFromPDFs(sessionCollectionName, {
        contains_tables: false,
        contains_images_of_text: false,
        contains_images_of_nontext: false,
      });
      
      // Step 3: Chunk the extracted text
      await chunkExtractedText(sessionCollectionName, {
        chosen_methods: ['pymupdf_extraction_text'],
        identifier: 'pdf_document',
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
        content: `Successfully uploaded and processed ${pdfFiles.length} PDF document(s): ${pdfFiles.map(f => f.name).join(', ')}. The documents have been extracted and chunked for analysis. You can now ask questions about these documents. Select additional collections below for extra context if needed.`,
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
  }, []);

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

  // Handle subquestion expansion toggle
  const toggleSubquestionExpansion = useCallback((id: string) => {
    setSubquestions(prev => prev.map(sq => 
      sq.id === id ? { ...sq, expanded: !sq.expanded } : sq
    ));
  }, []);

  // Handle streaming updates
  const handleStreamingUpdate = useCallback((update: StreamingUpdate) => {
    console.log('Streaming update:', update);
    
    switch (update.type) {
      case 'status':
        setStreamingStatus(update.message || '');
        setCurrentStage(update.stage || '');
        break;
        
      case 'subquestions_generated':
        if (update.subquestions) {
          const newSubquestions: SubquestionProgress[] = update.subquestions.map((q, index) => ({
            id: `subq_${index}`,
            question: q,
            status: 'pending',
            stage: 'waiting',
            expanded: false,
            timestamp: update.timestamp
          }));
          setSubquestions(newSubquestions);
        }
        break;
        
      case 'hypothetical_answers_generated':
        if (update.hypothetical_answers) {
          setHypotheticalAnswers(update.hypothetical_answers);
        }
        break;
        
      case 'subquestion_start':
        if (typeof update.index === 'number') {
          setSubquestions(prev => prev.map((sq, idx) => 
            idx === update.index ? { ...sq, status: 'processing', stage: 'hypothetical' } : sq
          ));
        }
        break;
        
      case 'subquestion_completed':
        if (typeof update.index === 'number' && update.answer) {
          setSubquestions(prev => prev.map((sq, idx) => 
            idx === update.index ? { 
              ...sq, 
              status: 'completed', 
              stage: 'done',
              answer: update.answer,
              searchResultsCount: update.search_results_count,
              timestamp: update.timestamp
            } : sq
          ));
        }
        break;
    }
  }, []);

  // Handle streaming completion
  const handleStreamingComplete = useCallback((response: any) => {
    setIsStreaming(false);
    setLoading(false);
    setProcessingTime(response.processing_time);
    
    // Remove loading message and add final response
    setMessages(prev => {
      const withoutLoading = prev.filter(msg => !msg.isLoading);
      const assistantMessage: ChatMessage = {
        id: `assistant_${Date.now()}`,
        type: 'assistant',
        content: response.response,
        sources: response.sources,
        timestamp: new Date(),
      };
      return [...withoutLoading, assistantMessage];
    });
    // Do NOT clear subquestions or answers here; preserve them for display
    setStreamingStatus('');
    setCurrentStage('');
  }, []);

  // Handle streaming error
  const handleStreamingError = useCallback((error: string) => {
    setIsStreaming(false);
    setLoading(false);
    setStreamingError(error);
    
    // Remove loading message and show error
    setMessages(prev => {
      const withoutLoading = prev.filter(msg => !msg.isLoading);
      const errorMessage: ChatMessage = {
        id: `error_${Date.now()}`,
        type: 'assistant',
        content: `Error during analysis: ${error}. Please try again.`,
        timestamp: new Date(),
      };
      return [...withoutLoading, errorMessage];
    });
  }, []);

  // Handle sending a message with streaming
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
    setIsStreaming(true);
    setStreamingError(null);
    // Only reset subquestions and answers when a new message is sent
    setSubquestions([]);
    setHypotheticalAnswers([]);
    setProcessingTime(null);

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
      await streamChatWithPDF(
        currentMessage,
        sessionCollectionName,
        selectedCollections,
        0,
        handleStreamingUpdate,
        handleStreamingError,
        handleStreamingComplete
      );
    } catch (err) {
      handleStreamingError(err instanceof Error ? err.message : 'Unknown error occurred');
    }
  }, [currentMessage, sessionCollectionName, selectedCollections, handleStreamingUpdate, handleStreamingError, handleStreamingComplete]);

  // Fallback to non-streaming if needed
  const handleSendMessageFallback = useCallback(async () => {
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
      const response = await chatWithPDF(
        currentMessage,
        sessionCollectionName,
        selectedCollections,
        0
      );
      
      // Remove loading message and add real response
      setMessages(prev => {
        const withoutLoading = prev.filter(msg => msg.id !== loadingMessage.id);
        const assistantMessage: ChatMessage = {
          id: `assistant_${Date.now()}`,
          type: 'assistant',
          content: response.response,
          sources: response.sources,
          timestamp: new Date(),
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

  const formatMarkdownContent = (content: string): string => {
    let html = content;
    
    // Convert headers
    html = html.replace(/^### (.*$)/gim, '<h3 class="text-md font-medium text-gray-700 mb-2 mt-4">$1</h3>');
    html = html.replace(/^## (.*$)/gim, '<h2 class="text-lg font-semibold text-gray-800 mb-2 mt-4">$1</h2>');
    html = html.replace(/^# (.*$)/gim, '<h1 class="text-xl font-bold text-gray-900 mb-3 mt-4">$1</h1>');
    
    // Convert bold text
    html = html.replace(/\*\*(.*?)\*\*/g, '<strong class="font-semibold text-gray-900">$1</strong>');
    
    // Convert bullet points
    html = html.replace(/^\* (.*$)/gim, '<li class="text-gray-700 mb-1">$1</li>');
    html = html.replace(/(<li.*<\/li>)/s, '<ul class="list-disc list-inside space-y-1 mb-3">$1</ul>');
    
    // Convert tables
    const tableRegex = /\|(.*)\|/g;
    const lines = html.split('\n');
    let inTable = false;
    let tableRows: string[] = [];
    let processedLines: string[] = [];
    
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i].trim();
      
      if (tableRegex.test(line)) {
        if (!inTable) {
          inTable = true;
          tableRows = [];
        }
        
        const cells = line.split('|').filter(cell => cell.trim() !== '').map(cell => cell.trim());
        
        // Skip separator rows (like |---|---|)
        if (!cells.every(cell => /^-+$/.test(cell))) {
          const isHeader = tableRows.length === 0;
          const cellTag = isHeader ? 'th' : 'td';
          const cellClass = isHeader 
            ? 'border border-gray-300 px-4 py-2 text-left font-semibold text-gray-900 bg-gray-50'
            : 'border border-gray-300 px-4 py-2 text-gray-700';
          
          const rowHtml = `<tr>${cells.map(cell => 
            `<${cellTag} class="${cellClass}">${cell}</${cellTag}>`
          ).join('')}</tr>`;
          
          tableRows.push(rowHtml);
        }
      } else {
        if (inTable) {
          // End of table, process accumulated rows
          const tableHtml = `
            <div class="overflow-x-auto my-4">
              <table class="min-w-full border-collapse border border-gray-300">
                ${tableRows.join('\n')}
              </table>
            </div>
          `;
          processedLines.push(tableHtml);
          inTable = false;
          tableRows = [];
        }
        processedLines.push(line);
      }
    }
    
    // Handle case where table is at the end
    if (inTable && tableRows.length > 0) {
      const tableHtml = `
        <div class="overflow-x-auto my-4">
          <table class="min-w-full border-collapse border border-gray-300">
            ${tableRows.join('\n')}
          </table>
        </div>
      `;
      processedLines.push(tableHtml);
    }
    
    html = processedLines.join('\n');
    
    // Convert line breaks to paragraphs
    html = html.replace(/\n\n/g, '</p><p class="mb-3 text-gray-700 leading-relaxed">');
    html = html.replace(/\n/g, '<br>');
    html = `<p class="mb-3 text-gray-700 leading-relaxed">${html}</p>`;
    
    // Clean up empty paragraphs
    html = html.replace(/<p class="mb-3 text-gray-700 leading-relaxed">\s*<\/p>/g, '');
    
    return html;
  };
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
            
            {/* Session Info */}
            <div className="mb-4 p-2 bg-blue-50 rounded-lg">
              <p className="text-xs text-blue-700">
                <strong>Session:</strong> {sessionId}
              </p>
              <p className="text-xs text-blue-600 mt-1">
                Documents uploaded in this session will be stored in a unique collection for focused analysis.
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
              <>
                {/* Subquestions Reasoning Section */}
                {subquestions.length > 0 && (
                  <div className="mb-6 bg-white border border-gray-200 rounded-lg p-4">
                    <h4 className="text-sm font-semibold text-gray-800 mb-3">Multi-Step Reasoning</h4>
                    <ol className="space-y-3">
                      {subquestions.map((sq, idx) => (
                        <li key={sq.id} className="border-b last:border-b-0 border-gray-100 pb-2">
                          <div className="flex items-center justify-between">
                            <span className="text-xs text-gray-500">Subquestion {idx + 1}</span>
                            <span className={
                              sq.status === 'completed'
                                ? 'text-green-600 text-xs font-medium'
                                : sq.status === 'processing'
                                ? 'text-blue-600 text-xs font-medium'
                                : 'text-gray-400 text-xs'
                            }>
                              {sq.status === 'completed' ? 'Answered' : sq.status === 'processing' ? 'In Progress' : 'Waiting'}
                            </span>
                          </div>
                          <div className="mt-1 text-sm text-gray-900 font-medium">{sq.question}</div>
                          {sq.answer && (
                            <div className="mt-2 bg-gray-50 rounded p-3 text-sm text-gray-700 whitespace-pre-line">
                              {sq.answer}
                            </div>
                          )}
                        </li>
                      ))}
                    </ol>
                  </div>
                )}
                {/* Chat Messages Section */}
                {messages.map((message) => (
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
                        <div 
                          className="prose prose-sm max-w-none"
                          dangerouslySetInnerHTML={{
                            __html: formatMarkdownContent(message.content)
                          }}
                        />
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
              ))}
            </>
            )}
            
            {/* Streaming Progress UI */}
            {isStreaming && (
              <div className="mt-6 bg-gradient-to-r from-blue-50 to-indigo-50 rounded-lg p-4 border border-blue-200">
                <div className="flex items-center mb-4">
                  <Loader2 className="w-5 h-5 text-blue-600 animate-spin mr-2" />
                  <h3 className="text-sm font-semibold text-blue-900">Multi-Step Analysis in Progress</h3>
                  {processingTime && (
                    <span className="ml-auto text-xs text-blue-600">
                      {processingTime.toFixed(1)}s
                    </span>
                  )}
                </div>
                
                {/* Current Status */}
                {streamingStatus && (
                  <div className="mb-4 p-3 bg-white rounded-md border border-blue-100">
                    <div className="flex items-center">
                      <Clock className="w-4 h-4 text-blue-500 mr-2" />
                      <span className="text-sm text-blue-800">{streamingStatus}</span>
                    </div>
                    {currentStage && (
                      <div className="mt-1 text-xs text-blue-600 capitalize">
                        Stage: {currentStage.replace('_', ' ')}
                      </div>
                    )}
                  </div>
                )}
                
                {/* Subquestions Progress */}
                {subquestions.length > 0 && (
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <h4 className="text-sm font-medium text-blue-900">Analysis Questions</h4>
                      <span className="text-xs text-blue-600">
                        {subquestions.filter(sq => sq.status === 'completed').length} / {subquestions.length} completed
                      </span>
                    </div>
                    
                    <div className="space-y-2">
                      {subquestions.map((subquestion, index) => (
                        <div key={subquestion.id} className="bg-white rounded-md border border-gray-200">
                          <button
                            onClick={() => toggleSubquestionExpansion(subquestion.id)}
                            className="w-full px-3 py-2 text-left flex items-center justify-between hover:bg-gray-50 transition-colors"
                          >
                            <div className="flex items-center flex-1">
                              <div className="flex items-center mr-3">
                                {subquestion.status === 'completed' ? (
                                  <CheckCircle className="w-4 h-4 text-green-500" />
                                ) : subquestion.status === 'processing' ? (
                                  <Loader2 className="w-4 h-4 text-blue-500 animate-spin" />
                                ) : (
                                  <Clock className="w-4 h-4 text-gray-400" />
                                )}
                              </div>
                              <div className="flex-1">
                                <div className="text-sm font-medium text-gray-900 truncate">
                                  {subquestion.question}
                                </div>
                                <div className="flex items-center mt-1 space-x-2">
                                  <span className={`text-xs px-2 py-1 rounded-full ${
                                    subquestion.status === 'completed' 
                                      ? 'bg-green-100 text-green-800'
                                      : subquestion.status === 'processing'
                                      ? 'bg-blue-100 text-blue-800'
                                      : 'bg-gray-100 text-gray-600'
                                  }`}>
                                    {subquestion.status === 'completed' ? 'Completed' : 
                                     subquestion.status === 'processing' ? 'Processing' : 'Pending'}
                                  </span>
                                  {subquestion.stage !== 'waiting' && (
                                    <span className="text-xs text-gray-500 capitalize">
                                      {subquestion.stage.replace('_', ' ')}
                                    </span>
                                  )}
                                  {subquestion.searchResultsCount && (
                                    <span className="text-xs text-gray-500 flex items-center">
                                      <Search className="w-3 h-3 mr-1" />
                                      {subquestion.searchResultsCount} docs
                                    </span>
                                  )}
                                </div>
                              </div>
                            </div>
                            <div className="ml-2">
                              {subquestion.expanded ? (
                                <ChevronDown className="w-4 h-4 text-gray-400" />
                              ) : (
                                <ChevronRight className="w-4 h-4 text-gray-400" />
                              )}
                            </div>
                          </button>
                          
                          {/* Expanded Content */}
                          {subquestion.expanded && (
                            <div className="px-3 pb-3 border-t border-gray-100">
                              {subquestion.answer ? (
                                <div className="mt-3">
                                  <div className="flex items-center mb-2">
                                    <Brain className="w-4 h-4 text-blue-500 mr-2" />
                                    <span className="text-sm font-medium text-gray-900">Analysis Result</span>
                                  </div>
                                  <div className="text-sm text-gray-700 bg-gray-50 rounded p-3">
                                    {subquestion.answer.length > 200 
                                      ? `${subquestion.answer.substring(0, 200)}...`
                                      : subquestion.answer
                                    }
                                  </div>
                                  {subquestion.timestamp && (
                                    <div className="text-xs text-gray-500 mt-2">
                                      Completed: {new Date(subquestion.timestamp).toLocaleTimeString()}
                                    </div>
                                  )}
                                </div>
                              ) : (
                                <div className="mt-3 text-sm text-gray-500 italic">
                                  {subquestion.status === 'processing' 
                                    ? 'Analysis in progress...'
                                    : 'Waiting to start analysis...'
                                  }
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                
                {/* Hypothetical Answers Preview */}
                {hypotheticalAnswers.length > 0 && (
                  <div className="mt-4 p-3 bg-yellow-50 rounded-md border border-yellow-200">
                    <div className="flex items-center mb-2">
                      <FileCheck className="w-4 h-4 text-yellow-600 mr-2" />
                      <span className="text-sm font-medium text-yellow-900">Hypothetical Guidance Generated</span>
                    </div>
                    <div className="text-xs text-yellow-700">
                      {hypotheticalAnswers.length} preliminary answers generated to guide document search
                    </div>
                  </div>
                )}
                
                {/* Error Display */}
                {streamingError && (
                  <div className="mt-4 p-3 bg-red-50 rounded-md border border-red-200">
                    <div className="flex items-center">
                      <X className="w-4 h-4 text-red-500 mr-2" />
                      <span className="text-sm font-medium text-red-900">Analysis Error</span>
                    </div>
                    <div className="text-sm text-red-700 mt-1">{streamingError}</div>
                  </div>
                )}
              </div>
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
