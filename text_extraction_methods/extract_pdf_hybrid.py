#!/usr/bin/env python3
"""
Hybrid PDF Extraction: pdfplumber for text pages, Camelot for table pages
Automatically detects which pages contain tables and uses the optimal extraction method.
"""

import pdfplumber
import camelot
import sys
import argparse
import re
from pathlib import Path
import pandas as pd

def fix_decimal_points(text):
    """
    Post-process text to fix missing decimal points in financial data.
    """
    # Apply the same decimal point corrections as before
    def fix_position_line(match):
        decimal_part = match.group(1)
        asterisks = match.group(2)
        integer_part = match.group(3)
        
        if len(integer_part) == 4 and integer_part.endswith('00'):
            corrected = f"{integer_part[:-2]}.00"
        elif len(integer_part) == 3 and integer_part.endswith('00'):
            corrected = f"{integer_part[:-2]}.00"
        else:
            corrected = integer_part
            
        return f"{decimal_part} {asterisks} {corrected}"
    
    text = re.sub(r'(\d+\.\d{2})\s+(\*+)\s+(\d{3,4})\b', fix_position_line, text)
    
    replacements = {
        r'\b1000\b(?=\s*\*?\s*$|\s*\*?\s+[A-Z])': '10.00',
        r'\b1500\b(?=\s*\*?\s*$|\s*\*?\s+[A-Z])': '15.00', 
        r'\b2700\b(?=\s*\*?\s*$|\s*\*?\s+[A-Z])': '27.00',
        r'\b3200\b(?=\s*\*?\s*$|\s*\*?\s+[A-Z])': '32.00',
        r'\b1400\b(?=\s*\*?\s*$|\s*\*?\s+[A-Z])': '14.00',
        r'\b1600\b(?=\s*\*?\s*$|\s*\*?\s+[A-Z])': '16.00',
        r'\b2500\b(?=\s*\*?\s*$|\s*\*?\s+[A-Z])': '25.00',
        r'\b900\b(?=\s*\*?\s*$|\s*\*?\s+[A-Z])': '9.00',
    }
    
    for pattern, replacement in replacements.items():
        text = re.sub(pattern, replacement, text)
    
    # Add commas to large financial numbers
    def add_commas_to_large_numbers(match):
        number = match.group(1)
        if len(number) >= 6:
            try:
                formatted = f"{int(number):,}"
                return formatted
            except ValueError:
                return number
        return number
    
    text = re.sub(r'\b(\d{6,})\b', add_commas_to_large_numbers, text)
    return text

