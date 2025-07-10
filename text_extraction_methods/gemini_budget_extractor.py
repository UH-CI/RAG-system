import os
import json
import time
import random
import concurrent.futures
from typing import List, Dict, Optional, Tuple, Type, Any, Callable
import PyPDF2
import google.generativeai as genai
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

class GeminiBudgetExtractor:
    def __init__(self, api_key: str):
        """Initialize the Gemini extractor with Google AI API key.
        
        Args:
            api_key: Your Google AI API key
        """
        self.api_key = api_key
        self.model = None
        self.budget_items: List[Dict] = []
        self.current_bill: Optional[str] = None
        self.initialize_gemini()
    
    def initialize_gemini(self) -> None:
        """Initialize the Gemini model using Google AI API."""
        try:
            # Configure the API key
            genai.configure(api_key=self.api_key)
            
            # Initialize the Gemini model
            self.model = genai.GenerativeModel('gemini-1.5-flash')
            print("Successfully initialized Gemini with Google AI API")
            
        except Exception as e:
            print(f"Error initializing Gemini: {e}")
            raise
    
    def retry_with_backoff(
        self,
        func: Callable,
        *args,
        max_retries: int = 3,
        initial_delay: float = 1.0,
        max_delay: float = 60.0,
        backoff_factor: float = 2.0,
        exceptions: tuple[Type[Exception], ...] = (Exception,)
    ) -> Any:
        """Retry a function with exponential backoff."""
        delay = initial_delay
        for attempt in range(1, max_retries + 1):
            try:
                return func(*args)
            except exceptions as e:
                if attempt == max_retries:
                    print(f"Max retries ({max_retries}) reached. Last error: {e}")
                    raise
                
                # Add jitter to avoid thundering herd
                sleep_time = min(delay * (1 + random.random() * 0.1), max_delay)
                print(f"Attempt {attempt} failed with error: {e}. Retrying in {sleep_time:.2f}s...")
                time.sleep(sleep_time)
                delay *= backoff_factor
                
        raise Exception("Max retries reached")

    def process_chunk(self, chunk_data: Tuple[int, str, str]) -> Tuple[int, List[Dict]]:
        """Process a single chunk of text and return its budget items with retry logic."""
        chunk_num, chunk, filename = chunk_data
        print(f"Processing chunk {chunk_num}...")
        
        def _process() -> List[Dict]:
            return self.extract_budget_items_with_gemini(chunk, filename) or []
            
        try:
            chunk_items = self.retry_with_backoff(
                _process,
                max_retries=3,
                initial_delay=2.0,
                backoff_factor=2.0
            )
            
            if chunk_items:
                print(f"Extracted {len(chunk_items)} budget items from chunk {chunk_num}")
                return (chunk_num, chunk_items)
            return (chunk_num, [])
            
        except Exception as e:
            print(f"Error in chunk {chunk_num} after retries: {e}")
            return (chunk_num, [])

    def find_budget_section_start(self, reader: PyPDF2.PdfReader, max_toc_pages: int = 20) -> int:
        """Analyze the PDF to find the starting page of the budget section using Gemini.
        
        Args:
            reader: PyPDF2 PdfReader instance
            max_toc_pages: Maximum number of pages to check for table of contents
            
        Returns:
            int: 1-based page number where budget section starts, or 1 if not found
        """
        print("  - Searching for budget section using Gemini...")
        
        # First, find a proper table of contents page
        toc_page_num = None
        max_pages_to_scan = min(30, len(reader.pages))  # Scan at most 30 pages
        
        # Phase 1: Find the table of contents using Gemini
        for page_num in range(max_pages_to_scan):
            try:
                page = reader.pages[page_num]
                text = page.extract_text()
                print(f"  - Analyzing page {page_num + 1} with Gemini... {text[:100]}")
                # Skip empty or very short pages
                if not text or len(text.strip()) < 20:
                    continue
                
                # Use Gemini to determine if this is a TOC page
                prompt = f"""Analyze if this page is a table of contents from a legislative budget document.
                A table of contents typically contains a list of sections and page numbers. Look for sections like:
                - General Information
                - Appropriations
                - Budget Summary
                - Department allocations
                - Fund information
                - Legislative provisions
                
                Page content:
                {text}...
                
                Is this a table of contents page? Answer with exactly 'yes' or 'no'."""
                
                response = self.model.generate_content(prompt)
                
                if response and hasattr(response, 'text'):
                    if response.text.strip().lower().startswith('yes'):
                        toc_page_num = page_num + 1  # Store 1-based page number
                        print(f"  - Gemini identified page {toc_page_num} as a table of contents")
                        break
                    
            except Exception as e:
                print(f"  - Error reading page {page_num + 1}: {e}")
        
        # Phase 2: Look for budget/appropriations starting from the TOC page
        if toc_page_num is not None:
            # Search up to 10 pages after the TOC
            end_page = min(toc_page_num + 10, len(reader.pages))
            for page_num in range(toc_page_num - 1, end_page):  # Convert back to 0-based
                try:
                    page = reader.pages[page_num]
                    text = page.extract_text()
                    
                    print(f"  - Analyzing TOC on page {page_num} with Gemini...{text}")
                    # Prepare the prompt with clear instructions
                    prompt_text = f"""You are analyzing a legislative budget document's table of contents.
                    Your task is to find the page number where the actual budget appropriations, allocations, or detailed financial information begins.
                    Look for sections like:
                    - 'Appropriations'
                    - 'Budget Details'
                    - 'Department Allocations'
                    - 'Financial Provisions'
                    - 'Fund Allocations'
                    - Or any section that would contain detailed budget line items
                    
                    Return ONLY the page number as an integer, or 'null' if you can't find any budget detail information in this TOC.
                    
                    Table of Contents:
                    {text}
                    
                    Page number where budget details begin (or 'null' if not found):"""
                    
                    # Send to Gemini
                    response = self.model.generate_content(prompt_text)
                
                    # Safely extract the response text
                    if response and hasattr(response, 'text'):
                        result = response.text.strip()
                        # Clean the result to get just the first number
                        import re
                        match = re.search(r'\d+', result)
                        if match:
                            page_num = int(match.group())
                            if 1 <= page_num <= len(reader.pages):
                                print(f"  - Gemini suggests starting at page {page_num}")
                                return page_num
                            else:
                                print(f"  - Gemini returned out-of-range page number: {page_num}")
                        else:
                            print(f"  - No page number found in Gemini response")
                    else:
                        print("  - Empty or invalid response from Gemini")
                    
                except Exception as e:
                    print(f"  - Error processing Gemini response: {str(e)}")
            
            # If we get here, we didn't find budget details but have a TOC page
            return toc_page_num
                        
        # If no TOC found, start from page 1
        return 1

    def process_pdf(self, filepath: str, max_workers: int = 4) -> List[Dict]:
        """Process a single PDF file and return extracted budget items using parallel processing."""
        filename = os.path.basename(filepath)
        print(f"Processing: {filename}")
        
        # Read the entire PDF with retry and proper resource management
        def _read_pdf() -> str:
            try:
                print(f"  - Opening PDF file: {filepath}")
                with open(filepath, 'rb') as file:
                    reader = PyPDF2.PdfReader(file)
                    total_pages = len(reader.pages)
                    
                    # Find the starting page for budget section
                    start_page = self.find_budget_section_start(reader)
                    print(f"  - Processing pages {start_page} to {total_pages} of {total_pages}...")
                    
                    # Use a list to collect page texts and join at the end
                    page_texts = []
                    for i in range(start_page - 1, total_pages):  # Convert to 0-based index
                        page = reader.pages[i]
                        if (i - start_page + 1) % 10 == 0 or i == start_page - 1 or i == total_pages - 1:
                            print(f"  - Extracting text from page {i + 1}/{total_pages}")
                        page_text = page.extract_text()
                        if page_text:  # Only add non-empty texts
                            page_texts.append(page_text)
                    
                    total_text = '\n'.join(page_texts)
                    print(f"  - Extracted {len(total_text):,} characters from {total_pages - start_page + 1} pages")
                    return total_text
                    
            except Exception as e:
                print(f"Error reading PDF: {e}")
                return ""
            finally:
                # Ensure any resources are released
                if 'reader' in locals():
                    if hasattr(reader, '_stream') and reader._stream:
                        reader._stream.close()
                    print("  - Closed PDF file")
        
        text = self.retry_with_backoff(_read_pdf, max_retries=3, initial_delay=1.0)
            
        if not text:
            print(f"Warning: Could not extract text from {filepath}")
            return []
            
        # Process text in chunks to avoid memory issues
        chunk_size = 10000  # Target chunk size
        min_chunk_size = 1000  # Minimum chunk size to ensure progress
        overlap = 1000  # 1K character overlap to prevent splitting budget items
        chunks = []
        start = 0
        chunk_num = 1
        total_chars = len(text)
        
        print(f"  - Splitting {total_chars:,} characters into chunks...")
        
        while start < total_chars:
            # Calculate end position for this chunk
            end = min(start + chunk_size, total_chars)
            
            # If this would be the last chunk and it's too small, just extend it to the end
            if end == total_chars and (end - start) < min_chunk_size and len(chunks) > 0:
                # Merge with previous chunk if possible
                prev_chunk_num, prev_chunk, _ = chunks[-1]
                chunks[-1] = (prev_chunk_num, prev_chunk + text[start:end], filename)
                print(f"  - Merged final small chunk ({end-start:,} chars) with previous chunk")
                break
            
            # Add the chunk if it's not empty
            if start < end:
                chunk_text = text[start:end]
                chunks.append((chunk_num, chunk_text, filename))
                
                # Calculate and log progress
                progress = min(100, int((end / total_chars) * 100))
                print(f"  - Created chunk {chunk_num}: positions {start:,}-{end:,} "
                      f"({len(chunk_text):,} chars, {progress}% of text)")
            
            # Calculate next start position (move forward by chunk_size - overlap)
            new_start = start + chunk_size - overlap
            
            # If we're at or beyond the end, we're done
            if new_start >= total_chars:
                break
                
            # Ensure we're making progress
            if new_start <= start:
                new_start = start + 1
                if new_start >= total_chars:
                    break
            
            # Update for next iteration
            start = new_start
            chunk_num += 1
            
            # Force garbage collection every 10 chunks to help with memory
            if chunk_num % 10 == 0:
                import gc
                gc.collect()
                
            # Safety check to prevent infinite loops
            if chunk_num > 1000:  # Arbitrary large number to prevent infinite loops
                print(f"  - Warning: Exceeded maximum number of chunks (1000). Stopping chunking.")
                break
                
        print(f"  - Split into {len(chunks)} chunks for processing")
        
        all_budget_items = []
        completed_chunks = set()
        
        # Process chunks in parallel with rate limiting
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all chunks for processing
            future_to_chunk = {}
            for chunk in chunks:
                future = executor.submit(self.process_chunk, chunk)
                future_to_chunk[future] = chunk[0]
                
                # Small delay between submissions to avoid overwhelming the API
                time.sleep(0.5)
            
            # Process results as they complete
            start_time = time.time()
            last_update = start_time
            
            print(f"\n  --- Starting parallel processing of {len(chunks)} chunks with {max_workers} workers ---")
            
            for future in concurrent.futures.as_completed(future_to_chunk):
                chunk_num = future_to_chunk[future]
                current_time = time.time()
                
                try:
                    chunk_num, chunk_items = future.result()
                    if chunk_items:
                        all_budget_items.extend(chunk_items)
                    completed_chunks.add(chunk_num)
                    
                    # Calculate progress and ETA
                    elapsed = current_time - start_time
                    chunks_remaining = len(chunks) - len(completed_chunks)
                    chunks_per_sec = len(completed_chunks) / (elapsed + 1e-6)
                    eta = chunks_remaining / (chunks_per_sec + 1e-6)
                    
                    # Only log every 5 chunks or if it's been more than 5 seconds since last update
                    if (len(completed_chunks) % 5 == 0 or 
                        current_time - last_update > 5 or 
                        len(completed_chunks) == len(chunks)):
                        print(
                            f"  - Processed chunk {len(completed_chunks)}/{len(chunks)} | "
                            f"{len(chunk_items)} budget items | "
                            f"ETA: {int(eta//60)}m {int(eta%60)}s"
                        )
                        last_update = current_time
                        
                except Exception as e:
                    print(f"Error processing chunk {chunk_num} after submission: {e}")
        
        total_time = time.time() - start_time
        print(f"\n  --- Completed processing {filename} in {total_time:.1f} seconds ---")
        print(f"  - Extracted {len(all_budget_items)} budget items from {len(chunks)} chunks")
        print(f"  - Average processing time: {total_time/len(chunks):.2f} seconds per chunk")
        return all_budget_items

    def extract_budget_items_with_gemini(self, text: str, filename: str) -> List[Dict]:
        """Use Gemini to extract budget information from text with financial details."""
        prompt = """Extract all budget items and appropriations from the following legislative budget document text. 
        For each budget item, return a JSON array of objects with these fields:
        - item_id (a unique identifier you create, e.g., 'HB300-001')
        - department (the government department or agency, e.g., 'Department of Education', 'University of Hawaii')
        - program (the specific program or initiative within the department)
        - description (detailed description of what the funding is for)
        - amount (the dollar amount as a number, without commas or dollar signs)
        - amount_formatted (the dollar amount as a formatted string, e.g., '$1,234,567')
        - fund_type (e.g., 'General Fund', 'Special Fund', 'Federal Fund', 'Other Fund')
        - fund_code (specific fund identifier if mentioned)
        - fiscal_year (the fiscal year this applies to, e.g., '2024', '2025')
        - positions (number of positions/FTE if mentioned)
        - appropriation_type (e.g., 'Operating', 'Capital', 'Personnel', 'Equipment')
        - page_reference (approximate page or section where this was found)
        - bill_version (the bill version, e.g., 'HB300', 'HB300_CD1')
        - notes (any additional relevant information)
        
        Important guidelines:
        - Extract actual monetary appropriations and budget allocations
        - Include both dollar amounts and position counts where available
        - Parse financial tables carefully to preserve exact amounts
        - Look for department names, program descriptions, and fund classifications
        - If an amount is in thousands (e.g., "1,234" in a table), convert to actual dollars
        - Preserve all decimal places in financial amounts
        
        Return ONLY valid JSON, nothing else. Example:
        [
            {
                "item_id": "HB300-001",
                "department": "Department of Education",
                "program": "General Education Operations",
                "description": "Operations and maintenance of public schools",
                "amount": 1500000,
                "amount_formatted": "$1,500,000",
                "fund_type": "General Fund",
                "fund_code": "A",
                "fiscal_year": "2024",
                "positions": 25.5,
                "appropriation_type": "Operating",
                "page_reference": "Page 15",
                "bill_version": "HB300",
                "notes": "Includes funding for rural school initiatives"
            },
            {
                "item_id": "HB300-002", 
                "department": "University of Hawaii",
                "program": "Research and Development",
                "description": "Scientific research initiatives and equipment",
                "amount": 2750000,
                "amount_formatted": "$2,750,000",
                "fund_type": "Special Fund",
                "fund_code": "S",
                "fiscal_year": "2024",
                "positions": 12,
                "appropriation_type": "Capital",
                "page_reference": "Page 22",
                "bill_version": "HB300",
                "notes": "Multi-year funding commitment"
            }
        ]
        
        Here's the text to process:
        """
        
        # Set the bill version based on filename
        self.set_bill_from_filename(filename)
        
        try:
            # Limit text size to avoid context window issues
            content = text
            
            # Create the full prompt
            full_prompt = prompt + content
            
            # Generate content with error handling
            try:
                response = self.model.generate_content(full_prompt)
            except Exception as e:
                print(f"Error generating content: {e}")
                return []
            
            # Debug: Print the raw response structure
            print("Response structure:", dir(response))
            
            # Extract text from response
            response_text = None
            try:
                # Try different ways to get the response text
                if hasattr(response, 'text'):
                    response_text = response.text
                elif hasattr(response, 'candidates') and response.candidates:
                    candidate = response.candidates[0]
                    if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
                        if candidate.content.parts:
                            response_text = candidate.content.parts[0].text
                
                if not response_text:
                    print("Could not extract text from response")
                    print("Full response:", response)
                    return []
                
                print("Raw response (first 500 chars):", response_text[:500])
                
                # Clean the response to extract just the JSON
                if '```json' in response_text:
                    response_text = response_text.split('```json')[1].split('```')[0]
                elif '```' in response_text:
                    response_text = response_text.split('```')[1].split('```')[0]
                
                # Parse the JSON
                budget_items = json.loads(response_text)
                
                # Ensure we have a list
                if not isinstance(budget_items, list):
                    budget_items = [budget_items]
                
                # Process each budget item to ensure required fields are present
                processed_items = []
                for item in budget_items:
                    # Ensure required fields exist with defaults
                    if not isinstance(item, dict):
                        continue
                        
                    # Initialize missing fields with defaults
                    item.setdefault('bill_version', self.current_bill)
                    item.setdefault('fiscal_year', '2024')  # Default fiscal year
                    item.setdefault('positions', None)
                    item.setdefault('fund_code', None)
                    item.setdefault('notes', '')
                    
                    # Ensure amount is a number
                    if 'amount' in item:
                        try:
                            # Handle string amounts by removing commas and converting
                            if isinstance(item['amount'], str):
                                amount_str = item['amount'].replace(',', '').replace('$', '').strip()
                                item['amount'] = float(amount_str) if '.' in amount_str else int(amount_str)
                        except (ValueError, TypeError):
                            item['amount'] = 0
                    
                    processed_items.append(item)
                
                print(f"Successfully extracted {len(processed_items)} budget items")
                return processed_items
                
            except json.JSONDecodeError as e:
                print(f"JSON decode error: {e}")
                print(f"Problematic response: {response_text}")
                return []
                
            except Exception as e:
                print(f"Error processing response: {e}")
                print(f"Response type: {type(response)}")
                print(f"Response dir: {dir(response)}")
                if hasattr(response, 'prompt_feedback'):
                    print(f"Prompt feedback: {response.prompt_feedback}")
                return []
                
        except Exception as e:
            print(f"Unexpected error: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def set_bill_from_filename(self, filename: str) -> None:
        """
        Extract and set the bill version from the filename.
        
        Args:
            filename: The name of the PDF file (e.g., 'HB300_CD1_.pdf')
        """
        # Remove file extension and any path
        base_name = os.path.splitext(os.path.basename(filename))[0]
        
        # Extract bill version from filename
        if 'HB300' in base_name.upper():
            if '_CD1' in base_name.upper():
                bill_version = 'HB300_CD1'
            elif '_HD1' in base_name.upper():
                bill_version = 'HB300_HD1'
            elif '_SD1' in base_name.upper():
                bill_version = 'HB300_SD1'
            else:
                bill_version = 'HB300'
        else:
            # Generic handling for other bill types
            bill_version = base_name.upper().replace('_', '_').replace('.PDF', '')
        
        self.current_bill = bill_version
        print(f"  - Extracted bill version: {bill_version}")

def process_pdfs_with_gemini(api_key: str, catalogs_dir: str, output_dir: str, max_workers: int = 4):
    """Process all PDFs in the catalogs directory using Gemini."""
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    # Initialize the extractor with Google AI API key
    extractor = GeminiBudgetExtractor(api_key)
    
    all_budget_items = []
    processed_files = 0
    
    # Process each PDF in the catalogs directory
    for filename in sorted(os.listdir(catalogs_dir)):
        if not filename.lower().endswith('.pdf'):
            continue
            
        filepath = os.path.join(catalogs_dir, filename)
        print(f"\nProcessing {filename}...")
        
        try:
            # Process the PDF and extract budget items
            budget_items = extractor.process_pdf(filepath, max_workers=max_workers)
            if budget_items:
                # Create a clean base name for the output file
                base_name = os.path.splitext(filename)[0]
                output_filename = f"{base_name}_budget_items.json"
                output_path = os.path.join(output_dir, output_filename)
                
                # Save budget items for this file
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(budget_items, f, indent=2, ensure_ascii=False)
                
                all_budget_items.extend(budget_items)
                processed_files += 1
                print(f"Extracted {len(budget_items)} budget items from {filename}")
                print(f"Saved to: {output_path}")
            else:
                print(f"No budget items extracted from {filename}")
                
        except Exception as e:
            print(f"Error processing {filename}: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    # Save combined results
    if all_budget_items:
        combined_output = os.path.join(output_dir, 'all_budget_items_combined.json')
        with open(combined_output, 'w', encoding='utf-8') as f:
            json.dump(all_budget_items, f, indent=2, ensure_ascii=False)
    
    print(f"\nProcessing complete!")
    print(f"Processed {processed_files} files")
    print(f"Extracted a total of {len(all_budget_items)} budget items")
    if all_budget_items:
        print(f"Individual budget item files saved in: {output_dir}")
        print(f"Combined results saved to: {combined_output}")
    
    return all_budget_items

def process_single_file(filepath: str, api_key: str, output_dir: str, max_workers: int = 4):
    """Process a single PDF file and save the extracted budget items."""
    if not os.path.isfile(filepath):
        print(f"Error: File not found: {filepath}")
        return []
        
    print(f"\nProcessing single file: {os.path.basename(filepath)}")
    
    # Initialize the extractor with Google AI API key
    extractor = GeminiBudgetExtractor(api_key)
    
    try:
        # Process the PDF and extract budget items
        budget_items = extractor.process_pdf(filepath, max_workers=max_workers)
        if budget_items:
            # Create a clean base name for the output file
            base_name = os.path.splitext(os.path.basename(filepath))[0]
            output_filename = f"{base_name}_budget_items.json"
            output_path = os.path.join(output_dir, output_filename)
            
            # Save budget items for this file
            os.makedirs(output_dir, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(budget_items, f, indent=2, ensure_ascii=False)
            
            print(f"Extracted {len(budget_items)} budget items from {os.path.basename(filepath)}")
            print(f"Saved to: {output_path}")
            return budget_items
        else:
            print(f"No budget items extracted from {os.path.basename(filepath)}")
            return []
            
    except Exception as e:
        print(f"Error processing {os.path.basename(filepath)}: {e}")
        import traceback
        traceback.print_exc()
        return []

if __name__ == "__main__":
    import argparse
    
    # Load environment variables from .env file
    load_dotenv()
    
    # Set up argument parser
    parser = argparse.ArgumentParser(description='Extract budget information from PDF legislative budget documents using Gemini.')
    parser.add_argument('--catalog', type=str, help='Path to a directory containing budget PDF files to process')
    parser.add_argument('--file', type=str, help='Path to a specific budget PDF file to process')
    args = parser.parse_args()
    
    # Configuration
    GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')  # Get from environment variable
    if not GOOGLE_API_KEY:
        print("Error: GOOGLE_API_KEY environment variable not found.")
        print("Please set your Google AI API key: export GOOGLE_API_KEY='your_api_key_here'")
        print("Or add it to your .env file: GOOGLE_API_KEY=your_api_key_here")
        exit(1)
    
    # Define directories
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    OUTPUT_DIR = os.path.join(BASE_DIR, "budget_output")
    
    # Process either a single file or a directory of files
    try:
        if args.file:
            # Process just the specified file
            filepath = os.path.abspath(args.file)
            if not filepath.lower().endswith('.pdf'):
                print("Error: The specified file is not a PDF")
                exit(1)
                
            process_single_file(
                filepath=filepath,
                api_key=GOOGLE_API_KEY,
                output_dir=OUTPUT_DIR,
                max_workers=4
            )
        else:
            # Process a directory of files (or default to src/documents directory)
            if args.catalog:
                if os.path.isdir(args.catalog):
                    BUDGET_DIR = os.path.abspath(args.catalog)
                    print(f"Processing all PDFs in directory: {BUDGET_DIR}")
                else:
                    print(f"Error: The provided path is not a directory: {args.catalog}")
                    exit(1)
            else:
                # Default to the src/documents directory if no path is provided
                BUDGET_DIR = os.path.join(BASE_DIR, "src/documents")
                print(f"No budget path provided. Defaulting to: {BUDGET_DIR}")
            
            if not os.path.exists(BUDGET_DIR):
                print(f"Error: Budget directory not found: {BUDGET_DIR}")
                print("Please ensure your HB300 PDF files are in the src/documents directory.")
                exit(1)
            
            process_pdfs_with_gemini(
                api_key=GOOGLE_API_KEY,
                catalogs_dir=BUDGET_DIR,
                output_dir=OUTPUT_DIR,
                max_workers=4
            )
    except Exception as e:
        print(f"An error occurred: {e}")
        exit(1)
