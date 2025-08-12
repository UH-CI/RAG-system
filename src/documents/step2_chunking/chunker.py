#!/usr/bin/env python3
"""
This script provides functions for chunking extracted PDF text using either
a simple sliding window method or an advanced AI-powered extraction method.
"""
import json
import logging
import os
from datetime import datetime
from typing import List, Dict, Any, Optional
import tiktoken
import re

# --- Set up logger ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- LLM Placeholders ---
# NOTE: Replace these with your actual LLM client and logic.
# You might use libraries like 'openai', 'anthropic', 'transformers', etc.

def _call_llm_for_rewriting(prompt_to_rewrite: str) -> str:
    """
    Placeholder for calling an LLM to rewrite a user's prompt for better clarity and performance.
    """
    logger.info("Calling placeholder LLM to rewrite prompt...")
    # In a real implementation, you would send the prompt to an LLM
    # with a meta-prompt like: "Rewrite the following user request for an item
    # extraction task to be clearer and more effective for a large language model.
    # Return only the rewritten prompt."
    rewritten = f"REWRITTEN PROMPT: Extract structured items based on the following rules: {prompt_to_rewrite}"
    return rewritten

def _call_llm_for_extraction(prompt: str) -> List[Dict[str, Any]]:
    """
    Placeholder for calling an LLM to extract structured data based on a prompt.
    """
    logger.info("Calling placeholder LLM for data extraction...")
    # This function should parse the LLM's response, which is expected to be
    # a JSON string representing a list of extracted items.
    # Mock response for demonstration:
    mock_response = [
        {"extracted_item": "Statute 101.5", "text": "The law of placeholders...", "notes": "This is a mock example."},
        {"extracted_item": "Statute 101.6", "text": "Another law...", "notes": "This demonstrates few-shot learning context."}
    ]
    # In a real scenario, you'd handle potential parsing errors.
    if "summary" in prompt.lower():
        for item in mock_response:
            item["summary"] = f"This is a mock summary for {item.get('extracted_item', 'an item')}."
    return mock_response

def clean_text(text: str) -> str:
    """
    Removes markdown, escaped newlines, and other unwanted characters from a text string.
    """
    # Remove markdown links and images
    text = re.sub(r'!\[.*?\]\(.*?\)', '', text)
    text = re.sub(r'\[.*?\]\(.*?\)', '', text)
    
    # Remove markdown headers, bold, italics, etc.
    text = re.sub(r'#+\s*', '', text)
    text = re.sub(r'(\*\*|__)(.*?)(\1)', r'\2', text)
    text = re.sub(r'(\*|_)(.*?)(\1)', r'\2', text)
    
    # Replace escaped newlines with a space
    text = text.replace('\\n', ' ')
    
    # Remove any remaining markdown-like characters
    text = text.replace('`', '').replace('>', '').replace('<', '')
    
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text

def _call_llm_for_summary(text_to_summarize: str) -> str:
    """
    Placeholder for calling an LLM to summarize a text chunk.
    """
    logger.info("Calling placeholder LLM to summarize text chunk...")
    # This function should call an LLM with a prompt like:
    # "Summarize the following text in one sentence:"
    cleaned_text = clean_text(text_to_summarize)
    summary = f"SUMMARY: {cleaned_text[:70]}..."
    return summary

# --- End LLM Placeholders ---

# --- Tokenizer setup ---
try:
    # Use the cl100k_base encoding, which is standard for GPT-3.5 and GPT-4
    tokenizer = tiktoken.get_encoding("cl100k_base")
except Exception:
    # Fallback to a different tokenizer if the primary one isn't available
    tokenizer = tiktoken.get_encoding("gpt2")

def count_tokens(text: str) -> int:
    """Counts the number of tokens in a text string using tiktoken."""
    return len(tokenizer.encode(text))

# --- End Tokenizer setup ---


