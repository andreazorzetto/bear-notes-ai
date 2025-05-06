#!/usr/bin/env python3
"""
Bear Notes to ChatGPT Integration
Send Bear notes directly to ChatGPT web interface via Tampermonkey
"""

import sqlite3
import argparse
import os
import re
import time
import webbrowser
import tempfile
import platform
import sys
import json
import urllib.parse
import http.server
import socketserver
from typing import List, Dict, Any
from pathlib import Path


class BearNotesProcessor:
    def __init__(self):
        """Initialize the Bear Notes processor"""
        self.bear_db_path = os.path.expanduser(
            "~/Library/Group Containers/9K33E3U3T4.net.shinyfrog.bear/Application Data/database.sqlite"
        )

    def check_bear_db_exists(self):
        """Check if the Bear database exists"""
        return os.path.exists(self.bear_db_path)

    def get_note_by_id(self, note_id):
        """Get a specific Bear note by its ID"""
        if not self.check_bear_db_exists():
            raise FileNotFoundError(f"Bear database not found at {self.bear_db_path}")

        conn = sqlite3.connect(self.bear_db_path)
        cursor = conn.cursor()
        query = """
        SELECT ZUNIQUEIDENTIFIER, ZTITLE, ZTEXT 
        FROM ZSFNOTE 
        WHERE ZUNIQUEIDENTIFIER = ? AND ZTRASHED = 0
        """
        cursor.execute(query, (note_id,))
        note = cursor.fetchone()
        conn.close()

        if not note:
            raise ValueError(f"No note found with ID '{note_id}'")
        return note

    def extract_note_id_from_url(self, callback_url):
        """Extract note ID from a Bear callback URL"""
        if not callback_url.startswith("bear://"):
            raise ValueError("Invalid Bear callback URL format")

        match = re.search(r'id=([^&]+)', callback_url)
        if not match:
            raise ValueError("No note ID found in the callback URL")

        note_id = match.group(1)
        return urllib.parse.unquote(note_id)

    def search_notes_by_tag(self, tag):
        """Search Bear notes by tag"""
        if not self.check_bear_db_exists():
            raise FileNotFoundError(f"Bear database not found at {self.bear_db_path}")

        conn = sqlite3.connect(self.bear_db_path)
        cursor = conn.cursor()
        tag_pattern = f"%#{tag}%"
        query = """
        SELECT ZUNIQUEIDENTIFIER, ZTITLE, ZTEXT, ZMODIFICATIONDATE 
        FROM ZSFNOTE 
        WHERE ZTEXT LIKE ? AND ZTRASHED = 0
        ORDER BY ZMODIFICATIONDATE DESC
        """
        cursor.execute(query, (tag_pattern,))
        notes = cursor.fetchall()
        conn.close()

        return self._format_notes(notes)

    def search_notes_by_keyword(self, keyword):
        """Search Bear notes by keyword"""
        if not self.check_bear_db_exists():
            raise FileNotFoundError(f"Bear database not found at {self.bear_db_path}")

        conn = sqlite3.connect(self.bear_db_path)
        cursor = conn.cursor()
        keyword_pattern = f"%{keyword}%"
        query = """
        SELECT ZUNIQUEIDENTIFIER, ZTITLE, ZTEXT, ZMODIFICATIONDATE 
        FROM ZSFNOTE 
        WHERE (ZTEXT LIKE ? OR ZTITLE LIKE ?) AND ZTRASHED = 0
        ORDER BY ZMODIFICATIONDATE DESC
        """
        cursor.execute(query, (keyword_pattern, keyword_pattern))
        notes = cursor.fetchall()
        conn.close()

        return self._format_notes(notes)

    def search_notes_by_tag_and_keyword(self, tag, keyword):
        """Search Bear notes by both tag and keyword"""
        if not self.check_bear_db_exists():
            raise FileNotFoundError(f"Bear database not found at {self.bear_db_path}")

        conn = sqlite3.connect(self.bear_db_path)
        cursor = conn.cursor()

        tag_pattern = f"%#{tag}%"
        keyword_pattern = f"%{keyword}%"

        query = """
        SELECT ZUNIQUEIDENTIFIER, ZTITLE, ZTEXT, ZMODIFICATIONDATE 
        FROM ZSFNOTE 
        WHERE ZTEXT LIKE ? AND (ZTEXT LIKE ? OR ZTITLE LIKE ?) AND ZTRASHED = 0
        ORDER BY ZMODIFICATIONDATE DESC
        """

        cursor.execute(query, (tag_pattern, keyword_pattern, keyword_pattern))
        notes = cursor.fetchall()
        conn.close()

        return self._format_notes(notes)

    def _format_notes(self, notes):
        """Format notes data into a consistent structure"""
        if not notes:
            return []

        formatted_notes = []
        for note_id, title, content, timestamp in notes:
            unix_timestamp = timestamp - 978307200  # Convert from Cocoa Core Data timestamp to Unix timestamp
            date_modified = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(unix_timestamp))
            formatted_notes.append({
                'id': note_id,
                'title': title,
                'content': content,
                'date_modified': date_modified
            })
        return formatted_notes

    def format_notes_for_chatgpt(self, notes, question):
        """Format notes into a prompt for ChatGPT"""
        # Format notes into a single content block
        combined_content = "\n\n===== NOTE SEPARATOR =====\n\n".join(
            [f"NOTE: {note['title']}\n\n{note['content']}" for note in notes]
        )

        # Create the full prompt
        return f"""Question: {question}

Document content:

{combined_content}

Please analyze the above document(s) and answer the question thoroughly."""


