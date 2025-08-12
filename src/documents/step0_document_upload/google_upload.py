#!/usr/bin/env python3
"""
Google Drive PDF Downloader
Downloads PDF files from Google Drive folders with optional recursive traversal.
"""

import os
import io
import re
import logging
from typing import List, Dict, Optional, Tuple
from urllib.parse import urlparse, parse_qs
from googleapiclient.discovery import build
from google.oauth2 import service_account
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.errors import HttpError
import time

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class GoogleDrivePDFDownloader:
    """
    A class to download PDF files from Google Drive folders.
    """
    
    def __init__(self):
        """
        Initialize the Google Drive downloader.
        
        Args:
            service_account_file: Path to the service account JSON file
        """
        self.scopes = ['https://www.googleapis.com/auth/drive.readonly']
        self.drive_service = None
        # Get the absolute path to the service account file relative to this script
        current_dir = os.path.dirname(os.path.abspath(__file__))
        self.SERVICE_ACCOUNT_FILE = os.path.join(current_dir, 'service_key.json')
        self._initialize_service()
    
    def _initialize_service(self):
        """Initialize the Google Drive service."""
        try:
            credentials = service_account.Credentials.from_service_account_file(
                self.SERVICE_ACCOUNT_FILE, scopes=self.scopes
            )
            self.drive_service = build('drive', 'v3', credentials=credentials)
            logger.info("Google Drive service initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Google Drive service: {e}")
            raise
    
    def extract_folder_id(self, drive_url: str) -> str:
        """
        Extract folder ID from various Google Drive URL formats.
        
        Args:
            drive_url: Google Drive folder URL
            
        Returns:
            Folder ID string
            
        Raises:
            ValueError: If URL format is not recognized
        """
        # Common Google Drive URL patterns
        patterns = [
            r'drive\.google\.com/drive/folders/([a-zA-Z0-9-_]+)',
            r'drive\.google\.com/drive/u/\d+/folders/([a-zA-Z0-9-_]+)',
            r'drive\.google\.com/open\?id=([a-zA-Z0-9-_]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, drive_url)
            if match:
                folder_id = match.group(1)
                logger.info(f"Extracted folder ID: {folder_id}")
                return folder_id
        
        # If no pattern matches, assume the URL itself might be just the ID
        if re.match(r'^[a-zA-Z0-9-_]+$', drive_url):
            logger.info(f"Using provided string as folder ID: {drive_url}")
            return drive_url
            
        raise ValueError(f"Could not extract folder ID from URL: {drive_url}")
    
    def get_folder_contents(self, folder_id: str) -> Tuple[List[Dict], List[Dict]]:
        """
        Get all files and folders in a specific folder.
        
        Args:
            folder_id: Google Drive folder ID
            
        Returns:
            Tuple of (pdf_files, subfolders)
        """
        try:
            # Get PDF files
            pdf_query = f"'{folder_id}' in parents and mimeType='application/pdf' and trashed=false"
            pdf_results = self.drive_service.files().list(
                q=pdf_query,
                fields="files(id, name, size, modifiedTime)",
                pageSize=1000
            ).execute()
            
            pdf_files = pdf_results.get('files', [])
            
            # Get subfolders
            folder_query = f"'{folder_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
            folder_results = self.drive_service.files().list(
                q=folder_query,
                fields="files(id, name)",
                pageSize=1000
            ).execute()
            
            subfolders = folder_results.get('files', [])
            
            logger.info(f"Found {len(pdf_files)} PDF files and {len(subfolders)} subfolders in folder {folder_id}")
            return pdf_files, subfolders
            
        except HttpError as e:
            logger.error(f"Error accessing folder {folder_id}: {e}")
            return [], []
    
    def download_file(self, file_info: Dict, download_path: str, subfolder_path: str = "") -> bool:
        """
        Download a single PDF file.
        
        Args:
            file_info: File information from Google Drive API
            download_path: Base download directory
            subfolder_path: Relative path for subfolder structure
            
        Returns:
            True if download successful, False otherwise
        """
        try:
            file_id = file_info['id']
            file_name = file_info['name']
            
            # Create full directory path
            full_dir_path = os.path.join(download_path, subfolder_path)
            os.makedirs(full_dir_path, exist_ok=True)
            
            # Handle duplicate filenames
            file_path = os.path.join(full_dir_path, file_name)
            counter = 1
            base_name, ext = os.path.splitext(file_name)
            while os.path.exists(file_path):
                new_name = f"{base_name}_{counter}{ext}"
                file_path = os.path.join(full_dir_path, new_name)
                counter += 1
            
            # Download the file
            request = self.drive_service.files().get_media(fileId=file_id)
            with open(file_path, 'wb') as fh:
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
                    if status:
                        progress = int(status.progress() * 100)
                        if progress % 25 == 0:  # Log every 25%
                            logger.info(f"Downloading {file_name}: {progress}%")
            
            file_size = file_info.get('size', 'Unknown')
            logger.info(f"Successfully downloaded: {file_name} ({file_size} bytes)")
            return True
            
        except Exception as e:
            logger.error(f"Error downloading {file_info.get('name', 'unknown')}: {e}")
            return False
    
    def download_pdfs_from_folder(
        self, 
        drive_url: str, 
        download_path: str = "./downloads", 
        recursive: bool = False,
        max_depth: int = 10
    ) -> Dict[str, int]:
        """
        Download all PDF files from a Google Drive folder.
        
        Args:
            drive_url: Google Drive folder URL or folder ID
            download_path: Local directory to save files
            recursive: Whether to recursively download from subfolders
            max_depth: Maximum recursion depth (safety limit)
            
        Returns:
            Dictionary with download statistics
        """
        logger.info(f"Starting PDF download from: {drive_url}")
        logger.info(f"Download path: {download_path}")
        logger.info(f"Recursive: {recursive}")
        
        # Extract folder ID
        try:
            folder_id = self.extract_folder_id(drive_url)
        except ValueError as e:
            logger.error(f"Invalid URL: {e}")
            return {"error": str(e), "downloaded": 0, "failed": 0}
        
        # Create download directory
        os.makedirs(download_path, exist_ok=True)
        
        # Statistics tracking
        stats = {"downloaded": 0, "failed": 0, "folders_processed": 0}
        
        # Process folders (using a queue for iterative approach to avoid deep recursion)
        folder_queue = [(folder_id, "", 0)]  # (folder_id, relative_path, depth)
        processed_folders = set()
        
        while folder_queue:
            current_folder_id, relative_path, depth = folder_queue.pop(0)
            
            # Safety checks
            if current_folder_id in processed_folders:
                logger.warning(f"Skipping already processed folder: {current_folder_id}")
                continue
                
            if depth > max_depth:
                logger.warning(f"Maximum depth ({max_depth}) reached, skipping folder")
                continue
            
            processed_folders.add(current_folder_id)
            stats["folders_processed"] += 1
            
            # Get folder contents
            pdf_files, subfolders = self.get_folder_contents(current_folder_id)
            
            # Download PDF files
            for pdf_file in pdf_files:
                if self.download_file(pdf_file, download_path, relative_path):
                    stats["downloaded"] += 1
                else:
                    stats["failed"] += 1
                
                # Small delay to respect rate limits
                time.sleep(0.1)
            
            # Add subfolders to queue if recursive
            if recursive:
                for subfolder in subfolders:
                    subfolder_path = os.path.join(relative_path, subfolder['name'])
                    folder_queue.append((subfolder['id'], subfolder_path, depth + 1))
        
        logger.info(f"Download complete. Downloaded: {stats['downloaded']}, Failed: {stats['failed']}, Folders processed: {stats['folders_processed']}")
        return stats


# Convenience function for direct usage
def download_pdfs_from_drive(
    drive_url: str,
    download_path: str = "./downloads",
    recursive: bool = False
) -> Dict[str, int]:
    """
    Convenience function to download PDFs from Google Drive.
    
    Args:
        drive_url: Google Drive folder URL or ID
        download_path: Local download directory
        recursive: Whether to download from subfolders recursively
        
    Returns:
        Dictionary with download statistics
    """
    download_path = os.path.join(os.getcwd(), download_path)
    downloader = GoogleDrivePDFDownloader()
    return downloader.download_pdfs_from_folder(drive_url, download_path, recursive)


# Example usage
if __name__ == "__main__":
    # Example usage
    DRIVE_URL = 'https://drive.google.com/drive/folders/12Ymx5EZdt_nM-UqgA-SkAg4NEaKffasm?usp=sharing'
    DOWNLOAD_PATH = '../storage_documents'
    
    try:
        stats = download_pdfs_from_drive(
            drive_url=DRIVE_URL,
            download_path=DOWNLOAD_PATH,
            recursive=True
        )
        print(f"Download completed: {stats}")
    except Exception as e:
        print(f"Error: {e}")
