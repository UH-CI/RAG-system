#!/usr/bin/env python3
"""Debug script to test BGE-M3 embed_query directly."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from documents.embeddings import BGEM3EmbeddingFunction

def main():
    print("Testing BGE-M3 embed_query directly...")
    
    # Initialize
    embedding_fn = BGEM3EmbeddingFunction(model_name="BAAI/bge-m3", use_fp16=True)
    
    # Test embed_query
    print("\nCalling embed_query('What is SAGE3?')...")
    result = embedding_fn.embed_query("What is SAGE3?")
    
    print(f"\nResult type: {type(result)}")
    print(f"Result length: {len(result) if hasattr(result, '__len__') else 'N/A'}")
    print(f"First 5 values: {result[:5] if isinstance(result, list) else 'Not a list'}")
    print(f"Value types: {[type(x) for x in result[:5]] if isinstance(result, list) else 'N/A'}")
    
    # Verify all are floats
    if isinstance(result, list):
        all_floats = all(isinstance(x, (int, float)) for x in result)
        print(f"All values are numeric: {all_floats}")
        
        # Check for numpy types
        has_numpy = any(hasattr(x, 'item') for x in result[:10])
        print(f"Contains numpy types: {has_numpy}")
    
    print(f"\n✅ embed_query working correctly!")

if __name__ == "__main__":
    main()