def detect_tables_in_page(pdf_path, page_num):
    """
    Detect if a page contains tables based on numerical content density.
    Uses Camelot to extract content first, then analyzes numerical density.
    
    Args:
        pdf_path (str): Path to PDF file
        page_num (int): Page number (1-indexed)
    
    Returns:
        dict: Detection results with confidence scores
    """
    detection_results = {
        'has_tables': False,
        'confidence': 0.0,
        'method_used': 'none',
        'table_count_estimate': 0,
        'detection_details': {}
    }
    
    try:
        # First try Camelot extraction
        camelot_text = ""
        camelot_tables = []
        
        try:
            # Try lattice method first (more accurate for bordered tables)
            tables = camelot.read_pdf(pdf_path, pages=str(page_num), flavor='lattice')
            if len(tables) > 0:
                camelot_tables = tables
                for table in tables:
                    df = table.df
                    camelot_text += df.to_string(index=False, header=False) + "\n\n"
        except:
            pass
        
        # If lattice didn't find tables, try stream method
        if not camelot_tables:
            try:
                tables = camelot.read_pdf(pdf_path, pages=str(page_num), flavor='stream')
                if len(tables) > 0:
                    camelot_tables = tables
                    for table in tables:
                        df = table.df
                        camelot_text += df.to_string(index=False, header=False) + "\n\n"
            except:
                pass
        
        # Fallback to pdfplumber if Camelot finds nothing
        if not camelot_text.strip():
            with pdfplumber.open(pdf_path) as pdf:
                if page_num <= len(pdf.pages):
                    page = pdf.pages[page_num - 1]
                    text = page.extract_text()
                    detection_results['detection_details']['extraction_method'] = 'pdfplumber_fallback'
                else:
                    detection_results['method_used'] = 'page_not_found'
                    return detection_results
        else:
            text = camelot_text
            detection_results['detection_details']['extraction_method'] = 'camelot'
            detection_results['detection_details']['camelot_tables_found'] = len(camelot_tables)
            detection_results['detection_details']['camelot_accuracies'] = [table.accuracy for table in camelot_tables] if camelot_tables else []
        
        if text:
            lines = [line.strip() for line in text.split('\n') if line.strip()]
            total_lines = len(lines)
            
            if total_lines < 5:  # Too little content to analyze
                detection_results['method_used'] = 'insufficient_content'
                return detection_results
            
            # Count lines with significant numerical content
            numeric_indicators = {
                'decimal_numbers': 0,      # Lines with decimal numbers (12.34)
                'comma_numbers': 0,        # Lines with comma-separated numbers (1,234)
                'multiple_numbers': 0,     # Lines with 3+ numbers
                'financial_patterns': 0,   # Lines with financial patterns (*, $, etc.)
                'total_numbers': 0         # Total count of all numbers found
            }
            
            for line in lines:
                # Find decimal numbers (like 12.34, 1.00, 15.00)
                decimal_matches = re.findall(r'\b\d+\.\d{2}\b', line)
                if decimal_matches:
                    numeric_indicators['decimal_numbers'] += 1
                    numeric_indicators['total_numbers'] += len(decimal_matches)
                
                # Find comma-separated numbers (like 1,234 or 1,234,567)
                comma_matches = re.findall(r'\b\d{1,3}(?:,\d{3})+\b', line)
                if comma_matches:
                    numeric_indicators['comma_numbers'] += 1
                    numeric_indicators['total_numbers'] += len(comma_matches)
                
                # Find lines with multiple numbers (3 or more)
                all_numbers = re.findall(r'\b\d+(?:[,\.]\d+)*\b', line)
                if len(all_numbers) >= 3:
                    numeric_indicators['multiple_numbers'] += 1
                
                # Find financial patterns (asterisks with numbers, dollar signs)
                if re.search(r'\d+\.\d{2}\s*\*|\$\s*\d+|Position|Fund|Account', line, re.IGNORECASE):
                    numeric_indicators['financial_patterns'] += 1
            
            # Calculate ratios
            decimal_ratio = numeric_indicators['decimal_numbers'] / total_lines
            comma_ratio = numeric_indicators['comma_numbers'] / total_lines
            multiple_number_ratio = numeric_indicators['multiple_numbers'] / total_lines
            financial_ratio = numeric_indicators['financial_patterns'] / total_lines
            
            # Calculate overall numerical density
            numerical_density = numeric_indicators['total_numbers'] / total_lines
            
            detection_results['detection_details']['numerical_analysis'] = {
                'total_lines': total_lines,
                **numeric_indicators,
                'decimal_ratio': decimal_ratio,
                'comma_ratio': comma_ratio,
                'multiple_number_ratio': multiple_number_ratio,
                'financial_ratio': financial_ratio,
                'numerical_density': numerical_density
            }
            
            # Simple, effective decision logic
            confidence = 0.0
            
            # Strong indicators of table content
            if decimal_ratio > 0.3:  # >30% of lines have decimal numbers
                confidence += 0.4
            elif decimal_ratio > 0.15:  # >15% of lines have decimal numbers
                confidence += 0.2
            
            if comma_ratio > 0.2:  # >20% of lines have comma numbers
                confidence += 0.3
            elif comma_ratio > 0.1:  # >10% of lines have comma numbers
                confidence += 0.15
            
            if multiple_number_ratio > 0.4:  # >40% of lines have 3+ numbers
                confidence += 0.3
            elif multiple_number_ratio > 0.2:  # >20% of lines have 3+ numbers
                confidence += 0.15
            
            if numerical_density > 2.0:  # Average >2 numbers per line
                confidence += 0.2
            elif numerical_density > 1.0:  # Average >1 number per line
                confidence += 0.1
            
            if financial_ratio > 0.1:  # >10% financial patterns
                confidence += 0.1
            
            # Final decision
            detection_results['confidence'] = min(confidence, 1.0)  # Cap at 1.0
            
            if confidence >= 0.5:  # Clear numerical content
                detection_results['has_tables'] = True
                detection_results['method_used'] = 'numerical_density_high'
                # Estimate table count based on content density
                detection_results['table_count_estimate'] = max(1, int(numerical_density))
            elif confidence >= 0.3:  # Moderate numerical content
                detection_results['has_tables'] = True
                detection_results['method_used'] = 'numerical_density_moderate'
                detection_results['table_count_estimate'] = 1
            else:  # Primarily text content
                detection_results['has_tables'] = False
                detection_results['method_used'] = 'text_content'
                
        else:
            detection_results['method_used'] = 'no_text_extracted'
                
    except Exception as e:
        detection_results['detection_details']['error'] = str(e)
        detection_results['method_used'] = 'extraction_error'
    
    return detection_results

