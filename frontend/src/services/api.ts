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
 * Create a new group/collection
 */
export const createGroup = async (
  name: string,
  description?: string
): Promise<{ collection_id: string; message: string }> => {
  const response = await api.post('/collections', {
    name,
    description,
  });
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

export default api; 