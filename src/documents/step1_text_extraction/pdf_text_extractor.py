#!/usr/bin/env python3
"""
Automatic PDF text extraction using multiple techniques based on content type.
Supports text extraction, table extraction, and OCR for images.
"""

import json
from pathlib import Path
from typing import Dict, List, Any
import logging

# PDF processing libraries
try:
    import pdfplumber
    import fitz  # PyMuPDF
    import camelot
    from PIL import Image
    import pytesseract
    import io
except ImportError as e:
    print(f"Missing required library: {e}")
    print("Install with: pip install pdfplumber PyMuPDF camelot-py[cv] pillow pytesseract")
    raise

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class PDFTextExtractor:
    """
    Multi-technique PDF text extractor that adapts based on content type.
    Processes a PDF page by page, combining results from different methods.
    """
    
    def __init__(self, pdf_path: str, contains_tables: bool, 
                 contains_images_of_text: bool, contains_images_of_nontext: bool):
        self.pdf_path = Path(pdf_path)
        self.contains_tables = contains_tables
        self.contains_images_of_text = contains_images_of_text
        self.contains_images_of_nontext = contains_images_of_nontext
        
        if not self.pdf_path.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    def extract_all_pages(self) -> List[Dict[str, Any]]:
        """
        Extracts data from each page of the PDF and returns a list of page objects.
        """
        logger.info(f"Starting page-by-page extraction for: {self.pdf_path}")
        page_results = []
        
        try:
            # Open documents once for efficiency
            with pdfplumber.open(self.pdf_path) as pdf_plumber_doc:
                pymupdf_doc = fitz.open(self.pdf_path)
                
                total_pages = len(pdf_plumber_doc.pages)
                if total_pages == 0:
                    logger.warning("PDF has no pages.")
                    return []
                    
                logger.info(f"Processing {total_pages} pages...")

                for i in range(total_pages):
                    page_num = i + 1
                    plumber_page = pdf_plumber_doc.pages[i]
                    mupdf_page = pymupdf_doc[i]
                    
                    page_data = {
                        "pdf_filename": self.pdf_path.name,
                        "page_number": page_num,
                        "contains_tables": self.contains_tables,
                        "contains_images_of_text": self.contains_images_of_text,
                        "contains_images_of_non_text": self.contains_images_of_nontext,
                        "pymupdf_extraction_text": mupdf_page.get_text() or "",
                        "pdfplumber_extraction_text": plumber_page.extract_text() or "",
                        "tables_extraction_text_csv": "",
                        "ocr_extraction_text": ""
                    }

                    # Extract tables if the flag is set
                    if self.contains_tables:
                        page_data["tables_extraction_text_csv"] = self._extract_tables_for_page(page_num)

                    # Perform OCR if image flags are set
                    if self.contains_images_of_text or self.contains_images_of_nontext:
                        page_data["ocr_extraction_text"] = self._extract_ocr_for_page(mupdf_page)
                    
                    page_results.append(page_data)

                pymupdf_doc.close()
        except Exception as e:
            logger.error(f"Failed during page-by-page extraction: {e}")
            raise
        
        return page_results

    def _extract_tables_for_page(self, page_num: int) -> str:
        """Extracts tables from a single page using Camelot and returns them as CSV strings."""
        page_tables_csv = []
        try:
            # First, try the 'lattice' method which is good for tables with clear grid lines
            tables = camelot.read_pdf(str(self.pdf_path), pages=str(page_num), flavor='lattice')
            
            # If lattice finds no tables, fall back to the 'stream' method
            if not tables:
                tables = camelot.read_pdf(str(self.pdf_path), pages=str(page_num), flavor='stream')
            
            for table in tables:
                page_tables_csv.append(table.df.to_csv(index=False))
        except Exception as e:
            # Camelot can be fragile; log the error but don't crash the entire extraction
            logger.warning(f"Could not extract tables from page {page_num}: {e}")
        
        # Join all found tables on the page with a clear separator
        return "\n\n--- NEW TABLE ---\n\n".join(page_tables_csv)

    def _extract_ocr_for_page(self, mupdf_page: fitz.Page) -> str:
        """Extracts text from images on a single page using Tesseract OCR."""
        page_ocr_text = ""
        try:
            if not mupdf_page.get_images(full=True):
                return ""

            # If images are present, OCR the entire page to maintain text context.
            # Use a 2x zoom factor for better OCR quality.
            mat = fitz.Matrix(2.0, 2.0)
            pix = mupdf_page.get_pixmap(matrix=mat)
            img_data = pix.tobytes("png")
            
            image = Image.open(io.BytesIO(img_data))
            page_ocr_text = pytesseract.image_to_string(image) or ""

            if self.contains_images_of_nontext and page_ocr_text:
                logger.warning(
                    f"Page {mupdf_page.number + 1}: 'contains_images_of_non_text' is True. "
                    "OCR was used as a placeholder; consider vision models for true non-text image analysis."
                )
        except Exception as e:
            logger.warning(f"Could not perform OCR on page {mupdf_page.number + 1}: {e}")
        
        return page_ocr_text


def extract_pdf_text(pdf_file_path: str, 
                     output_path: str,
                     contains_tables: bool = False,
                     contains_images_of_text: bool = False, 
                     contains_images_of_nontext: bool = False) -> List[Dict[str, Any]]:
    """
    Extracts text and data from a PDF page by page and saves it as a JSON array.

    Each item in the array represents a single page and contains the extracted
    text from various methods.

    Args:
        pdf_file_path: Path to the PDF file.
        output_path: Path to save the output JSON file.
        contains_tables: Set to True if the PDF contains tables.
        contains_images_of_text: Set to True if the PDF has images containing text.
        contains_images_of_nontext: Set to True for non-text images (uses OCR as a placeholder).

    Returns:
        A list of dictionaries, where each dictionary is a page's extracted data.
    """
    try:
        extractor = PDFTextExtractor(
            pdf_path=pdf_file_path,
            contains_tables=contains_tables,
            contains_images_of_text=contains_images_of_text,
            contains_images_of_nontext=contains_images_of_nontext
        )
        
        results = extractor.extract_all_pages()
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Extraction complete! Results saved to: {output_path}")
        
        # Print a summary of the extraction
        print("\n=== EXTRACTION SUMMARY ===")
        print(f"PDF File: {pdf_file_path}")
        print(f"Output: {output_path}")
        if results:
            print(f"Total Pages Processed: {len(results)}")
            has_tables = any(p.get("tables_extraction_text_csv") for p in results)
            has_ocr = any(p.get("ocr_extraction_text") for p in results)
            methods = ["pdfplumber", "pymupdf"]
            if has_tables: methods.append("camelot (tables)")
            if has_ocr: methods.append("tesseract (ocr)")
            print(f"Methods Applied: {', '.join(methods)}")
        else:
            print("No pages were processed or found.")
            
        return results

    except Exception as e:
        logger.error(f"A critical error occurred during PDF processing: {e}")
        return [] 