def extract_page_with_camelot(pdf_path, page_num, output_file):
    """Extract a page using Camelot (for table pages)."""
    try:
        print(f"  Using Camelot for page {page_num} (table detected)")
        
        # Try both methods and use the best result
        methods = [
            ('lattice', {'split_text': True, 'flag_size': True}),
            ('stream', {'split_text': True, 'flag_size': True})
        ]
        
        best_tables = None
        best_count = 0
        best_method = None
        
        for method, kwargs in methods:
            try:
                tables = camelot.read_pdf(pdf_path, pages=str(page_num), flavor=method, **kwargs)
                if len(tables) > best_count:
                    best_tables = tables
                    best_count = len(tables)
                    best_method = method
            except Exception as e:
                continue
        
        if best_tables:
            output_file.write(f"{'='*60}\n")
            output_file.write(f"PAGE {page_num} - CAMELOT EXTRACTION ({best_method})\n")
            output_file.write(f"{'='*60}\n")
            output_file.write(f"Tables found: {best_count}\n\n")
            
            for i, table in enumerate(best_tables):
                output_file.write(f"--- TABLE {i+1} ---\n")
                output_file.write(f"Shape: {table.shape[0]} rows x {table.shape[1]} columns\n")
                output_file.write(f"Accuracy: {table.parsing_report['accuracy']:.1f}%\n\n")
                
                try:
                    df = table.df
                    table_text = df.to_string(index=False)
                    corrected_text = fix_decimal_points(table_text)
                    output_file.write(corrected_text)
                    output_file.write("\n\n")
                except Exception as e:
                    output_file.write(f"Error processing table: {e}\n\n")
            
            return True
        else:
            # Fallback to pdfplumber if camelot fails
            return extract_page_with_pdfplumber(pdf_path, page_num, output_file, fallback=True)
            
    except Exception as e:
        print(f"    Camelot failed for page {page_num}: {e}")
        return extract_page_with_pdfplumber(pdf_path, page_num, output_file, fallback=True)

def extract_page_with_pdfplumber(pdf_path, page_num, output_file, fallback=False):
    """Extract a page using pdfplumber (for text pages)."""
    try:
        method_name = "pdfplumber (fallback)" if fallback else "pdfplumber"
        print(f"  Using {method_name} for page {page_num}")
        
        with pdfplumber.open(pdf_path) as pdf:
            if page_num <= len(pdf.pages):
                page = pdf.pages[page_num - 1]
                
                output_file.write(f"{'='*60}\n")
                output_file.write(f"PAGE {page_num} - PDFPLUMBER EXTRACTION\n")
                output_file.write(f"{'='*60}\n")
                
                # Extract text
                text = page.extract_text()
                if text:
                    corrected_text = fix_decimal_points(text)
                    output_file.write(corrected_text)
                    output_file.write("\n\n")
                else:
                    output_file.write("No text content found.\n\n")
                
                return True
            else:
                output_file.write(f"Page {page_num} not found in PDF.\n\n")
                return False
                
    except Exception as e:
        print(f"    pdfplumber failed for page {page_num}: {e}")
        output_file.write(f"Error extracting page {page_num}: {e}\n\n")
        return False

