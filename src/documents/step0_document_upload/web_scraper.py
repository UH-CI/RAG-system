def ai_crawler(start_url, extraction_prompt, collection_name, num_workers, num_levels_deep, google_api_key=None, null_is_okay=True):
    """
    AI-powered web crawler that visits URLs, extracts structured data using Gemini-1.5-lite,
    and saves results to a JSON file in the storage_documents collection folder.
    
    Args:
        start_url (str): The starting URL to begin crawling
        extraction_prompt (str): Prompt for the LLM describing what data to extract
        collection_name (str): Name of the collection folder where data will be saved
        num_workers (int): Number of parallel workers for processing pages
        num_levels_deep (int): Maximum depth to traverse web links
        google_api_key (str): Google API key for Gemini models (or use GOOGLE_API_KEY env var)
        null_is_okay (bool): If False, filters out items with null values
        
    Returns:
        list: List of all extracted data items
    """
    from urllib.parse import urlparse, urljoin
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.chrome.options import Options
    from bs4 import BeautifulSoup
    import time
    import json
    import os
    import pathlib
    from pathlib import Path
    import google.generativeai as genai
    import concurrent.futures
    import threading
    import html2text
    from pdfminer.high_level import extract_text
    from pdfminer.pdfpage import PDFPage
    from pdfminer.pdfinterp import PDFResourceManager, PDFPageInterpreter
    from pdfminer.converter import TextConverter
    from pdfminer.layout import LAParams
    from io import StringIO
    import requests
    import queue
    import atexit
    
    # Initialize Google Gemini client
    if not google_api_key:
        google_api_key = os.environ.get("GOOGLE_API_KEY")
    
    if not google_api_key:
        raise ValueError("Google API key must be provided either directly or via GOOGLE_API_KEY environment variable")
    
    # Extract the base URL for comparison
    parsed_url = urlparse(start_url)
    base_url = f"{parsed_url.scheme}://{parsed_url.netloc}/"
    print(f"\n=== AI CRAWLER STARTING ===")
    print(f"Starting URL: {start_url}")
    print(f"Base URL for filtering: {base_url}")
    print(f"Number of workers: {num_workers}")
    print(f"Max depth: {num_levels_deep}")
    
    # Set up storage directory
    base_dir = Path(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    storage_dir = base_dir / 'storage_documents' / collection_name
    storage_dir.mkdir(parents=True, exist_ok=True)
    output_file = storage_dir / f"web_scrape_{int(time.time())}.json"
    
    print(f"Output will be saved to: {output_file}")
    
    # Thread-safe data structures
    visited_lock = threading.Lock()
    data_lock = threading.Lock()
    
    visited = set()
    all_extracted_data = []
    
    # Initialize HTML to text converter
    h = html2text.HTML2Text()
    h.ignore_links = False
    h.ignore_images = True
    h.body_width = 0  # Don't wrap lines
    
    # Browser pool for shared use
    browser_pool = queue.Queue()
    browser_lock = threading.Lock()
    
    def create_browser():
        """Create a new browser instance"""
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        driver = webdriver.Chrome(options=chrome_options)
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        return driver
    
    def get_browser():
        """Get a browser from the pool or create a new one"""
        try:
            return browser_pool.get_nowait()
        except queue.Empty:
            return create_browser()
    
    def return_browser(driver):
        """Return a browser to the pool"""
        try:
            browser_pool.put_nowait(driver)
        except queue.Full:
            driver.quit()
    
    def cleanup_browsers():
        """Clean up all browsers in the pool"""
        while not browser_pool.empty():
            try:
                driver = browser_pool.get_nowait()
                driver.quit()
            except queue.Empty:
                break
    
    # Register cleanup function
    atexit.register(cleanup_browsers)
    
    def parse_malformed_json(raw_response, page_url):
        """Parse malformed JSON and extract what we can"""
        try:
            import re
            # Try to extract field-value pairs from the malformed JSON
            extracted_items = []
            
            # Look for patterns like "field": "value"
            field_pattern = r'"([^"]+)"\s*:\s*"([^"]*(?:\\.[^"]*)*)"'
            matches = re.findall(field_pattern, raw_response)
            
            if matches:
                item = {}
                for field, value in matches:
                    # Clean up the value
                    try:
                        # Unescape common escape sequences
                        cleaned_value = value.replace('\\"', '"').replace('\\n', '\n').replace('\\\\', '\\')
                        item[field] = cleaned_value
                    except:
                        item[field] = value
                
                if item:
                    item['source_url'] = page_url
                    item['extraction_timestamp'] = time.strftime("%Y-%m-%d %H:%M:%S")
                    item['extraction_status'] = 'partial_json_recovery'
                    extracted_items.append(item)
            
            return extracted_items if extracted_items else []
            
        except Exception as e:
            print(f"Error in malformed JSON parsing: {str(e)}")
            return []
    
    def extract_pdf_text(pdf_url, max_pages=100):
        """Extract text from PDF URL with page limit"""
        try:
            response = requests.get(pdf_url, timeout=30)
            response.raise_for_status()
            
            # Save PDF temporarily
            temp_pdf = f"/tmp/temp_pdf_{int(time.time())}_{threading.current_thread().ident}.pdf"
            with open(temp_pdf, 'wb') as f:
                f.write(response.content)
            
            try:
                # Count pages first
                with open(temp_pdf, 'rb') as file:
                    page_count = len(list(PDFPage.get_pages(file)))
                
                if page_count > max_pages:
                    print(f"PDF has {page_count} pages, exceeding limit of {max_pages}. Skipping.")
                    return None
                
                # Extract text
                text = extract_text(temp_pdf, maxpages=max_pages)
                return text.strip()
                
            finally:
                # Clean up temp file
                if os.path.exists(temp_pdf):
                    os.remove(temp_pdf)
                    
        except Exception as e:
            print(f"Error extracting PDF text from {pdf_url}: {str(e)}")
            return None
    
    def get_page_content(url):
        """Get content from URL (HTML or PDF)"""
        try:
            # Check if URL is PDF
            if url.lower().endswith('.pdf'):
                print(f"Processing PDF: {url}")
                pdf_text = extract_pdf_text(url)
                if pdf_text:
                    return pdf_text, [], 'pdf'
                else:
                    return None, [], 'pdf'
            
            # Get browser from pool
            driver = get_browser()
            
            try:
                driver.get(url)
                time.sleep(2)  # Wait for page to load
                
                # Check if we're on the right site
                current_page_url = driver.current_url
                current_parsed = urlparse(current_page_url)
                current_base = f"{current_parsed.scheme}://{current_parsed.netloc}/"
                
                if current_base != base_url:
                    print(f"ERROR: We've navigated away from {base_url} to {current_base}")
                    return None, [], 'html'
                
                # Scroll to make sure all content is loaded
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1)
                driver.execute_script("window.scrollTo(0, 0);")
                time.sleep(1)
                
                # Get page source and convert to readable text
                page_source = driver.page_source
                readable_text = h.handle(page_source)
                
                print(f"Page content length: {len(readable_text)} characters")
                
                # Get links for further crawling
                link_elements = driver.find_elements(By.CSS_SELECTOR, "a[href]")
                links = []
                
                for element in link_elements:
                    try:
                        href = element.get_attribute('href')
                        
                        if not href or href in ['#', 'javascript:void(0)', 'javascript:;']:
                            continue
                        
                        # Make URL absolute
                        if not href.startswith('http'):
                            href = urljoin(current_page_url, href)
                        
                        # Parse the link to get its base URL
                        link_parsed = urlparse(href)
                        link_base = f"{link_parsed.scheme}://{link_parsed.netloc}/"
                        
                        # Only process links with matching base URL
                        if link_base == base_url:
                            links.append(href)
                    except Exception as e:
                        continue
                
                return readable_text, links, 'html'
                
            finally:
                return_browser(driver)
                
        except Exception as e:
            print(f"Error getting page content from {url}: {str(e)}")
            return None, [], 'unknown'
    
    def extract_with_gemini(page_content, page_url, content_type):
        """Extract data using Gemini with thread isolation"""
        try:
            # Configure Gemini for this thread
            genai.configure(api_key=google_api_key)
            
            # Create a combined prompt with page URL and content
            combined_prompt = f"""
URL: {page_url}

EXTRACTION INSTRUCTIONS:
{extraction_prompt}

PAGE CONTENT:
{page_content}

IMPORTANT JSON FORMATTING RULES:
1. Return ONLY a valid JSON array
2. Each item must be a JSON object
3. Properly escape all special characters (quotes, backslashes, newlines)
4. Use double quotes for all strings
5. For newlines in text, use \\n (double backslash n)
6. For quotes in text, use \\" (backslash quote)
7. If no relevant information is found, return []

Example format:
[{{"field1": "value with \\"quotes\\" and \\n newlines", "field2": "another value"}}]

Return ONLY the JSON array without explanations or markdown formatting.
"""
            # Set up the model
            model = genai.GenerativeModel('gemini-1.5-flash')
            
            # Call the Gemini API
            response = model.generate_content(
                combined_prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.1,
                    max_output_tokens=8192,
                    response_mime_type="application/json"
                )
            )
            
            # Get the model response
            llm_response = response.text.strip()
            
            # Extract just the JSON part (in case the model added explanations)
            json_str = llm_response
            if "```json" in json_str:
                json_str = json_str.split("```json")[1].split("```")[0].strip()
            elif "```" in json_str:
                json_str = json_str.split("```")[1].split("```")[0].strip()
            
            # Parse the JSON response with better error handling
            try:
                extracted_data = json.loads(json_str)
            except json.JSONDecodeError as e:
                print(f"JSON decode error: {str(e)}")
                print(f"Raw response (first 500 chars): {llm_response[:500]}")
                
                # Try to fix common JSON issues
                try:
                    # Fix common escaping issues
                    fixed_json = json_str
                    
                    # Fix unescaped backslashes (but not already escaped ones)
                    import re
                    # Replace single backslashes that aren't followed by valid escape chars
                    fixed_json = re.sub(r'\\(?!["\\/bfnrt])', r'\\\\', fixed_json)
                    
                    # Fix unescaped quotes (but not already escaped ones)
                    fixed_json = re.sub(r'(?<!\\)"(?=.*":)', r'\\"', fixed_json)
                    
                    # Try parsing the fixed version
                    extracted_data = json.loads(fixed_json)
                    print(f"Successfully fixed JSON parsing issues")
                    
                except (json.JSONDecodeError, Exception) as fix_error:
                    print(f"Could not fix JSON: {str(fix_error)}")
                    # If we can't parse it, try to extract key-value pairs manually
                    extracted_data = parse_malformed_json(llm_response, page_url)
                    
            except Exception as e:
                print(f"Unexpected error parsing JSON: {str(e)}")
                extracted_data = []
                
            # Ensure we have a list
            if not isinstance(extracted_data, list):
                extracted_data = [extracted_data]
                
            # Add source URL and parsed text to each item
            for item in extracted_data:
                if isinstance(item, dict):
                    item['source_url'] = page_url
                    item['extraction_timestamp'] = time.strftime("%Y-%m-%d %H:%M:%S")
                    
                    # Add parsed text based on content type
                    if content_type == 'pdf':
                        item['pdf_miner_text'] = page_content
                    elif content_type == 'html':
                        item['html2text_text'] = page_content
            
            # If no data was extracted, create a fallback item with the parsed text
            if not extracted_data:
                fallback_item = {
                    'source_url': page_url,
                    'extraction_timestamp': time.strftime("%Y-%m-%d %H:%M:%S"),
                    'extraction_status': 'no_llm_results'
                }
                
                if content_type == 'pdf':
                    fallback_item['pdf_miner_text'] = page_content
                elif content_type == 'html':
                    fallback_item['html2text_text'] = page_content
                    
                extracted_data = [fallback_item]
                    
            return extracted_data
            
        except Exception as e:
            print(f"Error extracting data with Gemini: {str(e)}")
            # Create fallback item even on error
            fallback_item = {
                'source_url': page_url,
                'extraction_timestamp': time.strftime("%Y-%m-%d %H:%M:%S"),
                'extraction_status': 'error',
                'error_message': str(e)
            }
            
            if content_type == 'pdf':
                fallback_item['pdf_miner_text'] = page_content
            elif content_type == 'html':
                fallback_item['html2text_text'] = page_content
                
            return [fallback_item]
    
    def process_url(url, depth):
        """Process a single URL"""
        try:
            with visited_lock:
                if url in visited:
                    return [], []
                visited.add(url)
            
            print(f"\nProcessing (depth {depth}): {url}")
            
            # Get page content
            content, links, content_type = get_page_content(url)
            
            if content is None:
                return [], []
            
            # Extract data with Gemini
            print("Extracting data with Gemini-1.5-flash...")
            extracted_items = extract_with_gemini(content[:100000], url, content_type)  # Truncate if too long
            
            # Filter out items with null values if null_is_okay is False
            if not null_is_okay and extracted_items:
                original_count = len(extracted_items)
                filtered_items = []
                
                for item in extracted_items:
                    if isinstance(item, dict):
                        # Check if any values are None (but preserve our special fields)
                        contains_null = False
                        for key, value in item.items():
                            if key not in ['pdf_miner_text', 'html2text_text', 'source_url', 'extraction_timestamp', 'extraction_status', 'error_message']:
                                if value is None:
                                    contains_null = True
                                    break
                                    
                        if not contains_null:
                            filtered_items.append(item)
                    else:
                        filtered_items.append(item)
                
                if original_count != len(filtered_items):
                    print(f"Filtered out {original_count - len(filtered_items)} items with null values")
                extracted_items = filtered_items
            
            if extracted_items:
                print(f"Extracted {len(extracted_items)} items")
            else:
                print("No data extracted from this page")
            
            return extracted_items, links
            
        except Exception as e:
            print(f"Error processing {url}: {str(e)}")
            return [], []
    
    def save_to_json(data, filepath):
        """Save data to JSON file"""
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f"Data saved to {filepath}")
        except Exception as e:
            print(f"Error saving data to {filepath}: {str(e)}")
    
    try:
        # Initialize browser pool
        for _ in range(min(num_workers, 3)):  # Limit initial browsers to prevent resource issues
            browser_pool.put(create_browser())
        
        # Initialize with starting URL
        current_level_urls = [start_url]
        
        for current_depth in range(num_levels_deep + 1):
            if not current_level_urls:
                break
                
            print(f"\n=== PROCESSING DEPTH LEVEL {current_depth} ===")
            print(f"URLs to process: {len(current_level_urls)}")
            
            next_level_urls = []
            
            # Process URLs in smaller batches to prevent worker contention
            batch_size = max(1, len(current_level_urls) // num_workers)
            
            for i in range(0, len(current_level_urls), batch_size):
                batch_urls = current_level_urls[i:i + batch_size]
                
                # Process batch in parallel
                with concurrent.futures.ThreadPoolExecutor(max_workers=min(num_workers, len(batch_urls))) as executor:
                    # Submit URLs for processing
                    future_to_url = {
                        executor.submit(process_url, url, current_depth): url 
                        for url in batch_urls
                    }
                    
                    # Collect results
                    for future in concurrent.futures.as_completed(future_to_url):
                        url = future_to_url[future]
                        try:
                            extracted_items, links = future.result()
                            
                            # Add extracted data
                            if extracted_items:
                                with data_lock:
                                    all_extracted_data.extend(extracted_items)
                            
                            # Add new links for next level (if not at max depth)
                            if current_depth < num_levels_deep:
                                for link in links:
                                    with visited_lock:
                                        if link not in visited and link not in next_level_urls:
                                            next_level_urls.append(link)
                            
                        except Exception as e:
                            print(f"Error processing future for {url}: {str(e)}")
            
            # Save progress after each level
            print(f"Level {current_depth} complete. Total items extracted: {len(all_extracted_data)}")
            save_to_json(all_extracted_data, str(output_file))
            
            # Prepare for next level
            current_level_urls = next_level_urls
        
        print(f"\n=== CRAWLING COMPLETE ===")
        print(f"Total pages visited: {len(visited)}")
        print(f"Total data items extracted: {len(all_extracted_data)}")
        
        # Final save
        save_to_json(all_extracted_data, str(output_file))
        
        return all_extracted_data
        
    except Exception as e:
        print(f"Crawler error: {str(e)}")
        
        # Try to save any data collected so far
        if all_extracted_data:
            save_to_json(all_extracted_data, str(output_file))
            
        return all_extracted_data
    
    finally:
        # Clean up browsers
        cleanup_browsers()

def scrape_bill_page_links(bill_name: str, year: str):
    """
    Scrapes the Hawaii Capitol website for a specific bill to extract all document links.
    """
    import os
    import time
    import tempfile
    import shutil
    from urllib.parse import urlparse, urljoin, parse_qs
    from bs4 import BeautifulSoup
    from selenium.webdriver.common.by import By
    import undetected_chromedriver as uc

    bill_type = ''.join(filter(str.isalpha, bill_name))
    bill_number = ''.join(filter(str.isdigit, bill_name))

    measure_url = f"https://www.capitol.hawaii.gov/session/measure_indiv.aspx?billtype={bill_type}&billnumber={bill_number}&year={year}"
    
    download_dir = tempfile.mkdtemp()
    
    options = uc.ChromeOptions()
    options.add_experimental_option("prefs", {
        "download.default_directory": download_dir,
        "download.prompt_for_download": False,
        "plugins.always_open_pdf_externally": True
    })
    driver = uc.Chrome(options=options)
    
    try:
        driver.get(measure_url)
        time.sleep(0.1)

        main_content = driver.find_element(By.ID, "main-content")
        a_tags = main_content.find_elements(By.XPATH, ".//a[@href]")
        
        base_url = measure_url
        raw_links = [urljoin(base_url, a.get_attribute("href")) for a in a_tags]
        
        # Filter for .htm and .pdf links
        filtered_links = [u for u in raw_links if u.lower().endswith((".htm", ".pdf"))]
        
        # Prioritize .htm over .pdf for the same document base name
        unique_docs = {}
        for link in filtered_links:
            path = urlparse(link).path
            base = os.path.splitext(os.path.basename(path))[0]
            key = os.path.dirname(path) + "/" + base
            ext = os.path.splitext(path)[1].lower()
            
            if ext == ".htm":
                unique_docs[key] = link
            elif ext == ".pdf" and key not in unique_docs:
                unique_docs[key] = link
                
        return list(unique_docs.values())

    finally:
        driver.quit()
        shutil.rmtree(download_dir)