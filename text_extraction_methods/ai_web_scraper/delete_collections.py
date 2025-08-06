import chromadb
import argparse
import os

def delete_collections_by_prefix(prefix: str, persist_directory: str):
    """
    Deletes ChromaDB collections that start with a given prefix.

    Args:
        prefix (str): The prefix of the collections to delete.
        persist_directory (str): The directory where ChromaDB is persisted.
    """
    if not os.path.exists(persist_directory):
        print(f"Error: Persist directory not found at '{persist_directory}'")
        return

    try:
        client = chromadb.PersistentClient(path=persist_directory)
        collections = client.list_collections()
        collection_names = [c.name for c in collections]
        
        print(f"Found {len(collection_names)} collections: {collection_names}")

        collections_to_delete = [name for name in collection_names if name.startswith(prefix)]

        if not collections_to_delete:
            print(f"No collections found with prefix '{prefix}'.")
            return

        print(f"\nCollections to be deleted ({len(collections_to_delete)}):")
        for name in collections_to_delete:
            print(f" - {name}")

        response = input("\nAre you sure you want to delete these collections? (y/n): ")
        if response.lower() == 'y':
            for name in collections_to_delete:
                try:
                    client.delete_collection(name=name)
                    print(f"Deleted collection: {name}")
                except Exception as e:
                    print(f"Error deleting collection {name}: {e}")
            print("\nDeletion complete.")
        else:
            print("\nDeletion cancelled.")

    except Exception as e:
        print(f"An error occurred: {e}")

def main():
    """Main function to parse arguments and delete collections."""
    parser = argparse.ArgumentParser(description="Delete ChromaDB collections by prefix.")
    parser.add_argument("--prefix", type=str, required=True, help="Prefix of collections to delete (e.g., 'pdf_session_').")
    parser.add_argument("--persist_directory", type=str, default="./chroma_db", help="Path to ChromaDB persistent storage.")
    
    args = parser.parse_args()
    
    delete_collections_by_prefix(args.prefix, args.persist_directory)

if __name__ == "__main__":
    main() 