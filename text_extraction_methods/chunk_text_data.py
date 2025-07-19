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
import hashlib
from pathlib import Path

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class GenericWebScraper:
    def __init__(self, use_delays=False, max_depth=3, download_directory="downloads"):
        self.driver = None
        self.setup_driver()
        self.processed_urls = set()
        self.max_depth = max_depth
        self.use_delays = use_delays
        self.download_directory = download_directory
        
        # Create download directory if it doesn't exist
        os.makedirs(self.download_directory, exist_ok=True)
        
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
        
        # PDF handling - tell Chrome to download PDFs instead of viewing them
        options.add_experimental_option('prefs', {
            "download.default_directory": os.path.abspath(self.download_directory),
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "plugins.always_open_pdf_externally": True  # Key setting
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
            time.sleep(1)
            
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

    def generate_filename(self, url):
        """Generate a safe filename from URL"""
        # Create a hash of the URL for uniqueness
        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
        
        # Extract filename from URL
        parsed = urlparse(url)
        filename = os.path.basename(parsed.path)
        
        # If no filename or extension, use default
        if not filename or not filename.endswith('.pdf'):
            filename = f"document_{url_hash}.pdf"
        else:
            # Add hash to avoid conflicts
            name, ext = os.path.splitext(filename)
            filename = f"{name}_{url_hash}{ext}"
        
        return filename

    def download_pdf(self, pdf_url):
        """Download PDF file to local directory using the browser."""
        try:
            logger.info(f"📥 Navigating to PDF for download: {pdf_url}")

            # Generate safe filename and path
            filename = self.generate_filename(pdf_url)
            filepath = os.path.join(self.download_directory, filename)

            # Check if file already exists
            if os.path.exists(filepath):
                logger.info(f"📄 PDF already exists: {filepath}")
                return filepath

            # Clear any old '.crdownload' files to avoid confusion
            for f in os.listdir(self.download_directory):
                if f.endswith('.crdownload'):
                    os.remove(os.path.join(self.download_directory, f))

            # Navigate to the URL to trigger the download
            self.driver.get(pdf_url)
            
            # Wait for the download to complete
            download_wait_time = 60  # Increased timeout for larger files
            time_waited = 0
            
            while time_waited < download_wait_time:
                # Check if the target file exists and is fully downloaded
                if os.path.exists(filepath):
                    # Check that there are no .crdownload files left
                    if not any(f.endswith('.crdownload') for f in os.listdir(self.download_directory)):
                        logger.info(f"✅ Download complete: {filepath}")
                        break
                time.sleep(1)
                time_waited += 1
            else: # This 'else' belongs to the 'while' loop
                logger.error(f"❌ PDF download timed out for {pdf_url}")
                # Clean up partial file if it exists
                if os.path.exists(filepath):
                     os.remove(filepath)
                # Also clean up .crdownload file if it's stuck
                crdownload_path = filepath + ".crdownload"
                if os.path.exists(crdownload_path):
                    os.remove(crdownload_path)
                return None
            
            # Verify the downloaded file
            file_size = os.path.getsize(filepath)
            if file_size < 1000:
                logger.warning(f"⚠️ Downloaded PDF seems too small ({file_size} bytes)")
                os.remove(filepath)
                return None
            
            logger.info(f"✅ PDF downloaded successfully: {filepath} ({file_size} bytes)")
            return filepath
            
        except Exception as e:
            logger.error(f"❌ Error downloading PDF {pdf_url}: {e}")
            return None

    def extract_text_from_local_pdf(self, filepath):
        """Extract text from a local PDF file"""
        try:
            logger.info(f"📄 Extracting text from local PDF: {filepath}")
            
            if not os.path.exists(filepath):
                logger.error(f"❌ PDF file not found: {filepath}")
                return None
            
            # Try pdfplumber first
            try:
                logger.debug("📄 Trying pdfplumber extraction...")
                with pdfplumber.open(filepath) as pdf:
                    text = ""
                    for page_num, page in enumerate(pdf.pages):
                        page_text = page.extract_text()
                        if page_text:
                            text += page_text + "\n"
                        logger.debug(f"📄 Page {page_num + 1}: {len(page_text) if page_text else 0} characters")
                    
                    if text.strip():
                        logger.info(f"✅ Extracted {len(text)} characters from PDF using pdfplumber")
                        return text.strip()
            except Exception as e:
                logger.warning(f"⚠️ pdfplumber failed: {e}")
            
            # Fallback to PyMuPDF (fitz)
            try:
                logger.debug("📄 Trying PyMuPDF (fitz) extraction...")
                doc = fitz.open(filepath)
                text = ""
                for page_num in range(len(doc)):
                    page = doc.load_page(page_num)
                    page_text = page.get_text()
                    if page_text:
                        text += page_text + "\n"
                    logger.debug(f"📄 Page {page_num + 1}: {len(page_text) if page_text else 0} characters")
                doc.close()
                
                if text.strip():
                    logger.info(f"✅ Extracted {len(text)} characters from PDF using PyMuPDF")
                    return text.strip()
            except Exception as e:
                logger.warning(f"⚠️ PyMuPDF failed: {e}")
            
            logger.error(f"❌ Both PDF extraction methods failed for {filepath}")
            return None
            
        except Exception as e:
            logger.error(f"❌ Error extracting text from PDF {filepath}: {e}")
            return None

    def extract_text_from_pdf(self, pdf_url):
        """Download PDF and extract text from it"""
        # Download the PDF first
        filepath = self.download_pdf(pdf_url)
        if not filepath:
            return None
        
        # Extract text from the downloaded PDF
        return self.extract_text_from_local_pdf(filepath)

    def is_directory(self, url):
        """Check if this is a directory based on the URL structure."""
        return url.endswith('/')

    def is_content_file(self, url):
        """Determine if this is a content file (HTML, PDF, etc.)"""
        if self.is_directory(url):
            return False

        parsed_url = urlparse(url)
        path = parsed_url.path
        
        # Check for common file extensions
        file_extensions = ['.htm', '.html', '.txt', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx']
        if any(path.lower().endswith(ext) for ext in file_extensions):
            return True
        
        # If it's not a directory and doesn't have a common file extension,
        # it's very likely an HTML page we want to scrape
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

    def crawl_website(self, start_url, max_files=100):
        """
        Crawl a website by processing each page for text and finding new links.
        
        Args:
            start_url: URL to start crawling from
            max_files: Maximum number of files to extract
        """
        logger.info(f"🔍 Starting to crawl from: {start_url}")
        
        self.processed_urls = set()
        queue = [(start_url, 0)]
        extracted_documents = []
        
        while queue and len(extracted_documents) < max_files:
            current_url, depth = queue.pop(0)
            
            # Check if already processed
            if current_url in self.processed_urls:
                logger.debug(f"⏭️ Already processed: {current_url}")
                continue
                
            if depth > self.max_depth:
                logger.info(f"⏭️ Skipping {current_url} - max depth reached")
                continue

            # Check if the URL is within the desired scope
            if not self.is_within_scope(current_url, start_url):
                logger.info(f"⏭️ Skipping {current_url} - outside target scope")
                continue

            # Mark as processed
            self.processed_urls.add(current_url)
            
            soup = None
            extracted_text = None
            content_type = 'unknown'
            local_file_path = None

            # Process current URL for content
            if current_url.lower().endswith('.pdf'):
                content_type = 'pdf'
                extracted_text = self.extract_text_from_pdf(current_url)
                # Store the local file path for reference
                local_file_path = os.path.join(self.download_directory, self.generate_filename(current_url))
            else:
                # Assumed to be HTML
                soup = self.load_page(current_url)
                if soup:
                    content_type = 'html'
                    extracted_text = self.extract_clean_text(soup)
                    
                    # Check if this HTML page actually contains a PDF embed or redirect
                    if not extracted_text or len(extracted_text.strip()) < 100:
                        # Look for PDF embeds or iframes
                        pdf_embeds = soup.find_all(['embed', 'iframe'], src=True)
                        for embed in pdf_embeds:
                            src = embed.get('src', '')
                            if src.lower().endswith('.pdf'):
                                full_pdf_url = urljoin(current_url, src)
                                logger.info(f"🔍 Found embedded PDF: {full_pdf_url}")
                                pdf_text = self.extract_text_from_pdf(full_pdf_url)
                                if pdf_text:
                                    extracted_text = pdf_text
                                    content_type = 'pdf'
                                    local_file_path = os.path.join(self.download_directory, self.generate_filename(full_pdf_url))
                                    break

            # Save extracted text if any is found
            if extracted_text and len(extracted_text.strip()) > 0:
                file_data = {
                    "url": current_url,
                    "type": content_type,
                    "text": extracted_text,
                    "text_length": len(extracted_text),
                    "depth": depth,
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "local_file_path": local_file_path  # Add local file path for PDFs
                }
                extracted_documents.append(file_data)
                logger.info(f"✅ Extracted {len(extracted_text)} characters from {current_url}")
            else:
                logger.warning(f"⚠️ No text extracted from {current_url}")
 
             # If we hit the file limit, stop crawling
             if len(extracted_documents) >= max_files:
                logger.info(f"🛑 Reached file limit ({max_files}). Stopping crawl.")
                break

            # If it was an HTML page, find links and add to queue
            if soup:
                links = self.get_links_in_page(soup, current_url, start_url)
                logger.info(f"🔗 Found {len(links)} links on page {current_url}")
                for link_info in links:
                    link_url = link_info['url']
                    if link_url not in self.processed_urls:
                        # Decide whether to process immediately (PDF) or queue (HTML)
                        if link_info['url'].lower().endswith('.pdf'):
                            if len(extracted_documents) < max_files:
                                self.processed_urls.add(link_info['url'])
                                pdf_text = self.extract_text_from_pdf(link_info['url'])
                                if pdf_text:
                                    file_data = {
                                        "url": link_info['url'],
                                        "type": "pdf",
                                        "text": pdf_text,
                                        "text_length": len(pdf_text),
                                        "depth": depth + 1,
                                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                                        "local_file_path": os.path.join(self.download_directory, self.generate_filename(link_info['url']))
                                    }
                                    extracted_documents.append(file_data)
                                    logger.info(f"✅ Extracted {len(pdf_text)} characters from PDF {link_info['url']}")
                                else:
                                    logger.warning(f"⚠️ No text extracted from PDF {link_info['url']}")
                            else:
                                logger.info("File limit reached, skipping further PDF processing.")
                        else:
                            queue.append((link_info['url'], depth + 1))
                            logger.debug(f"📝 Added to queue: {link_info['url']} (depth: {depth + 1})")
 
            self.maybe_delay(0.5, 1)
        
        logger.info(f"✅ Website crawling completed: {len(extracted_documents)} documents extracted")
        return extracted_documents

    def close(self):
        """Close the browser"""
        if self.driver:
            self.driver.quit()
            logger.info("🔒 Browser closed")

def crawl_and_extract(start_url, output_directory, max_files=100, max_depth=3, use_delays=False):
    """
    Generalized function to crawl a website, scrape text, and output to a flat JSON.
    
    Args:
        start_url (str): The URL to start crawling from.
        output_directory (str): The directory to save the output JSON file.
        max_files (int): Maximum number of files (HTML pages or PDFs) to extract.
        max_depth (int): Maximum depth to crawl from the start_url.
        use_delays (bool): Whether to use delays between requests.
    """
    
    # Ensure output directory exists
    os.makedirs(output_directory, exist_ok=True)
    
    # Create download directory within output directory
    download_directory = os.path.join(output_directory, "downloaded_pdfs")
    
    # Create a unique filename for the output
    sanitized_url = re.sub(r'[^a-zA-Z0-9_.-]', '_', start_url)
    output_filename = os.path.join(output_directory, f"scraped_data_{sanitized_url[:50]}_{int(time.time())}.json")

    scraper = GenericWebScraper(use_delays=use_delays, max_depth=max_depth, download_directory=download_directory)
    all_extracted_data = []

    try:
        all_extracted_data = scraper.crawl_website(
            start_url=start_url, 
            max_files=max_files
        )
        
        # Save the collected data to a single flat JSON file
        with open(output_filename, 'w', encoding='utf-8') as f:
            json.dump(all_extracted_data, f, indent=2, ensure_ascii=False)
            
        logger.info(f"🎉 Crawling and extraction completed! Data saved to: {output_filename}")
        logger.info(f"📚 Total documents extracted: {len(all_extracted_data)}")
        logger.info(f"📥 Downloaded PDFs saved to: {download_directory}")
        
    except Exception as e:
        logger.error(f"❌ An error occurred during the crawling process: {e}")
    finally:
        scraper.close()

# Example Usage:
if __name__ == "__main__":
    start_url = "https://www.capitol.hawaii.gov/sessions/session2025/bills/"
    output_directory = "output"
    
    # Create the output directory if it doesn't exist
    os.makedirs(output_directory, exist_ok=True)
    
    crawl_and_extract(
        start_url=start_url,
        output_directory=output_directory,
        max_files=50,
        max_depth=2,
        use_delays=True
    )