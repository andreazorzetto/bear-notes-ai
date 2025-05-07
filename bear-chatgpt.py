#!/usr/bin/env python3
"""
Bear Notes to ChatGPT Integration
Send Bear notes directly to ChatGPT web interface and receive automated responses
"""

import sqlite3
import argparse
import os
import re
import time
import webbrowser
import json
import urllib.parse
import http.server
import socketserver
import socket
import threading
from pathlib import Path


class BearDB:
    """Access and query the Bear Notes database"""

    DB_PATH = os.path.expanduser(
        "~/Library/Group Containers/9K33E3U3T4.net.shinyfrog.bear/Application Data/database.sqlite"
    )

    def __init__(self):
        if not os.path.exists(self.DB_PATH):
            raise FileNotFoundError(f"Bear database not found at {self.DB_PATH}")

    def query(self, sql, params=()):
        """Execute a query on the Bear database"""
        with sqlite3.connect(self.DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            return cursor.fetchall()

    def get_note_by_id(self, note_id):
        """Retrieve a note by its ID"""
        note = self.query("""
            SELECT ZUNIQUEIDENTIFIER, ZTITLE, ZTEXT 
            FROM ZSFNOTE 
            WHERE ZUNIQUEIDENTIFIER = ? AND ZTRASHED = 0
        """, (note_id,))

        if not note:
            raise ValueError(f"No note found with ID '{note_id}'")
        return note[0]  # Return the first (and only) note

    def search_notes(self, tag=None, keyword=None, limit=None):
        """Search for notes by tag, keyword, or both"""
        sql = None
        params = []

        if tag and keyword:
            sql = """
                SELECT ZUNIQUEIDENTIFIER, ZTITLE, ZTEXT, ZMODIFICATIONDATE 
                FROM ZSFNOTE 
                WHERE ZTEXT LIKE ? AND (ZTEXT LIKE ? OR ZTITLE LIKE ?) 
                AND ZTRASHED = 0
                ORDER BY ZMODIFICATIONDATE DESC
            """
            params = [f"%#{tag}%", f"%{keyword}%", f"%{keyword}%"]
        elif tag:
            sql = """
                SELECT ZUNIQUEIDENTIFIER, ZTITLE, ZTEXT, ZMODIFICATIONDATE 
                FROM ZSFNOTE 
                WHERE ZTEXT LIKE ? AND ZTRASHED = 0
                ORDER BY ZMODIFICATIONDATE DESC
            """
            params = [f"%#{tag}%"]
        elif keyword:
            sql = """
                SELECT ZUNIQUEIDENTIFIER, ZTITLE, ZTEXT, ZMODIFICATIONDATE 
                FROM ZSFNOTE 
                WHERE (ZTEXT LIKE ? OR ZTITLE LIKE ?) AND ZTRASHED = 0
                ORDER BY ZMODIFICATIONDATE DESC
            """
            params = [f"%{keyword}%", f"%{keyword}%"]

        if limit:
            sql += f" LIMIT {limit}"

        return self.format_notes(self.query(sql, params))

    @staticmethod
    def format_notes(db_notes):
        """Format database results into usable note objects"""
        if not db_notes:
            return []

        formatted_notes = []
        for note_id, title, content, timestamp in db_notes:
            # Convert from Cocoa Core Data timestamp to Unix timestamp
            unix_timestamp = timestamp - 978307200
            date_modified = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(unix_timestamp))
            formatted_notes.append({
                'id': note_id,
                'title': title,
                'content': content,
                'date_modified': date_modified
            })
        return formatted_notes

    @staticmethod
    def extract_note_id_from_url(callback_url):
        """Extract note ID from Bear callback URL"""
        if not callback_url.startswith("bear://"):
            raise ValueError("Invalid Bear callback URL format")

        match = re.search(r'id=([^&]+)', callback_url)
        if not match:
            raise ValueError("No note ID found in the callback URL")

        return urllib.parse.unquote(match.group(1))


