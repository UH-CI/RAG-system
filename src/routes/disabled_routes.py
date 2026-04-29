"""
DISABLED ROUTES — Path traversal vulnerabilities need to be fixed before re-enabling.

These endpoints are NOT registered with the app. To re-enable, fix the path sanitization
using the helpers below, then do: from routes.disabled_routes import router and
app.include_router(router) in api.py.

Required fixes before re-enabling:
  - All collection_name inputs: use sanitize_collection_name()
  - All file.filename inputs in upload_pdf: use sanitize_filename()
"""

import os
import re
import json
import logging
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Form, File, UploadFile, Query
from fastapi.responses import JSONResponse

from app_types.requests import CollectionRequest, ChunkingRequest
from documents.step1_text_extraction.pdf_text_extractor import extract_pdf_text
from documents.step2_chunking.chunker import chunk_document

router = APIRouter()


# ---------------------------------------------------------------------------
# Path sanitization helpers — apply these before re-enabling the routes
# ---------------------------------------------------------------------------

def sanitize_collection_name(name: str) -> str:
    """Strip directory traversal characters and enforce safe alphanumeric names."""
    name = name.strip().lower()
    name = re.sub(r'[^a-z0-9_-]', '_', name)
    name = name.strip('_-')
    if not name:
        raise ValueError("Collection name is empty after sanitization")
    return name


def sanitize_filename(filename: str) -> str:
    """Return only the final filename component — no directory traversal."""
    name = Path(filename).name
    name = re.sub(r'[^a-zA-Z0-9._-]', '_', name)
    if not name:
        raise ValueError("Filename is empty after sanitization")
    return name


def safe_join(base: str, *parts: str) -> str:
    """Join paths and raise if the result escapes the base directory."""
    base = os.path.realpath(base)
    target = os.path.realpath(os.path.join(base, *parts))
    if not target.startswith(base + os.sep) and target != base:
        raise ValueError(f"Path traversal detected: {target}")
    return target


# ---------------------------------------------------------------------------
# Disabled endpoints
# ---------------------------------------------------------------------------

