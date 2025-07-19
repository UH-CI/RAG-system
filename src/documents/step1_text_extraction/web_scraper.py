import time
import json
import re
import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import logging
from urllib.parse import urljoin, urlparse
import requests
import pdfplumber
import fitz
import io
import tempfile
import shutil # Import shutil for cleaning up temporary directories

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class GenericWebScraper:
    def __init__(self, use_delays=False, max_depth=3, progress_filepath=None, output_directory=None):
        self.driver = None
        self.download_dir = tempfile.mkdtemp()
        self.setup_driver()
        self.processed_urls = set()
        self.max_depth = max_depth
        self.use_delays = use_delays
        self.progress_filepath = progress_filepath
        self.output_directory = output_directory # Store output directory
        self.extracted_documents = [] # This will now be the main list for extracted documents

        # Load from both progress file and existing scraped data files
        self.extracted_documents = self._load_progress()
        for doc in self.extracted_documents:
            self.processed_urls.add(doc['url'])
        logger.info(f"💾 Loaded {len(self.extracted_documents)} documents from previous sessions.")
        
    def setup_driver(self):
        """Setup Chrome driver with anti-detection measures"""
        options = Options()
        
        # Anti-detection settings
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        options.add_argument('--disable-web-security')
        options.add_argument('--allow-running-insecure-content')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        
        # PDF handling
        options.add_experimental_option('prefs', {
            "download.default_directory": self.download_dir,
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "plugins.always_open_pdf_externally": True
        })
        
        # Make it look like a regular user
        options.add_argument('--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        
        # Uncomment to run headless
        # options.add_argument('--headless')
        
        try:
            self.driver = webdriver.Chrome(options=options)
            
            # Additional anti-detection
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            self.driver.execute_cdp_cmd('Network.setUserAgentOverride', {
                "userAgent": 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            })
            
            logger.info("✅ Chrome driver initialized successfully")
            
        except Exception as e:
            logger.error(f"❌ Error setting up Chrome driver: {e}")
            raise
            
    def maybe_delay(self, min_sec=0.5, max_sec=1):
        """Add optional delay if enabled"""
        if self.use_delays:
            import random
            delay = random.uniform(min_sec, max_sec)
            time.sleep(delay)
        
    def load_page(self, url, timeout=30):
        """Load a page and return BeautifulSoup object"""
        try:
            logger.info(f"🌐 Loading: {url}")
            self.driver.get(url)
            
            # Wait for page to load
            WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # Small wait for dynamic content
            time.sleep(1)  # Increased slightly for more reliable loading
            
            # Get page source
            page_source = self.driver.page_source
            soup = BeautifulSoup(page_source, 'html.parser')
            logger.debug(f"🔍 Page source length: {len(page_source)}")
            
            # Check if blocked
            if "403" in self.driver.title or "forbidden" in self.driver.title.lower():
                logger.warning("⚠️ Page might be blocked")
                return None
                
            logger.info("✅ Page loaded successfully")
            return soup
            
        except Exception as e:
            logger.error(f"❌ Error loading {url}: {e}")
            return None
    
    def extract_clean_text(self, soup):
        """Extract clean text from BeautifulSoup object"""
        if not soup:
            return ""
            
        # Remove unwanted elements
        for element in soup(['script', 'style', 'nav', 'header', 'footer', 'aside', 'noscript']):
            element.decompose()
            
        # Get text content
        text = soup.get_text(separator=' ', strip=True)
        logger.debug(f"Raw extracted text length: {len(text)}")
        
        # Clean up text
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'\n\s*\n', '\n\n', text)
        
        return text.strip()
    
    def _load_progress(self):
        """Loads previously extracted data from the progress file and existing scraped data files."""
        all_loaded_docs = []
        loaded_urls = set()

        # 1. Load from the temporary progress file (if exists and valid)
        if self.progress_filepath and os.path.exists(self.progress_filepath):
            try:
                with open(self.progress_filepath, 'r', encoding='utf-8') as f:
                    progress_data = json.load(f)
                    for doc in progress_data:
                        if doc['url'] not in loaded_urls:
                            all_loaded_docs.append(doc)
                            loaded_urls.add(doc['url'])
                logger.info(f"Loaded {len(progress_data)} documents from progress file {self.progress_filepath}")
            except json.JSONDecodeError as e:
                logger.error(f"❌ Error decoding JSON from progress file {self.progress_filepath}: {e}. Ignoring this file.")
            except Exception as e:
                logger.error(f"❌ Error loading progress file {self.progress_filepath}: {e}. Ignoring this file.")

        # 2. Load from existing scraped_data_*.json files in the output directory
        if self.output_directory and os.path.exists(self.output_directory):
            for filename in os.listdir(self.output_directory):
                if filename.startswith("scraped_data_") and filename.endswith(".json"):
                    filepath = os.path.join(self.output_directory, filename)
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            scraped_data = json.load(f)
                            for doc in scraped_data:
                                if doc['url'] not in loaded_urls:
                                    all_loaded_docs.append(doc)
                                    loaded_urls.add(doc['url'])
                        logger.info(f"Loaded {len(scraped_data)} documents from existing file {filepath}")
                    except json.JSONDecodeError as e:
                        logger.warning(f"⚠️ Error decoding JSON from {filepath}: {e}. Skipping file.")
                    except Exception as e:
                        logger.warning(f"⚠️ Error reading existing data file {filepath}: {e}. Skipping file.")

        return all_loaded_docs

    def _save_progress(self):
        """Saves the current state of extracted documents to the progress file."""
        if not self.progress_filepath:
            return
        try:
            with open(self.progress_filepath, 'w', encoding='utf-8') as f:
                json.dump(self.extracted_documents, f, indent=2, ensure_ascii=False)
            logger.info(f"💾 Progress saved to {self.progress_filepath} ({len(self.extracted_documents)} documents).")
        except Exception as e:
            logger.error(f"❌ Error saving progress to {self.progress_filepath}: {e}")

    def extract_text_from_pdf(self, pdf_url):
        """Download PDF using the browser and extract text."""
        logger.info(f"📄 Processing PDF: {pdf_url}")
        
        try:
            # Clear download directory to ensure we get the right file
            for f in os.listdir(self.download_dir):
                os.remove(os.path.join(self.download_dir, f))

            # Navigate to the URL, which will trigger the download
            self.driver.get(pdf_url)

            # Wait for the download to complete
            filepath = None
            time_waited = 0
            timeout = 60
            while time_waited < timeout:
                # Look for a file with a .pdf extension, which indicates the download is complete.
                pdf_files = [f for f in os.listdir(self.download_dir) if f.lower().endswith('.pdf')]
                if pdf_files:
                    filepath = os.path.join(self.download_dir, pdf_files[0])
                    # Give it a moment to ensure the file handle is released
                    time.sleep(1)
                    logger.info(f"✅ PDF downloaded to: {filepath}")
                    break
                time.sleep(1)
                time_waited += 1

            if not filepath:
                logger.error(f"❌ PDF download timed out for {pdf_url}")
                return None
            
            with open(filepath, 'rb') as f:
                pdf_data = f.read()

            if not pdf_data or len(pdf_data) < 1000:
                logger.warning(f"⚠️ PDF data from {filepath} seems too small ({len(pdf_data)} bytes)")
                return None

            # Try pdfplumber first
            try:
                logger.debug("📄 Trying pdfplumber extraction...")
                with pdfplumber.open(io.BytesIO(pdf_data)) as pdf:
                    text = ""
                    for page_num, page in enumerate(pdf.pages):
                        page_text = page.extract_text()
                        if page_text:
                            text += page_text + "\n"
                    
                    if text.strip():
                        logger.info(f"✅ Extracted {len(text)} characters from PDF using pdfplumber")
                        return text.strip()
            except Exception as e:
                logger.warning(f"⚠️ pdfplumber failed: {e}")

            # Fallback to PyMuPDF (fitz)
            try:
                logger.debug("📄 Trying PyMuPDF (fitz) extraction...")
                doc = fitz.open(stream=pdf_data, filetype="pdf")
                text = ""
                for page_num in range(len(doc)):
                    page = doc.load_page(page_num)
                    page_text = page.get_text()
                    if page_text:
                        text += page_text + "\n"
                doc.close()
                
                if text.strip():
                    logger.info(f"✅ Extracted {len(text)} characters from PDF using PyMuPDF")
                    return text.strip()
            except Exception as e:
                logger.warning(f"⚠️ PyMuPDF failed: {e}")

            logger.error(f"❌ Both PDF extraction methods failed for {pdf_url}")
            return None

        except Exception as e:
            logger.error(f"❌ Error processing PDF {pdf_url}: {e}")
            return None

    def is_directory(self, url):
        """Check if this is a directory based on the URL structure."""
        return url.endswith('/')
    
    def is_content_file(self, url):
        """Determine if this is a content file (HTML, PDF, etc.)"""
        if self.is_directory(url):
            return False

        parsed_url = urlparse(url)
        path = parsed_url.path
        
        # Check for common file extensions. PDFs are handled separately later.
        file_extensions = ['.htm', '.html', '.txt', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx']
        if any(path.lower().endswith(ext) for ext in file_extensions):
            return True
        
        # If it's not a directory and doesn't have a common file extension,
        # it's very likely an HTML page we want to scrape.
        # This handles "pretty URLs" like /about, /products/item1
        # Check if the last segment of the path contains a dot, implying a file extension.
        # If no dot, and not a directory, treat as a content page.
        if '.' not in path.split('/')[-1]:
            return True
            
        return False
    
    def is_within_scope(self, url, start_url):
        """Check if URL is within the scraping scope defined by the start_url."""
        return url.startswith(start_url)

    def get_links_in_page(self, soup, current_url, start_url):
        """Extract links that are within the scraping scope"""
        if not soup:
            return []
            
        links = []
        for link in soup.find_all('a', href=True):
            href = link['href']
            
            if href in ['.', '..', '#', ''] or href.startswith('mailto:') or href.startswith('javascript:'):
                continue
                
            full_url = urljoin(current_url, href)
            logger.debug(f"Found link - Href: {href}, Full URL: {full_url}")
                
            # Use the correct scope-checking method
            if not self.is_within_scope(full_url, start_url):
                logger.debug(f"Skipping link outside scope: {full_url}")
                continue
                
            # Avoid adding the same page again if href is empty or just a fragment
            if full_url == current_url:
                continue

            link_info = {
                'url': full_url,
                'href': href,
                'text': link.get_text(strip=True),
                'is_file': self.is_content_file(full_url),
                'is_directory': self.is_directory(full_url)
            }
            
            links.append(link_info)
            
        return links
    
    def crawl_website(self, start_url):
        """
        Crawl a website by processing each page for text and finding new links.
        
        Args:
            start_url: URL to start crawling from
        """
        logger.info(f"🔍 Starting to crawl from: {start_url}")
        
        # self.processed_urls is populated by __init__ from existing files
        queue = [(start_url, 0)]
        
        # URLs we have added to the queue during this session, to avoid duplicates
        queued_urls = {start_url}

        while queue:
            current_url, depth = queue.pop(0)
            
            # --- Depth Check ---
            if depth > self.max_depth:
                logger.info(f"⏭️ Skipping {current_url} - max depth ({self.max_depth}) reached")
                continue
            
            soup = None # Reset soup for each item in queue

            # --- Content Extraction ---
            # We only extract content if we haven't processed this URL before
            if current_url not in self.processed_urls:
                extracted_text = None
                content_type = 'unknown'

                if current_url.lower().endswith('.pdf'):
                    content_type = 'pdf'
                    extracted_text = self.extract_text_from_pdf(current_url)
                else: # Assumed to be HTML
                    soup = self.load_page(current_url)
                    if soup:
                        content_type = 'html'
                        extracted_text = self.extract_clean_text(soup)
                
                # If we got text, save it
                if extracted_text and len(extracted_text.strip()) > 0:
                    file_data = {
                        "url": current_url,
                        "type": content_type,
                        "text": extracted_text,
                        "text_length": len(extracted_text),
                        "depth": depth,
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                    }
                    self.extracted_documents.append(file_data)
                    self.processed_urls.add(current_url)
                    self._save_progress()
                else:
                    logger.warning(f"⚠️ No text extracted from {current_url}")

            # --- Link Finding ---
            # We only scan for links on HTML pages that are within crawling depth
            if not current_url.lower().endswith('.pdf') and depth < self.max_depth:
                # If we didn't load the page during content extraction, load it now
                if soup is None:
                    soup = self.load_page(current_url)
                
                if soup:
                    links = self.get_links_in_page(soup, current_url, start_url)
                    logger.info(f"🔗 Found {len(links)} links on page {current_url} to consider for queue.")
                    for link_info in links:
                        link_url = link_info['url']
                        # Add to queue only if it's new for this session
                        if link_url not in queued_urls:
                            queue.append((link_url, depth + 1))
                            queued_urls.add(link_url)
                            logger.debug(f"📝 Added to queue: {link_url} (depth: {depth + 1})")

            self.maybe_delay(0.5, 1)

        logger.info(f"✅ Website crawling completed: {len(self.extracted_documents)} documents extracted")
        return self.extracted_documents
    
    def close(self):
        """Close the browser"""
        if self.driver:
            self.driver.quit()
            logger.info("🔒 Browser closed")
        
        # Clean up temp directory
        if hasattr(self, 'download_dir') and os.path.exists(self.download_dir):
            shutil.rmtree(self.download_dir)
            logger.info(f"🗑️ Removed temp directory: {self.download_dir}")

def crawl_and_extract(start_url, output_directory, max_depth=1, use_delays=False):
    """
    Generalized function to crawl a website, scrape text, and output to a flat JSON.

    Args:
        start_url (str): The URL to start crawling from.
        output_directory (str): The directory to save the output JSON file.
        max_depth (int): Maximum depth to crawl from the start_url.
        use_delays (bool): Whether to use delays between requests.
    """
    
    # Ensure output directory exists
    os.makedirs(output_directory, exist_ok=True)
    
    # Create a unique progress filename
    progress_filename = os.path.join(output_directory, f"progress_{re.sub(r'[^a-zA-Z0-9_.-]', '_', start_url)[:50]}.json")
    
    # Create a unique filename for the output
    # Sanitize URL for filename
    sanitized_url = re.sub(r'[^a-zA-Z0-9_.-]', '_', start_url)
    output_filename = os.path.join(output_directory, f"scraped_data_{sanitized_url[:50]}_{int(time.time())}.json") # Limit URL length for filename

    scraper = GenericWebScraper(use_delays=use_delays, max_depth=max_depth, progress_filepath=progress_filename, output_directory=output_directory)
    all_extracted_data = []

    try:
        all_extracted_data = scraper.crawl_website(
            start_url=start_url 
        )
        
        # Save the collected data to a single flat JSON file
        with open(output_filename, 'w', encoding='utf-8') as f:
            json.dump(all_extracted_data, f, indent=2, ensure_ascii=False)
            
        logger.info(f"🎉 Crawling and extraction completed! Data saved to: {output_filename}")
        logger.info(f"📚 Total documents extracted: {len(all_extracted_data)}")
        
        # Remove progress file on successful completion
        if os.path.exists(progress_filename):
            os.remove(progress_filename)
            logger.info(f"🗑️ Removed progress file: {progress_filename}")
        
    except Exception as e:
        logger.error(f"❌ An error occurred during the crawling process: {e}")
    finally:
        scraper.close() 

# Example Usage:
if __name__ == "__main__":
    start_url = "https://www.capitol.hawaii.gov/sessions/session2025/bills/"  # Replace with the URL you want to crawl
    output_directory = "output" # Directory to save the extracted data

    # Create the output directory if it doesn't exist
    os.makedirs(output_directory, exist_ok=True)

    crawl_and_extract(
        start_url=start_url,
        output_directory=output_directory,
        max_depth=1,        # Only process links on the start page
        use_delays=True     # Set to True to use delays between requests (slower but safer)
    )