class LocalServer:
    """HTTP server to provide content to the automation client and receive responses"""

    def __init__(self, prompt_content, prompt_question, port=8765, timeout=600):
        self.prompt_content = prompt_content
        self.prompt_question = prompt_question
        self.port = port
        self.timeout = timeout  # Maximum runtime in seconds
        self.chatgpt_response = None
        self.response_received = False
        self.server = None
        self.metrics = None
        self.start_time = None

    def start(self):
        """Start the local server and wait for a response"""
        import time
        from colorama import init, Fore, Style

        # Initialize colorama for colored terminal output
        init()

        handler = self._create_handler()

        # Enable socket reuse to prevent "Address already in use" errors
        socketserver.TCPServer.allow_reuse_address = True

        try:
            self.server = socketserver.TCPServer(("", self.port), handler)
            self.start_time = time.time()

            # Print server info with colors
            print(f"\n{Fore.GREEN}{'=' * 80}{Style.RESET_ALL}")
            print(f"{Fore.CYAN}Bear Notes to ChatGPT Server{Style.RESET_ALL}")
            print(f"{Fore.GREEN}{'-' * 80}{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}Server started at{Style.RESET_ALL} http://localhost:{self.port}")
            print(f"{Fore.YELLOW}Content size:{Style.RESET_ALL} {len(self.prompt_content):,} characters")
            print(f"{Fore.YELLOW}Question:{Style.RESET_ALL} \"{self.prompt_question}\"")
            print(f"{Fore.YELLOW}Timeout:{Style.RESET_ALL} {self.timeout} seconds")
            print(f"{Fore.GREEN}{'-' * 80}{Style.RESET_ALL}")
            print(f"{Fore.CYAN}Waiting for the client to fetch the content...{Style.RESET_ALL}")
            print(f"Please navigate to {Fore.CYAN}https://chatgpt.com{Style.RESET_ALL} in your browser")
            print(f"The server will automatically stop after receiving the response")
            print(f"(You can also press {Fore.RED}Ctrl+C{Style.RESET_ALL} to stop the server manually)")
            print(f"{Fore.GREEN}{'=' * 80}{Style.RESET_ALL}")

            # Set a short timeout to allow checking for response_received flag
            self.server.timeout = 1.0

            # Set maximum runtime
            start_time = time.time()
            last_update = start_time
            dots = 0

            # Continue serving until we receive a response or timeout
            while not self.response_received:
                now = time.time()
                elapsed = now - start_time

                # Update waiting animation every 2 seconds
                if now - last_update > 2.0:
                    dots = (dots + 1) % 4
                    dot_str = '.' * dots
                    elapsed_str = f"{int(elapsed)}s elapsed"
                    print(
                        f"\r{Fore.CYAN}Waiting for response{dot_str.ljust(4)} {Fore.YELLOW}[{elapsed_str}]{Style.RESET_ALL}",
                        end='')
                    last_update = now

                if elapsed > self.timeout:
                    print(
                        f"\n\n{Fore.RED}Timeout after {self.timeout} seconds. Shutting down server...{Style.RESET_ALL}")
                    break

                self.server.handle_request()

        except KeyboardInterrupt:
            print(f"\n\n{Fore.YELLOW}Server stopped manually.{Style.RESET_ALL}")
        except OSError as e:
            if "Address already in use" in str(e):
                print(f"\n\n{Fore.RED}Error: Port {self.port} is already in use.{Style.RESET_ALL}")
                print(
                    f"{Fore.YELLOW}Another instance may be running. Please wait a moment and try again.{Style.RESET_ALL}")
            else:
                print(f"\n\n{Fore.RED}Server error: {e}{Style.RESET_ALL}")
        finally:
            if self.server:
                self.server.server_close()

        # Print the response if we got one
        if self.response_received and self.chatgpt_response:
            self._print_formatted_response()
            return self.chatgpt_response
        return None

    def _print_formatted_response(self):
        """Print the response in a nicely formatted way with metrics"""
        from colorama import Fore, Style
        import time

        separator = "=" * 80
        metrics_str = ""

        # Calculate total processing time
        total_time = time.time() - self.start_time

        # Format metrics if available
        if self.metrics:
            js_time = self.metrics.get('totalTime', 0) / 1000  # Convert from ms to seconds
            chunk_count = max(self.metrics.get('chunkCount', 1), 1)  # Ensure minimum of 1 to avoid division by zero

            metrics_str = f"""
    {Fore.CYAN}PROCESSING METRICS:{Style.RESET_ALL}
    {Fore.YELLOW}Total processing time:{Style.RESET_ALL} {total_time:.2f} seconds
    {Fore.YELLOW}JavaScript processing time:{Style.RESET_ALL} {js_time:.2f} seconds
    {Fore.YELLOW}Server overhead time:{Style.RESET_ALL} {(total_time - js_time):.2f} seconds
    {Fore.YELLOW}Chunks processed:{Style.RESET_ALL} {chunk_count}
    {Fore.YELLOW}Average time per chunk:{Style.RESET_ALL} {(js_time / chunk_count):.2f} seconds
    """

        print(f"\n{Fore.GREEN}{separator}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}CHATGPT RESPONSE:{Style.RESET_ALL}")
        print(f"{Fore.GREEN}{'-' * 80}{Style.RESET_ALL}")
        print(self.chatgpt_response)  # Print the response, preserving formatting
        print(f"{Fore.GREEN}{separator}{Style.RESET_ALL}")

        if metrics_str:
            print(metrics_str)
            print(f"{Fore.GREEN}{separator}{Style.RESET_ALL}")

    def _create_handler(self):
        """Create and return the HTTP request handler class"""
        prompt_content = self.prompt_content
        prompt_question = self.prompt_question
        server_instance = self  # Reference to the server instance

        from colorama import Fore, Style
        import time

        class CustomHandler(http.server.SimpleHTTPRequestHandler):
            def do_GET(self):
                if self.path == '/content':
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()

                    response = json.dumps({
                        'content': prompt_content,
                        'question': prompt_question,
                        'timestamp': time.time()
                    })

                    self.wfile.write(response.encode())
                    print(f"\n{Fore.GREEN}Content served successfully! {Style.RESET_ALL}")
                    print(f"{Fore.CYAN}Waiting for response...{Style.RESET_ALL}")
                else:
                    self.send_response(404)
                    self.end_headers()
                    self.wfile.write(b'Not found')

            def do_POST(self):
                if self.path == '/response':
                    content_length = int(self.headers['Content-Length'])
                    post_data = self.rfile.read(content_length)

                    try:
                        data = json.loads(post_data.decode('utf-8'))
                        response_text = data.get('response', '')
                        metrics = data.get('metrics', {})

                        acknowledgment_patterns = [
                            r'Acknowledged\.\s+Waiting for Chunk \d+\/\d+\.',
                            r'Received Chunk \d+\/\d+\.\s+Awaiting the final part\.',
                            r'Waiting for Chunk \d+\/\d+\.',
                            r'Chunk \d+\/\d+ received\.',
                            r'BEGIN RAW NOTES DATA',  # Don't accept if it just contains the data
                        ]

                        is_acknowledgment = any(
                            re.search(pattern, response_text) for pattern in acknowledgment_patterns)

                        if is_acknowledgment:
                            # This is not the final response - acknowledge but don't shut down
                            self.send_response(200)
                            self.send_header('Content-type', 'application/json')
                            self.send_header('Access-Control-Allow-Origin', '*')
                            self.end_headers()
                            self.wfile.write(json.dumps({'success': True, 'acknowledgment': True}).encode())
                            print(f"\nReceived intermediate response; waiting for final response...")
                            return

                        # Save the actual final response in the server instance
                        server_instance.chatgpt_response = response_text
                        server_instance.metrics = metrics
                        server_instance.response_received = True

                        # Send success response
                        self.send_response(200)
                        self.send_header('Content-type', 'application/json')
                        self.send_header('Access-Control-Allow-Origin', '*')
                        self.end_headers()

                        self.wfile.write(json.dumps({'success': True}).encode())
                        print(f"\nResponse received! Server will stop shortly...")

                        # Graceful shutdown after a short delay
                        def shutdown_server():
                            time.sleep(0.5)  # Give time for response to be sent
                            server_instance.server.shutdown()

                        threading.Thread(target=shutdown_server, daemon=True).start()

                    except Exception as e:
                        print(f"\n{Fore.RED}Error processing response: {e}{Style.RESET_ALL}")
                        self.send_response(400)
                        self.send_header('Content-type', 'application/json')
                        self.send_header('Access-Control-Allow-Origin', '*')
                        self.end_headers()

                        self.wfile.write(json.dumps({
                            'success': False,
                            'error': str(e)
                        }).encode())
                else:
                    self.send_response(404)
                    self.end_headers()
                    self.wfile.write(b'Not found')

            def do_OPTIONS(self):
                self.send_response(200)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
                self.send_header('Access-Control-Allow-Headers', 'Content-Type')
                self.end_headers()

            def log_message(self, format, *args):
                # Suppress detailed log messages
                return

        return CustomHandler


