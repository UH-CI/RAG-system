def ai_crawler(start_url, extraction_prompt, collection_name, google_api_key=None, null_is_okay=True):
    """
    AI-powered web crawler that visits URLs, extracts structured data using Gemini-1.5-lite,
    and saves results to a JSON file in the storage_documents collection folder.
    
    Args:
        start_url (str): The starting URL to begin crawling
        extraction_prompt (str): Prompt for the LLM describing what data to extract
        collection_name (str): Name of the collection folder where data will be saved
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
    
    # Initialize Google Gemini client
    if not google_api_key:
        google_api_key = os.environ.get("GOOGLE_API_KEY")
    
    if not google_api_key:
        raise ValueError("Google API key must be provided either directly or via GOOGLE_API_KEY environment variable")
    
    genai.configure(api_key=google_api_key)
    
    # Set up Chrome options
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # Run in headless mode
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    
    # Initialize the browser
    driver = webdriver.Chrome(options=chrome_options)
    
    # Extract the base URL for comparison
    parsed_url = urlparse(start_url)
    base_url = f"{parsed_url.scheme}://{parsed_url.netloc}/"
    print(f"\n=== AI CRAWLER STARTING ===")
    print(f"Starting URL: {start_url}")
    print(f"Base URL for filtering: {base_url}")
    
    # Initialize queue and visited set
    queue = [start_url]
    visited = set()
    all_discovered_links = set()
    
    # Set up storage directory
    base_dir = Path(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    storage_dir = base_dir / 'storage_documents' / collection_name
    storage_dir.mkdir(parents=True, exist_ok=True)
    output_file = storage_dir / f"web_scrape_{int(time.time())}.json"
    
    print(f"Output will be saved to: {output_file}")
    
    # Initialize data storage
    all_extracted_data = []
    
    pages_visited = 0
    
    # Function to extract data using Gemini
    def extract_with_gemini(page_content, page_url):
        try:
            # Create a combined prompt with page URL and content
            combined_prompt = f"""
URL: {page_url}

EXTRACTION INSTRUCTIONS:
{extraction_prompt}

PAGE CONTENT:
{page_content}

Please extract the requested information as a valid JSON array. Each item should be a JSON object.
If no relevant information is found, return an empty array [].
Return ONLY a valid JSON array without any explanations, markdown formatting, or additional text.
"""
            # Set up the model
            model = genai.GenerativeModel('gemini-1.5-flash')
            
            # Call the Gemini API
            response = model.generate_content(
                combined_prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.1,  # Lower temperature for more consistent outputs
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
                
            # Parse the JSON response
            extracted_data = json.loads(json_str)
            
            # Ensure we have a list
            if not isinstance(extracted_data, list):
                extracted_data = [extracted_data]
                
            # Add source URL to each item
            for item in extracted_data:
                if isinstance(item, dict):
                    item['source_url'] = page_url
                    item['extraction_timestamp'] = time.strftime("%Y-%m-%d %H:%M:%S")
                    
            return extracted_data
            
        except Exception as e:
            print(f"Error extracting data with Gemini: {str(e)}")
            return []
    
    # Function to save data to JSON file
    def save_to_json(data, filepath):
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f"Data saved to {filepath}")
        except Exception as e:
            print(f"Error saving data to {filepath}: {str(e)}")
            # Create backup file
            backup_file = f"{filepath}.backup_{int(time.time())}.json"
            try:
                with open(backup_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                print(f"Backup data saved to {backup_file}")
            except Exception as backup_err:
                print(f"Failed to save backup: {str(backup_err)}")
    
    try:
        while queue:
            # Get the next URL from the queue
            current_url = queue.pop(0)
            
            # Skip if already visited
            if current_url in visited:
                continue
            
            print(f"\nProcessing: {current_url}")
            
            # Visit the URL
            try:
                driver.get(current_url)
                time.sleep(0.1)  # Wait for page to load
                
                # Mark as visited
                visited.add(current_url)
                pages_visited += 1
                
                # Check if we're on the right site
                current_page_url = driver.current_url
                current_parsed = urlparse(current_page_url)
                current_base = f"{current_parsed.scheme}://{current_parsed.netloc}/"
                
                if current_base != base_url:
                    print(f"ERROR: We've navigated away from {base_url} to {current_base}")
                    continue
                
                # Scroll to make sure all content is loaded
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(0.1)
                driver.execute_script("window.scrollTo(0, 0);")
                time.sleep(0.1)
                
                # Get page content
                page_source = driver.page_source
                soup = BeautifulSoup(page_source, 'html.parser')
                
                # Clean up page content (remove scripts, styles, etc.)
                for tag in soup(["script", "style", "noscript", "iframe", "meta"]):
                    tag.decompose()
                
                # Get the cleaned text
                page_text = soup.get_text(separator="\n", strip=True)
                page_text = "\n".join(line.strip() for line in page_text.split("\n") if line.strip())
                
                print(f"Page content length: {len(page_text)} characters")
                
                # Process with Gemini and extract data
                print("Extracting data with Gemini-1.5-lite...")
                extracted_items = extract_with_gemini(page_text[:100000], current_page_url)  # Truncate if too long
                
                # Filter out items with null values if null_is_okay is False
                if not null_is_okay and extracted_items:
                    original_count = len(extracted_items)
                    filtered_items = []
                    
                    for item in extracted_items:
                        if isinstance(item, dict):
                            # Check if any values are None
                            contains_null = False
                            for key, value in item.items():
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
                
                # Add to overall results
                if extracted_items:
                    print(f"Extracted {len(extracted_items)} items")
                    all_extracted_data.extend(extracted_items)
                else:
                    print("No data extracted from this page")
                
                # Save after each page (incremental saving to prevent data loss)
                print(f"Saving {len(all_extracted_data)} total items to {output_file}")
                save_to_json(all_extracted_data, str(output_file))
                
                # Get ALL anchor elements with href attributes
                link_elements = driver.find_elements(By.CSS_SELECTOR, "a[href]")
                print(f"Found {len(link_elements)} total links on the page")
                
                # Extract and process links
                new_links = 0
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
                            # Add to all discovered links
                            all_discovered_links.add(href)
                            
                            # If not visited and not in queue, add to queue
                            if href not in visited and href not in queue:
                                queue.append(href)
                                new_links += 1
                    except Exception as e:
                        continue
                
                print(f"Added {new_links} new links to the queue")
                print(f"Queue size: {len(queue)}")
                print(f"Total discovered links: {len(all_discovered_links)}")
                
            except Exception as e:
                print(f"Error processing {current_url}: {str(e)}")
        
        print(f"Total pages visited: {pages_visited}")
        print(f"Total unique links discovered: {len(all_discovered_links)}")
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
        # Always close the browser
        driver.quit()

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