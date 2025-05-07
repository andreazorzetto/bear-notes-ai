#!/usr/bin/env python3
"""
Bear Notes to ChatGPT Integration
Send Bear notes directly to ChatGPT web interface and receive automated responses
with improved console formatting and enhanced features
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
import signal
import sys
import platform
from pathlib import Path
from datetime import datetime

# Check for optional dependencies for enhanced features
try:
    import colorama
    from colorama import Fore, Back, Style

    colorama.init()
    HAS_COLORS = True
except ImportError:
    HAS_COLORS = False

try:
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich.table import Table

    HAS_RICH = True
    console = Console()
except ImportError:
    HAS_RICH = False


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


class ConsoleFormatter:
    """Format text output for the terminal with better visual appearance"""

    @staticmethod
    def print_header(text, width=80):
        """Print a header with decorative elements"""
        if HAS_RICH:
            console.print(Panel(text, style="bold blue", expand=False))
        elif HAS_COLORS:
            print(f"\n{Fore.BLUE}{Style.BRIGHT}" + "=" * width)
            print(text.center(width))
            print("=" * width + f"{Style.RESET_ALL}\n")
        else:
            print("\n" + "=" * width)
            print(text.center(width))
            print("=" * width + "\n")

    @staticmethod
    def print_subheader(text, width=80):
        """Print a subheader with decorative elements"""
        if HAS_RICH:
            console.print(f"[bold cyan]{text}[/bold cyan]")
        elif HAS_COLORS:
            print(f"\n{Fore.CYAN}{Style.BRIGHT}" + text)
            print("-" * len(text) + f"{Style.RESET_ALL}")
        else:
            print("\n" + text)
            print("-" * len(text))

    @staticmethod
    def print_note_info(note, index=None):
        """Print formatted note information"""
        if HAS_RICH:
            table = Table(show_header=False, box=None, padding=(0, 1))
            table.add_column("Index", style="dim", width=4)
            table.add_column("Details", style="green")
            prefix = f"{index}. " if index is not None else ""
            table.add_row("", f"[bold green]{prefix}{note['title']}[/bold green]")
            table.add_row("", f"[dim]Modified: {note['date_modified']}[/dim]")
            console.print(table)
        elif HAS_COLORS:
            prefix = f"{index}. " if index is not None else ""
            print(f"{Fore.GREEN}{Style.BRIGHT}{prefix}{note['title']}{Style.RESET_ALL}")
            print(f"{Fore.WHITE}{Style.DIM}Modified: {note['date_modified']}{Style.RESET_ALL}")
        else:
            prefix = f"{index}. " if index is not None else ""
            print(f"{prefix}{note['title']}")
            print(f"Modified: {note['date_modified']}")

    @staticmethod
    def print_success(text):
        """Print success message"""
        if HAS_RICH:
            console.print(f"[bold green]✓ {text}[/bold green]")
        elif HAS_COLORS:
            print(f"{Fore.GREEN}{Style.BRIGHT}✓ {text}{Style.RESET_ALL}")
        else:
            print(f"✓ {text}")

    @staticmethod
    def print_error(text):
        """Print error message"""
        if HAS_RICH:
            console.print(f"[bold red]✗ {text}[/bold red]")
        elif HAS_COLORS:
            print(f"{Fore.RED}{Style.BRIGHT}✗ {text}{Style.RESET_ALL}")
        else:
            print(f"✗ {text}")

    @staticmethod
    def print_warning(text):
        """Print warning message"""
        if HAS_RICH:
            console.print(f"[bold yellow]⚠ {text}[/bold yellow]")
        elif HAS_COLORS:
            print(f"{Fore.YELLOW}{Style.BRIGHT}⚠ {text}{Style.RESET_ALL}")
        else:
            print(f"⚠ {text}")

    @staticmethod
    def print_info(text):
        """Print info message"""
        if HAS_RICH:
            console.print(f"[bold blue]ℹ {text}[/bold blue]")
        elif HAS_COLORS:
            print(f"{Fore.BLUE}{Style.BRIGHT}ℹ {text}{Style.RESET_ALL}")
        else:
            print(f"ℹ {text}")

    @staticmethod
    def format_chatgpt_response(response):
        """Format ChatGPT response for display in console, preserving markdown if possible"""
        if HAS_RICH:
            try:
                # Try to render as markdown
                md = Markdown(response)
                console.print(Panel(md, title="ChatGPT Response", border_style="green", expand=False))
            except Exception:
                # Fallback to plain text if markdown parsing fails
                console.print(Panel(response, title="ChatGPT Response", border_style="green", expand=False))
        elif HAS_COLORS:
            print(f"\n{Fore.GREEN}{Style.BRIGHT}ChatGPT Response:{Style.RESET_ALL}")
            print(f"{Fore.WHITE}{'-' * 80}{Style.RESET_ALL}")
            print(response)
            print(f"{Fore.WHITE}{'-' * 80}{Style.RESET_ALL}")
        else:
            print("\nChatGPT Response:")
            print("-" * 80)
            print(response)
            print("-" * 80)

    @staticmethod
    def format_progress_bar(current, total, width=50):
        """Display a progress bar"""
        percent = current / total
        arrow = '■' * int(width * percent)
        spaces = ' ' * (width - len(arrow))

        if HAS_RICH:
            console.print(f"[bold cyan]Progress: [{arrow}{spaces}] {int(percent * 100)}%[/bold cyan]", end='\r')
        elif HAS_COLORS:
            print(f"{Fore.CYAN}{Style.BRIGHT}Progress: [{arrow}{spaces}] {int(percent * 100)}%{Style.RESET_ALL}",
                  end='\r')
        else:
            print(f"Progress: [{arrow}{spaces}] {int(percent * 100)}%", end='\r')

        if current == total:
            print()


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
        self.start_time = None
        self.shutdown_requested = False

        # Set up interrupt handler
        signal.signal(signal.SIGINT, self._handle_interrupt)

    def start(self):
        """Start the local server and wait for a response"""
        handler = self._create_handler()

        # Enable socket reuse to prevent "Address already in use" errors
        socketserver.TCPServer.allow_reuse_address = True

        try:
            # Try to find an available port if the specified one is in use
            port_to_use = self.port
            max_port_attempts = 5

            for attempt in range(max_port_attempts):
                try:
                    self.server = socketserver.TCPServer(("", port_to_use), handler)
                    break
                except OSError as e:
                    if "Address already in use" in str(e) and attempt < max_port_attempts - 1:
                        port_to_use += 1
                        ConsoleFormatter.print_warning(f"Port {self.port + attempt} is in use, trying {port_to_use}...")
                    else:
                        raise

            if port_to_use != self.port:
                self.port = port_to_use
                ConsoleFormatter.print_success(f"Using port {self.port} instead")

            ConsoleFormatter.print_header(f"Bear Notes to ChatGPT Server")
            ConsoleFormatter.print_info(f"Server started at http://localhost:{self.port}")
            ConsoleFormatter.print_info("Waiting for the client to fetch the content...")
            ConsoleFormatter.print_info("Please navigate to https://chatgpt.com in your browser")
            ConsoleFormatter.print_info("The server will automatically stop after receiving the response")
            ConsoleFormatter.print_info("(You can also press Ctrl+C to stop the server manually)")

            # Set a short timeout to allow checking for response_received flag
            self.server.timeout = 1.0

            # Set maximum runtime
            self.start_time = time.time()
            last_status_time = self.start_time
            status_interval = 10  # Show status every 10 seconds

            # Continue serving until we receive a response or timeout
            while not self.response_received and not self.shutdown_requested:
                if time.time() - self.start_time > self.timeout:
                    ConsoleFormatter.print_warning(f"\nTimeout after {self.timeout} seconds. Shutting down server...")
                    break

                # Show periodic status updates
                current_time = time.time()
                if current_time - last_status_time >= status_interval:
                    elapsed = int(current_time - self.start_time)
                    remaining = self.timeout - elapsed
                    ConsoleFormatter.format_progress_bar(elapsed, self.timeout)
                    last_status_time = current_time

                self.server.handle_request()

        except KeyboardInterrupt:
            ConsoleFormatter.print_warning("\nServer stopped manually.")
        except OSError as e:
            if "Address already in use" in str(e):
                ConsoleFormatter.print_error(f"\nError: All attempted ports are in use.")
                ConsoleFormatter.print_info("Another instance may be running. Please wait a moment and try again.")
            else:
                ConsoleFormatter.print_error(f"\nServer error: {e}")
        finally:
            if self.server:
                self.server.server_close()

        # Print the response if we got one
        if self.response_received and self.chatgpt_response:
            self._print_formatted_response()
            return self.chatgpt_response
        return None

    def _print_formatted_response(self):
        """Print the response in a nicely formatted way"""
        ConsoleFormatter.format_chatgpt_response(self.chatgpt_response)

        # Calculate and display timing information
        if self.start_time:
            elapsed_time = time.time() - self.start_time
            ConsoleFormatter.print_info(f"Response received in {elapsed_time:.2f} seconds")

    def _handle_interrupt(self, sig, frame):
        """Handle keyboard interrupt gracefully"""
        self.shutdown_requested = True
        ConsoleFormatter.print_warning("\nShutdown requested. Cleaning up...")

    def _create_handler(self):
        """Create and return the HTTP request handler class"""
        prompt_content = self.prompt_content
        prompt_question = self.prompt_question
        server_instance = self  # Reference to the server instance

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
                    ConsoleFormatter.print_success("Content served successfully! Waiting for response...")
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

                        # Save the response in the server instance
                        server_instance.chatgpt_response = response_text
                        server_instance.response_received = True

                        # Send success response
                        self.send_response(200)
                        self.send_header('Content-type', 'application/json')
                        self.send_header('Access-Control-Allow-Origin', '*')
                        self.end_headers()

                        self.wfile.write(json.dumps({'success': True}).encode())
                        ConsoleFormatter.print_success("Response received! Server will stop shortly...")

                        # Graceful shutdown after a short delay
                        def shutdown_server():
                            time.sleep(0.5)  # Give time for response to be sent
                            server_instance.server.shutdown()

                        threading.Thread(target=shutdown_server, daemon=True).start()

                    except Exception as e:
                        self.send_response(400)
                        self.send_header('Content-type', 'application/json')
                        self.send_header('Access-Control-Allow-Origin', '*')
                        self.end_headers()

                        self.wfile.write(json.dumps({
                            'success': False,
                            'error': str(e)
                        }).encode())
                        ConsoleFormatter.print_error(f"Error processing response: {e}")
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
        """Format notes content, keeping question separate for the userscript"""
        combined_content = "\n\n===== NOTE SEPARATOR =====\n\n".join(
            [f"NOTE: {note['title']}\n\n{note['content']}" for note in notes]
        )

        # Return just the content without the question
        # The question will be sent separately in the JSON
        return combined_content

    @staticmethod
    def save_response_to_file(response, question, notes):
        """Save the response and context to a file"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Create a more descriptive filename based on the question
        # Remove any characters that aren't safe for filenames
        question_slug = re.sub(r'[^\w\s-]', '', question)[:40].strip().replace(' ', '_')
        filename = f"chatgpt_response_{question_slug}_{timestamp}.md"

        with open(filename, 'w') as f:
            # Write header with metadata
            f.write(f"# ChatGPT Response: {question}\n\n")
            f.write(f"*Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n\n")

            # Write the question
            f.write("## Question\n\n")
            f.write(f"{question}\n\n")

            # Write the response
            f.write("## Response\n\n")
            f.write(f"{response}\n\n")

            # Write the source note information
            f.write("## Source Notes\n\n")
            for i, note in enumerate(notes, 1):
                f.write(f"### {i}. {note['title']}\n\n")
                f.write(f"*Last Modified: {note['date_modified']}*\n\n")
                # Only write a small excerpt of the content to keep the file manageable
                content_excerpt = note['content'][:500]
                if len(note['content']) > 500:
                    content_excerpt += "...\n[Content truncated]"
                f.write(f"```\n{content_excerpt}\n```\n\n")

        return filename