class LocalServer:
    """HTTP server to provide the content for Tampermonkey and receive responses"""

    def __init__(self, prompt_content, port=8765):
        self.prompt_content = prompt_content
        self.port = port
        self.chatgpt_response = None
        self.response_received = False

    def start(self):
        """Start the local server to serve the content and wait for response"""
        handler = self._create_handler()

        with socketserver.TCPServer(("", self.port), handler) as httpd:
            print(f"\nServer started at http://localhost:{self.port}")
            print("Waiting for the Tampermonkey script to fetch the content...")
            print("Please activate the script by navigating to chat.openai.com")
            print("The server will automatically stop after receiving ChatGPT's response")
            print("(You can also press Ctrl+C to stop the server manually)")

            # Set a short timeout to allow checking for response_received flag
            httpd.timeout = 1.0

            try:
                # Continue serving until we receive a response or get interrupted
                while not self.response_received:
                    httpd.handle_request()
            except KeyboardInterrupt:
                print("\nServer stopped manually.")

            # If we got a response, print it
            if self.response_received:
                print("\n" + "=" * 80)
                print("CHATGPT RESPONSE:")
                print("-" * 80)
                print(self.chatgpt_response)
                print("=" * 80)

                # Offer to save the response to a file
                save_option = input("\nWould you like to save this response to a file? (y/n) [n]: ")
                if save_option.lower() == 'y':
                    filename = input("Enter filename (default: chatgpt_response.txt): ") or "chatgpt_response.txt"
                    with open(filename, 'w') as f:
                        f.write(self.chatgpt_response)
                    print(f"Response saved to {filename}")
            else:
                print("\nServer stopped without receiving a response.")

    def _create_handler(self):
        prompt_content = self.prompt_content
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
                        'timestamp': time.time()
                    })

                    self.wfile.write(response.encode())
                    print("Content served successfully! Waiting for ChatGPT to respond...")
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
                        print("ChatGPT response received! Server will stop shortly...")
                    except Exception as e:
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


