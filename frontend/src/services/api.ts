import axios from 'axios';
import type { SearchResponse, QuestionResponse, ApiError, CollectionsResponse } from '../types';

// API configuration
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8200';

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add response interceptor for error handling
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response) {
      // Server responded with error status
      const apiError: ApiError = {
        message: error.response.data?.detail || error.response.data?.message || 'Server error',
        code: error.response.status.toString(),
        details: error.response.data,
      };
      throw apiError;
    } else if (error.request) {
      // Request was made but no response received
      const apiError: ApiError = {
        message: 'Unable to connect to the server. Please check if the API is running.',
        code: 'CONNECTION_ERROR',
      };
      throw apiError;
    } else {
      // Something else happened
      const apiError: ApiError = {
        message: error.message || 'An unexpected error occurred',
        code: 'UNKNOWN_ERROR',
      };
      throw apiError;
    }
  }
);

/**
 * Get available collections and their stats
 */
export const getCollections = async (): Promise<CollectionsResponse> => {
  const response = await api.get('/collections');
  return response.data;
};

/**
 * Search documents in a specific collection
 */
export const searchDocuments = async (
  query: string,
  collection: string = 'courses',
  searchType: string = 'semantic',
  maxResults: number = 10
): Promise<SearchResponse> => {
  const response = await api.post('/search', {
    query,
    collections: [collection],
    search_type: searchType,
    num_results: maxResults,
  });

  // Transform the backend response to match our frontend types
  const backendResults = response.data;
  
  return {
    results: backendResults.map((item: any) => ({
      id: item.metadata?.id || `result_${Math.random()}`,
      content: item.content,
      metadata: item.metadata || {},
      score: item.score || 0,
    })),
    total_results: backendResults.length,
    query,
    collection,
    search_type: searchType,
  };
};

/**
 * Ask a question and get an AI-generated answer across all collections
 */
export const askQuestion = async (
  question: string
): Promise<QuestionResponse> => {
  const response = await api.post('/query', {
    query: question,
    // Don't specify collections - let it search across all collections
    threshold: 0,  // Default threshold for similarity filtering
  },{
    timeout: 300000, // 24 seconds
  });

  // Transform the backend response to match our frontend types
  const backendData = response.data;
  
  return {
    answer: backendData.response || 'No answer available',
    sources: (backendData.sources || []).map((source: any) => ({
      id: source.metadata?.id || `source_${Math.random()}`,
      content: source.content,
      metadata: source.metadata || {},
      score: source.score || 0,
    })),
    query: question,
    collection: 'all', // Indicate it searched across all collections
  };
};

/**
 * Health check endpoint
 */
export const healthCheck = async (): Promise<{ status: string }> => {
  const response = await api.get('/');
  return response.data;
};

/**
 * Upload documents to a group/collection
 */
export const uploadDocuments = async (
  collectionId: string,
  files: File[],
  parsingType: string,
  customParsingDescription?: string,
  onProgress?: (fileName: string, progress: number) => void
): Promise<{ message: string; processed_files: number }> => {
  const formData = new FormData();
  
  files.forEach((file) => {
    formData.append('files', file);
  });
  
  formData.append('parsing_type', parsingType);
  if (customParsingDescription) {
    formData.append('custom_description', customParsingDescription);
  }

  const response = await api.post(`/collections/${collectionId}/upload`, formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
    onUploadProgress: (progressEvent) => {
      if (progressEvent.total && onProgress) {
        const progress = Math.round((progressEvent.loaded * 100) / progressEvent.total);
        // For simplicity, we'll use the first file name for progress
        onProgress(files[0]?.name || 'files', progress);
      }
    },
  });

  return response.data;
};

/**
 * Create a new collection
 */
export const createCollection = async (
  collection_name: string,
): Promise<{ message: string; collection_name: string; collection_path: string; directories_created: any }> => {
  const response = await api.post('/create-collection', {
    collection_name: collection_name,
  });
  return response.data;
};

/**
 * Upload PDF files for fiscal note generation to a specific collection
 */
