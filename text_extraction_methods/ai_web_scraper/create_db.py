#!/usr/bin/env python3
"""
Demo script for creating ChromaDB from the HB_400_2025.json file
with specified chunk size and overlap.
"""

import os
import argparse
from json_to_chromadb import process_json_file

def main():
    parser = argparse.ArgumentParser(description="Create ChromaDB from JSON with custom chunking")
    parser.add_argument("--chunk_size", type=int, default=500, 
                        help="Size of text chunks (default: 500)")
    parser.add_argument("--chunk_overlap", type=int, default=200, 
                        help="Overlap between chunks (default: 200)")
    parser.add_argument("--collection_name", type=str, 
                        help="Specify a collection name (default: auto-generated from chunk parameters)")
    parser.add_argument("--reset", action="store_true", 
                        help="Reset collection if it exists (WARNING: this will delete the existing collection)")
    
    args = parser.parse_args()
    
    # File paths
    input_file = os.path.join(os.path.dirname(__file__), "HB_400_2025.json")
    
    # Use provided collection name or generate one based on parameters
    if args.collection_name:
        collection_name = args.collection_name
    else:
        collection_name = f"HB400_chunks_{args.chunk_size}_{args.chunk_overlap}"
    
    # Warn if reset flag is used
    if args.reset:
        print(f"WARNING: The --reset flag is set. Collection '{collection_name}' will be deleted if it exists.")
        response = input("Do you want to continue? (y/n): ")
        if response.lower() != 'y':
            print("Operation cancelled.")
            return
    
    # Create ChromaDB
    db_path, collection = process_json_file(
        input_file=input_file,
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
        collection_name=collection_name,
        reset=args.reset
    )
    
    action = "Created new" if args.reset else "Created or updated"
    print(f"\n{action} ChromaDB collection '{collection}' with:")
    print(f"  - Chunk size: {args.chunk_size}")
    print(f"  - Chunk overlap: {args.chunk_overlap}")
    print(f"  - Database path: {db_path}")
    print("\nExample query commands:")
    print(f"  python query_db.py --collection {collection} --query \"women's court pilot program\"")

if __name__ == "__main__":
    main()