def generate_tampermonkey_script(port=8765):
    """Generate a Tampermonkey script file"""
    script_dir = Path(__file__).parent
    script_path = script_dir / "bear_to_chatgpt.user.js"

    script_content = f"""// ==UserScript==
// @name         Bear Notes to ChatGPT
// @namespace    http://tampermonkey.net/
// @version      1.0
// @description  Automatically paste Bear Notes content into ChatGPT
// @author       Generated Script
// @match        https://chat.openai.com/*
// @grant        GM_xmlhttpRequest
// ==/UserScript==

(function() {{
    'use strict';

    // Configuration
    const serverPort = {port};
    const serverUrl = `http://localhost:${{serverPort}}/content`;

    // Create UI
    const createUI = () => {{
        const container = document.createElement('div');
        container.style.position = 'fixed';
        container.style.bottom = '20px';
        container.style.right = '20px';
        container.style.zIndex = '10000';
        container.style.padding = '10px';
        container.style.background = '#10a37f';
        container.style.borderRadius = '8px';
        container.style.boxShadow = '0 2px 10px rgba(0,0,0,0.2)';
        container.style.color = 'white';
        container.style.fontFamily = 'Arial, sans-serif';

        const button = document.createElement('button');
        button.textContent = 'Fetch & Paste Bear Notes';
        button.style.padding = '8px 12px';
        button.style.border = 'none';
        button.style.borderRadius = '4px';
        button.style.backgroundColor = '#fff';
        button.style.color = '#10a37f';
        button.style.fontWeight = 'bold';
        button.style.cursor = 'pointer';

        const status = document.createElement('div');
        status.style.marginTop = '8px';
        status.style.fontSize = '12px';
        status.style.display = 'none';

        container.appendChild(button);
        container.appendChild(status);
        document.body.appendChild(container);

        return {{ button, status }};
    }};

    // Fetch content from local server
    const fetchContent = () => {{
        return new Promise((resolve, reject) => {{
            GM_xmlhttpRequest({{
                method: 'GET',
                url: serverUrl,
                onload: (response) => {{
                    if (response.status === 200) {{
                        try {{
                            const data = JSON.parse(response.responseText);
                            resolve(data.content);
                        }} catch (error) {{
                            reject('Error parsing content');
                        }}
                    }} else {{
                        reject(`Server error: ${{response.status}}`);
                    }}
                }},
                onerror: () => reject('Connection error')
            }});
        }});
    }};

    // Find and fill the ChatGPT input
    const fillChatGPTInput = (content) => {{
        // Try multiple selectors for the ChatGPT input
        const selectors = [
            'textarea[placeholder^="Send a message"]',
            'div[contenteditable="true"]',
            'textarea.w-full',
            'textarea'
        ];

        let inputElement = null;

        for (const selector of selectors) {{
            const element = document.querySelector(selector);
            if (element) {{
                inputElement = element;
                break;
            }}
        }}

        if (!inputElement) {{
            throw new Error('ChatGPT input not found');
        }}

        // Focus the input
        inputElement.focus();

        // Set the value directly if it's a textarea
        if (inputElement.tagName === 'TEXTAREA') {{
            inputElement.value = content;

            // Create and dispatch an input event
            const inputEvent = new Event('input', {{ bubbles: true }});
            inputElement.dispatchEvent(inputEvent);
        }} 
        // Use innerText if it's a contenteditable div
        else if (inputElement.getAttribute('contenteditable') === 'true') {{
            inputElement.innerText = content;

            // Create and dispatch an input event
            const inputEvent = new Event('input', {{ bubbles: true }});
            inputElement.dispatchEvent(inputEvent);
        }}

        return inputElement;
    }};

    // Wait for ChatGPT to fully load
    const waitForChatGPT = () => {{
        return new Promise((resolve) => {{
            const checkInterval = setInterval(() => {{
                // Check for common elements that indicate the ChatGPT interface is loaded
                if (
                    document.querySelector('textarea[placeholder^="Send a message"]') ||
                    document.querySelector('div[contenteditable="true"]') ||
                    document.querySelector('textarea.w-full')
                ) {{
                    clearInterval(checkInterval);
                    resolve();
                }}
            }}, 500);
        }});
    }};

    // Main function
    const init = async () => {{
        await waitForChatGPT();

        const {{ button, status }} = createUI();

        button.addEventListener('click', async () => {{
            try {{
                status.textContent = 'Fetching content...';
                status.style.display = 'block';

                const content = await fetchContent();
                status.textContent = 'Pasting content...';

                const inputElement = fillChatGPTInput(content);

                status.textContent = 'Content pasted! Press Enter to submit.';
                setTimeout(() => {{
                    status.style.display = 'none';
                }}, 3000);

                // Focus on the input element to prepare for Enter key
                inputElement.focus();
            }} catch (error) {{
                status.textContent = `Error: ${{error.message || error}}`;
                status.style.color = '#ff4c4c';
                setTimeout(() => {{
                    status.style.color = 'white';
                    status.style.display = 'none';
                }}, 5000);
            }}
        }});
    }};

    init();
}})();
"""

    with open(script_path, 'w') as f:
        f.write(script_content)

    print(f"\nTampermonkey script generated at: {script_path}")
    print("Please install this script in Tampermonkey for Firefox.")

    return script_path


