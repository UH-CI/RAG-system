from fastapi import FastAPI, HTTPException, Query, Form, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from typing import List, Dict, Any, Optional, Union
import os
from pathlib import Path
import json
import google.generativeai as genai
from tqdm import tqdm
import logging
from datetime import datetime
from documents.step0_document_upload.web_scraper import ai_crawler
from typing import Generator

from app_types.requests import (
    CollectionRequest, SearchRequest, QueryRequest,
    ChunkingRequest, DocumentResponse, CrawlRequest,
    UploadPDFRequest, ChatWithPDFRequest, DriveUploadRequest,
    CollectionStatistics, CollectionsStatsResponse
)

from documents.step0_document_upload.google_upload import download_pdfs_from_drive
from documents.step1_text_extraction.pdf_text_extractor import extract_pdf_text
from documents.step2_chunking.chunker import chunk_document
from documents.step0_document_upload.web_scraper import scrape_bill_page_links


from settings import Settings
from documents.embeddings import DynamicChromeManager
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

# Allowed origins — add your domain here once it is assigned
ALLOWED_ORIGINS = [
    "http://149.165.170.204",
    "http://149.165.170.204:3000",
    "https://hoku.its.hawaii.edu",
    "http://localhost:3000",
    # "https://yourdomain.com",  # uncomment and update once domain is live
]

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


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


