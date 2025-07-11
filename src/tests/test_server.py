#!/usr/bin/env python3
"""
Simple HTTP server for testing the Course RAG System
Serves HTML interface for testing intelligent query processing and collection management
"""

import http.server
import socketserver
import webbrowser
import threading
import time
import argparse
from pathlib import Path

class TestServer:
    def __init__(self, port=8280):
        self.port = port
        self.server = None
        self.thread = None
        
    def start(self):
        """Start the test server"""
        # Change to tests directory to serve files
        tests_dir = Path(__file__).parent
        original_dir = Path.cwd()
        
        try:
            import os
            os.chdir(tests_dir)
            
            Handler = http.server.SimpleHTTPRequestHandler
            
            # Custom handler to set CORS headers
            class CORSRequestHandler(Handler):
                def end_headers(self):
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
                    self.send_header('Access-Control-Allow-Headers', 'Content-Type')
                    super().end_headers()
                
                def do_OPTIONS(self):
                    self.send_response(200)
                    self.end_headers()
            
            self.server = socketserver.TCPServer(("", self.port), CORSRequestHandler)
            
            print(f"🌐 Course RAG Test Server starting on http://localhost:{self.port}")
            print(f"📁 Serving files from: {tests_dir}")
            print(f"🔗 Open: http://localhost:{self.port}/course_rag_interface.html")
            print("Press Ctrl+C to stop the server")
            
            # Start server in a separate thread
            self.thread = threading.Thread(target=self.server.serve_forever)
            self.thread.daemon = True
            self.thread.start()
            
            # Open browser after a short delay
            def open_browser():
                time.sleep(1)
                webbrowser.open(f"http://localhost:{self.port}/course_rag_interface.html")
            
            browser_thread = threading.Thread(target=open_browser)
            browser_thread.daemon = True
            browser_thread.start()
            
            # Keep main thread alive
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                print("\n🛑 Shutting down test server...")
                self.stop()
                
        finally:
            os.chdir(original_dir)
    
    def stop(self):
        """Stop the test server"""
        if self.server:
            self.server.shutdown()
            self.server.server_close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Course RAG System Test Server')
    parser.add_argument('--port', type=int, default=8280, help='Port to run the server on (default: 8280)')
    args = parser.parse_args()
    
    server = TestServer(port=args.port)
    server.start() 