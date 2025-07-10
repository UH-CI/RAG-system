#!/usr/bin/env python3
"""
Enhanced PDF Text Extraction Script using PyMuPDF
Handles rotated tables and content automatically.
"""

import pymupdf  # PyMuPDF
import sys
import argparse
from pathlib import Path

def extract_text_from_pdf(pdf_path, max_pages=None):
    """
    Extract text from PDF using PyMuPDF which handles rotation automatically.
    
    Args:
        pdf_path (str): Path to PDF file
        max_pages (int): Maximum pages to extract (None for all)
    
    Returns:
        dict: Extracted text by page
    """
    extracted_text = {}
    
    try:
        doc = pymupdf.open(pdf_path)
        total_pages = len(doc)
        pages_to_process = min(max_pages, total_pages) if max_pages else total_pages
        
        print(f"PyMuPDF: Processing {pages_to_process} of {total_pages} pages...")
        
        for page_num in range(pages_to_process):
            page = doc[page_num]
            
            # PyMuPDF automatically handles rotation
            # Try to find tables first
            try:
                tables = page.find_tables()
                table_list = list(tables)  # Convert to list to get length
                page_text = []
                
                if table_list:
                    print(f"Found {len(table_list)} table(s) on page {page_num + 1}")
                    for i, table in enumerate(table_list):
                        page_text.append(f"=== TABLE {i + 1} ===")
                        try:
                            table_data = table.extract()
                            for row in table_data:
                                if row:  # Skip empty rows
                                    # Join non-None cells with tabs
                                    row_text = "\t".join([str(cell) if cell else "" for cell in row])
                                    page_text.append(row_text)
                        except Exception as table_error:
                            page_text.append(f"Error extracting table {i + 1}: {table_error}")
                        page_text.append("")  # Empty line after table
                
            except Exception as e:
                print(f"Table detection failed on page {page_num + 1}: {e}")
                page_text = []
            
            # Extract all text content
            text = page.get_text()
            if text.strip():
                if page_text:  # If we found tables, add a separator
                    page_text.append("=== TEXT CONTENT ===")
                page_text.append(text)
            
            # If no tables were found, just use the text
            if not page_text:
                page_text = [text] if text.strip() else ["No text content found"]
            
            extracted_text[page_num + 1] = "\n".join(page_text)
            print(f"PyMuPDF: Processed page {page_num + 1}")
        
        doc.close()
        
    except Exception as e:
        print(f"PyMuPDF extraction failed: {e}")
    
    return extracted_text

def save_results(extracted_text, output_dir, filename_base):
    """
    Save extracted text to files.
    
    Args:
        extracted_text (dict): Extracted text data
        output_dir (Path): Output directory
        filename_base (str): Base filename
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True)
    
    output_file = output_dir / f"{filename_base}.txt"
    with open(output_file, 'w', encoding='utf-8') as f:
        for page_num in sorted(extracted_text.keys()):
            f.write(f"=== PAGE {page_num} ===\n")
            f.write(extracted_text[page_num])
            f.write("\n\n" + "="*50 + "\n\n")
    
    print(f"Saved results to: {output_file}")

def main():
    parser = argparse.ArgumentParser(description="PDF text extraction using PyMuPDF (handles rotated content)")
    parser.add_argument("directory", help="Directory containing PDF files")
    parser.add_argument("-o", "--output", default="output_enhanced", help="Output directory (default: output_enhanced)")
    parser.add_argument("--max-pages", type=int, help="Maximum pages to process per PDF")
    
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
    print("Using PyMuPDF for extraction (handles rotated content automatically)")
    
    for pdf_file in pdf_files:
        print(f"\n{'='*60}")
        print(f"Processing: {pdf_file.name}")
        print('='*60)
        
        try:
            extracted_text = extract_text_from_pdf(str(pdf_file), args.max_pages)
            
            filename_base = pdf_file.stem
            save_results(extracted_text, args.output, filename_base)
            
        except Exception as e:
            print(f"Failed to process {pdf_file.name}: {e}")
    
    print(f"\nExtraction complete! Check the '{args.output}' directory for results.")
    return 0

if __name__ == "__main__":
    sys.exit(main()) 