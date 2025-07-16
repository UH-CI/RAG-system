export interface SearchResult {
  id: string;
  content: string;
  metadata: Record<string, any>;
  score: number;
}

export interface CollectionStats {
  count: number;
  name: string;
  status: string;
}

export interface CollectionsResponse {
  collections: Record<string, CollectionStats>;
  config: {
    default_collection: string;
    collection_aliases?: Record<string, string>;
    total_collections: number;
  };
}

export interface Collection {
  id: string;
  name: string;
  count: number;
  status: string;
}

export interface SearchResponse {
  results: SearchResult[];
  total_results: number;
  query: string;
  collection: string;
  search_type: string;
}

export interface QuestionResponse {
  answer: string;
  sources: SearchResult[];
  query: string;
  collection: string;
}

export interface ChatMessage {
  id: string;
  type: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  collection?: string;
  sources?: SearchResult[];
  isLoading?: boolean;
}

export interface ApiError {
  message: string;
  code?: string;
  details?: any;
}

export interface DocumentParsingType {
  id: string;
  label: string;
  description: string;
}

export interface CreateGroupData {
  name: string;
  description?: string;
  documents: File[];
  parsingType: string;
  customParsingDescription?: string;
}

export interface CreateGroupStep {
  id: number;
  title: string;
  description: string;
}

export interface UploadProgress {
  fileName: string;
  progress: number;
  status: 'pending' | 'uploading' | 'completed' | 'error';
  error?: string;
} 