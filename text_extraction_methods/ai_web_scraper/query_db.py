#!/usr/bin/env python3
"""
Query script for testing ChromaDB collections with different search terms.

This helps evaluate the effectiveness of different chunk sizes and overlap values
for RAG applications.
"""

import os
import argparse
import chromadb
from chromadb.utils import embedding_functions
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings


def query_collection(
    collection_name: str,
    query: str,
    persist_directory: str = None,
    limit: int = 5,
    embedding_model_name: str = "sentence-transformers/all-mpnet-base-v2"
):
    """
    Query a ChromaDB collection and display results.
    
    Args:
        collection_name: Name of the ChromaDB collection
        query: Search query
        persist_directory: Directory where ChromaDB is stored
        limit: Maximum number of results to return
        embedding_model_name: Name of the embedding model to use
    """
    # Set default persist directory if not specified
    if not persist_directory:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        persist_directory = os.path.join(script_dir, "chroma_db")
    
    # Initialize embeddings
    embeddings = HuggingFaceEmbeddings(model_name=embedding_model_name)
    
    try:
        # Connect to ChromaDB
        client = chromadb.PersistentClient(path=persist_directory)
        print(f"Available collections: {[c.name for c in client.list_collections()]}")
        # Check if collection exists
        try:
            collection = client.get_collection(collection_name)
        except Exception as e:
            print(f"Error: Collection '{collection_name}' not found.")
            print(f"Available collections: {[c.name for c in client.list_collections()]}")
            return
        
        # Initialize Langchain Chroma wrapper
        vectorstore = Chroma(
            client=client,
            collection_name=collection_name,
            embedding_function=embeddings,
        )
        
        # Perform similarity search
        print(f"\nQuerying collection '{collection_name}' for: '{query}'")
        results = vectorstore.similarity_search_with_score(query, k=limit)
        
        # Display results
        print(f"\nFound {len(results)} results:\n")
        
        for i, (doc, score) in enumerate(results):
            print(f"Result {i+1} [Similarity score: {score:.4f}]")
            print(f"Source: {doc.metadata.get('source', 'Unknown')}")
            print(f"Chunk {doc.metadata.get('chunk_index', 'N/A')} of {doc.metadata.get('total_chunks', 'N/A')}")
            print(f"\nCONTENT:")
            print("-" * 80)
            print(doc.page_content)
            print("-" * 80)
            print("\n")
            
        print(f"Query complete. Retrieved {len(results)} documents.")
        
    except Exception as e:
        print(f"Error querying collection: {e}")


def main():
    parser = argparse.ArgumentParser(description="Query ChromaDB collection")
    parser.add_argument("--collection", type=str, required=True, help="Collection name to query")
    parser.add_argument("--query", type=str, required=True, help="Search query")
    parser.add_argument("--db_path", type=str, help="Path to ChromaDB directory")
    parser.add_argument("--limit", type=int, default=5, help="Maximum number of results (default: 5)")
    
    args = parser.parse_args()
    
    query_collection(
        collection_name=args.collection,
        query=args.query,
        persist_directory=args.db_path,
        limit=args.limit
    )


if __name__ == "__main__":
    main()
