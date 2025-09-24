#!/usr/bin/env python3
"""
Simplified web-based search UI for local code search.
"""

import sys
import os
from pathlib import Path
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse
import threading
import webbrowser
import time

# Add the tools directory to the path
sys.path.insert(0, str(Path(__file__).parent))

from local_code_search import search_code

class SimpleSearchHandler(BaseHTTPRequestHandler):
    """Simplified HTTP handler for the search UI."""
    
    def do_GET(self):
        """Handle GET requests."""
        print(f"DEBUG: GET request to {self.path}")
        
        if self.path == '/':
            self.serve_html()
        elif self.path.startswith('/search'):
            self.handle_search()
        else:
            self.send_error(404, "Not Found")
    
    def serve_html(self):
        """Serve the main HTML page."""
        html = """<!DOCTYPE html>
<html>
<head>
    <title>UF Flow Code Search</title>
    <style>
        body { font-family: Arial, sans-serif; max-width: 800px; margin: 50px auto; padding: 20px; }
        .search-box { margin: 20px 0; }
        input, select, button { padding: 10px; margin: 5px; font-size: 16px; }
        button { background: #007cba; color: white; border: none; border-radius: 4px; cursor: pointer; }
        button:hover { background: #005a8b; }
        .results { margin-top: 20px; }
        .result { border: 1px solid #ddd; padding: 10px; margin: 10px 0; border-radius: 4px; }
        .error { background: #fee; color: #c33; padding: 10px; border-radius: 4px; }
    </style>
</head>
<body>
    <h1>🔍 UF Flow Code Search</h1>
    
    <div class="search-box">
        <input type="text" id="query" placeholder="Enter search query..." style="width: 300px;">
        <select id="searchType">
            <option value="text">Text</option>
            <option value="function">Function</option>
            <option value="class">Class</option>
            <option value="import">Import</option>
            <option value="symbol">Symbol</option>
        </select>
        <button onclick="search()">Search</button>
    </div>
    
    <div id="results" class="results"></div>
    
    <script>
        function search() {
            const query = document.getElementById('query').value;
            const searchType = document.getElementById('searchType').value;
            
            if (!query) {
                alert('Please enter a search query');
                return;
            }
            
            document.getElementById('results').innerHTML = '<p>Searching...</p>';
            
            const url = '/search?query=' + encodeURIComponent(query) + '&search_type=' + searchType;
            console.log('Fetching:', url);
            
            fetch(url)
                .then(response => {
                    console.log('Response status:', response.status);
                    if (!response.ok) {
                        throw new Error('HTTP ' + response.status);
                    }
                    return response.text();
                })
                .then(text => {
                    console.log('Response text:', text.substring(0, 200));
                    try {
                        const data = JSON.parse(text);
                        displayResults(data);
                    } catch (e) {
                        document.getElementById('results').innerHTML = '<div class="error">JSON Parse Error: ' + e.message + '<br>Response: ' + text.substring(0, 500) + '</div>';
                    }
                })
                .catch(error => {
                    document.getElementById('results').innerHTML = '<div class="error">Search failed: ' + error.message + '</div>';
                });
        }
        
        function displayResults(data) {
            const resultsDiv = document.getElementById('results');
            
            if (!data.success) {
                resultsDiv.innerHTML = '<div class="error">Error: ' + (data.error || 'Unknown error') + '</div>';
                return;
            }
            
            if (data.total_results === 0) {
                resultsDiv.innerHTML = '<p>No results found.</p>';
                return;
            }
            
            let html = '<h3>Found ' + data.total_results + ' results:</h3>';
            
            data.results.forEach((result, i) => {
                html += '<div class="result">';
                html += '<strong>' + result.file_path + ':' + result.line_number + '</strong><br>';
                html += '<code>' + result.content + '</code>';
                html += '</div>';
            });
            
            resultsDiv.innerHTML = html;
        }
        
        // Allow Enter key to trigger search
        document.getElementById('query').addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                search();
            }
        });
    </script>
</body>
</html>"""
        
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(html.encode())
    
    def handle_search(self):
        """Handle search requests."""
        print(f"DEBUG: Handling search request: {self.path}")
        
        try:
            # Parse query parameters
            parsed_url = urllib.parse.urlparse(self.path)
            query_params = urllib.parse.parse_qs(parsed_url.query)
            
            print(f"DEBUG: Query params: {query_params}")
            
            # Extract parameters
            query = query_params.get('query', [''])[0]
            search_type = query_params.get('search_type', ['text'])[0]
            file_pattern = query_params.get('file_pattern', [''])[0] or None
            max_results = int(query_params.get('max_results', ['20'])[0])
            
            print(f"DEBUG: Search - query='{query}', type='{search_type}', pattern='{file_pattern}'")
            
            # Perform search
            result = search_code(
                query=query,
                search_type=search_type,
                file_pattern=file_pattern,
                max_results=max_results
            )
            
            print(f"DEBUG: Search result: {result.get('total_results', 0)} results")
            
        except Exception as e:
            print(f"DEBUG: Search error: {e}")
            result = {
                "success": False,
                "error": str(e),
                "results": [],
                "total_results": 0
            }
        
        # Send JSON response
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        
        json_response = json.dumps(result)
        print(f"DEBUG: Sending JSON response: {json_response[:100]}...")
        self.wfile.write(json_response.encode())
    
    def log_message(self, format, *args):
        """Override to add debug logging."""
        print(f"DEBUG: {format % args}")

def start_simple_search_ui(port=8081):
    """Start the simplified search UI web server."""
    server = HTTPServer(('localhost', port), SimpleSearchHandler)
    
    print(f"🚀 Starting Simple UF Flow Code Search UI...")
    print(f"📱 Web interface: http://localhost:{port}")
    print(f"🔍 Search your codebase!")
    print(f"⏹️  Press Ctrl+C to stop")
    
    # Open browser after a short delay
    def open_browser():
        time.sleep(1)
        webbrowser.open(f'http://localhost:{port}')
    
    browser_thread = threading.Thread(target=open_browser)
    browser_thread.daemon = True
    browser_thread.start()
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 Stopping search UI...")
        server.shutdown()

if __name__ == "__main__":
    import sys
    
    port = 8081
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            print("Invalid port number. Using default port 8081.")
    
    start_simple_search_ui(port)
