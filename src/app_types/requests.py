

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from fastapi import File
from fastapi import UploadFile

# Collection Request
class CollectionRequest(BaseModel):
    collection_name: str

class DriveUploadRequest(BaseModel):
    drive_url: str
    recursive: bool = True

class SearchRequest(BaseModel):
    query: str = Field(..., description="Search query")
    collections: Optional[List[str]] = Field(default=None, description="Collections to search in")
    num_results: int = Field(default=None, description="Number of results to return")
    search_type: str = Field(default="semantic", description="Type of search: semantic, metadata, or both")

class QueryRequest(BaseModel):
    query: str = Field(..., description="User query")
    collections: Optional[List[str]] = Field(default=None, description="Collections to search in")
    threshold: float = Field(default=0.0, ge=0.0, le=1.0, description="Similarity threshold (0.0 to 1.0) - only return documents with similarity scores above this threshold")

class DocumentResponse(BaseModel):
    content: str
    metadata: Dict[str, Any]
    score: Optional[float] = None

class ChunkingRequest(BaseModel):
    collection_name: str
    identifier: str = "fiscal_note"
    chunk_size: int = 1000
    chunk_overlap: int = 200
    use_ai: bool = False
    prompt_description: Optional[str] = None
    previous_pages_to_include: int = 1
    context_items_to_show: int = 2
    rewrite_query: bool = False
    chosen_methods: List[str] = ["pymupdf_extraction_text"]

class ChatWithPDFRequest(BaseModel):
    query: str = Field(..., description="User's question about the document")
    session_collection: str = Field(..., description="Unique collection ID for the uploaded document")
    context_collections: List[str] = Field(default=[], description="Additional collections to use as context")
    threshold: float = Field(default=0, description="Similarity threshold for search results")

class CrawlRequest(BaseModel):
    start_url: str
    extraction_prompt: str
    collection_name: str
    null_is_okay: bool = True

class UploadPDFRequest(BaseModel):
    collection_name: str
    files: List[UploadFile]


class CollectionStatistics(BaseModel):
    collection_name: str
    document_count: int
    embedding_model: Optional[str] = None
    error: Optional[str] = None


class CollectionsStatsResponse(BaseModel):
    collections: List[CollectionStatistics]
    total_collections: int
    total_documents: int