def main():
    parser = argparse.ArgumentParser(description="Send Bear notes directly to ChatGPT via Tampermonkey")

    # Search options
    search_group = parser.add_argument_group('Search Options')
    search_group.add_argument("-t", "--tag", help="Tag to search for")
    search_group.add_argument("-k", "--keyword", help="Keyword to search for")
    search_group.add_argument("-u", "--url", help="Bear callback URL")

    # Other options
    parser.add_argument("-q", "--question", help="Question to ask about the notes")
    parser.add_argument("-l", "--list", action="store_true", help="Just list matching notes, don't process")
    parser.add_argument("--limit", type=int, help="Limit the number of notes to process")
    parser.add_argument("-y", "--yes", action="store_true", help="Process notes without confirmation")
    parser.add_argument("--port", type=int, default=8765, help="Port to use for the local server")
    parser.add_argument("--gen-script", action="store_true", help="Generate Tampermonkey script and exit")
    parser.add_argument("--debug", action="store_true", help="Show additional debug information")

    args = parser.parse_args()

    # Generate Tampermonkey script if requested
    if args.gen_script:
        script_path = generate_tampermonkey_script(args.port)
        print("Tampermonkey script generation completed.")
        return

    # Enable debug logging if requested
    debug_mode = args.debug
    if debug_mode:
        print("Debug mode enabled. Additional information will be shown.")

        # Print system information
        print("\nSystem Information:")
        print(f"- Operating System: {platform.system()} {platform.version()}")
        print(f"- Python Version: {platform.python_version()}")
        print(f"- Script Path: {os.path.abspath(__file__)}")

    if not (args.tag or args.keyword or args.url):
        parser.error("At least one search option (--tag, --keyword, or --url) is required")

    if not args.list and not args.question:
        parser.error("--question is required unless --list is used")

    processor = BearNotesProcessor()
    matching_notes = []

    # Search for notes
    try:
        if args.url:
            note_id = processor.extract_note_id_from_url(args.url)
            note_id, title, content = processor.get_note_by_id(note_id)
            matching_notes.append({
                'id': note_id,
                'title': title,
                'content': content,
                'date_modified': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
            })
            print(f"Found note: {title}")
        elif args.tag and args.keyword:
            combined_notes = processor.search_notes_by_tag_and_keyword(args.tag, args.keyword)
            matching_notes.extend(combined_notes)
            print(f"Found {len(combined_notes)} notes with tag #{args.tag} and keyword '{args.keyword}'")
        elif args.tag:
            tag_notes = processor.search_notes_by_tag(args.tag)
            matching_notes.extend(tag_notes)
            print(f"Found {len(tag_notes)} notes with tag #{args.tag}")
        elif args.keyword:
            keyword_notes = processor.search_notes_by_keyword(args.keyword)
            matching_notes.extend(keyword_notes)
            print(f"Found {len(keyword_notes)} notes with keyword '{args.keyword}'")
    except Exception as e:
        print(f"Error: {e}")
        return

    if not matching_notes:
        print("No matching notes found.")
        return

    # Apply limit if provided
    original_count = len(matching_notes)
    if args.limit:
        try:
            limit = int(args.limit)
            if limit <= 0:
                print("\nWarning: Invalid limit (must be positive). Processing all notes.")
            elif limit < original_count:
                matching_notes = matching_notes[:limit]
                print("\n" + "=" * 50)
                print(f"  LIMITED TO {limit} OF {original_count} NOTES")
                print("=" * 50 + "\n")
        except (ValueError, TypeError):
            print("\nWarning: Invalid limit value. Processing all notes.")

    # Display matching notes
    total_notes = len(matching_notes)
    print("\nMatching Notes:")
    for i, note in enumerate(matching_notes, 1):
        print(f"{i}. {note['title']} (Modified: {note['date_modified']})")

    # Just list the notes if requested
    if args.list:
        return

    # Ask for confirmation before processing
    if not args.yes:
        confirmation = input(f"\nFound {total_notes} matching notes. Process them? (y/n) [y]: ")
        if confirmation.lower() and confirmation.lower() != 'y':
            print("Operation cancelled.")
            return

    # Process the notes
    prompt = processor.format_notes_for_chatgpt(matching_notes, args.question)

    # Check if the Tampermonkey script exists, generate if not
    script_path = Path(__file__).parent / "bear_to_chatgpt.user.js"
    if not script_path.exists():
        print("\nTampermonkey script not found. Generating it now...")
        generate_tampermonkey_script(args.port)

    # Open ChatGPT in the browser
    print("\nOpening ChatGPT in your default browser...")
    webbrowser.open("https://chat.openai.com/")

    # Start the local server to provide the content
    server = LocalServer(prompt, port=args.port)
    print(f"\nStarting local server on port {args.port}...")
    print("Please use the 'Fetch & Paste Bear Notes' button in ChatGPT to load your content.")
    server.start()


if __name__ == "__main__":
    main()