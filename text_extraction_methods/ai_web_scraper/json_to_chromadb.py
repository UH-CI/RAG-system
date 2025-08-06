#!/usr/bin/env python3
"""
JSON to ChromaDB Converter

This script takes a JSON file with legislative documents, processes the content,
and creates a ChromaDB collection with chunked text for RAG applications.

Usage:
    python json_to_chromadb.py --input_file HB_727_2025.json --chunk_size 500 --chunk_overlap 200 [--reset]
"""

import json
import os
import argparse
import uuid
from typing import Dict, List, Any, Optional

import chromadb
from chromadb.utils import embedding_functions
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings


def load_json_data(file_path: str) -> List[Dict[str, Any]]:
    """
    Load JSON data from the specified file path.
    
    Args:
        file_path: Path to the JSON file
        
    Returns:
        List of document entries from the JSON file
    """
    print(f"Loading JSON data from {file_path}")
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    print(f"Loaded {len(data)} document entries")
    return data


def chunk_text(
    text: str, 
    url: str, 
    chunk_size: int, 
    chunk_overlap: int
) -> List[Dict[str, Any]]:
    """
    Chunk text into smaller pieces for embedding.
    
    Args:
        text: Text content to chunk
        url: Source URL of the document
        chunk_size: Size of each chunk
        chunk_overlap: Overlap between consecutive chunks
        
    Returns:
        List of document chunks with metadata
    """
    # Create text splitter
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        separators=["\n\n", "\n", " ", ""]
    )
    
    # Split text into chunks
    chunks = text_splitter.split_text(text)
    
    # Create a larger context chunk (2x chunk_size) for metadata
    context_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size*2,
        chunk_overlap=chunk_overlap*2,
        length_function=len,
        separators=["\n\n", "\n", " ", ""]
    )
    context_chunks = context_splitter.split_text(text)
    
    # Prepare document chunks with metadata
    document_chunks = []
    
    for i, chunk in enumerate(chunks):
        # Find the appropriate context chunk that contains this chunk
        context = None
        for ctx in context_chunks:
            if chunk in ctx:
                context = ctx
                break
        
        # If no context found, use the chunk itself
        if not context:
            context = chunk
            
        # Create metadata
        metadata = {
            "source": url,
            "chunk_index": i,
            "total_chunks": len(chunks),
            # "context": context[:1000] if len(context) > 1000 else context,  # Limit context size
            "context": context,  # Limit context size
            "document_id": url.split("/")[-1],
            "chunk_id": str(uuid.uuid4())
        }
        
        document_chunks.append({
            "text": chunk,
            "metadata": metadata
        })
    
    return document_chunks


def create_chromadb_collection(
    documents: List[Dict[str, Any]], 
    collection_name: str,
    persist_directory: str,
    embedding_model_name: str = "sentence-transformers/all-mpnet-base-v2",
    reset: bool = False
) -> None:
    """
    Create or update a ChromaDB collection with document chunks.
    
    Args:
        documents: List of document chunks with metadata
        collection_name: Name of the ChromaDB collection
        persist_directory: Directory to persist ChromaDB
        embedding_model_name: HuggingFace model name for embeddings
        reset: Whether to reset the collection if it exists
    """
    # Initialize embeddings
    print(f"Initializing embeddings with model: {embedding_model_name}")
    embeddings = HuggingFaceEmbeddings(model_name=embedding_model_name)
    
    # Ensure directory exists
    os.makedirs(persist_directory, exist_ok=True)
    
    # Initialize Chroma client
    client = chromadb.PersistentClient(path=persist_directory)
    
    # Check if collection exists and handle reset
    if reset:
        try:
            print(f"Resetting collection: {collection_name}")
            client.delete_collection(collection_name)
        except Exception as e:
            print(f"Collection doesn't exist or couldn't be deleted: {e}")
    
    # Get or create collection
    try:
        collection = client.get_or_create_collection(collection_name)
        print(f"Using existing or new collection: {collection_name}")
    except Exception as e:
        print(f"Error creating collection: {e}")
        return
    
    # Process documents in batches to avoid memory issues
    batch_size = 50
    num_batches = (len(documents) + batch_size - 1) // batch_size
    
    print(f"Processing {len(documents)} documents in {num_batches} batches")
    
    for batch_index in range(num_batches):
        start_idx = batch_index * batch_size
        end_idx = min((batch_index + 1) * batch_size, len(documents))
        batch = documents[start_idx:end_idx]
        
        # Extract data for Chroma
        texts = [doc["text"] for doc in batch]
        ids = [doc["metadata"]["chunk_id"] for doc in batch]
        metadatas = [doc["metadata"] for doc in batch]
        
        # Add documents to the collection
        try:
            # Use langchain's Chroma wrapper for convenience
            vectorstore = Chroma(
                client=client,
                collection_name=collection_name,
                embedding_function=embeddings,
            )
            
            # Add documents
            vectorstore.add_texts(
                texts=texts,
                metadatas=metadatas,
                ids=ids
            )
            
            print(f"Added batch {batch_index+1}/{num_batches} to collection")
        except Exception as e:
            print(f"Error adding documents to collection: {e}")
    
    print(f"Completed creating/updating ChromaDB collection '{collection_name}'")
    print(f"Total documents added: {len(documents)}")


