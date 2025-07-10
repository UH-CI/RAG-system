#!/usr/bin/env python3
"""
Gemini Text Cleaner - Small version for testing on first 10 pages
"""

import os
import json
import time
import re
from typing import List, Dict, Optional
from dotenv import load_dotenv
import google.generativeai as genai

class GeminiTextCleanerSmall:
    def __init__(self, api_key: str):
        """Initialize the Gemini text cleaner with Google AI API key."""
        self.api_key = api_key
        self.model = None
        self.initialize_gemini()
    
    def initialize_gemini(self) -> None:
        """Initialize the Gemini model using Google AI API."""
        try:
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel('gemini-1.5-flash')
            print("✅ Successfully initialized Gemini API")
        except Exception as e:
            print(f"❌ Error initializing Gemini: {e}")
            raise

    def extract_first_n_pages(self, text: str, n: int = 10) -> str:
        """Extract just the first N pages from the text."""
        
        # Find all page markers
        page_pattern = r'============================================================\nPAGE (\d+) - (PDFPLUMBER|CAMELOT) EXTRACTION[^\n]*\n============================================================'
        
        pages = []
        matches = list(re.finditer(page_pattern, text))
        
        for i, match in enumerate(matches):
            page_num = int(match.group(1))
            if page_num > n:
                break
                
            # Get content between this page and the next
            start_pos = match.end()
            if i + 1 < len(matches):
                end_pos = matches[i + 1].start()
                page_content = text[start_pos:end_pos].strip()
            else:
                # Last page
                page_content = text[start_pos:].strip()
            
            if page_content:
                pages.append(f"=== PAGE {page_num} ===\n{page_content}")
        
        return "\n\n".join(pages)

    def clean_and_structure_text(self, text_chunk: str) -> Dict:
        """Use Gemini to clean and structure a chunk of budget text."""
        
        prompt = """You are analyzing pages from a legislative budget document (HB300). 

Your task is to:
1. Clean up the formatting and remove extraction artifacts
2. Extract any structured budget information you find
3. Identify departments, programs, and financial details
4. Return clean, organized data

For any budget items you find, extract:
- Department/Agency name
- Program name and ID
- Dollar amounts (with proper formatting)
- Position counts (FTE)
- Fund types (A=General Fund, B=Special Fund, etc.)
- Appropriation type (Operating, Capital, etc.)

Return a JSON object with this structure:
{
  "cleaned_text": "Clean, readable version of the text content",
  "budget_items": [
    {
      "department": "Department name",
      "program": "Program name", 
      "program_id": "Program ID (e.g., BED100)",
      "amount": 1234567,
      "amount_formatted": "$1,234,567",
      "fund_type": "General Fund",
      "fund_code": "A",
      "positions": 25.5,
      "appropriation_type": "Operating",
      "fiscal_year": "2025-2026"
    }
  ],
  "summary": {
    "total_items": 5,
    "total_amount": 12345678,
    "departments": ["Dept 1", "Dept 2"]
  }
}

Important:
- Fix formatting issues like missing spaces, broken words
- Convert fund codes to readable names (A=General Fund, B=Special Fund, etc.)
- Preserve exact dollar amounts and position counts
- Clean up table formatting but keep the financial data accurate
- If text is mostly legislative language without budget data, focus on cleaning the text
- For early pages that are mostly definitions/introductory text, just clean the formatting

Here's the text to process:

""" + text_chunk

        try:
            response = self.model.generate_content(prompt)
            
            if response and hasattr(response, 'text'):
                response_text = response.text.strip()
                
                # Clean JSON from markdown formatting
                if '```json' in response_text:
                    response_text = response_text.split('```json')[1].split('```')[0]
                elif '```' in response_text:
                    response_text = response_text.split('```')[1].split('```')[0]
                
                try:
                    result = json.loads(response_text)
                    return result
                except json.JSONDecodeError as e:
                    print(f"⚠️  JSON decode error: {e}")
                    print(f"Raw response: {response_text[:500]}...")
                    
                    # Try to extract JSON manually if it's malformed
                    try:
                        # Look for the actual JSON structure in the response
                        if response_text.startswith('{') and '"budget_items"' in response_text:
                            # Try to find the end of the JSON
                            brace_count = 0
                            json_end = 0
                            for i, char in enumerate(response_text):
                                if char == '{':
                                    brace_count += 1
                                elif char == '}':
                                    brace_count -= 1
                                    if brace_count == 0:
                                        json_end = i + 1
                                        break
                            
                            if json_end > 0:
                                clean_json = response_text[:json_end]
                                result = json.loads(clean_json)
                                return result
                    except:
                        pass
                    
                    # Return a basic structure with just cleaned text
                    return {
                        "cleaned_text": response_text,
                        "budget_items": [],
                        "summary": {"total_items": 0, "total_amount": 0, "departments": []}
                    }
            else:
                print("⚠️  No response from Gemini")
                return None
                
        except Exception as e:
            print(f"❌ Error processing with Gemini: {e}")
            return None

    def process_file(self, input_file: str, output_dir: str, num_pages: int = 10) -> Dict:
        """Process first N pages of a text file and return cleaned results."""
        
        print(f"\n🔄 Processing first {num_pages} pages of: {os.path.basename(input_file)}")
        
        # Read the input file
        try:
            with open(input_file, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            print(f"❌ Error reading file: {e}")
            return {}
        
        print(f"📄 Full file size: {len(content):,} characters")
        
        # Extract first N pages
        first_pages_content = self.extract_first_n_pages(content, num_pages)
        print(f"📑 Extracted first {num_pages} pages: {len(first_pages_content):,} characters")
        
        if not first_pages_content:
            print("❌ No content extracted from first pages")
            return {}
        
        # Process the content
        print(f"🤖 Processing with Gemini...")
        result = self.clean_and_structure_text(first_pages_content)
        
        if not result:
            print("❌ No result from Gemini processing")
            return {}
        
        # Compile final results
        final_result = {
            "source_file": os.path.basename(input_file),
            "pages_processed": num_pages,
            "cleaned_text": result.get('cleaned_text', ''),
            "budget_items": result.get('budget_items', []),
            "summary": result.get('summary', {"total_items": 0, "total_amount": 0, "departments": []})
        }
        
        # Save results
        base_name = os.path.splitext(os.path.basename(input_file))[0]
        
        # Save cleaned text
        cleaned_text_file = os.path.join(output_dir, f"{base_name}_first_{num_pages}_pages_cleaned.txt")
        with open(cleaned_text_file, 'w', encoding='utf-8') as f:
            f.write(final_result['cleaned_text'])
        
        # Save structured data
        json_file = os.path.join(output_dir, f"{base_name}_first_{num_pages}_pages_structured.json")
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(final_result, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Completed processing")
        print(f"   📊 Extracted {len(final_result['budget_items'])} budget items")
        print(f"   🏛️  Found {len(final_result['summary']['departments'])} departments")
        print(f"   💰 Total amount: ${final_result['summary']['total_amount']:,.2f}")
        print(f"   📁 Saved to: {json_file}")
        print(f"   📄 Cleaned text: {cleaned_text_file}")
        
        return final_result

def main():
    """Main function to process text files."""
    
    # Load environment variables
    load_dotenv()
    
    # Get API key
    api_key = os.getenv('GOOGLE_API_KEY')
    if not api_key:
        print("❌ GOOGLE_API_KEY not found in environment variables")
        print("💡 Add it to your .env file: GOOGLE_API_KEY=your_api_key_here")
        return
    
    # Set up directories
    output_dir = "cleaned_output"
    os.makedirs(output_dir, exist_ok=True)
    
    # Initialize cleaner
    cleaner = GeminiTextCleanerSmall(api_key)
    
    # Process files
    import sys
    if len(sys.argv) > 1:
        # Process specific file
        input_file = sys.argv[1]
        if not os.path.exists(input_file):
            print(f"❌ File not found: {input_file}")
            return
        
        # Get number of pages (default 10)
        num_pages = 10
        if len(sys.argv) > 2:
            try:
                num_pages = int(sys.argv[2])
            except ValueError:
                print(f"⚠️  Invalid page number '{sys.argv[2]}', using default of 10")
        
        cleaner.process_file(input_file, output_dir, num_pages)
    else:
        print("❌ Please provide a file to process")
        print("Usage: python gemini_text_cleaner_small.py <file_path> [num_pages]")

if __name__ == "__main__":
    print("🧹 Gemini Text Cleaner - Small Version (First N Pages)")
    print("=" * 60)
    main() 