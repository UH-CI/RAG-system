#!/usr/bin/env python3
"""
PDF Table Extraction using Tabula-py
Alternative specialized library for PDF table extraction.
"""

import tabula
import sys
import argparse
from pathlib import Path
import pandas as pd

def extract_tables_with_tabula(pdf_path, output_dir, max_pages=None):
    """
    Extract tables using tabula-py.
    
    Args:
        pdf_path (str): Path to PDF file
        output_dir (str): Output directory  
        max_pages (int): Maximum pages to process
    
    Returns:
        bool: Success status
    """
    try:
        pdf_path = str(pdf_path)
        output_dir = Path(output_dir)
        output_dir.mkdir(exist_ok=True)
        
        # Determine pages to process
        if max_pages:
            pages = list(range(1, max_pages + 1))
        else:
            pages = "all"
        
        print(f"Tabula: Extracting tables from {pdf_path}")
        print(f"Pages: {pages}")
        
        filename_base = Path(pdf_path).stem
        
        # Try different tabula options for better results
        extraction_methods = [
            {"lattice": True, "multiple_tables": True},
            {"stream": True, "multiple_tables": True}, 
            {"lattice": True, "multiple_tables": True, "guess": False},
            {"stream": True, "multiple_tables": True, "guess": False}
        ]
        
        best_tables = []
        best_method = None
        best_count = 0
        
        for i, method in enumerate(extraction_methods):
            try:
                print(f"\nTrying method {i+1}: {method}")
                
                tables = tabula.read_pdf(
                    pdf_path,
                    pages=pages,
                    **method
                )
                
                if isinstance(tables, list):
                    table_count = len(tables)
                else:
                    table_count = 1
                    tables = [tables]
                
                print(f"Found {table_count} tables")
                
                # Check table quality
                non_empty_tables = []
                for j, table in enumerate(tables):
                    if not table.empty and table.shape[0] > 1:
                        non_empty_tables.append(table)
                        print(f"  Table {j+1}: {table.shape} (rows x cols)")
                
                if len(non_empty_tables) > best_count:
                    best_tables = non_empty_tables
                    best_method = method
                    best_count = len(non_empty_tables)
                    print(f"New best method with {best_count} non-empty tables")
                        
            except Exception as e:
                print(f"Method {i+1} failed: {e}")
                continue
        
        if not best_tables:
            print("No tables found with tabula-py")
            return False
        
        print(f"\nUsing best method: {best_method}")
        print(f"Extracting {best_count} tables")
        
        # Save individual tables
        summary_file = output_dir / f"{filename_base}_tabula_summary.txt"
        with open(summary_file, 'w', encoding='utf-8') as f:
            f.write(f"PDF: {pdf_path}\n")
            f.write(f"Method: {best_method}\n")
            f.write(f"Tables found: {best_count}\n\n")
            
            for i, table in enumerate(best_tables):
                # Save CSV
                csv_file = output_dir / f"{filename_base}_tabula_table_{i+1}.csv"
                table.to_csv(csv_file, index=False)
                
                # Add to summary
                f.write(f"{'='*50}\n")
                f.write(f"TABLE {i+1}\n")
                f.write(f"{'='*50}\n")
                f.write(f"Shape: {table.shape}\n")
                f.write(f"Saved to: {csv_file.name}\n\n")
                f.write("Sample data (first 10 rows):\n")
                f.write("-" * 30 + "\n")
                f.write(table.head(10).to_string(index=False))
                f.write("\n\n")
        
        print(f"Results saved to: {output_dir}")
        print(f"Summary: {summary_file}")
        return True
        
    except Exception as e:
        print(f"Tabula extraction failed: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="PDF table extraction using Tabula-py")
    parser.add_argument("directory", help="Directory containing PDF files")
    parser.add_argument("-o", "--output", default="output_tabula", help="Output directory")
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
    
    print(f"Found {len(pdf_files)} PDF file(s)")
    print("Using Tabula-py for table extraction")
    
    success_count = 0
    for pdf_file in pdf_files:
        print(f"\n{'='*60}")
        print(f"Processing: {pdf_file.name}")
        print('='*60)
        
        try:
            if extract_tables_with_tabula(pdf_file, args.output, args.max_pages):
                success_count += 1
        except Exception as e:
            print(f"Failed to process {pdf_file.name}: {e}")
    
    print(f"\nProcessing complete! Successfully processed {success_count}/{len(pdf_files)} files.")
    return 0

if __name__ == "__main__":
    sys.exit(main()) 