from fastapi import FastAPI, HTTPException, Query, Form, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from typing import List, Optional, Dict, Any
import os
from pathlib import Path
import json
import google.generativeai as genai
from tqdm import tqdm
import logging
from datetime import datetime
from documents.step0_document_upload.web_scraper import ai_crawler
from typing import Generator

from src.types.requests import *

from documents.step0_document_upload.google_upload import download_pdfs_from_drive
from documents.step1_text_extraction.pdf_text_extractor import extract_pdf_text
from documents.step2_chunking.chunker import chunk_document

# Handle both relative and absolute imports
try:
    from .settings import Settings
    from .documents.embeddings import ChromaDBManager
    from .query_processor import QueryProcessor
    from .langgraph_agent import LangGraphRAGAgent
except ImportError:
    from settings import Settings
    from documents.embeddings import ChromaDBManager
    from query_processor import QueryProcessor
    from langgraph_agent import LangGraphRAGAgent

# Load configuration
def load_config() -> Dict[str, Any]:
    """Load configuration from config.json"""
    config_path = Path(__file__).parent / "config.json"
    with open(config_path, 'r') as f:
        return json.load(f)

config = load_config()

# Initialize FastAPI app with config
app = FastAPI(
    title=config["api"]["title"],
    description=config["api"]["description"],
    version=config["api"]["version"]
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



class DynamicChromeManager(ChromaDBManager):
    """Dynamic ChromaDB manager that works with any collection name"""
    def __init__(self, collection_name: str):
        self.collection_name = collection_name
        
        # Initialize the base class components first
        self.client = None
        self.collection = None
        self.embedding_function = None
        
        # Initialize client and embedding function
        self._initialize_client()
        self._initialize_embedding_function()
        
        # Now create/get the specific collection
        try:
            # Try to get existing collection
            self.collection = self.client.get_collection(
                name=collection_name,
                embedding_function=self.embedding_function
            )
            print(f"✅ Retrieved existing collection: {collection_name}")
            
        except Exception:
            # Create new collection if it doesn't exist
            self.collection = self.client.create_collection(
                name=collection_name,
                embedding_function=self.embedding_function,
                metadata={"hnsw:space": "cosine"}
            )
            print(f"✅ Created new collection: {collection_name}")
    
    def add_document(self, document: dict, ingestion_config: dict) -> bool:
        """Add a document to the collection using specified contents_to_embed"""
        try:
            # Extract content fields specified in ingestion config
            contents_to_embed = ingestion_config.get("contents_to_embed", [])
            
            # Combine all specified content fields
            content_parts = []
            for field in contents_to_embed:
                if field in document and document[field]:
                    content_parts.append(str(document[field]))
            
            if not content_parts:
                print(f"No content found in fields {contents_to_embed} for document")
                return False
            
            # Join all content with newlines
            combined_content = "\n\n".join(content_parts)
            
            # Generate unique ID
            import time
            import uuid
            doc_id = f"{self.collection_name}_{uuid.uuid4().hex[:8]}_{int(time.time())}"
            
            # Use entire document as metadata, ensuring all values are JSON-serializable
            metadata = {}
            for key, value in document.items():
                if value is not None:
                    if isinstance(value, (str, int, float, bool)):
                        metadata[key] = value
                    else:
                        metadata[key] = str(value)
                else:
                    metadata[key] = ""
            
            # Add system metadata
            metadata["id"] = doc_id
            metadata["collection"] = self.collection_name
            metadata["embedded_fields"] = json.dumps(contents_to_embed)  # Convert list to JSON string
            
            self.collection.add(
                documents=[combined_content],
                metadatas=[metadata],
                ids=[doc_id]
            )
            return True
                        
        except Exception as e:
            print(f"Error adding document to {self.collection_name}: {e}")
            return False
    
    def search_similar_chunks(self, query: str, num_results: int = 50) -> List[Dict[str, Any]]:
        """Search for similar chunks in the collection"""
        try:
            # HACK: Increase results for budget collection to account for filtering
            if self.collection_name == "budget":
                # Request 4x for budget to ensure we get ~200 items after filtering
                actual_num_results = min(num_results * 4, 800)  # Cap at 800 to avoid excessive queries
            else:
                actual_num_results = num_results
            
            results = self.collection.query(
                query_texts=[query],
                n_results=actual_num_results
            )
            
            formatted_results = []
            print("🔍 Number of results before filtering:", len(results["documents"][0]))
            if results["documents"] and results["documents"][0]:
                for i, doc in enumerate(results["documents"][0]):
                    result = {
                        "content": doc,
                        "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                        "score": 1.0 - results["distances"][0][i] if results["distances"] else 1.0
                    }
                    
                    # HACK: Filter out budget items with "unknown" values
                    if self.collection_name == "budget":
                        content_lower = doc.lower()
                        metadata_str = str(result["metadata"]).lower()
                        metadata = result["metadata"]
                        
                        # Check for "unknown" in specific metadata fields
                        fiscal_2025_amount = str(metadata.get("fiscal_year_2025_2026_amount", "")).lower()
                        fiscal_2026_amount = str(metadata.get("fiscal_year_2026_2027_amount", "")).lower()
                        expending_agency = str(metadata.get("expending_agency", "")).lower()
                        
                        # Filter if "unknown" appears in key financial fields (original logic)
                        should_filter_original = (
                            "amount: unknown" in content_lower or
                            "appropriation: unknown" in content_lower or
                            "funding: unknown" in content_lower or
                            "budget: unknown" in content_lower or
                            "'amount': 'unknown'" in metadata_str or
                            "'appropriation': 'unknown'" in metadata_str or
                            "'funding': 'unknown'" in metadata_str or
                            "'budget': 'unknown'" in metadata_str
                        )
                        
                        # Filter if "unknown" appears in specific metadata fields (new logic)
                        should_filter_metadata = (
                            "unknown" in fiscal_2025_amount or
                            "unknown" in fiscal_2026_amount or
                            "unknown" in expending_agency
                        )
                        
                        if should_filter_original or should_filter_metadata:
                            continue  # Skip this item
                    
                    formatted_results.append(result)
            print("🔍 Number of results after filtering:", len(formatted_results))
            # Limit to original requested number after filtering
            return formatted_results[:num_results]
                            
        except Exception as e:
            print(f"Error searching in {self.collection_name}: {e}")
            return []

# Create collection managers dynamically from config
collection_names = config["collections"]
collection_managers: Dict[str, DynamicChromeManager] = {}

for collection_name in collection_names:
    collection_managers[collection_name] = DynamicChromeManager(collection_name)

# Initialize query processor with collection managers and config
query_processor = QueryProcessor(collection_managers, config)

# Initialize LangGraph RAG Agent
try:
    langgraph_agent = LangGraphRAGAgent(collection_managers, config)
    print("✅ LangGraph RAG Agent initialized successfully")
    USE_LANGGRAPH = True
except Exception as e:
    print(f"⚠️  LangGraph Agent initialization failed: {e}")
    print("🔄 Falling back to traditional QueryProcessor")
    langgraph_agent = None
    USE_LANGGRAPH = False

# Helper functions for collection management
def get_collection_manager(collection_name: str) -> DynamicChromeManager:
    """Get collection manager by name"""
    if collection_name not in collection_managers:
        raise HTTPException(status_code=404, detail=f"Collection '{collection_name}' not found")
    
    return collection_managers[collection_name]

def get_ingestion_config(collection_name: str) -> dict:
    """Get ingestion configuration for a specific collection"""
    for config_item in config.get("ingestion_configs", []):
        if config_item.get("collection_name") == collection_name:
            return config_item
    
    # Return default if not found
    return {
        "collection_name": collection_name,
        "contents_to_embed": ["text", "content", "description"]
    }

def get_default_collection_manager() -> DynamicChromeManager:
    """Get the default collection manager"""
    default_collection = config.get("default_collection", collection_names[0])
    if default_collection not in collection_managers:
        # If default collection doesn't exist, use first available collection
        default_collection = collection_names[0]
    return get_collection_manager(default_collection)

def ingest_from_source_file(collection_name: str, source_file: str, ingestion_config: dict) -> dict:
    """Ingest documents from a source file into a specific collection"""
    try:
        from settings import settings
        import os
        
        # Construct full file path
        file_path = os.path.join(settings.documents_path, source_file)
        
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Source file not found: {file_path}")
        
        # Load and parse JSON file
        with open(file_path, 'r') as f:
            data = json.load(f)
        
        # Expect JSON to be an array of documents
        if not isinstance(data, list):
            raise Exception(f"JSON file must contain an array of documents, got {type(data)}")
        
        documents = data
        manager = get_collection_manager(collection_name)
        
        # Ingest documents
        ingested_count = 0
        errors = []
        
        print(f"📥 Ingesting {len(documents)} documents from '{source_file}' into '{collection_name}'...")
        print(f"🎯 Embedding fields: {ingestion_config.get('contents_to_embed', [])}")
        
        for i, doc in enumerate(tqdm(documents, desc=f"Processing {source_file}")):
            try:
                if manager.add_document(doc, ingestion_config):
                    ingested_count += 1
                else:
                    errors.append(f"Document {i}: Failed to add to collection")
            except Exception as e:
                errors.append(f"Document {i}: {str(e)}")
                continue
        
        return {
            "success": True,
            "collection_name": collection_name,
            "source_file": source_file,
            "ingested_count": ingested_count,
            "total_documents": len(documents),
            "embedded_fields": ingestion_config.get('contents_to_embed', []),
            "errors": errors[:10]
        }
        
    except Exception as e:
        return {
            "success": False,
            "collection_name": collection_name,
            "source_file": source_file,
            "error": str(e),
            "ingested_count": 0,
            "total_documents": 0
        }


def get_search_params(num_results: Optional[int] = None) -> int:
    """Get search parameters with config defaults"""
    if num_results is None:
        return config["search"]["default_results"]
    return min(num_results, config["search"]["max_results"])

def process_pdf_file( file_location: str,
    output_json_path: str,
    chunked_json_path: str,
    contains_tables: bool = Query(False, description="Set to True if the PDF contains tables."),
    contains_images_of_text: bool = Query(False, description="Set to True if the PDF has images containing text."),
    contains_images_of_nontext: bool = Query(False, description="Set to True for non-text images (uses OCR as a placeholder)."),
    # New parameters for chunking
    use_ai: bool = Query(False, description="If True, uses AI-powered chunking; otherwise, simple chunking."),
    chosen_methods: Optional[List[str]] = Query(None, description="For AI chunking: list of text fields to combine (e.g., ['pymupdf_extraction_text'])."),
    prompt_description: Optional[str] = Query(None, description="For AI chunking: prompt for LLM on how to extract items."),
    previous_pages_to_include: int = Query(1, description="For AI chunking: number of previous pages for context."),
    context_items_to_show: int = Query(2, description="For AI chunking: number of previously extracted items for few-shot examples."),
    rewrite_query: bool = Query(False, description="For AI chunking: If True, refine prompt_description with LLM."),
    chosen_method: Optional[str] = Query(None, description="For simple chunking: single text field to chunk (e.g., 'pymupdf_extraction_text')."),
    chunk_size: int = Query(1000, description="For simple chunking: character count per chunk."),
    overlap: int = Query(100, description="For simple chunking: character overlap between chunks.")):
    # Call the PDF text extraction function
    # Based on your instruction, we assume 'extract_pdf_text' will be modified
    # to *not* take an 'output_path' and instead return the extracted data directly.
    # The API endpoint will then be responsible for saving this data.
    try:
        print(f"Starting text extraction for {file.filename}...")
        extracted_data = extract_pdf_text(
            pdf_file_path=file_location,
            output_path=output_json_path,
            contains_tables=contains_tables,
            contains_images_of_text=contains_images_of_text,
            contains_images_of_nontext=contains_images_of_nontext
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error extracting text: {str(e)}")
    
    try:    
        # Save the extracted data to a JSON file
        with open(output_json_path, 'w', encoding='utf-8') as f:
            json.dump(extracted_data, f, indent=2, ensure_ascii=False)
        print(f"Extracted text saved to: {output_json_path}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error saving extracted text: {str(e)}")

    try:
        # Call the chunking function
        print(f"Starting chunking for {file.filename}...")
        from documents.step2_chunking.chunker import chunk_document # Import locally to avoid circular dependency issues if any
        chunk_document(
            input_json_path=output_json_path, # Input for chunking is the output from extraction
        output_json_path=chunked_json_path,
        use_ai=use_ai,
        chosen_methods=chosen_methods,
        prompt_description=prompt_description,
        previous_pages_to_include=previous_pages_to_include,
        context_items_to_show=context_items_to_show,
        rewrite_query=rewrite_query,
        chosen_method=chosen_method,
        chunk_size=chunk_size,
        overlap=overlap
    )
        print(f"Chunked data saved to: {chunked_json_path}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error chunking document: {str(e)}")
    return {"message": "PDF processed successfully"}


def search_relevant_documents(query: str, collections: Optional[List[str]] = None, num_results: int = None) -> List[Dict[str, Any]]:
    """Search for relevant documents across collections"""
    if num_results is None:
        num_results = get_search_params()
    
    search_collections = collections or collection_names
    all_results = []
    
    for collection_name in search_collections:
        try:
            manager = get_collection_manager(collection_name)
            results = manager.search_similar_chunks(query, num_results)
            
            for result in results:
                result["metadata"]["collection"] = collection_name
                all_results.append(result)
        except Exception as e:
            print(f"Error searching collection {collection_name}: {e}")
            continue
                            
    # Sort by score and return top results
    if all_results and "score" in all_results[0]:
        all_results.sort(key=lambda x: x.get("score", 0), reverse=True)
    
    return all_results[:num_results]

@app.get("/")
async def root():
    processing_method = "LangGraph Agentic Workflow" if USE_LANGGRAPH else "Multi-step Reasoning"
    
    return {
        "message": f"Welcome to {config['api']['title']}",
        "version": config['api']['version'],
        "available_collections": collection_names,
        "processing_method": processing_method,
        "features": [
            "🤖 Agentic query processing with LangGraph tools" if USE_LANGGRAPH else "Multi-step query processing with reasoning",
            "🔍 Intelligent tool-based document search" if USE_LANGGRAPH else "Semantic search across collections",
            "📊 Dynamic context building and analysis",
            "📚 Document ingestion and management",
            "📈 Collection statistics and management"
        ],
        "endpoints": ["/search", "/query", "/ingest", "/reset", "/collections"],
        "agentic_features": [
            "Query analysis and intent detection",
            "Strategic tool-based search execution", 
            "Context-aware answer generation",
            "Multi-collection intelligent search"
        ] if USE_LANGGRAPH else None
    }

@app.get("/chunked_text")
async def get_chunked_text():
    """Get chunked text stored in documents/chunked_text folder"""
    chunked_text = []
    for filename in os.listdir("documents/chunked_text"):
        chunked_text.append({
            "filename": filename,
            "path": os.path.join("documents/chunked_text", filename)
        })
    
    return {
        "chunked_text": chunked_text,
        "total_chunked_text": len(chunked_text)
    }

@app.get("/documents")
async def get_documents():
    """Get documents stored in documents/storage_documents folder"""
    documents = []
    for filename in os.listdir("documents/storage_documents"):
        documents.append({
            "filename": filename,
            "path": os.path.join("documents/storage_documents", filename)
        })
    
    return {
        "documents": documents,
        "total_documents": len(documents)
    }

@app.get("/collections")
async def get_collections():
    """Get list of collections stored in documents/storage_documents folder, 
    AKA, list of directories in documents/storage_documents folder"""
    base_path = "documents/storage_documents"
    collections = []

    for entry in os.listdir(base_path):
        full_path = os.path.join(base_path, entry)
        if os.path.isdir(full_path):
            num_documents = len(os.listdir(full_path))
        else:
            # Skip files like .DS_Store
            continue
        if os.path.isdir(full_path):
            print(f"Found collection: {entry}")
            collections.append({
                "name": entry,
                "num_documents": num_documents
            })

    return {
        "collections": collections,
        "total_collections": len(collections)
    }

@app.post("/search", response_model=List[DocumentResponse])
async def search_documents(request: SearchRequest):
    """Search documents across specified collections"""
    num_results = get_search_params(request.num_results)
    search_collections = request.collections or collection_names
    
    # Validate collections
    for collection_name in search_collections:
        if collection_name not in collection_managers:
            raise HTTPException(status_code=400, detail=f"Collection '{collection_name}' not found")
    
    all_results = []
    
    for collection_name in search_collections:
        try:
            manager = get_collection_manager(collection_name)
            results = manager.search_similar_chunks(request.query, num_results)
            
            # Add collection info to metadata
            for result in results:
                result["metadata"]["collection"] = collection_name
                all_results.append(DocumentResponse(
                    content=result["content"],
                    metadata=result["metadata"],
                    score=result.get("score")
                ))
        except Exception as e:
            print(f"Error searching collection {collection_name}: {e}")
            continue
            
    # Sort by score if available and limit results
    if all_results and all_results[0].score is not None:
        all_results.sort(key=lambda x: x.score, reverse=True)
    
    return all_results[:num_results]



@app.post("/query")
async def query_documents(request: QueryRequest):
    """Advanced query processing with agentic LangGraph workflow or multi-step reasoning fallback"""
    try:
        # if USE_LANGGRAPH and langgraph_agent is not None:
        #     # Use LangGraph RAG Agent (agentic approach)
        #     print(f"🤖 Using LangGraph Agent for query: '{request.query}'")
        #     result = langgraph_agent.process_query(request.query, threshold=request.threshold)
            
        #     # Add metadata about the request
        #     result["query"] = request.query
        #     result["collections_available"] = collection_names
        #     result["processing_method"] = "langgraph-agentic"
        #     result["threshold_used"] = request.threshold
            
        # else:
        # Fallback to traditional multi-step query processor
        print(f"🔄 Using traditional QueryProcessor for query: '{request.query}'")
        result = query_processor.process_query(request.query, threshold=request.threshold)
        
        # Add metadata about the request
        result["query"] = request.query
        result["collections_available"] = collection_names
        result["processing_method"] = "multi-step-reasoning"
        result["threshold_used"] = request.threshold
        
        return result
                            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing query: {str(e)}")




@app.post("/step2-chunking")
async def step2_chunking(payload: ChunkingRequest):
    """
    Chunk extracted text from all JSON files in a specific collection.
    
    Args:
        collection_name (str): Name of the collection to process.
        chosen_methods (List[str]): Methods to use for chunking.
        identifier (str): Identifier for the chunking process.
        chunk_size (int): Size of each chunk.
        chunk_overlap (int): Overlap between chunks.
        use_ai (bool): Whether to use AI for chunking.
        prompt_description (Optional[str]): Prompt description for AI chunking.
        previous_pages_to_include (int): Number of previous pages for context.
        context_items_to_show (int): Number of context items to show.
        rewrite_query (bool): Whether to rewrite the query.
    """
    logging.info(f"Starting chunking for collection '{payload.collection_name}'")
    # Define paths
    collection_extracted_dir = os.path.join("documents", "extracted_text", payload.collection_name)
    collection_chunked_dir = os.path.join("documents", "chunked_text", payload.collection_name)

    # Check if collection extracted directory exists
    if not os.path.exists(collection_extracted_dir):
        raise HTTPException(status_code=404, detail=f"Collection '{payload.collection_name}' not found in extracted text")
    
    # Create chunked text directory for collection
    os.makedirs(collection_chunked_dir, exist_ok=True)
    
    # Get all JSON files in the extracted text collection
    json_files = [f for f in os.listdir(collection_extracted_dir) if f.lower().endswith('.json')]
    logging.info(f"Found {len(json_files)} JSON files in collection '{payload.collection_name}'")
    if not json_files:
        raise HTTPException(status_code=404, detail=f"No extracted text files found in collection '{payload.collection_name}'")
    
    processed_files = []
    errors = []
    
    logging.info(f"Starting chunking for collection '{payload.collection_name}' with {len(json_files)} files...")
    
    for filename in json_files:
        try:
            file_path = os.path.join(collection_extracted_dir, filename)
            output_json_path = os.path.join(collection_chunked_dir, filename)
            logging.info(f"Processing file: {filename}")
            chunked_data = chunk_document(
                input_json_path=file_path,
                output_json_path=output_json_path,
                chosen_methods=payload.chosen_methods,
                identifier=payload.identifier,
                use_ai=payload.use_ai,
                prompt_description=payload.prompt_description,
                previous_pages_to_include=payload.previous_pages_to_include,
                context_items_to_show=payload.context_items_to_show,
                rewrite_query=payload.rewrite_query,
                chunk_size=payload.chunk_size,
                overlap=payload.chunk_overlap
            )
            
            # Save the chunked data to a JSON file
            with open(output_json_path, 'w', encoding='utf-8') as f:
                json.dump(chunked_data, f, indent=2, ensure_ascii=False)
            
            logging.info(f"Chunked text saved to: {output_json_path}")
            processed_files.append({
                "filename": filename,
                "output_path": output_json_path,
                "chunks_created": len(chunked_data) if isinstance(chunked_data, list) else 1
            })
            
        except Exception as e:
            error_msg = f"Error processing {filename}: {str(e)}"
            print(f"❌ {error_msg}")
            errors.append(error_msg)
    
    if not processed_files:
        raise HTTPException(status_code=500, detail=f"Failed to chunk any files in collection '{payload.collection_name}'. Errors: {'; '.join(errors)}")
    
    return {
        "message": f"Chunking completed for collection '{payload.collection_name}'",
        "collection_name": payload.collection_name,
        "processed_files": processed_files,
        "total_processed": len(processed_files),
        "errors": errors
    }

@app.post("/chat-with-pdf")
async def chat_with_pdf(payload: ChatWithPDFRequest):
    """
    Chat with a specific document (session collection) using additional collections as context.
    
    This is a generalized endpoint that allows users to:
    1. Upload a document to a unique session collection
    2. Ask questions about that document
    3. Use other collections as additional context for better answers
    
    Args:
        payload: ChatWithPDFRequest containing query, session_collection, context_collections, and threshold
    """
    try:
        # Combine session collection with context collections
        all_collections = [payload.session_collection] + payload.context_collections
        
        # Filter out any collections that don't exist
        valid_collections = []
        for collection_name in all_collections:
            collection_path = os.path.join("documents", "chunked_text", collection_name)
            if os.path.exists(collection_path) and os.listdir(collection_path):
                valid_collections.append(collection_name)
            else:
                logging.warning(f"Collection '{collection_name}' not found or empty, skipping")
        
        if not valid_collections:
            raise HTTPException(
                status_code=404, 
                detail=f"No valid collections found. Session collection '{payload.session_collection}' and context collections {payload.context_collections} are either missing or empty."
            )
        
        logging.info(f"Processing chat query with collections: {valid_collections}")
        
        # Use the specialized single PDF method with primary collection and context collections
        response = langgraph_agent.process_query_with_single_pdf(
            query=payload.query,
            primary_collection=payload.session_collection,
            context_collections=payload.context_collections,
            threshold=payload.threshold
        )
        
        return {
            "response": response.get("response", "No response generated"),
            "rest_of_response": response,
            "sources": response.get("sources", []),
            "session_collection": payload.session_collection,
            "context_collections": payload.context_collections,
            "valid_collections_used": valid_collections,
            "query": payload.query
        }
        
    except Exception as e:
        logging.error(f"Error in chat-with-pdf: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing chat query: {str(e)}")

def generate_stream(request: ChatWithPDFRequest) -> Generator[str, None, None]:
    try:
        print(f"📡 Starting stream generation...")
        
        # Validate collections by checking if they exist on disk
        valid_collections = []
        
        def collection_exists_on_disk(collection_name: str) -> bool:
            """Check if collection directory exists in storage_documents"""
            collection_path = os.path.join("documents", "storage_documents", collection_name)
            return os.path.exists(collection_path) and os.path.isdir(collection_path)
        
        # Check session collection
        if request.session_collection:
            if collection_exists_on_disk(request.session_collection):
                valid_collections.append(request.session_collection)
                print(f"✅ Valid session collection: {request.session_collection}")
                # Load into memory if not already loaded
                if request.session_collection not in collection_managers:
                    collection_managers[request.session_collection] = DynamicChromeManager(request.session_collection)
                    print(f"📥 Loaded session collection into memory: {request.session_collection}")
            else:
                print(f"❌ Invalid session collection (not found on disk): {request.session_collection}")
        
        # Check context collections
        if request.context_collections:
            for collection in request.context_collections:
                if collection_exists_on_disk(collection):
                    valid_collections.append(collection)
                    print(f"✅ Valid context collection: {collection}")
                    # Load into memory if not already loaded
                    if collection not in collection_managers:
                        collection_managers[collection] = DynamicChromeManager(collection)
                        print(f"📥 Loaded context collection into memory: {collection}")
                else:
                    print(f"❌ Invalid context collection (not found on disk): {collection}")
        
        if not valid_collections:
            error_msg = f"data: {json.dumps({'type': 'error', 'message': 'No valid collections found'})}\n\n"
            print(f"❌ No valid collections, sending: {error_msg}")
            yield error_msg
            return
        
        # Send initial status
        initial_status = f"data: {json.dumps({'type': 'status', 'message': 'Starting analysis...', 'timestamp': datetime.now().isoformat()})}\n\n"
        print(f"📤 Sending initial status: {initial_status.strip()}")
        yield initial_status
        
        # Send a test message to verify streaming is working
        test_message = f"data: {json.dumps({'type': 'status', 'message': 'TEST: Streaming connection established!', 'timestamp': datetime.now().isoformat()})}\n\n"
        print(f"📤 Sending test message: {test_message.strip()}")
        yield test_message
        
        # Create a streaming version of the LangGraph agent
        print(f"🔄 Starting streaming agent with collections: {valid_collections}")
        for update in langgraph_agent.process_query_with_single_pdf_stream(
            query=request.query,
            primary_collection=request.session_collection,
            context_collections=request.context_collections,
            threshold=request.threshold
        ):
            stream_data = f"data: {json.dumps(update)}\n\n"
            print(f"📤 Streaming update: {update.get('type', 'unknown')} - {update.get('message', '')[:100]}...")
            yield stream_data
            
    except Exception as e:
        logging.error(f"Error in streaming chat-with-pdf: {str(e)}")
        yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

@app.post("/chat-with-pdf-stream")
async def chat_with_pdf_stream(request: ChatWithPDFRequest):
    """Streaming version of chat-with-pdf that provides real-time updates"""
    
    print(f"🚀 STREAMING ENDPOINT CALLED: query='{request.query[:50]}...', session_collection='{request.session_collection}'")
    
    return StreamingResponse(
        generate_stream(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Content-Type": "text/event-stream"
        }
    )

@app.post("/step1-text-extraction") 
async def step1_text_extraction(
    collection_name: str, 
    contains_tables: bool = False, 
    contains_images_of_text: bool = False, 
    contains_images_of_nontext: bool = False
):
    """
    Extract text from all PDF files in a specific collection.
    
    Args:
        collection_name (str): Name of the collection to process.
        contains_tables (bool): Whether PDFs contain tables that should be extracted.
        contains_images_of_text (bool): Whether PDFs contain images with text that should be OCR'd.
        contains_images_of_nontext (bool): Whether PDFs contain non-text images.
    """
    # Define paths
    collection_storage_dir = os.path.join("documents", "storage_documents", collection_name)
    collection_extracted_dir = os.path.join("documents", "extracted_text", collection_name)
    
    # Check if collection storage directory exists
    if not os.path.exists(collection_storage_dir):
        raise HTTPException(status_code=404, detail=f"Collection '{collection_name}' not found in storage documents")
    
    # Create extracted text directory for collection
    os.makedirs(collection_extracted_dir, exist_ok=True)
    
    # Get all PDF files in the collection
    pdf_files = [f for f in os.listdir(collection_storage_dir) if f.lower().endswith('.pdf')]
    
    if not pdf_files:
        raise HTTPException(status_code=404, detail=f"No PDF files found in collection '{collection_name}'")
    
    processed_files = []
    errors = []
    
    print(f"Starting text extraction for collection '{collection_name}' with {len(pdf_files)} files...")
    
    for filename in pdf_files:
        try:
            file_path = os.path.join(collection_storage_dir, filename)
            output_json_path = os.path.join(collection_extracted_dir, filename.replace(".pdf", ".json"))
            
            extracted_data = extract_pdf_text(
                pdf_file_path=file_path,
                output_path=output_json_path,
                contains_tables=contains_tables,
                contains_images_of_text=contains_images_of_text,
                contains_images_of_nontext=contains_images_of_nontext
            )
            
            # Save the extracted data to a JSON file
            with open(output_json_path, 'w', encoding='utf-8') as f:
                json.dump(extracted_data, f, indent=2, ensure_ascii=False)
            
            print(f"Extracted text saved to: {output_json_path}")
            processed_files.append({
                "filename": filename,
                "output_path": output_json_path,
                "pages_extracted": len(extracted_data) if isinstance(extracted_data, list) else 1
            })
            
        except Exception as e:
            error_msg = f"Error processing {filename}: {str(e)}"
            print(f"❌ {error_msg}")
            errors.append(error_msg)
    
    if not processed_files:
        raise HTTPException(status_code=500, detail=f"Failed to extract text from any files in collection '{collection_name}'. Errors: {'; '.join(errors)}")
    
    return {
        "message": f"Text extraction completed for collection '{collection_name}'",
        "collection_name": collection_name,
        "processed_files": processed_files,
        "total_processed": len(processed_files),
        "errors": errors
    }



@app.post("/crawl-through-web")
async def crawl_through_web(
    payload: CrawlRequest
):
    try:
        # Save to src/documents/storage_documents
        stats = ai_crawler(
            start_url=  payload.start_url,
            extraction_prompt=payload.extraction_prompt,
            collection_name=payload.collection_name,
            null_is_okay=payload.null_is_okay
        )
        return {"message": f"Crawling completed successfully for {payload.collection_name} with {len(stats)} items created"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error downloading PDFs: {str(e)}")

@app.post("/upload-through-google-drive")
async def upload_through_google_drive(payload: DriveUploadRequest):
    try:
        # Save to src/documents/storage_documents
        download_path = os.path.join("documents", "storage_documents")
        stats = download_pdfs_from_drive(
            drive_url=payload.drive_url,
            download_path=download_path,
            recursive=payload.recursive
        )
        return {"downloaded": stats["downloaded"], "failed": stats["failed"], "folders_processed": stats["folders_processed"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error downloading PDFs: {str(e)}")

    
@app.post("/create-collection")
async def create_collection(payload: CollectionRequest):
    collection_name = payload.collection_name

    if not collection_name or not collection_name.strip():
        raise HTTPException(status_code=400, detail="Collection name cannot be empty")
    
    sanitized_name = collection_name.strip().lower().replace(' ', '_')
    
    collection_storage_dir = os.path.join("./documents/storage_documents", sanitized_name)
    collection_extracted_dir = os.path.join("./documents/extracted_text", sanitized_name)
    collection_chunked_dir = os.path.join("./documents/chunked_text", sanitized_name)

    try:
        os.makedirs(collection_storage_dir, exist_ok=True)
        os.makedirs(collection_extracted_dir, exist_ok=True)
        os.makedirs(collection_chunked_dir, exist_ok=True)

        return {
            "message": f"Collection '{sanitized_name}' created successfully",
            "collection_name": sanitized_name,
            "directories_created": {
                "storage": collection_storage_dir,
                "extracted_text": collection_extracted_dir,
                "chunked_text": collection_chunked_dir
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create collection '{sanitized_name}': {str(e)}")



@app.post("/upload-pdf")
async def upload_pdf(
    collection_name: str = Form(...),
    files: List[UploadFile] = File(...)
):
    """
    Uploads PDF files to a specific collection directory.

    Args:
        collection_name (str): Name of the collection to organize files under.
        files (List[UploadFile]): List of PDF files to upload.
    """
    # Create collection-specific directory structure
    collection_storage_dir = os.path.join("./documents/storage_documents", collection_name)
    
    # Ensure collection directory exists
    os.makedirs(collection_storage_dir, exist_ok=True)
    
    uploaded_files = []
    
    for file in files:
        # Validate file type
        if not file.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail=f"File {file.filename} is not a PDF")
        
        file_location = os.path.join(collection_storage_dir, file.filename)
        
        try:
            # Write the file in chunks to handle potentially large files
            with open(file_location, "wb") as buffer:
                while contents := await file.read(1024 * 1024): # Read 1MB chunks
                    buffer.write(contents)
            
            print(f"Successfully uploaded {file.filename} to {file_location}")
            uploaded_files.append({
                "filename": file.filename,
                "path": file_location,
                "size": os.path.getsize(file_location)
            })
            
        except Exception as e:
            # Clean up the uploaded PDF if upload fails
            if os.path.exists(file_location):
                os.remove(file_location)
            # Convert exception to string representation to avoid binary encoding issues
            error_msg = str(e)
            raise HTTPException(status_code=500, detail=f"Could not upload file {file.filename}: {error_msg}")
    
    return {
        "message": f"Successfully uploaded {len(uploaded_files)} PDF file(s) to collection '{collection_name}'",
        "collection_name": collection_name,
        "uploaded_files": uploaded_files,
        "total_files": len(uploaded_files)
    }

@app.post("/reset")
async def reset_collections(collections: Optional[List[str]] = None):
    """Reset specified collections or all collections"""
    target_collections = collections or collection_names
    
    reset_results = {}
    
    for collection_name in target_collections:
        try:
            if collection_name in collection_managers:
                manager = collection_managers[collection_name]
                manager.reset_collection()
                reset_results[collection_name] = "success"
                print(f"✅ Reset collection: {collection_name}")
            else:
                reset_results[collection_name] = "collection not found"
        except Exception as e:
            reset_results[collection_name] = f"error: {str(e)}"
            print(f"❌ Error resetting {collection_name}: {e}")
        
        return {
        "message": f"Reset operation completed for collections: {list(target_collections)}",
        "results": reset_results
    }

# Debug endpoint for collection managers
@app.get("/debug/managers")
async def debug_managers():
    """Debug endpoint to check collection managers"""
    return {
        "config_collections": collection_names,
        "active_managers": list(collection_managers.keys()),
        "config": config
    }