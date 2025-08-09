"""
Embedding system for the Financial Document RAG System.
Integrates ChromaDB with Google AI embeddings for document storage and retrieval.
"""

import os
import time
from typing import List, Dict, Any, Optional, Tuple
import chromadb
from chromadb.config import Settings
import google.generativeai as genai

# Handle both relative and absolute imports
try:
    from ..settings import settings, validate_settings
except ImportError:
    from settings import settings, validate_settings

import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class GoogleEmbeddingFunction:
    """Custom embedding function for Google AI embeddings."""
    
    def __init__(self, api_key: str, model_name: str = "text-embedding-004"):
        """Initialize Google embedding function.
        
        Args:
            api_key: Google AI API key
            model_name: Name of the embedding model to use
        """
        self.api_key = api_key
        self.model_name = model_name
        genai.configure(api_key=api_key)
        logger.info(f"Initialized Google embeddings with model: {model_name}")
    
    def name(self) -> str:
        """Return the name of this embedding function."""
        return f"google_{self.model_name}"
    
    def __call__(self, input: List[str]) -> List[List[float]]:
        """Generate embeddings for input texts.
        
        Args:
            input: List of texts to embed
            
        Returns:
            List of embedding vectors
        """
        embeddings = []
        
        for text in input:
            try:
                # Generate embedding using Google AI
                result = genai.embed_content(
                    model=f"models/{self.model_name}",
                    content=text,
                    task_type="retrieval_document"
                )
                embeddings.append(result['embedding'])
                
                # Add small delay to respect rate limits
                time.sleep(0.1)
                
            except Exception as e:
                logger.error(f"Error generating embedding for text: {str(e)}")
                # Return zero vector as fallback
                embeddings.append([0.0] * 768)  # Default dimension for Google embeddings
        
        return embeddings