class NotesProcessor:
    """Process Bear notes content for ChatGPT"""

    @staticmethod
    def format_prompt(notes, question):
        """Format notes content with clear boundaries"""
        combined_content = "\n\n===== NOTE ENTRY SEPARATOR =====\n\n".join(
            [f"NOTE: {note['title']}\n{note['content']}" for note in notes]
        )

        return combined_content


def main():
    parser = argparse.ArgumentParser(description="Send Bear notes to ChatGPT")

    # Search options
    search_group = parser.add_argument_group('Search Options')
    search_group.add_argument("-t", "--tag", help="Tag to search for")
    search_group.add_argument("-k", "--keyword", help="Keyword to search for")
    search_group.add_argument("-u", "--url", help="Bear callback URL")

    # Other options
    parser.add_argument("-q", "--question", help="Question to ask about the notes", required=True)
    parser.add_argument("-l", "--list", action="store_true", help="Just list matching notes, don't process")
    parser.add_argument("--limit", type=int, help="Limit the number of notes to process")
    parser.add_argument("-y", "--yes", action="store_true", help="Process notes without confirmation")
    parser.add_argument("--port", type=int, default=8765, help="Port for the local server")
    parser.add_argument("--timeout", type=int, default=600, help="Maximum server runtime in seconds")

    args = parser.parse_args()

    # Validate arguments
    if not (args.tag or args.keyword or args.url):
        parser.error("At least one search option (--tag, --keyword, or --url) is required")

    # Process notes
    try:
        bear_db = BearDB()
        matching_notes = []

        if args.url:
            note_id = BearDB.extract_note_id_from_url(args.url)
            note_id, title, content = bear_db.get_note_by_id(note_id)
            matching_notes.append({
                'id': note_id,
                'title': title,
                'content': content,
                'date_modified': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
            })
            print(f"Found note: {title}")
        else:
            # Search for notes
            notes = bear_db.search_notes(tag=args.tag, keyword=args.keyword, limit=args.limit)
            matching_notes.extend(notes)

            # Print search results
            if args.tag and args.keyword:
                print(f"Found {len(notes)} notes with tag #{args.tag} and keyword '{args.keyword}'")
            elif args.tag:
                print(f"Found {len(notes)} notes with tag #{args.tag}")
            elif args.keyword:
                print(f"Found {len(notes)} notes with keyword '{args.keyword}'")

            # Apply explicit limit if provided
            if args.limit and len(matching_notes) > args.limit:
                print(f"\nLIMITED TO {args.limit} OF {len(matching_notes)} NOTES\n")
                matching_notes = matching_notes[:args.limit]

    except Exception as e:
        print(f"Error: {e}")
        return

    if not matching_notes:
        print("No matching notes found.")
        return

    # Display matching notes
    print("\nMatching Notes:")
    for i, note in enumerate(matching_notes, 1):
        print(f"{i}. {note['title']} (Modified: {note['date_modified']})")

    # Just list the notes if requested
    if args.list:
        return

    # Ask for confirmation before processing
    if not args.yes:
        confirmation = input(f"\nFound {len(matching_notes)} matching notes. Process them? (y/n) [y]: ")
        if confirmation.lower() and confirmation.lower() != 'y':
            print("Operation cancelled.")
            return

    # Process the notes
    content = NotesProcessor.format_prompt(matching_notes, args.question)
    question = args.question  # Keep question separate from content

    # Open ChatGPT in the browser
    print("\nOpening ChatGPT in your default browser...")
    webbrowser.open("https://chatgpt.com/")

    # Start the local server to provide the content
    server = LocalServer(content, question, port=args.port, timeout=args.timeout)
    print(f"\nStarting local server on port {args.port}...")
    print("Starting the automation process. The server is ready to serve content and receive responses.")
    response = server.start()

    # Optional: Save the response to a file
    # if response:
    #     with open('chatgpt_response.txt', 'w') as f:
    #         f.write(response)
    #     print("Response saved to chatgpt_response.txt")


if __name__ == "__main__":
    main()