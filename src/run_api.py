#!/usr/bin/env python3
"""
FastAPI Server Startup Script
Launches the House Finance Document API server
"""

import sys
import os
import uvicorn
import argparse
from pathlib import Path

def main():
    """Start the FastAPI server"""
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description='Document RAG API Server - Generalized system for JSON document arrays',
        epilog='''
Examples:
  python run_api.py                                    # Start server only
  python run_api.py --ingest                          # Reset collections and ingest from configured files
  python run_api.py --ingest --append                 # Add documents to existing collections from configured files
  python run_api.py --ingest-only --append            # Only ingest from configured files, don't start server
  python run_api.py --ingest-file documents/custom_data.json --no-reset  # Ingest custom JSON without reset

The system automatically uses the source files specified in config.json for each collection.
Each collection has specific fields that will be embedded as specified in config.json.
        ''',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--ingest', action='store_true', 
                       help='Ingest documents from configured source files before starting the server')
    parser.add_argument('--ingest-only', action='store_true',
                       help='Only ingest documents from configured source files, do not start the server')
    parser.add_argument('--ingest-file', 
                       help='Path to a specific JSON file to ingest (overrides config-based ingestion)')
    parser.add_argument('--no-reset', action='store_true',
                       help='Do not reset collections before ingestion (append to existing data)')
    parser.add_argument('--append', action='store_true',
                       help='Append documents to existing collections without resetting (same as --no-reset)')
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind server to')
    parser.add_argument('--port', type=int, default=8000, help='Port to bind server to')
    parser.add_argument('--reload', action='store_true', help='Enable auto-reload for development')
    parser.add_argument('--log-level', choices=['debug', 'info', 'warning', 'error'], default='info',
                       help='Log level')
    args = parser.parse_args()
    
    try:
        print("🚀 Starting House Finance Document API...")
        print("📚 Loading ChromaDB and embedding models...")
        
        # Set the current directory as the project root (src directory is now root)
        project_root = Path(__file__).parent
        sys.path.insert(0, str(project_root))
        
        # Change working directory to project root
        os.chdir(project_root)
        
        # Import here to catch any configuration errors early
        from settings import Settings
        config = Settings()
        
        print(f"✅ Configuration loaded:")
        print(f"   - Documents Path: {config.documents_path}")
        print(f"   - ChromaDB Path: {config.chroma_db_path}")
        print(f"   - Collection: {config.chroma_collection_name}")
        print(f"   - Embedding Model: {config.embedding_model} ({config.embedding_provider})")
        print("=" * 60)
        
        # Handle document ingestion if requested
        if args.ingest or args.ingest_only or args.ingest_file:
            if args.ingest_file:
                print(f"\n📥 Ingesting documents from {args.ingest_file}...")
            else:
                print(f"\n📥 Ingesting all collections from configured source files...")
            
            # Determine if we should reset collections
            reset_collections = not (args.no_reset or args.append)
            
            if reset_collections:
                print("🔄 Collections will be reset before ingestion")
            else:
                print("➕ Documents will be appended to existing collections")
            
            try:
                if args.ingest_file:
                    # Use the specified file for ingestion
                    from api import get_collection_manager, get_ingestion_config, config
                    import json
                    from tqdm import tqdm
                    import time
                    
                    # Reset collections before ingestion to avoid duplicates (if requested)
                    if reset_collections:
                        print("🔄 Resetting collections to avoid duplicates...")
                        from api import collection_managers
                        for manager in collection_managers.values():
                            manager.reset_collection()
                        print("✅ Collections reset successfully")
                        
                        # Reinitialize the managers to get fresh collection references
                        print("🔄 Reinitializing collection managers...")
                        from api import DynamicChromeManager, collection_names
                        import api
                        api.collection_managers = {}
                        for collection_name in collection_names:
                            api.collection_managers[collection_name] = DynamicChromeManager(collection_name)
                        print("✅ Collection managers reinitialized")
                    else:
                        print("📊 Using existing collections (no reset)")
                    
                    # Load and process the JSON file using simplified structure
                    start_time = time.time()
                    
                    try:
                        with open(args.ingest_file, 'r') as f:
                            data = json.load(f)
                    except FileNotFoundError:
                        raise FileNotFoundError(f"File not found: {args.ingest_file}")
                    except json.JSONDecodeError:
                        raise Exception(f"Invalid JSON file: {args.ingest_file}")
                    
                    # Expect JSON to be an array of documents
                    if not isinstance(data, list):
                        raise Exception(f"JSON file must contain an array of documents, got {type(data)}")
                    
                    documents = data
                    
                    # Use default collection for ingestion
                    target_collection = config.get("default_collection", config["collections"][0])
                    manager = get_collection_manager(target_collection)
                    ingestion_config = get_ingestion_config(target_collection)
                    
                    # Ingest documents
                    ingested_count = 0
                    errors = []
                    
                    print(f"📥 Ingesting {len(documents)} documents into '{target_collection}'...")
                    print(f"🎯 Embedding fields: {ingestion_config.get('contents_to_embed', [])}")
                    
                    for i, doc in enumerate(tqdm(documents, desc=f"Processing documents")):
                        try:
                            # Add the document with its ingestion config
                            if manager.add_document(doc, ingestion_config):
                                ingested_count += 1
                            else:
                                errors.append(f"Document {i}: Failed to add to collection")
                            
                        except Exception as e:
                            errors.append(f"Document {i}: {str(e)}")
                            continue
                    
                    end_time = time.time()
                    processing_time = end_time - start_time
                    items_per_second = ingested_count / processing_time if processing_time > 0 else 0
                    
                    # Create result summary
                    result = {
                        "success": True,
                        "ingested_count": ingested_count,
                        "total_documents": len(documents),
                        "target_collection": target_collection,
                        "embedded_fields": ingestion_config.get('contents_to_embed', []),
                        "processing_time_seconds": processing_time,
                        "items_per_second": items_per_second,
                        "errors": errors[:10]  # Limit error messages
                    }
                    
                    # Print results using generalized format
                    print(f"✅ Document ingestion completed:")
                    print(f"   - Documents ingested: {ingested_count}")
                    print(f"   - Target collection: {target_collection}")
                    print(f"   - Embedded fields: {ingestion_config.get('contents_to_embed', [])}")
                    print(f"   - Processing time: {processing_time:.2f} seconds")
                    print(f"   - Rate: {items_per_second:.1f} items/second")
                    
                    if errors:
                        print(f"   - Errors: {len(errors)} (showing first 10)")
                        for error in errors[:10]:
                            print(f"     • {error}")
                    
                    if not result["success"]:
                        raise Exception("Ingestion failed")
                        
                else:
                    # Use the configured source files for each collection
                    from api import ingest_from_source_file, config
                    import time
                    
                    # Reset collections before ingestion to avoid duplicates (if requested)
                    if reset_collections:
                        print("🔄 Resetting collections to avoid duplicates...")
                        from api import collection_managers
                        for manager in collection_managers.values():
                            manager.reset_collection()
                        print("✅ Collections reset successfully")
                        
                        # Reinitialize the managers to get fresh collection references
                        print("🔄 Reinitializing collection managers...")
                        from api import DynamicChromeManager, collection_names
                        import api
                        api.collection_managers = {}
                        for collection_name in collection_names:
                            api.collection_managers[collection_name] = DynamicChromeManager(collection_name)
                        print("✅ Collection managers reinitialized")
                    else:
                        print("📊 Using existing collections (no reset)")
                    
                    # Process each collection from config
                    start_time = time.time()
                    all_results = []
                    total_ingested = 0
                    
                    for ing_config in config.get("ingestion_configs", []):
                        collection_name = ing_config.get("collection_name")
                        source_file = ing_config.get("source_file")
                        
                        if not collection_name or not source_file:
                            print(f"❌ Skipping invalid config: {ing_config}")
                            continue
                        
                        result = ingest_from_source_file(collection_name, source_file, ing_config)
                        all_results.append(result)
                        
                        if result["success"]:
                            total_ingested += result["ingested_count"]
                            print(f"✅ {collection_name}: {result['ingested_count']} documents from {source_file}")
                        else:
                            print(f"❌ {collection_name}: Failed - {result.get('error', 'Unknown error')}")
                    
                    end_time = time.time()
                    processing_time = end_time - start_time
                    
                    # Print summary
                    print(f"\n✅ Bulk ingestion completed:")
                    print(f"   - Total documents ingested: {total_ingested}")
                    print(f"   - Collections processed: {len(all_results)}")
                    successful = [r for r in all_results if r["success"]]
                    print(f"   - Successful collections: {len(successful)}")
                    print(f"   - Processing time: {processing_time:.2f} seconds")
                    
                    if total_ingested == 0:
                        raise Exception("No documents were ingested")
                    
            except FileNotFoundError as e:
                print(f"❌ File not found: {e}")
                print(f"💡 Make sure the file exists: {args.ingest_file}")
                if args.ingest_only:
                    sys.exit(1)
                else:
                    print("⚠️  Continuing with server startup despite ingestion error...")
            except Exception as e:
                print(f"❌ Error during document ingestion: {e}")
                if args.ingest_only:
                    sys.exit(1)
                else:
                    print("⚠️  Continuing with server startup despite ingestion error...")
        
        # Exit if only ingesting documents
        if args.ingest_only:
            print("✅ Document ingestion completed successfully. Exiting.")
            return
        
        print(f"\n🌐 Starting server at http://{args.host}:{args.port}")
        print(f"📖 API Documentation: http://localhost:{args.port}/docs")
        print(f"🔍 Interactive API: http://localhost:{args.port}/redoc")
        print("\nPress Ctrl+C to stop the server\n")
        
        # Start the server
        uvicorn.run(
            "api:app",
            host=args.host,
            port=args.port,
            reload=args.reload,
            log_level=args.log_level,
            access_log=True
        )
        
    except ImportError as e:
        print(f"❌ Import Error: {e}")
        print("💡 Make sure all dependencies are installed:")
        print("   pip install fastapi uvicorn python-multipart chromadb sentence-transformers google-generativeai python-dotenv pydantic")
        sys.exit(1)
        
    except Exception as e:
        print(f"❌ Error starting server: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 