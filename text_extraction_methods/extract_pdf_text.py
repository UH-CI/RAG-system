#!/usr/bin/env python3
"""
PDF Text Extraction Script
Extracts text from all pages of all PDF files in a given directory using pdfplumber.
"""

import pdfplumber
import sys
import argparse
from pathlib import Path

def extract_text_from_pdf(pdf_path, max_pages=None):
    """
    Extract text from all pages of a PDF file.
    
    Args:
        pdf_path (str): Path to the PDF file
        max_pages (int): Maximum number of pages to extract (default: None for all pages)
    
    Returns:
        dict: Dictionary with page numbers as keys and extracted text as values
    """
    extracted_text = {}
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            total_pages = len(pdf.pages)
            pages_to_extract = total_pages if max_pages is None else min(max_pages, total_pages)
            
            print(f"PDF opened successfully. Total pages: {total_pages}")
            print(f"Extracting text from all {pages_to_extract} pages...\n")
            
            for i in range(pages_to_extract):
                page = pdf.pages[i]
                page_num = i + 1
                
                print(f"Processing page {page_num}/{pages_to_extract}...", end=" ")
                
                # Extract text from the page
                text = page.extract_text()
                
                if text:
                    extracted_text[page_num] = text
                    print(f"✓ ({len(text)} characters)")
                else:
                    extracted_text[page_num] = ""
                    print("✗ (No text found)")
    
    except FileNotFoundError:
        print(f"Error: PDF file not found at {pdf_path}")
        return None
    except Exception as e:
        print(f"Error processing PDF: {str(e)}")
        return None
    
    return extracted_text

def save_extracted_text(extracted_text, output_file):
    """Save the extracted text to a file."""
    try:
        # Create output directory if it doesn't exist
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            for page_num, text in extracted_text.items():
                f.write(f"=== PAGE {page_num} ===\n")
                f.write(text)
                f.write(f"\n\n{'='*50}\n\n")
        
        print(f"✓ Extracted text saved to: {output_file}")
    except Exception as e:
        print(f"✗ Error saving text: {str(e)}")

def process_directory(directory_path, output_dir="output"):
    """
    Process all PDF files in a directory.
    
    Args:
        directory_path (str): Path to the directory containing PDF files
        output_dir (str): Directory to save output text files
    """
    directory = Path(directory_path)
    
    if not directory.exists():
        print(f"Error: Directory not found at {directory_path}")
        return
    
    if not directory.is_dir():
        print(f"Error: {directory_path} is not a directory")
        return
    
    # Find all PDF files in the directory
    pdf_files = list(directory.glob("*.pdf"))
    
    if not pdf_files:
        print(f"No PDF files found in {directory_path}")
        return
    
    print(f"Found {len(pdf_files)} PDF file(s) in {directory_path}:")
    for pdf_file in pdf_files:
        print(f"  - {pdf_file.name}")
    print()
    
    # Process each PDF file
    for pdf_file in pdf_files:
        print(f"{'='*60}")
        print(f"Processing: {pdf_file.name}")
        print(f"{'='*60}")
        
        # Extract text from all pages
        extracted_text = extract_text_from_pdf(str(pdf_file))
        
        if extracted_text:
            # Create output filename
            output_filename = f"{pdf_file.stem}.txt"
            output_path = Path(output_dir) / output_filename
            
            # Save to file
            save_extracted_text(extracted_text, str(output_path))
            
            # Print summary
            total_chars = sum(len(text) for text in extracted_text.values())
            print(f"\nSummary for {pdf_file.name}:")
            print(f"- Total pages processed: {len(extracted_text)}")
            print(f"- Total characters extracted: {total_chars:,}")
            print(f"- Average characters per page: {total_chars // len(extracted_text) if extracted_text else 0:,}")
        else:
            print(f"✗ Failed to extract text from {pdf_file.name}")
        
        print("\n")

def main():
    parser = argparse.ArgumentParser(
        description="Extract text from all PDF files in a directory",
        epilog="Example: python extract_pdf_text.py src/documents"
    )
    parser.add_argument(
        "directory",
        help="Directory containing PDF files to process"
    )
    parser.add_argument(
        "-o", "--output",
        default="output",
        help="Output directory for text files (default: output)"
    )
    
    args = parser.parse_args()
    
    print(f"PDF Text Extraction Tool")
    print(f"Input directory: {args.directory}")
    print(f"Output directory: {args.output}")
    print("-" * 50)
    
    process_directory(args.directory, args.output)
    
    print("Processing complete!")

if __name__ == "__main__":
    main() 