def open_browser_with_retry(url, max_retries=3, retry_delay=2):
    """Open the browser with retry logic"""
    for attempt in range(max_retries):
        try:
            webbrowser.open(url)
            return True
        except Exception as e:
            if attempt < max_retries - 1:
                ConsoleFormatter.print_warning(f"Failed to open browser: {e}. Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
            else:
                ConsoleFormatter.print_error(f"Failed to open browser after {max_retries} attempts: {e}")
                return False


def check_environment():
    """Check if all requirements are met and provide suggestions for better experience"""
    issues = []
    suggestions = []

    # Check operating system
    if platform.system() != "Darwin":
        issues.append("This script is designed for macOS where Bear Notes is available.")

    # Check if Bear is installed
    bear_app_path = "/Applications/Bear.app"
    if not os.path.exists(bear_app_path):
        issues.append("Bear Notes app not found in /Applications. Is it installed?")

    # Check for enhancement libraries
    if not HAS_COLORS:
        suggestions.append("Install 'colorama' for colored console output: pip install colorama")
    if not HAS_RICH:
        suggestions.append("Install 'rich' for enhanced console formatting: pip install rich")

    # Check for Tampermonkey extension
    # (This is a user check, we can't programmatically check browser extensions)
    suggestions.append("Ensure Tampermonkey browser extension is installed and the userscript is loaded")

    # Print any issues
    if issues:
        ConsoleFormatter.print_header("Environment Check - Issues Found")
        for issue in issues:
            ConsoleFormatter.print_error(issue)

    # Print suggestions
    if suggestions:
        ConsoleFormatter.print_subheader("Suggestions for better experience")
        for suggestion in suggestions:
            ConsoleFormatter.print_info(suggestion)

    # Return True if no critical issues, False otherwise
    return len(issues) == 0


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
    parser.add_argument("--save", action="store_true", help="Save the response to a file")
    parser.add_argument("--check", action="store_true", help="Check environment for proper setup")
    parser.add_argument("--version", action="version", version="Bear to ChatGPT v2.0")

    args = parser.parse_args()

    # Run environment check if requested
    if args.check:
        check_environment()
        return

    # Validate arguments
    if not (args.tag or args.keyword or args.url):
        parser.error("At least one search option (--tag, --keyword, or --url) is required")

    # Process notes
    try:
        ConsoleFormatter.print_header("Bear Notes to ChatGPT")

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
            ConsoleFormatter.print_success(f"Found note: {title}")
        else:
            # Search for notes
            ConsoleFormatter.print_subheader("Searching Notes")

            search_desc = []
            if args.tag:
                search_desc.append(f"tag '#{args.tag}'")
            if args.keyword:
                search_desc.append(f"keyword '{args.keyword}'")

            ConsoleFormatter.print_info(f"Searching for notes with {' and '.join(search_desc)}...")

            notes = bear_db.search_notes(tag=args.tag, keyword=args.keyword, limit=args.limit)
            matching_notes.extend(notes)

            # Print search results
            if notes:
                ConsoleFormatter.print_success(f"Found {len(notes)} matching notes")
            else:
                ConsoleFormatter.print_warning("No matching notes found")

            # Apply explicit limit if provided
            if args.limit and len(matching_notes) > args.limit:
                ConsoleFormatter.print_info(f"Limited to {args.limit} of {len(matching_notes)} notes")
                matching_notes = matching_notes[:args.limit]

    except Exception as e:
        ConsoleFormatter.print_error(f"Error: {e}")
        return

    if not matching_notes:
        ConsoleFormatter.print_error("No matching notes found.")
        return

    # Display matching notes
    ConsoleFormatter.print_subheader("Matching Notes")
    for i, note in enumerate(matching_notes, 1):
        ConsoleFormatter.print_note_info(note, i)

    # Just list the notes if requested
    if args.list:
        return

    # Ask for confirmation before processing
    if not args.yes:
        try:
            confirmation = input(f"\nFound {len(matching_notes)} matching notes. Process them? (y/n) [y]: ")
            if confirmation.lower() and confirmation.lower() != 'y':
                ConsoleFormatter.print_info("Operation cancelled.")
                return
        except KeyboardInterrupt:
            print()  # Add a newline after ^C
            ConsoleFormatter.print_info("Operation cancelled.")
            return

    # Process the notes
    ConsoleFormatter.print_subheader("Processing Notes")
    ConsoleFormatter.print_info(f"Question: {args.question}")

    content = NotesProcessor.format_prompt(matching_notes, args.question)
    question = args.question  # Keep question separate from content

    # Open ChatGPT in the browser
    ConsoleFormatter.print_info("Opening ChatGPT in your default browser...")
    success = open_browser_with_retry("https://chatgpt.com/")
    if not success:
        ConsoleFormatter.print_warning(
            "Failed to open browser automatically. Please open https://chatgpt.com/ manually.")

    # Start the local server to provide the content
    server = LocalServer(content, question, port=args.port, timeout=args.timeout)
    ConsoleFormatter.print_info(f"Starting local server on port {args.port}...")
    response = server.start()

    # Save the response to a file if requested
    if response and args.save:
        filename = NotesProcessor.save_response_to_file(response, question, matching_notes)
        ConsoleFormatter.print_success(f"Response saved to {filename}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()  # Add a newline after ^C
        ConsoleFormatter.print_info("Operation cancelled by user.")
        sys.exit(0)