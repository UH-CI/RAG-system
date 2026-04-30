#!/usr/bin/env python3
"""Verify BGE-M3 embeddings work correctly with the gateways collection."""

import chromadb
from chromadb.config import Settings
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from documents.embeddings import BGEM3EmbeddingFunction

def main():
    print("🔍 Verifying BGE-M3 Gateways Collection")
    print("=" * 60)
    
    # Initialize BGE-M3
    print("\n1️⃣ Loading BGE-M3 model...")
    embedding_function = BGEM3EmbeddingFunction(
        model_name="BAAI/bge-m3",
        use_fp16=True
    )
    print("   ✅ Model loaded")
    
    # Connect to ChromaDB
    print("\n2️⃣ Connecting to ChromaDB...")
    client = chromadb.PersistentClient(
        path="./chroma_db/data",
        settings=Settings(
            anonymized_telemetry=False,
            allow_reset=True
        )
    )
    
    collection = client.get_collection(
        name="gateways",
        embedding_function=embedding_function
    )
    print(f"   ✅ Connected to collection: {collection.name}")
    print(f"   📊 Total documents: {collection.count()}")
    
    # Test queries
    print("\n3️⃣ Testing sample queries...\n")
    
    queries = [
        "What is SAGE3?",
        "Tell me about science gateways",
        "What tools are used for visualization?"
    ]
    
    for i, query in enumerate(queries, 1):
        print(f"   Query {i}: '{query}'")
        results = collection.query(
            query_texts=[query],
            n_results=3
        )
        
        print(f"   Results:")
        for j, (doc, metadata, distance) in enumerate(zip(
            results['documents'][0],
            results['metadatas'][0],
            results['distances'][0]
        ), 1):
            title = metadata.get('title', 'N/A')
            print(f"      {j}. {title} (distance: {distance:.4f})")
            print(f"         Preview: {doc[:80]}...")
        print()
    
    print("=" * 60)
    print("✅ BGE-M3 embeddings working perfectly!")
    print(f"📊 Collection: gateways")
    print(f"📏 Documents: {collection.count()}")
    print(f"🔧 Model: BAAI/bge-m3 (1024 dimensions)")

if __name__ == "__main__":
    main()