def extract_hybrid(pdf_path, output_dir, max_pages=None):
    """
    Hybrid extraction: detect tables per page and use appropriate method.
    """
    try:
        pdf_path = str(pdf_path)
        output_dir = Path(output_dir)
        output_dir.mkdir(exist_ok=True)
        
        filename_base = Path(pdf_path).stem
        output_file_path = output_dir / f"{filename_base}_hybrid_extraction.txt"
        
        # Get total pages
        with pdfplumber.open(pdf_path) as pdf:
            total_pages = len(pdf.pages)
        
        pages_to_process = min(max_pages, total_pages) if max_pages else total_pages
        
        print(f"Hybrid extraction from {pdf_path}")
        print(f"Processing {pages_to_process} of {total_pages} pages")
        
        # Phase 1: Detect tables in all pages
        print("\nPhase 1: Detecting tables in each page...")
        page_analysis = {}
        
        for page_num in range(1, pages_to_process + 1):
            print(f"  Analyzing page {page_num}...")
            detection = detect_tables_in_page(pdf_path, page_num)
            page_analysis[page_num] = detection
            
            status = "TABLE" if detection['has_tables'] else "TEXT"
            confidence = detection['confidence']
            method = detection['method_used']
            
            print(f"    Result: {status} (confidence: {confidence:.1f}, method: {method})")
        
        # Phase 2: Extract using appropriate method
        print(f"\nPhase 2: Extracting content...")
        
        with open(output_file_path, 'w', encoding='utf-8') as f:
            f.write(f"PDF: {pdf_path}\n")
            f.write(f"Method: Hybrid (pdfplumber + Camelot)\n")
            f.write(f"Pages processed: {pages_to_process}\n")
            f.write(f"Decimal point correction: Applied\n")
            f.write("="*80 + "\n\n")
            
            # Write analysis summary
            f.write("PAGE ANALYSIS SUMMARY:\n")
            f.write("-" * 40 + "\n")
            table_pages = []
            text_pages = []
            
            for page_num, analysis in page_analysis.items():
                page_type = "TABLE" if analysis['has_tables'] else "TEXT"
                f.write(f"Page {page_num:2d}: {page_type:5s} (confidence: {analysis['confidence']:.1f}, method: {analysis['method_used']})\n")
                
                if analysis['has_tables']:
                    table_pages.append(page_num)
                else:
                    text_pages.append(page_num)
            
            f.write(f"\nTable pages: {len(table_pages)} - {table_pages}\n")
            f.write(f"Text pages:  {len(text_pages)} - {text_pages}\n")
            f.write("="*80 + "\n\n")
            
            # Extract each page
            success_count = 0
            for page_num in range(1, pages_to_process + 1):
                analysis = page_analysis[page_num]
                
                if analysis['has_tables']:
                    success = extract_page_with_camelot(pdf_path, page_num, f)
                else:
                    success = extract_page_with_pdfplumber(pdf_path, page_num, f)
                
                if success:
                    success_count += 1
        
        print(f"\nHybrid extraction completed!")
        print(f"Successfully processed {success_count}/{pages_to_process} pages")
        print(f"Output saved to: {output_file_path}")
        print(f"Table pages: {len(table_pages)}, Text pages: {len(text_pages)}")
        
        return True
        
    except Exception as e:
        print(f"Hybrid extraction failed: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Hybrid PDF extraction: pdfplumber for text, Camelot for tables")
    parser.add_argument("directory", help="Directory containing PDF files")
    parser.add_argument("-o", "--output", default="output_hybrid", help="Output directory")
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
    print("Using hybrid extraction: pdfplumber for text pages, Camelot for table pages")
    
    success_count = 0
    
    for pdf_file in pdf_files:
        print(f"\n{'='*80}")
        print(f"Processing: {pdf_file.name}")
        print('='*80)
        
        try:
            if extract_hybrid(pdf_file, args.output, args.max_pages):
                success_count += 1
        except Exception as e:
            print(f"Failed to process {pdf_file.name}: {e}")
    
    print(f"\nProcessing complete! Successfully processed {success_count}/{len(pdf_files)} files.")
    print(f"Check the '{args.output}' directory for results.")
    return 0

if __name__ == "__main__":
    sys.exit(main()) 