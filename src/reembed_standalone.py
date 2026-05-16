#!/usr/bin/env python3
"""
Standalone re-embedding script for all-MiniLM-L6-v2.
No dependencies on embeddings.py to avoid import issues.
"""

import json
import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer
from tqdm import tqdm

def main():
    print("🚀 Re-embedding Gateways Collection with all-MiniLM-L6-v2")
    print("=" * 60)
    
    # Configuration
    chroma_db_path = "./chroma_db/data"
    collection_name = "gateways"
    data_file = "gateways_export.json"
    model_name = "all-MiniLM-L6-v2"
    
    # Load SentenceTransformer model
    print(f"\n1️⃣ Loading {model_name} model...")
    model = SentenceTransformer(model_name)
    print(f"   ✅ Model loaded (~90MB, 384 dimensions)")
    
    # Create embedding function wrapper for ChromaDB
    class MiniLMEmbeddingFunction:
        def __init__(self, model):
            self.model = model
            
        def __call__(self, input):
            embeddings = self.model.encode(input, show_progress_bar=False, convert_to_numpy=True)
            return [emb.tolist() for emb in embeddings]
        
        def embed_query(self, input):
            """Embed a single query for ChromaDB compatibility"""
            embedding = self.model.encode(input, show_progress_bar=False, convert_to_numpy=True)
            return embedding.tolist()
    
    embedding_function = MiniLMEmbeddingFunction(model)
    
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
    
    # Delete existing collection
    print(f"\n3️⃣ Clearing existing '{collection_name}' collection...")
    try:
        client.delete_collection(name=collection_name)
        print(f"   ✅ Deleted old collection")
    except Exception as e:
        print(f"   ℹ️  Collection didn't exist (this is fine)")
    
    # Create new collection
    print(f"\n4️⃣ Creating new collection with {model_name} embeddings...")
    collection = client.create_collection(
        name=collection_name,
        embedding_function=embedding_function,
        metadata={"description": "Science Gateways with MiniLM embeddings"}
    )
    print(f"   ✅ Collection created")
    
    # Load documents
    print(f"\n5️⃣ Loading documents from {data_file}...")
    with open(data_file, 'r', encoding='utf-8') as f:
        documents = json.load(f)
    print(f"   ✅ Loaded {len(documents)} documents")
    
    # Prepare data
    print(f"\n6️⃣ Preparing documents...")
    ids = []
    contents = []
    metadatas = []
    
    for doc in documents:
        ids.append(doc['id'])
        contents.append(doc['content'])
        
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
    
    # Insert in batches
    print(f"\n7️⃣ Inserting documents with embeddings...")
    batch_size = 32
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
    
    # Verify
    print(f"\n8️⃣ Verifying collection...")
    final_count = collection.count()
    print(f"   ✅ Collection '{collection_name}' now has {final_count} documents")
    
    # Test query
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
    print(f"🔧 Embedding model: {model_name}")
    print(f"📏 Embedding dimensions: 384")
    print(f"💾 Location: {chroma_db_path}/{collection_name}")
    print(f"\n💡 Update config.json with:")
    print(f'   "embedding_provider": "sentence-transformers"')
    print(f'   "embedding_model": "{model_name}"')
    print(f'   "embedding_dimensions": 384')

if __name__ == "__main__":
    main()
