from fastapi import FastAPI, HTTPException, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, TypedDict
import os
import tempfile
import shutil
from pathlib import Path
import json
import google.generativeai as genai
from tqdm import tqdm

# Handle both relative and absolute imports
try:
    from .settings import Settings
    from .documents.embeddings import ChromaDBManager
    from .query_processor import QueryProcessor
except ImportError:
    from settings import Settings
    from documents.embeddings import ChromaDBManager
    from query_processor import QueryProcessor

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
        
        # Import settings locally to avoid circular imports
        try:
            from .settings import settings
        except ImportError:
            from settings import settings
        
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
    
    def search_similar_chunks(self, query: str, num_results: int = 5) -> List[Dict[str, Any]]:
        """Search for similar chunks in the collection"""
        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=num_results
            )
            
            formatted_results = []
            if results["documents"] and results["documents"][0]:
                for i, doc in enumerate(results["documents"][0]):
                    result = {
                        "content": doc,
                        "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                        "score": 1.0 - results["distances"][0][i] if results["distances"] else 1.0
                    }
                    formatted_results.append(result)
            
            return formatted_results
                            
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

# API Models
class SearchRequest(BaseModel):
    query: str = Field(..., description="Search query")
    collections: Optional[List[str]] = Field(default=None, description="Collections to search in")
    num_results: int = Field(default=None, description="Number of results to return")
    search_type: str = Field(default="semantic", description="Type of search: semantic, metadata, or both")

class QueryRequest(BaseModel):
    query: str = Field(..., description="User query")
    collections: Optional[List[str]] = Field(default=None, description="Collections to search in")
    threshold: float = Field(default=0.5, ge=0.0, le=1.0, description="Similarity threshold (0.0 to 1.0) - only return documents with similarity scores above this threshold")

class DocumentResponse(BaseModel):
    content: str
    metadata: Dict[str, Any]
    score: Optional[float] = None

def get_search_params(num_results: Optional[int] = None) -> int:
    """Get search parameters with config defaults"""
    if num_results is None:
        return config["search"]["default_results"]
    return min(num_results, config["search"]["max_results"])

@app.get("/")
async def root():
    return {
        "message": f"Welcome to {config['api']['title']}",
        "version": config['api']['version'],
        "available_collections": collection_names,
        "features": [
            "Multi-step query processing with reasoning",
            "Semantic search across collections", 
            "Document ingestion and management",
            "Collection statistics and management"
        ],
        "endpoints": ["/search", "/query", "/ingest", "/reset", "/collections"]
    }

@app.get("/collections")
async def get_collections():
    """Get available collections and their stats"""
    collection_stats = {}
    
    for collection_name, manager in collection_managers.items():
        try:
            collection = manager.collection
            count = collection.count()
            collection_stats[collection_name] = {
                "count": count,
                "name": collection_name,
                "status": "active"
            }
        except Exception as e:
            collection_stats[collection_name] = {
                "count": 0,
                "name": collection_name,
                "status": f"error: {str(e)}"
            }
    
    return {
        "collections": collection_stats,
        "config": {
            "default_collection": config.get("default_collection"),
            "collection_aliases": config.get("collection_aliases", {}),
            "total_collections": len(collection_names)
        }
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

@app.post("/query")
async def query_documents(request: QueryRequest):
    """Advanced query processing with multi-step reasoning, searching, and answering"""
    try:
        # Use the multi-step query processor with threshold filtering
        result = query_processor.process_query(request.query, threshold=request.threshold)
        
        # Add metadata about the request
        result["query"] = request.query
        result["collections_available"] = collection_names
        result["processing_method"] = "multi-step-reasoning"
        result["threshold_used"] = request.threshold
        
        return result
                            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing query: {str(e)}")

@app.post("/ingest")
async def ingest_json_file(file: UploadFile = File(...), target_collection: Optional[str] = None):
    """Ingest documents from a JSON file into specified collection"""
    try:
        # Determine target collection
        if target_collection is None:
            target_collection = config.get("default_collection", collection_names[0])
        
        manager = get_collection_manager(target_collection)
        ingestion_config = get_ingestion_config(target_collection)
        
        # Read and parse JSON file
        content = await file.read()
        data = json.loads(content)
        
        # Expect JSON to be an array of documents
        if not isinstance(data, list):
            raise HTTPException(status_code=400, detail="JSON file must contain an array of documents")
        
        documents = data
        
        # Ingest documents
        ingested_count = 0
        errors = []
        
        print(f"📥 Ingesting {len(documents)} documents into '{target_collection}'...")
        print(f"🎯 Embedding fields: {ingestion_config.get('contents_to_embed', [])}")
        
        for i, doc in enumerate(tqdm(documents, desc=f"Ingesting into {target_collection}")):
            try:
                # Add the document with its ingestion config
                if manager.add_document(doc, ingestion_config):
                    ingested_count += 1
                else:
                    errors.append(f"Document {i}: Failed to add to collection")
            except Exception as e:
                errors.append(f"Document {i}: {str(e)}")
                continue
        
        return {
            "message": f"Successfully ingested {ingested_count} documents into '{target_collection}'",
            "ingested_count": ingested_count,
            "total_documents": len(documents),
            "errors": errors[:10],  # Limit error messages
            "collection": target_collection,
            "embedded_fields": ingestion_config.get('contents_to_embed', [])
        }
        
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON file")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error ingesting documents: {str(e)}")

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