def _simple_chunker(text: str, chunk_size: int, overlap: int, preserve_sentences: bool, chunk_in_tokens: bool, sentence_overlap: int) -> List[str]:
    """
    Splits a text into chunks.
    If preserve_sentences is True, it splits by sentences and groups them to near chunk_size.
    In this mode, `overlap` is ignored, and `sentence_overlap` is used for sentence-based overlap.
    Otherwise, it uses a sliding window with character/token `overlap`.
    """
    if not text:
        return []

    if preserve_sentences:
        # Split text into sentences
        sentence_enders = re.compile(r'(?<=[.?!])\s+')
        sentences = sentence_enders.split(text)
        sentences = [s.strip() for s in sentences if s.strip()]

        if not sentences:
            return []

        chunks = []
        start_index = 0
        
        def get_size(items):
            content = " ".join(items)
            return count_tokens(content) if chunk_in_tokens else len(content)

        while start_index < len(sentences):
            # Greedily add sentences to build a chunk
            end_index = start_index
            current_chunk_sentences = []
            while end_index < len(sentences):
                sentence_to_add = sentences[end_index]
                # If the chunk is empty, add the first sentence even if it's too big.
                if not current_chunk_sentences:
                    current_chunk_sentences.append(sentence_to_add)
                    end_index += 1
                    continue
                
                if get_size(current_chunk_sentences + [sentence_to_add]) > chunk_size:
                    break
                
                current_chunk_sentences.append(sentence_to_add)
                end_index += 1
            
            chunks.append(" ".join(current_chunk_sentences))

            if end_index >= len(sentences):
                break

            # Determine the start of the next chunk based on sentence_overlap
            num_sentences_in_chunk = end_index - start_index
            if sentence_overlap > 0 and num_sentences_in_chunk > sentence_overlap:
                start_index = end_index - sentence_overlap
            else:
                start_index = end_index
        return chunks

    # --- Original sliding window logic (if preserve_sentences is False) ---
    if chunk_in_tokens:
        tokens = tokenizer.encode(text)
        if len(tokens) <= chunk_size:
            return [text]
        
        chunks = []
        start = 0
        while start < len(tokens):
            end = start + chunk_size
            chunks.append(tokenizer.decode(tokens[start:end]))
            
            if end >= len(tokens):
                break
            
            start += (chunk_size - overlap)
        return chunks
    
    else: # character-based sliding window
        if len(text) <= chunk_size:
            return [text]
        
        chunks = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            chunks.append(text[start:end])
            
            if end >= len(text):
                break
            
            start += (chunk_size - overlap)
        return chunks