export const uploadPDFFiles = async (
  collectionName: string,
  files: File[],
  onProgress?: (fileName: string, progress: number) => void
): Promise<{ message: string; collection_name: string; uploaded_files: any[]; total_files: number }> => {
  const formData = new FormData();
  formData.append('collection_name', collectionName);

  files.forEach((file) => {
    formData.append('files', file);
  });

  const response = await api.post('/upload-pdf', formData, {
    headers: {
      'Content-Type': undefined, // Let browser set multipart/form-data with boundary
    },
    onUploadProgress: (progressEvent) => {
      if (progressEvent.total && onProgress) {
        const progress = Math.round((progressEvent.loaded * 100) / progressEvent.total);
        // For simplicity, we'll use the first file name for progress
        onProgress(files[0]?.name || 'files', progress);
      }
    },
  });

  return response.data;
};

/**
 * Upload PDF files to a collection path
 */
export const uploadPDFToCollection = async (
  files: File[],
  collection_path: string
): Promise<any> => {
  const formData = new FormData();
  files.forEach(file => formData.append('files', file));
  formData.append('collection_path', collection_path);
  
  const response = await api.post('/upload-pdf', formData, {
    headers: {
      'Content-Type': 'multipart/form-data'
    }
  });
  return response.data;
};

/**
 * Upload documents from Google Drive
 */
export const uploadFromGoogleDrive = async (
  folder_link: string,
  collection_path: string,
  recursive: boolean
): Promise<any> => {
  const response = await api.post('/upload-through-google-drive', {
    folder_link,
    collection_path,
    recursive
  });
  return response.data;
};

/**
 * Upload documents via web crawler
 */
export const uploadFromWebUrl = async (
  url: string,
  collection_path: string
): Promise<any> => {
  const response = await api.post('/web-crawler', {
    url,
    collection_path
  });
  return response.data;
};

/**
 * Extract text from documents
 */
export const extractText = async (
  collection_path: string,
  extract_tables: boolean,
  extract_images_with_text: boolean,
  extract_images_without_text: boolean
): Promise<any> => {
  const response = await api.post('/step1-text-extraction', {
    collection_path,
    extract_tables,
    extract_images_with_text,
    extract_images_without_text
  });
  return response.data;
};

/**
 * Chunk extracted text
 */
export const chunkText = async (
  collection_path: string,
  chunking_method: string,
  chunk_size: number,
  chunk_overlap: number,
  use_ai: boolean,
  context_prompt: string
): Promise<any> => {
  const response = await api.post('/step2-chunking', {
    collection_name: collection_path, // Backend expects collection_name
    chosen_methods: [chunking_method], // Backend expects chosen_methods array
    chunk_size,
    chunk_overlap,
    use_ai,
    prompt_description: context_prompt, // Backend expects prompt_description
    identifier: 'fiscal_note', // Add required field
    previous_pages_to_include: 1, // Add default
    context_items_to_show: 2, // Add default
    rewrite_query: false // Add default
  });
  return response.data;
};

/**
 * Extract text from all PDF files in a collection
 */
export const extractTextFromPDFs = async (
  collectionName: string,
  options: {
    contains_tables?: boolean;
    contains_images_of_text?: boolean;
    contains_images_of_nontext?: boolean;
  } = {}
): Promise<{ message: string; collection_name: string; processed_files: any[]; total_processed: number; errors: string[] }> => {
  const response = await api.post('/step1-text-extraction', null, {
    params: {
      collection_name: collectionName,
      contains_tables: options.contains_tables || false,
      contains_images_of_text: options.contains_images_of_text || false,
      contains_images_of_nontext: options.contains_images_of_nontext || false,
    },
  });

  return response.data;
};

/**
 * Chunk extracted text from all files in a collection
 */
export const chunkExtractedText = async (
  collectionName: string,
  options: {
    chosen_methods?: string[];
    identifier?: string;
    chunk_size?: number;
    chunk_overlap?: number;
    use_ai?: boolean;
    prompt_description?: string;
    previous_pages_to_include?: number;
    context_items_to_show?: number;
    rewrite_query?: boolean;
  } = {}
): Promise<{ message: string; collection_name: string; processed_files: any[]; total_processed: number; errors: string[] }> => {
  const response = await api.post('/step2-chunking', {
    collection_name: collectionName,
    chosen_methods: options.chosen_methods || ['pymupdf_extraction_text'],
    identifier: options.identifier || 'fiscal_note',
    chunk_size: options.chunk_size || 1000,
    chunk_overlap: options.chunk_overlap || 200,
    use_ai: options.use_ai || false,
    prompt_description: options.prompt_description,
    previous_pages_to_include: options.previous_pages_to_include || 1,
    context_items_to_show: options.context_items_to_show || 2,
    rewrite_query: options.rewrite_query || false,
  });

  return response.data;
};