class ChromaDBManager:
    """Manages ChromaDB operations with Google embeddings."""
    
    def __init__(self):
        """Initialize ChromaDB manager."""
        validate_settings()
        
        self.client = None
        self.collection = None
        self.embedding_function = None
        
        self._initialize_client()
        self._initialize_embedding_function()
        self._initialize_collection()
    
    def _initialize_client(self):
        """Initialize ChromaDB client."""
        try:
            # Create ChromaDB client with persistent storage (embedded mode only)
            self.client = chromadb.PersistentClient(
                path=str(settings.chroma_db_path),
                settings=Settings(
                    anonymized_telemetry=False,
                    allow_reset=True
                )
            )
            logger.info(f"ChromaDB persistent client initialized at: {settings.chroma_db_path}")
            
        except Exception as e:
            logger.error(f"Failed to initialize ChromaDB client: {str(e)}")
            raise
    
    def _initialize_embedding_function(self):
        """Initialize Google embedding function."""
        try:
            self.embedding_function = GoogleEmbeddingFunction(
                api_key=settings.google_api_key,
                model_name=settings.embedding_model
            )
            logger.info("Google embedding function initialized")
            
        except Exception as e:
            logger.error(f"Failed to initialize embedding function: {str(e)}")
            raise
    
    def _initialize_collection(self):
        """Initialize or get existing collection."""
        try:
            # Try to get existing collection
            try:
                self.collection = self.client.get_collection(
                    name=settings.chroma_collection_name,
                    embedding_function=self.embedding_function
                )
                logger.info(f"Retrieved existing collection: {settings.chroma_collection_name}")
                
            except Exception:
                # Create new collection if it doesn't exist
                self.collection = self.client.create_collection(
                    name=settings.chroma_collection_name,
                    embedding_function=self.embedding_function,
                    metadata={"hnsw:space": settings.chroma_distance_function}
                )
                logger.info(f"Created new collection: {settings.chroma_collection_name}")
                
        except Exception as e:
            logger.error(f"Failed to initialize collection: {str(e)}")
            raise
    
    def add_documents(self, documents: List[str], metadatas: List[Dict[str, Any]], ids: List[str]) -> bool:
        """Add documents to the collection.
        
        Args:
            documents: List of document texts
            metadatas: List of metadata dictionaries
            ids: List of unique document IDs
            
        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(f"Adding {len(documents)} documents to collection")
            
            # Clean metadata to remove None values that ChromaDB can't handle
            cleaned_metadatas = []
            for metadata in metadatas:
                cleaned_meta = {}
                for key, value in metadata.items():
                    if value is not None:
                        # Convert all values to strings, ints, floats, or bools only
                        if isinstance(value, (str, int, float, bool)):
                            cleaned_meta[key] = value
                        else:
                            cleaned_meta[key] = str(value)
                cleaned_metadatas.append(cleaned_meta)
            
            # Add documents in batches to avoid memory issues
            batch_size = settings.batch_size
            for i in range(0, len(documents), batch_size):
                batch_docs = documents[i:i + batch_size]
                batch_metas = cleaned_metadatas[i:i + batch_size]
                batch_ids = ids[i:i + batch_size]
                
                self.collection.add(
                    documents=batch_docs,
                    metadatas=batch_metas,
                    ids=batch_ids
                )
                
                logger.info(f"Added batch {i//batch_size + 1}/{(len(documents) + batch_size - 1)//batch_size}")
                
                # Small delay between batches
                time.sleep(0.5)
            
            logger.info("Successfully added all documents")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add documents: {str(e)}")
            return False
    
    def add_document_chunks(self, chunks) -> bool:
        """Add DocumentChunk objects to the collection.
        
        Args:
            chunks: List of DocumentChunk objects
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Convert DocumentChunk objects to lists
            documents = [chunk.content for chunk in chunks]
            metadatas = [chunk.metadata for chunk in chunks]
            ids = [chunk.chunk_id for chunk in chunks]
            
            return self.add_documents(documents, metadatas, ids)
            
        except Exception as e:
            logger.error(f"Failed to add document chunks: {str(e)}")
            return False
    
    def query_documents(self, query_text: str, n_results: int = None, 
                       where: Dict[str, Any] = None) -> Dict[str, Any]:
        """Query documents from the collection.
        
        Args:
            query_text: Query text
            n_results: Number of results to return
            where: Metadata filter conditions
            
        Returns:
            Query results dictionary
        """
        try:
            if n_results is None:
                n_results = settings.default_k
            
            results = self.collection.query(
                query_texts=[query_text],
                n_results=n_results,
                where=where
            )
            
            logger.info(f"Query returned {len(results['documents'][0])} results")
            return results
            
        except Exception as e:
            logger.error(f"Failed to query documents: {str(e)}")
            return {"documents": [[]], "metadatas": [[]], "distances": [[]]}
    
    def query_by_metadata(self, where: Dict[str, Any], n_results: int = None) -> Dict[str, Any]:
        """Query documents by metadata only (no semantic search).
        
        Args:
            where: Metadata filter conditions
            n_results: Number of results to return
            
        Returns:
            Query results dictionary
        """
        try:
            if n_results is None:
                n_results = settings.default_k
            
            # Get all documents that match the metadata filter
            results = self.collection.get(
                where=where,
                limit=n_results
            )
            
            logger.info(f"Metadata query returned {len(results['documents'])} results")
            
            # Convert to same format as query() for consistency
            return {
                "documents": [results['documents']],
                "metadatas": [results['metadatas']], 
                "distances": [[0.0] * len(results['documents'])],  # No distances for metadata-only
                "ids": [results['ids']]
            }
            
        except Exception as e:
            logger.error(f"Failed to query by metadata: {str(e)}")
            return {"documents": [[]], "metadatas": [[]], "distances": [[]], "ids": [[]]}
    
    def search_metadata_fields(self, field_name: str, search_value: str, 
                              exact_match: bool = True, n_results: int = None) -> Dict[str, Any]:
        """Search for documents with specific metadata field values.
        
        Args:
            field_name: Name of the metadata field to search
            search_value: Value to search for
            exact_match: If True, exact match; if False, contains match
            n_results: Number of results to return
            
        Returns:
            Query results dictionary
        """
        try:
            if exact_match:
                where = {field_name: search_value}
            else:
                where = {field_name: {"$contains": search_value}}
            
            return self.query_by_metadata(where, n_results)
            
        except Exception as e:
            logger.error(f"Failed to search metadata field {field_name}: {str(e)}")
            return {"documents": [[]], "metadatas": [[]], "distances": [[]], "ids": [[]]}
    
    def flexible_metadata_search(self, query: str, n_results: int = None) -> Dict[str, Any]:
        """Flexible search across all metadata fields with case-insensitive partial matching.
        
        Args:
            query: Search query string
            n_results: Number of results to return
            
        Returns:
            Query results dictionary
        """
        try:
            if n_results is None:
                n_results = settings.default_k
            
            # Get all documents and filter in Python for maximum flexibility
            all_docs = self.collection.get(limit=n_results * 10)  # Get more docs to filter from
            
            query_lower = query.lower()
            matching_docs = []
            matching_metadatas = []
            matching_ids = []
            
            for doc_id, doc_content, metadata in zip(
                all_docs['ids'], 
                all_docs['documents'], 
                all_docs['metadatas']
            ):
                # Check if query appears in any metadata field (case-insensitive)
                match_found = False
                for key, value in metadata.items():
                    if value and isinstance(value, str) and query_lower in value.lower():
                        match_found = True
                        break
                
                if match_found:
                    matching_docs.append(doc_content)
                    matching_metadatas.append(metadata)
                    matching_ids.append(doc_id)
                    
                    # Stop if we have enough results
                    if len(matching_docs) >= n_results:
                        break
            
            logger.info(f"Flexible metadata search returned {len(matching_docs)} results")
            
            # Return in same format as other query methods
            return {
                "documents": [matching_docs],
                "metadatas": [matching_metadatas],
                "distances": [[0.0] * len(matching_docs)],  # No distances for metadata-only
                "ids": [matching_ids]
            }
            
        except Exception as e:
            logger.error(f"Failed to perform flexible metadata search: {str(e)}")
            return {"documents": [[]], "metadatas": [[]], "distances": [[]], "ids": [[]]}
    
    def get_collection_stats(self) -> Dict[str, Any]:
        """Get collection statistics.
        
        Returns:
            Dictionary with collection statistics
        """
        try:
            count = self.collection.count()
            return {
                "collection_name": settings.chroma_collection_name,
                "document_count": count,
                "embedding_model": settings.embedding_model,
                "embedding_dimensions": settings.embedding_dimensions
            }
            
        except Exception as e:
            logger.error(f"Failed to get collection stats: {str(e)}")
            return {}
    
    def reset_collection(self) -> bool:
        """Reset (clear) the collection.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            self.client.delete_collection(name=settings.chroma_collection_name)
            self._initialize_collection()
            logger.info("Collection reset successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to reset collection: {str(e)}")
            return False

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

# Global instance
_chroma_manager = None

def get_chroma_manager() -> ChromaDBManager:
    """Get global ChromaDB manager instance."""
    global _chroma_manager
    if _chroma_manager is None:
        _chroma_manager = ChromaDBManager()
    return _chroma_manager

if __name__ == "__main__":
    # Test the embedding system
    try:
        print("Testing ChromaDB setup...")
        manager = get_chroma_manager()
        
        # Test adding a document
        test_docs = ["This is a test document about financial data."]
        test_metas = [{"source": "test", "type": "financial"}]
        test_ids = ["test_doc_1"]
        
        success = manager.add_documents(test_docs, test_metas, test_ids)
        print(f"Document addition: {'✅ Success' if success else '❌ Failed'}")
        
        # Test querying
        results = manager.query_documents("financial data", n_results=1)
        print(f"Query test: {'✅ Success' if results['documents'][0] else '❌ Failed'}")
        
        # Show stats
        stats = manager.get_collection_stats()
        print(f"Collection stats: {stats}")
        
    except Exception as e:
        print(f"❌ Test failed: {str(e)}") 