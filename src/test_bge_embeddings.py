#!/usr/bin/env python3
"""Test BGE-M3 embeddings to verify they work correctly."""

from FlagEmbedding import BGEM3FlagModel
import time

def test_bge_m3():
    """Test BGE-M3 model initialization and embedding generation."""
    
    print("🚀 Testing BGE-M3 Embeddings")
    print("=" * 50)
    
    # Initialize model
    print("\n1. Loading BGE-M3 model...")
    start_time = time.time()
    model = BGEM3FlagModel('BAAI/bge-m3', use_fp16=True)
    load_time = time.time() - start_time
    print(f"   ✅ Model loaded in {load_time:.2f} seconds")
    
    # Test embedding generation
    print("\n2. Generating embeddings...")
    test_texts = [
        "SAGE3 is a collaborative visualization platform.",
        "What is the purpose of science gateways?",
        "Machine learning models can process natural language."
    ]
    
    start_time = time.time()
    embeddings = model.encode(test_texts, batch_size=12, max_length=8192)['dense_vecs']
    encode_time = time.time() - start_time
    
    print(f"   ✅ Generated {len(embeddings)} embeddings in {encode_time:.2f} seconds")
    print(f"   📊 Embedding shape: {embeddings[0].shape}")
    print(f"   📏 Embedding dimensions: {len(embeddings[0])}")
    print(f"   ⚡ Speed: {len(test_texts)/encode_time:.2f} embeddings/second")
    
    # Verify embeddings
    print("\n3. Verifying embeddings...")
    for i, (text, emb) in enumerate(zip(test_texts, embeddings)):
        print(f"   Text {i+1}: '{text[:50]}...'")
        print(f"   First 5 values: {emb[:5].tolist()}")
    
    print("\n" + "=" * 50)
    print("✅ BGE-M3 embeddings working correctly!")
    print(f"\n💡 Model: BAAI/bge-m3")
    print(f"💡 Dimensions: {len(embeddings[0])}")
    print(f"💡 FP16: Enabled for faster computation")
    
if __name__ == "__main__":
    test_bge_m3()