def get_collection_stats(collection_manager: DynamicChromeManager) -> Dict[str, Any]:
    """Get statistics for a collection"""
    try:
        from settings import settings
        count = collection_manager.collection.count()
        return {
            "collection_name": collection_manager.collection_name,
            "document_count": count,
            "embedding_model": settings.embedding_model
        }
    except Exception as e:
        print(f"Error getting stats for collection {collection_manager.collection_name}: {str(e)}")
        return {
            "collection_name": collection_manager.collection_name,
            "document_count": 0,
            "error": str(e)
        }

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
    """Ingest documents from a source file into a specific collection using batching"""
    try:
        from settings import settings
        import os
        
        # Construct full file path
        file_path = os.path.join(settings.documents_path, source_file)
        
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Source file not found: {file_path}")
        
        # Load and parse JSON file
        with open(file_path, 'r') as f:
            documents = json.load(f)
        
        # Expect JSON to be an array of documents
        if not isinstance(documents, list):
            raise Exception(f"JSON file must contain an array of documents, got {type(documents)}")
        
        manager = get_collection_manager(collection_name)
        
        # Prepare documents for ingestion
        doc_ids = []
        contents = []
        metadatas = []
        
        for doc in tqdm(documents, desc=f"Preparing docs from {source_file}"):
            prepared_doc = manager.prepare_document_for_ingestion(doc, collection_name, ingestion_config)
            if prepared_doc:
                doc_ids.append(prepared_doc['doc_id'])
                contents.append(prepared_doc['combined_content'])
                metadatas.append(prepared_doc['metadata'])

        # Ingest documents in batches
        print(f"📥 Ingesting {len(contents)} documents from '{source_file}' into '{collection_name}'...")
        ingested_count = manager.add_documents(doc_ids, contents, metadatas)
        
        return {
            "success": True,
            "collection_name": collection_name,
            "source_file": source_file,
            "ingested_count": ingested_count,
            "total_documents": len(documents),
            "embedded_fields": ingestion_config.get('contents_to_embed', []),
            "errors": [] # Batch method handles errors internally for now
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

# Unused routes - commented out for chat-only functionality
# @app.get("/chunked_text")
# async def get_chunked_text():
#     """Get chunked text stored in documents/chunked_text folder"""
#     chunked_text = []
#     for filename in os.listdir("documents/chunked_text"):
#         chunked_text.append({
#             "filename": filename,
#             "path": os.path.join("documents/chunked_text", filename)
#         })
#     
#     return {
#         "chunked_text": chunked_text,
#         "total_chunked_text": len(chunked_text)
#     }

# @app.get("/documents")
# async def get_documents():
#     """Get documents stored in documents/storage_documents folder"""
#     documents = []
#     for filename in os.listdir("documents/storage_documents"):
#         documents.append({
#             "filename": filename,
#             "path": os.path.join("documents/storage_documents", filename)
#         })
#     
#     return {
#         "documents": documents,
#         "total_documents": len(documents)
#     }

@app.get("/collections")
async def get_collections():
    """Get list of collections stored in documents/storage_documents folder, 
    AKA, list of directories in documents/storage_documents folder"""
    # Debug: Print current working directory and absolute path
    current_dir = os.getcwd()
    base_path = "documents/storage_documents"
    abs_base_path = os.path.abspath(base_path)
    print(f"Current working directory: {current_dir}")
    print(f"Looking for collections in: {abs_base_path}")
    
    collections = []

    try:
        # Check if the base directory exists
        if not os.path.exists(base_path):
            print(f"Warning: Base path '{base_path}' does not exist. Creating it...")
            os.makedirs(base_path, exist_ok=True)
            return {
                "collections": collections,
                "total_collections": 0
            }

        for entry in os.listdir(base_path):
            full_path = os.path.join(base_path, entry)
            if os.path.isdir(full_path):
                try:
                    num_documents = len(os.listdir(full_path))
                    print(f"Found collection: {entry}")
                    collections.append({
                        "name": entry,
                        "num_documents": num_documents
                    })
                except PermissionError:
                    print(f"Permission denied accessing collection: {entry}")
                    continue
                except Exception as e:
                    print(f"Error processing collection {entry}: {e}")
                    continue
            else:
                # Skip files like .DS_Store
                continue

    except PermissionError:
        raise HTTPException(
            status_code=403, 
            detail=f"Permission denied accessing collections directory: {base_path}"
        )
    except Exception as e:
        print(f"Error accessing collections: {e}")
        raise HTTPException(
            status_code=500, 
            detail=f"Error accessing collections directory: {str(e)}"
        )

    return {
        "collections": collections,
        "total_collections": len(collections)
    }


# @app.get("/collections/stats", response_model=CollectionsStatsResponse)
# async def get_collections_statistics():
#     """Get statistics about all collections in ChromaDB
#     
#     Returns:
#         CollectionsStatsResponse: Statistics for all collections including document counts
#     """
#     # Gather stats for all collections
#     collections_stats = []
#     total_documents = 0
#     for collection_name, manager in collection_managers.items():
#         stats = get_collection_stats(manager)
#         collections_stats.append(CollectionStatistics(**stats))
#         # Update total document count
#         total_documents += stats.get("document_count", 0)
#     
#     return CollectionsStatsResponse(
#         collections=collections_stats,
#         total_collections=len(collections_stats),
#         total_documents=total_documents
#     )

# @app.post("/search", response_model=List[DocumentResponse])
# async def search_documents(request: SearchRequest):
#     """Search documents across specified collections"""
#     num_results = get_search_params(request.num_results)
#     search_collections = request.collections or collection_names
#     
#     # Validate collections
#     for collection_name in search_collections:
#         if collection_name not in collection_managers:
#             raise HTTPException(status_code=400, detail=f"Collection '{collection_name}' not found")
#     
#     all_results = []
#     
#     for collection_name in search_collections:
#         try:
#             manager = get_collection_manager(collection_name)
#             results = manager.search_similar_chunks(request.query, num_results)
#             
#             # Add collection info to metadata
#             for result in results:
#                 result["metadata"]["collection"] = collection_name
#                 all_results.append(DocumentResponse(
#                     content=result["content"],
#                     metadata=result["metadata"],
#                     score=result.get("score")
#                 ))
#         except Exception as e:
#             print(f"Error searching collection {collection_name}: {e}")
#             continue
#             
#     # Sort by score if available and limit results
#     if all_results and all_results[0].score is not None:
#         all_results.sort(key=lambda x: x.score, reverse=True)
#     
#     return all_results[:num_results]



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
        result = query_processor.process_query(request.query, threshold=request.threshold, k=request.k, conversation_history=request.conversation_history)
        
        # Add metadata about the request
        result["query"] = request.query
        result["collections_available"] = collection_names
        result["processing_method"] = "multi-step-reasoning"
        result["threshold_used"] = request.threshold
        
        return result
                            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing query: {str(e)}")




# @app.post("/chat-with-pdf")
# async def chat_with_pdf(payload: ChatWithPDFRequest):
#     """
#     Chat with a specific document (session collection) using additional collections as context.
#     
#     This is a generalized endpoint that allows users to:
#     1. Upload a document to a unique session collection
#     2. Ask questions about that document
#     3. Use other collections as additional context for better answers
#     
#     Args:
#         payload: ChatWithPDFRequest containing query, session_collection, context_collections, and threshold
#     """
#     try:
#         # Combine session collection with context collections
#         all_collections = [payload.session_collection] + payload.context_collections
#         
#         # Filter out any collections that don't exist
#         valid_collections = []
#         for collection_name in all_collections:
#             collection_path = os.path.join("documents", "chunked_text", collection_name)
#             if os.path.exists(collection_path) and os.listdir(collection_path):
#                 valid_collections.append(collection_name)
#             else:
#                 logging.warning(f"Collection '{collection_name}' not found or empty, skipping")
#         
#         if not valid_collections:
#             raise HTTPException(
#                 status_code=404, 
#                 detail=f"No valid collections found. Session collection '{payload.session_collection}' and context collections {payload.context_collections} are either missing or empty."
#             )
#         
#         logging.info(f"Processing chat query with collections: {valid_collections}")
#         
#         # Use the specialized single PDF method with primary collection and context collections
#         response = langgraph_agent.process_query_with_single_pdf(
#             query=payload.query,
#             primary_collection=payload.session_collection,
#             context_collections=payload.context_collections,
#             threshold=payload.threshold
#         )
#         
#         return {
#             "response": response.get("response", "No response generated"),
#             "rest_of_response": response,
#             "sources": response.get("sources", []),
#             "session_collection": payload.session_collection,
#             "context_collections": payload.context_collections,
#             "valid_collections_used": valid_collections,
#             "query": payload.query
#         }
#         
#     except Exception as e:
#         logging.error(f"Error in chat-with-pdf: {str(e)}")
#         raise HTTPException(status_code=500, detail=f"Error processing chat query: {str(e)}")

# def generate_stream(request: ChatWithPDFRequest) -> Generator[str, None, None]:
#     try:
#         print(f"📡 Starting stream generation...")
#         
#         # Validate collections by checking if they exist on disk
#         valid_collections = []
#         
#         def collection_exists_on_disk(collection_name: str) -> bool:
#             """Check if collection directory exists in storage_documents"""
#             collection_path = os.path.join("documents", "storage_documents", collection_name)
#             return os.path.exists(collection_path) and os.path.isdir(collection_path)
#         
#         # Check session collection
#         if request.session_collection:
#             if collection_exists_on_disk(request.session_collection):
#                 valid_collections.append(request.session_collection)
#                 print(f"✅ Valid session collection: {request.session_collection}")
#                 # Load into memory if not already loaded
#                 if request.session_collection not in collection_managers:
#                     collection_managers[request.session_collection] = DynamicChromeManager(request.session_collection)
#                     print(f"📥 Loaded session collection into memory: {request.session_collection}")
#             else:
#                 print(f"❌ Invalid session collection (not found on disk): {request.session_collection}")
#         
#         # Check context collections
#         if request.context_collections:
#             for collection in request.context_collections:
#                 if collection_exists_on_disk(collection):
#                     valid_collections.append(collection)
#                     print(f"✅ Valid context collection: {collection}")
#                     # Load into memory if not already loaded
#                     if collection not in collection_managers:
#                         collection_managers[collection] = DynamicChromeManager(collection)
#                         print(f"📥 Loaded context collection into memory: {collection}")
#                 else:
#                     print(f"❌ Invalid context collection (not found on disk): {collection}")
#         
#         if not valid_collections:
#             error_msg = f"data: {json.dumps({'type': 'error', 'message': 'No valid collections found'})}\n\n"
#             print(f"❌ No valid collections, sending: {error_msg}")
#             yield error_msg
#             return
#         
#         # Send initial status
#         initial_status = f"data: {json.dumps({'type': 'status', 'message': 'Starting analysis...', 'timestamp': datetime.now().isoformat()})}\n\n"
#         print(f"📤 Sending initial status: {initial_status.strip()}")
#         yield initial_status
#         
#         # Send a test message to verify streaming is working
#         test_message = f"data: {json.dumps({'type': 'status', 'message': 'TEST: Streaming connection established!', 'timestamp': datetime.now().isoformat()})}\n\n"
#         print(f"📤 Sending test message: {test_message.strip()}")
#         yield test_message
#         
#         # Create a streaming version of the LangGraph agent
#         print(f"🔄 Starting streaming agent with collections: {valid_collections}")
#         for update in langgraph_agent.process_query_with_single_pdf_stream(
#             query=request.query,
#             primary_collection=request.session_collection,
#             context_collections=request.context_collections,
#             threshold=request.threshold
#         ):
#             stream_data = f"data: {json.dumps(update)}\n\n"
#             print(f"📤 Streaming update: {update.get('type', 'unknown')} - {update.get('message', '')[:100]}...")
#             yield stream_data
#             
#     except Exception as e:
#         logging.error(f"Error in streaming chat-with-pdf: {str(e)}")
#         yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

# @app.post("/chat-with-pdf-stream")
# async def chat_with_pdf_stream(request: ChatWithPDFRequest):
#     """Streaming version of chat-with-pdf that provides real-time updates"""
#     
#     print(f"🚀 STREAMING ENDPOINT CALLED: query='{request.query[:50]}...', session_collection='{request.session_collection}'")
#     
#     return StreamingResponse(
#         generate_stream(request),
#         media_type="text/event-stream",
#         headers={
#             "Cache-Control": "no-cache",
#             "Connection": "keep-alive",
#             "Content-Type": "text/event-stream"
#         }
#     )

# @app.post("/crawl-through-web")
# async def crawl_through_web(
#     payload: CrawlRequest
# ):
#     try:
#         # Save to src/documents/storage_documents
#         stats = ai_crawler(
#             start_url= payload.start_url,
#             extraction_prompt=payload.extraction_prompt,
#             collection_name=payload.collection_name,
#             null_is_okay=payload.null_is_okay,
#             num_workers=payload.num_workers,
#             num_levels_deep=payload.num_levels_deep
#         )
#         return {"message": f"Crawling completed successfully for {payload.collection_name} with {len(stats)} items created"}
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Error downloading PDFs: {str(e)}")

# @app.post("/upload-through-google-drive")
# async def upload_through_google_drive(payload: DriveUploadRequest):
#     try:
#         # Save to src/documents/storage_documents
#         download_path = os.path.join("documents", "storage_documents")
#         stats = download_pdfs_from_drive(
#             drive_url=payload.drive_url,
#             download_path=download_path,
#             recursive=payload.recursive
#         )
#         return {"downloaded": stats["downloaded"], "failed": stats["failed"], "folders_processed": stats["folders_processed"]}
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Error downloading PDFs: {str(e)}")


# @app.post("/extract-bill-links")
# async def extract_bill_links(bill_name: str = Form(...), year: str = Form(...)):
#     """
#     Extracts document links for a given bill and year from the Hawaii Capitol website.
#     """
#     try:
#         links = scrape_bill_page_links(bill_name, year)
#         return {"links": links}
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")