@router.post("/create-collection")
async def create_collection(payload: CollectionRequest):
    collection_name = payload.collection_name

    if not collection_name or not collection_name.strip():
        raise HTTPException(status_code=400, detail="Collection name cannot be empty")

    sanitized_name = collection_name.strip().lower().replace(' ', '_')

    collection_storage_dir = os.path.join("./documents/storage_documents", sanitized_name)
    collection_extracted_dir = os.path.join("./documents/extracted_text", sanitized_name)
    collection_chunked_dir = os.path.join("./documents/chunked_text", sanitized_name)

    try:
        os.makedirs(collection_storage_dir, exist_ok=True)
        os.makedirs(collection_extracted_dir, exist_ok=True)
        os.makedirs(collection_chunked_dir, exist_ok=True)

        return {
            "message": f"Collection '{sanitized_name}' created successfully",
            "collection_name": sanitized_name,
            "directories_created": {
                "storage": collection_storage_dir,
                "extracted_text": collection_extracted_dir,
                "chunked_text": collection_chunked_dir
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create collection '{sanitized_name}': {str(e)}")


@router.post("/upload-pdf")
async def upload_pdf(
    collection_name: str = Form(...),
    files: List[UploadFile] = File(...)
):
    collection_storage_dir = os.path.join("./documents/storage_documents", collection_name)
    os.makedirs(collection_storage_dir, exist_ok=True)

    uploaded_files = []

    for file in files:
        if not file.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail=f"File {file.filename} is not a PDF")

        file_location = os.path.join(collection_storage_dir, file.filename)

        try:
            with open(file_location, "wb") as buffer:
                while contents := await file.read(1024 * 1024):
                    buffer.write(contents)

            uploaded_files.append({
                "filename": file.filename,
                "path": file_location,
                "size": os.path.getsize(file_location)
            })

        except Exception as e:
            if os.path.exists(file_location):
                os.remove(file_location)
            raise HTTPException(status_code=500, detail=f"Could not upload file {file.filename}: {str(e)}")

    return {
        "message": f"Successfully uploaded {len(uploaded_files)} PDF file(s) to collection '{collection_name}'",
        "collection_name": collection_name,
        "uploaded_files": uploaded_files,
        "total_files": len(uploaded_files)
    }


@router.post("/step1-text-extraction")
async def step1_text_extraction(
    collection_name: str,
    contains_tables: bool = False,
    contains_images_of_text: bool = False,
    contains_images_of_nontext: bool = False
):
    collection_storage_dir = os.path.join("documents", "storage_documents", collection_name)
    collection_extracted_dir = os.path.join("documents", "extracted_text", collection_name)

    if not os.path.exists(collection_storage_dir):
        raise HTTPException(status_code=404, detail=f"Collection '{collection_name}' not found in storage documents")

    os.makedirs(collection_extracted_dir, exist_ok=True)

    pdf_files = [f for f in os.listdir(collection_storage_dir) if f.lower().endswith('.pdf')]

    if not pdf_files:
        raise HTTPException(status_code=404, detail=f"No PDF files found in collection '{collection_name}'")

    processed_files = []
    errors = []

    for filename in pdf_files:
        try:
            file_path = os.path.join(collection_storage_dir, filename)
            output_json_path = os.path.join(collection_extracted_dir, filename.replace(".pdf", ".json"))

            extracted_data = extract_pdf_text(
                pdf_file_path=file_path,
                output_path=output_json_path,
                contains_tables=contains_tables,
                contains_images_of_text=contains_images_of_text,
                contains_images_of_nontext=contains_images_of_nontext
            )

            with open(output_json_path, 'w', encoding='utf-8') as f:
                json.dump(extracted_data, f, indent=2, ensure_ascii=False)

            processed_files.append({
                "filename": filename,
                "output_path": output_json_path,
                "pages_extracted": len(extracted_data) if isinstance(extracted_data, list) else 1
            })

        except Exception as e:
            errors.append(f"Error processing {filename}: {str(e)}")

    if not processed_files:
        raise HTTPException(status_code=500, detail=f"Failed to extract text from any files. Errors: {'; '.join(errors)}")

    return {
        "message": f"Text extraction completed for collection '{collection_name}'",
        "collection_name": collection_name,
        "processed_files": processed_files,
        "total_processed": len(processed_files),
        "errors": errors
    }


@router.post("/step2-chunking")
async def step2_chunking(payload: ChunkingRequest):
    logging.info(f"Starting chunking for collection '{payload.collection_name}'")
    collection_extracted_dir = os.path.join("documents", "extracted_text", payload.collection_name)
    collection_chunked_dir = os.path.join("documents", "chunked_text", payload.collection_name)

    if not os.path.exists(collection_extracted_dir):
        raise HTTPException(status_code=404, detail=f"Collection '{payload.collection_name}' not found in extracted text")

    os.makedirs(collection_chunked_dir, exist_ok=True)

    json_files = [f for f in os.listdir(collection_extracted_dir) if f.lower().endswith('.json')]
    if not json_files:
        raise HTTPException(status_code=404, detail=f"No extracted text files found in collection '{payload.collection_name}'")

    processed_files = []
    errors = []

    for filename in json_files:
        try:
            file_path = os.path.join(collection_extracted_dir, filename)
            output_json_path = os.path.join(collection_chunked_dir, filename)

            chunked_data = chunk_document(
                input_json_path=file_path,
                output_json_path=output_json_path,
                chosen_methods=payload.chosen_methods,
                identifier=payload.identifier,
                use_ai=payload.use_ai,
                prompt_description=payload.prompt_description,
                previous_pages_to_include=payload.previous_pages_to_include,
                context_items_to_show=payload.context_items_to_show,
                rewrite_query=payload.rewrite_query,
                chunk_size=payload.chunk_size,
                overlap=payload.chunk_overlap
            )

            with open(output_json_path, 'w', encoding='utf-8') as f:
                json.dump(chunked_data, f, indent=2, ensure_ascii=False)

            processed_files.append({
                "filename": filename,
                "output_path": output_json_path,
                "chunks_created": len(chunked_data) if isinstance(chunked_data, list) else 1
            })

        except Exception as e:
            errors.append(f"Error processing {filename}: {str(e)}")

    if not processed_files:
        raise HTTPException(status_code=500, detail=f"Failed to chunk any files. Errors: {'; '.join(errors)}")

    return {
        "message": f"Chunking completed for collection '{payload.collection_name}'",
        "collection_name": payload.collection_name,
        "processed_files": processed_files,
        "total_processed": len(processed_files),
        "errors": errors
    }
