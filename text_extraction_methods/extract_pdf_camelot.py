#!/usr/bin/env python3
"""
PDF Text and Table Extraction using Camelot
Specialized for table extraction from PDFs, including rotated tables.
"""

import camelot
import sys
import argparse
from pathlib import Path
import time
import signal

class TimeoutError(Exception):
    pass

def timeout_handler(signum, frame):
    raise TimeoutError("Operation timed out")

def extract_tables_from_pdf(pdf_path, output_dir, max_pages=None, timeout_seconds=120):
    """
    Extract tables from PDF using Camelot (specialized for table extraction).
    
    Args:
        pdf_path (str): Path to PDF file
        output_dir (str): Output directory
        max_pages (int): Maximum pages to process (None for all)
        timeout_seconds (int): Timeout for each method attempt
    
    Returns:
        bool: Success status
    """
    try:
        pdf_path = str(pdf_path)
        output_dir = Path(output_dir)
        output_dir.mkdir(exist_ok=True)
        
        # Check if file already processed
        filename_base = Path(pdf_path).stem
        tables_output_file = output_dir / f"{filename_base}_tables_extracted.txt"
        if tables_output_file.exists():
            print(f"DEBUG: File {filename_base} already processed, skipping...")
            return True
        
        # Determine pages to process
        if max_pages:
            pages = f"1-{max_pages}"
        else:
            pages = "all"
        
        print(f"Camelot: Extracting tables from {pdf_path}")
        print(f"Pages: {pages}")
        print(f"DEBUG: Starting extraction at {time.strftime('%H:%M:%S')}")
        
        # Try both Lattice and Stream methods for better coverage
        methods_to_try = [
            ("stream", {}),  # Try stream first as it's usually faster
            ("lattice", {}),
        ]
        
        best_extraction = None
        best_table_count = 0
        best_method = None
        failed_methods = []
        
        for method_idx, (method, kwargs) in enumerate(methods_to_try):
            try:
                print(f"\nDEBUG: Method {method_idx + 1}/{len(methods_to_try)} - Trying method: {method} with options: {kwargs}")
                print(f"DEBUG: Starting {method} at {time.strftime('%H:%M:%S')}")
                
                # Set up timeout
                signal.signal(signal.SIGALRM, timeout_handler)
                signal.alarm(timeout_seconds)
                
                try:
                    # Extract tables using camelot with timeout-like behavior
                    start_time = time.time()
                    tables = camelot.read_pdf(
                        pdf_path, 
                        pages=pages, 
                        flavor=method,
                        **kwargs
                    )
                    end_time = time.time()
                    
                    # Cancel timeout
                    signal.alarm(0)
                    
                    print(f"DEBUG: {method} completed in {end_time - start_time:.2f} seconds")
                    
                    table_count = len(tables)
                    print(f"Found {table_count} tables with {method} method")
                    
                    if table_count > best_table_count:
                        best_extraction = tables
                        best_table_count = table_count
                        best_method = method
                        print(f"New best method: {method} with {table_count} tables")
                    
                    # Show table quality metrics
                    for i, table in enumerate(tables):
                        try:
                            report = table.parsing_report
                            print(f"  Table {i+1}: Accuracy={report['accuracy']:.1f}%, "
                                  f"Whitespace={report['whitespace']:.1f}%")
                        except Exception as e:
                            print(f"  Table {i+1}: Error getting report - {e}")
                            
                except TimeoutError:
                    signal.alarm(0)  # Cancel alarm
                    print(f"DEBUG: Method {method} timed out after {timeout_seconds} seconds")
                    failed_methods.append(f"{method} (timeout)")
                    continue
                        
            except Exception as e:
                signal.alarm(0)  # Cancel alarm in case of error
                error_msg = str(e)
                print(f"DEBUG: Method {method} failed with error: {error_msg}")
                print(f"DEBUG: Error type: {type(e).__name__}")
                failed_methods.append(f"{method} ({type(e).__name__})")
                
                # Check for specific PDF corruption errors
                if any(keyword in error_msg.lower() for keyword in ['trailer', 'object', 'not defined', 'nonetype']):
                    print(f"DEBUG: PDF appears to be corrupted or has structural issues")
                    # Skip remaining camelot methods and go straight to text extraction
                    break
                continue
        
        print(f"DEBUG: Attempted methods: {', '.join([m for m, _ in methods_to_try])}")
        print(f"DEBUG: Failed methods: {', '.join(failed_methods)}")
        print(f"DEBUG: Best extraction has {best_table_count} tables")
        
        if not best_extraction or best_table_count == 0:
            print("No tables found with any camelot method. Trying text extraction...")
            return extract_text_fallback(pdf_path, output_dir, max_pages)
        
        print(f"\nUsing best method: {best_method} with {best_table_count} tables")
        print(f"DEBUG: Starting to save results at {time.strftime('%H:%M:%S')}")
        
        # Save results
        print(f"DEBUG: Writing to {tables_output_file}")
        
        with open(tables_output_file, 'w', encoding='utf-8') as f:
            f.write(f"PDF: {pdf_path}\n")
            f.write(f"Extraction Method: {best_method}\n")
            f.write(f"Total tables found: {best_table_count}\n")
            f.write(f"Failed methods: {', '.join(failed_methods)}\n")
            f.write(f"Extraction Date: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("="*80 + "\n\n")
            
            for i, table in enumerate(best_extraction):
                print(f"DEBUG: Processing table {i+1}/{best_table_count}")
                try:
                    f.write(f"{'='*60}\n")
                    f.write(f"TABLE {i+1} (Page {table.parsing_report['page']})\n")
                    f.write(f"{'='*60}\n")
                    f.write(f"Shape: {table.shape[0]} rows x {table.shape[1]} columns\n")
                    f.write(f"Accuracy: {table.parsing_report['accuracy']:.2f}%\n")
                    f.write(f"Whitespace: {table.parsing_report['whitespace']:.2f}%\n\n")
                    
                    # Write table data
                    df = table.df
                    f.write(df.to_string(index=False))
                    f.write("\n\n")
                except Exception as e:
                    print(f"DEBUG: Error processing table {i+1}: {e}")
                    f.write(f"Error processing table {i+1}: {e}\n\n")
        
        print(f"DEBUG: File saved successfully at {time.strftime('%H:%M:%S')}")
        print(f"All tables extracted to: {tables_output_file}")
        return True
        
    except Exception as e:
        signal.alarm(0)  # Cancel any pending alarm
        print(f"DEBUG: Camelot extraction failed with error: {e}")
        print(f"DEBUG: Error type: {type(e).__name__}")
        print(f"DEBUG: Falling back to text extraction for {pdf_path}")
        return extract_text_fallback(pdf_path, output_dir, max_pages)

def extract_text_fallback(pdf_path, output_dir, max_pages=None):
    """
    Fallback to basic text extraction if no tables found.
    """
    print("Falling back to basic text extraction...")
    
    try:
        import pymupdf
        
        output_dir = Path(output_dir)
        filename_base = Path(pdf_path).stem
        
        doc = pymupdf.open(pdf_path)
        total_pages = len(doc)
        pages_to_process = min(max_pages, total_pages) if max_pages else total_pages
        
        text_output = output_dir / f"{filename_base}_text.txt"
        with open(text_output, 'w', encoding='utf-8') as f:
            for page_num in range(pages_to_process):
                page = doc[page_num]
                text = page.get_text()
                f.write(f"=== PAGE {page_num + 1} ===\n")
                f.write(text)
                f.write("\n\n" + "="*50 + "\n\n")
        
        doc.close()
        print(f"Text extracted to: {text_output}")
        return True
        
    except Exception as e:
        print(f"Text fallback failed: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="PDF table extraction using Camelot (specialized for tables)")
    parser.add_argument("directory", help="Directory containing PDF files")
    parser.add_argument("-o", "--output", default="output_camelot", help="Output directory (default: output_camelot)")
    parser.add_argument("--max-pages", type=int, help="Maximum pages to process per PDF")
    parser.add_argument("--timeout", type=int, default=120, help="Timeout per method in seconds (default: 120)")
    
    args = parser.parse_args()
    
    pdf_dir = Path(args.directory)
    if not pdf_dir.exists():
        print(f"Error: Directory {pdf_dir} does not exist")
        return 1
    
    pdf_files = list(pdf_dir.glob("*.pdf"))
    if not pdf_files:
        print(f"No PDF files found in {pdf_dir}")
        return 1
    
    print(f"Found {len(pdf_files)} PDF file(s) in {pdf_dir}")
    print("Using Camelot for table extraction (specialized for complex tables)")
    print(f"Using timeout of {args.timeout} seconds per method")
    
    success_count = 0
    for pdf_file in pdf_files:
        print(f"\n{'='*60}")
        print(f"Processing: {pdf_file.name}")
        print(f"DEBUG: Starting file {pdf_file.name} at {time.strftime('%H:%M:%S')}")
        print('='*60)
        
        try:
            if extract_tables_from_pdf(pdf_file, args.output, args.max_pages, args.timeout):
                success_count += 1
                print(f"DEBUG: Successfully completed {pdf_file.name}")
            else:
                print(f"DEBUG: Failed to process {pdf_file.name}")
        except Exception as e:
            print(f"Failed to process {pdf_file.name}: {e}")
            print(f"DEBUG: Exception type: {type(e).__name__}")
    
    print(f"\nProcessing complete! Successfully processed {success_count}/{len(pdf_files)} files.")
    print(f"Check the '{args.output}' directory for results.")
    return 0

if __name__ == "__main__":
    sys.exit(main()) 