def chunk_document(
    input_json_path: str,
    output_json_path: str,
    chosen_methods: List[str],  # Required: list of property names to extract text from
    identifier: str,            # Required: property name to use as source identifier
    use_ai: bool = False,
    preserve_sentences: bool = False,
    preserve_document_in_metadata: bool = False,
    chunk_in_tokens: bool = False,
    # AI-related parameters
    prompt_description: Optional[str] = None,
    previous_pages_to_include: int = 1,
    context_items_to_show: int = 2,
    rewrite_query: bool = False,
    # Non-AI (simple chunking) parameters
    chunk_size: int = 1000,
    overlap: int = 100,
    sentence_overlap: int = 0, # Number of sentences to overlap when preserve_sentences is True
):
    """
    Chunks a document from an extracted text JSON using either simple or AI-powered methods.

    Args:
        input_json_path: Path to the input JSON file (from step1_text_extraction).
        output_json_path: Path to save the output chunked JSON file.
        chosen_methods: List of property names to extract text from (e.g., ['text'], ['pymupdf_extraction_text']).
        identifier: Property name to use as source identifier (e.g., 'url', 'filename').
        use_ai: If True, uses the AI-powered extraction method. Otherwise, uses the simple chunker.
        preserve_sentences: If True, tries to preserve whole sentences during simple chunking.
        preserve_document_in_metadata: If True, stores the entire document text in each chunk's metadata.
        chunk_in_tokens: If True, chunk_size and overlap are treated as token counts.

        -- AI Parameters --
        prompt_description: The prompt explaining to the LLM how to extract items.
        previous_pages_to_include: How many previous pages' text to include as context.
        context_items_to_show: How many previously extracted items to show as few-shot examples.
        rewrite_query: If True, a preliminary LLM call is made to refine the prompt_description.

        -- Simple Chunker Parameters --
        chunk_size: Size of each chunk in characters or tokens (see chunk_in_tokens).
        overlap: Character/token overlap for sliding window. Ignored if preserve_sentences is True.
        sentence_overlap: Sentence overlap for sentence chunker. Ignored if preserve_sentences is False.
    """
    # --- Parameter Validation ---
    if use_ai:
        if not all([chosen_methods, prompt_description]):
            raise ValueError("For AI chunking, 'chosen_methods' and 'prompt_description' are required.")
    else:
        if not chosen_methods:
            raise ValueError("For simple chunking, 'chosen_methods' is required.")

    # --- Load and Parse Input JSON ---
    with open(input_json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Assume the JSON structure is a list of pages/documents, each with various text extraction methods
    all_pages_data = data if isinstance(data, list) else [data]
    
    final_results = []
    all_docs_full_text = ""
    source_identifiers = []

    # Group pages by identifier
    docs = {}
    if all_pages_data:
        # Check for identifier in the first item to avoid errors with empty lists.
        if identifier not in all_pages_data[0]:
             raise ValueError(f"Identifier '{identifier}' not found in the first item of the input data.")
        for page in all_pages_data:
            source_id = page.get(identifier)
            # Use the full URL as source identifier, don't shorten it
            if source_id not in docs:
                docs[source_id] = []
            docs[source_id].append(page)

    for source_identifier, pages_data in docs.items():
        source_identifiers.append(source_identifier)
        # Concatenate and clean all text from the chosen methods to get the full document text
        full_text = "\n".join(
            "\n".join(page.get(method, "") for method in chosen_methods)
            for page in pages_data
        )
        full_text = clean_text(full_text)
        all_docs_full_text += full_text + "\n"

        if use_ai:
            logger.info(f"Starting AI-powered chunking for {source_identifier}...")
            effective_prompt = prompt_description
            if rewrite_query:
                logger.info("Rewriting user query with LLM...")
                effective_prompt = _call_llm_for_rewriting(prompt_description)
                logger.info(f"Using rewritten prompt: {effective_prompt}")
            
            doc_results = []
            for i, page in enumerate(pages_data):
                # 1. Assemble context from previous pages
                context_start_index = max(0, i - previous_pages_to_include)
                context_pages = pages_data[context_start_index:i]
                previous_pages_text = "\n".join(
                    "\n".join(p.get(method, "") for method in chosen_methods)
                    for p in context_pages if any(p.get(method) for method in chosen_methods)
                )

                # 2. Assemble few-shot examples from previously extracted items in the same document
                examples_start_index = max(0, len(doc_results) - context_items_to_show)
                few_shot_examples_json = json.dumps(doc_results[examples_start_index:], indent=2)

                # 3. Get current page text
                current_page_text = "\n".join(page.get(method, "") for method in chosen_methods)
                if not current_page_text.strip():
                    logger.info(f"Skipping page {page.get('page_number')} as it has no text in chosen methods.")
                    continue

                # Escape raw text to prevent breaking the prompt structure or subsequent JSON parsing.
                safe_previous_pages_text = previous_pages_text.replace('\\', r'\\').replace('"', r'\"')
                safe_current_page_text = current_page_text.replace('\\', r'\\').replace('"', r'\"')

                # 4. Construct the final prompt
                summary_instruction = ""
                full_prompt = (
                    f"**Instructions:**\n{effective_prompt}\n{summary_instruction}\n\n"
                    f"**Format Examples (previously extracted items):**\n{few_shot_examples_json}\n\n"
                    f"**Context from Previous Pages:**\n{safe_previous_pages_text}\n\n"
                    f"---\n"
                    f"**Current Page Text to Process:**\n{safe_current_page_text}\n\n"
                    f"---\n"
                    f"Based on the instructions, extract items ONLY from the 'Current Page Text to Process'. "
                    f"Return the items as a JSON array of objects. If no items are found, return an empty array []."
                )

                # 5. Call LLM and add metadata to results
                extracted_items = _call_llm_for_extraction(full_prompt)
                for item in extracted_items:
                    item['source_identifier'] = source_identifier
                    item['metadata'] = {
                        'source_page': page.get('page_number', i),
                        'chunking_method': 'ai_extraction',
                        'source_extraction_methods': chosen_methods,
                        'chunk_size_tokens': count_tokens(item.get('text', json.dumps(item)))
                    }
                    if preserve_document_in_metadata:
                        item['metadata']['original_document'] = full_text
                doc_results.extend(extracted_items)
            final_results.extend(doc_results)

        else:
            logger.info(f"Starting simple sliding-window chunking for {source_identifier}...")
            text_chunks = _simple_chunker(full_text, chunk_size, overlap, preserve_sentences, chunk_in_tokens, sentence_overlap)
            
            for chunk in text_chunks:
                chunk_data = {
                    "chunk_id": len(final_results),
                    "text": chunk,
                    "source_identifier": source_identifier,
                    "metadata": {
                        "chunking_method": "simple_sliding_window",
                        "source_extraction_methods": chosen_methods,
                        "chunk_size_tokens": count_tokens(chunk)
                    }
                }
                if preserve_document_in_metadata:
                    chunk_data['metadata']['original_document'] = full_text
                final_results.append(chunk_data)

    # --- Calculate text statistics for the full document ---
    full_document_char_length = len(all_docs_full_text)
    full_document_token_length = count_tokens(all_docs_full_text)

    # --- Save Final Results ---
    with open(output_json_path, 'w', encoding='utf-8') as f:
        json.dump(final_results, f, indent=2, ensure_ascii=False)
    
    # Get the size of the output file
    chunked_file_size_bytes = os.path.getsize(output_json_path)

    # --- Create Metadata File ---
    metadata_path = output_json_path.replace('.json', '_metadata.json')
    metadata = {
        "timestamp": datetime.now().isoformat(),
        "input_file": input_json_path,
        "output_file": output_json_path,
        "parameters": {
            "chosen_methods": chosen_methods,
            "identifier": identifier,
            "use_ai": use_ai,
            "chunk_size": chunk_size,
            "overlap": overlap,
            "preserve_sentences": preserve_sentences,
            "preserve_document_in_metadata": preserve_document_in_metadata,
            "chunk_in_tokens": chunk_in_tokens,
            "sentence_overlap": sentence_overlap
        },
        "results": {
            "total_chunks": len(final_results),
            "source_identifiers": source_identifiers,
            "input_documents_count": len(all_pages_data),
            "chunked_file_size_bytes": chunked_file_size_bytes
        }
    }
    
    # Add AI-specific metadata if applicable
    if use_ai:
        metadata["parameters"].update({
            "prompt_description": prompt_description,
            "previous_pages_to_include": previous_pages_to_include,
            "context_items_to_show": context_items_to_show,
            "rewrite_query": rewrite_query
        })
        metadata["results"]["chunking_method"] = "ai_extraction"
    else:
        metadata["results"]["chunking_method"] = "simple_sliding_window"
        
    # Calculate text and token statistics
    if final_results:
        # Assuming 'text' key exists in chunk dictionaries for both methods
        if "text" in final_results[0]:
            chunk_texts = [chunk["text"] for chunk in final_results]
            chunk_char_lengths = [len(text) for text in chunk_texts]
            chunk_token_lengths = [count_tokens(text) for text in chunk_texts]

            metadata["results"]["text_statistics"] = {
                "full_document_char_length": full_document_char_length,
                "min_chunk_char_length": min(chunk_char_lengths),
                "max_chunk_char_length": max(chunk_char_lengths),
                "avg_chunk_char_length": sum(chunk_char_lengths) / len(chunk_char_lengths),
                "total_chars_in_chunks": sum(chunk_char_lengths)
            }
            metadata["results"]["token_statistics"] = {
                "full_document_token_length": full_document_token_length,
                "min_chunk_token_length": min(chunk_token_lengths),
                "max_chunk_token_length": max(chunk_token_lengths),
                "avg_chunk_token_length": sum(chunk_token_lengths) / len(chunk_token_lengths),
                "total_tokens_in_chunks": sum(chunk_token_lengths)
            }
    
    with open(metadata_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    
    logger.info(f"Chunking complete. Saved {len(final_results)} items to {output_json_path}")
    logger.info(f"Metadata saved to {metadata_path}")
    
    # Return the chunked results
    return final_results


# This basic setup allows the script to be used as a module.
# You could add argparse here to make it a CLI tool as well.
if __name__ == '__main__':
    # Example of how to run the function
    # The logger is already configured at the top level, so no need to reconfigure here.
    
    # Create a dummy input file for testing
    input_path = "../extracted_text/policies/policies.json"
    output_path = "../chunked_text/policies/policies.json"

    # --- Example 1: Simple Chunker ---
    logger.info("--- Running Simple Chunker Example ---")
    chunk_document(
        input_json_path=input_path,
        output_json_path=output_path,
        chosen_methods=['extracted'],  # Use 'text' field from your JSON
        identifier='url',         # Use 'url' field as source identifier
        use_ai=False,
        chunk_size=500,
        overlap=0, # Overlap is ignored when preserve_sentences is True
        sentence_overlap=2, # Number of sentences to overlap
        preserve_sentences=True,
        preserve_document_in_metadata=False,
        chunk_in_tokens=True, # Set to True for token-based chunking
        # Removed generate_chunk_summary as it's no longer a parameter
    )
    print(f"Simple chunking output saved to {output_path}")

    # # --- Example 2: AI Chunker ---
    # logger.info("--- Running AI Chunker Example ---")
    # chunk_document(
    #     input_json_path=dummy_input_path,
    #     output_json_path=dummy_output_path,
    #     use_ai=True,
    #     chosen_methods=['pymupdf_extraction_text', 'pdfplumber_extraction_text'],
    #     prompt_description="Extract each statute mentioned in the text. Each item should have 'statute_id' and 'description' fields."
    # )
    print(f"AI chunking output saved to {output_path}") 