def process_json_file(
    input_file: str,
    chunk_size: int,
    chunk_overlap: int,
    collection_name: Optional[str] = None,
    persist_directory: Optional[str] = None,
    reset: bool = False
) -> None:
    """
    Process a JSON file and create a ChromaDB collection.
    
    Args:
        input_file: Path to the input JSON file
        chunk_size: Size of text chunks
        chunk_overlap: Overlap between chunks
        collection_name: Name of the ChromaDB collection (default: derived from filename)
        persist_directory: Directory to persist ChromaDB (default: ./chroma_db)
        reset: Whether to reset the collection
    """
    # Set default values
    if not collection_name:
        collection_name = os.path.splitext(os.path.basename(input_file))[0]
    
    if not persist_directory:
        # Create in the same directory as the input file
        input_dir = os.path.dirname(os.path.abspath(input_file))
        persist_directory = os.path.join(input_dir, "chroma_db")
    
    # Load JSON data
    documents = load_json_data(input_file)
    
    # Process and chunk documents
    all_chunks = []
    for doc in documents:
        if "url" in doc and "text" in doc:
            chunks = chunk_text(doc["text"], doc["url"], chunk_size, chunk_overlap)
            all_chunks.extend(chunks)
    
    print(f"Created {len(all_chunks)} chunks from {len(documents)} documents")
    
    # Create ChromaDB collection
    create_chromadb_collection(
        all_chunks, 
        collection_name, 
        persist_directory, 
        reset=reset
    )
    
    return persist_directory, collection_name


def main():
    """Main function to parse arguments and process the JSON file."""
    parser = argparse.ArgumentParser(description="Convert JSON legislative data to ChromaDB collection")
    parser.add_argument("--input_file", type=str, required=True, help="Input JSON file path")
    parser.add_argument("--chunk_size", type=int, default=500, help="Size of text chunks")
    parser.add_argument("--chunk_overlap", type=int, default=200, help="Overlap between chunks")
    parser.add_argument("--collection_name", type=str, help="Name of the ChromaDB collection")
    parser.add_argument("--persist_directory", type=str, help="Directory to persist ChromaDB")
    parser.add_argument("--reset", action="store_true", help="Reset collection if it exists")
    
    args = parser.parse_args()
    
    db_path, collection = process_json_file(
        args.input_file,
        args.chunk_size,
        args.chunk_overlap,
        args.collection_name,
        args.persist_directory,
        args.reset
    )
    
    print(f"\nProcessing complete!")
    print(f"ChromaDB collection '{collection}' created at: {db_path}")
    print(f"You can now use this collection for RAG applications.")


if __name__ == "__main__":
    main()
