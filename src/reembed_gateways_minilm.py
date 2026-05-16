#!/usr/bin/env python3
"""
Re-embed gateways collection using all-MiniLM-L6-v2 (lightweight, CPU-friendly).
Clears existing collection and re-inserts all documents from gateways_export.json.
"""

import json
import chromadb
from chromadb.config import Settings
from pathlib import Path
import sys
from tqdm import tqdm

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from documents.embeddings import SentenceTransformerEmbeddingFunction

def main():
    print("🚀 Re-embedding Gateways Collection with all-MiniLM-L6-v2")
    print("=" * 60)
    
    # Configuration
    chroma_db_path = "./chroma_db/data"
    collection_name = "gateways"
    data_file = "gateways_export.json"
    
    # Initialize SentenceTransformer embedding function
    print("\n1️⃣ Loading all-MiniLM-L6-v2 model...")
    embedding_function = SentenceTransformerEmbeddingFunction(
        model_name="all-MiniLM-L6-v2"
    )
    print("   ✅ Model loaded (~90MB, 384 dimensions)")
    
    # Initialize ChromaDB client
    print("\n2️⃣ Connecting to ChromaDB...")
    client = chromadb.PersistentClient(
        path=chroma_db_path,
        settings=Settings(
            anonymized_telemetry=False,
            allow_reset=True
        )
    )
    print(f"   ✅ Connected to ChromaDB at: {chroma_db_path}")
    
    # Delete existing collection if it exists
    print(f"\n3️⃣ Clearing existing '{collection_name}' collection...")
    try:
        client.delete_collection(name=collection_name)
        print(f"   ✅ Deleted old collection")
    except Exception as e:
        print(f"   ℹ️  Collection didn't exist (this is fine)")
    
    # Create new collection with SentenceTransformer embeddings
    print(f"\n4️⃣ Creating new collection with all-MiniLM-L6-v2 embeddings...")
    collection = client.create_collection(
        name=collection_name,
        embedding_function=embedding_function,
        metadata={"description": "Science Gateways documents with MiniLM embeddings"}
    )
    print(f"   ✅ Collection created")
    
    # Load documents from JSON
    print(f"\n5️⃣ Loading documents from {data_file}...")
    with open(data_file, 'r', encoding='utf-8') as f:
        documents = json.load(f)
    print(f"   ✅ Loaded {len(documents)} documents")
    
    # Prepare data for insertion
    print(f"\n6️⃣ Preparing documents for insertion...")
    ids = []
    contents = []
    metadatas = []
    
    for doc in documents:
        ids.append(doc['id'])
        contents.append(doc['content'])
        
        # Prepare metadata (ChromaDB requires all values to be strings, ints, or floats)
        metadata = {}
        for key, value in doc['metadata'].items():
            if value is None:
                metadata[key] = ""
            elif isinstance(value, (str, int, float)):
                metadata[key] = value
            else:
                metadata[key] = str(value)
        
        metadatas.append(metadata)
    
    print(f"   ✅ Prepared {len(ids)} documents")
    
    # Insert documents in batches
    print(f"\n7️⃣ Inserting documents with all-MiniLM-L6-v2 embeddings...")
    batch_size = 32  # Good batch size for CPU processing
    total_batches = (len(ids) + batch_size - 1) // batch_size
    
    for i in tqdm(range(0, len(ids), batch_size), desc="Embedding batches", total=total_batches):
        batch_ids = ids[i:i + batch_size]
        batch_contents = contents[i:i + batch_size]
        batch_metadatas = metadatas[i:i + batch_size]
        
        collection.add(
            ids=batch_ids,
            documents=batch_contents,
            metadatas=batch_metadatas
        )
    
    # Verify collection
    print(f"\n8️⃣ Verifying collection...")
    final_count = collection.count()
    print(f"   ✅ Collection '{collection_name}' now has {final_count} documents")
    
    # Test a sample query
    print(f"\n9️⃣ Testing sample query...")
    results = collection.query(
        query_texts=["What is SAGE3?"],
        n_results=3
    )
    
    print(f"\n   Sample query results:")
    for i, (doc, metadata, distance) in enumerate(zip(
        results['documents'][0],
        results['metadatas'][0],
        results['distances'][0]
    )):
        print(f"\n   Result {i+1}:")
        print(f"   - Title: {metadata.get('title', 'N/A')}")
        print(f"   - Distance: {distance:.4f}")
        print(f"   - Content preview: {doc[:100]}...")
    
    print("\n" + "=" * 60)
    print("✅ Re-embedding complete!")
    print(f"📊 Total documents: {final_count}")
    print(f"🔧 Embedding model: all-MiniLM-L6-v2")
    print(f"📏 Embedding dimensions: 384")
    print(f"💾 Location: {chroma_db_path}/{collection_name}")
    print(f"\n💡 Update config.json with:")
    print(f'   "embedding_provider": "sentence-transformers"')
    print(f'   "embedding_model": "all-MiniLM-L6-v2"')
    print(f'   "embedding_dimensions": 384')

if __name__ == "__main__":
    main()