/**
 * Ask a question with specific collections selected
 */
export const askQuestionWithCollections = async (
  question: string,
  selectedCollections: string[] = []
): Promise<QuestionResponse> => {
  const response = await api.post('/query', {
    query: question,
    collections: selectedCollections.length > 0 ? selectedCollections : undefined,
    threshold: 0,
  }, {
    timeout: 300000, // 5 minutes for complex fiscal analysis
  });

  const backendData = response.data;
  
  return {
    answer: backendData.response || 'No answer available',
    sources: (backendData.sources || []).map((source: any) => ({
      id: source.metadata?.id || `source_${Math.random()}`,
      content: source.content,
      metadata: source.metadata || {},
      score: source.score || 0,
    })),
    query: question,
    collection: selectedCollections.length > 0 ? selectedCollections.join(', ') : 'all',
  };
};

/**
 * Chat with a specific PDF document using additional collections as context
 */
export const chatWithPDF = async (
  query: string,
  sessionCollection: string,
  contextCollections: string[] = [],
  threshold: number = 0
): Promise<{
  response: string;
  sources: any[];
  session_collection: string;
  context_collections: string[];
  valid_collections_used: string[];
  query: string;
}> => {
  const response = await api.post('/chat-with-pdf', {
    query,
    session_collection: sessionCollection,
    context_collections: contextCollections,
    threshold,
  }, {
    timeout: 300000, // 5 minutes for complex analysis
  });
  console.log(response.data);
  return response.data;
};

/**
 * Stream chat with PDF - provides real-time updates during subquestion processing
 */
export const streamChatWithPDF = async (
  query: string,
  sessionCollection: string,
  contextCollections: string[] = [],
  threshold: number = 0,
  onUpdate: (update: any) => void,
  onError: (error: string) => void,
  onComplete: (response: any) => void
): Promise<void> => {
  try {
    console.log('🚀 FRONTEND: Starting streaming connection...');
    console.log('📝 Request data:', { query: query.substring(0, 50) + '...', sessionCollection, contextCollections, threshold });
    
    const response = await fetch(`${API_BASE_URL}/chat-with-pdf-stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        query,
        session_collection: sessionCollection,
        context_collections: contextCollections,
        threshold,
      }),
    });

    console.log('📡 Response status:', response.status, response.statusText);
    console.log('📡 Response headers:', Object.fromEntries(response.headers.entries()));

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const reader = response.body?.getReader();
    if (!reader) {
      throw new Error('Failed to get response reader');
    }

    console.log('✅ FRONTEND: Stream reader obtained successfully');
    const decoder = new TextDecoder();
    let buffer = '';
    let messageCount = 0;

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) {
          console.log('📡 FRONTEND: Stream ended (done=true)');
          break;
        }

        const chunk = decoder.decode(value, { stream: true });
        buffer += chunk;
        messageCount++;
        
        console.log(`📨 FRONTEND: Received chunk ${messageCount}:`, chunk.substring(0, 100) + (chunk.length > 100 ? '...' : ''));
        
        const lines = buffer.split('\n');
        buffer = lines.pop() || ''; // Keep incomplete line in buffer

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const jsonData = line.slice(6);
              console.log('🔍 FRONTEND: Parsing JSON:', jsonData.substring(0, 200) + (jsonData.length > 200 ? '...' : ''));
              const data = JSON.parse(jsonData);
              
              console.log('✅ FRONTEND: Parsed data:', data.type, data.message?.substring(0, 50));
              
              if (data.type === 'error') {
                console.log('❌ FRONTEND: Error received:', data.message);
                onError(data.message);
                return;
              } else if (data.type === 'completed') {
                console.log('🏁 FRONTEND: Completion received');
                onComplete(data.response);
                return;
              } else {
                console.log('📤 FRONTEND: Calling onUpdate with:', data.type);
                onUpdate(data);
              }
            } catch (parseError) {
              console.error('❌ FRONTEND: Failed to parse streaming data:', parseError, 'Line:', line);
            }
          } else if (line.trim()) {
            console.log('⚠️ FRONTEND: Non-data line received:', line);
          }
        }
      }
    } finally {
      reader.releaseLock();
    }
  } catch (error) {
    console.error('Streaming error:', error);
    onError(error instanceof Error ? error.message : 'Unknown streaming error');
  }
};

export default api; 