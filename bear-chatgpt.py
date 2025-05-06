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
from pathlib import Path


class BearNotesProcessor:
    """Process Bear notes and prepare them for ChatGPT"""

    def __init__(self):
        self.bear_db_path = os.path.expanduser(
            "~/Library/Group Containers/9K33E3U3T4.net.shinyfrog.bear/Application Data/database.sqlite"
        )

    def get_note_by_id(self, note_id):
        """Retrieve a single note by its ID"""
        if not os.path.exists(self.bear_db_path):
            raise FileNotFoundError(f"Bear database not found at {self.bear_db_path}")

        with sqlite3.connect(self.bear_db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT ZUNIQUEIDENTIFIER, ZTITLE, ZTEXT 
                FROM ZSFNOTE 
                WHERE ZUNIQUEIDENTIFIER = ? AND ZTRASHED = 0
            """, (note_id,))
            note = cursor.fetchone()

        if not note:
            raise ValueError(f"No note found with ID '{note_id}'")
        return note

    def extract_note_id_from_url(self, callback_url):
        """Extract note ID from Bear callback URL"""
        if not callback_url.startswith("bear://"):
            raise ValueError("Invalid Bear callback URL format")

        match = re.search(r'id=([^&]+)', callback_url)
        if not match:
            raise ValueError("No note ID found in the callback URL")

        return urllib.parse.unquote(match.group(1))

    def search_notes(self, tag=None, keyword=None):
        """Search for notes by tag, keyword, or both"""
        if not os.path.exists(self.bear_db_path):
            raise FileNotFoundError(f"Bear database not found at {self.bear_db_path}")

        with sqlite3.connect(self.bear_db_path) as conn:
            cursor = conn.cursor()

            if tag and keyword:
                cursor.execute("""
                    SELECT ZUNIQUEIDENTIFIER, ZTITLE, ZTEXT, ZMODIFICATIONDATE 
                    FROM ZSFNOTE 
                    WHERE ZTEXT LIKE ? AND (ZTEXT LIKE ? OR ZTITLE LIKE ?) AND ZTRASHED = 0
                    ORDER BY ZMODIFICATIONDATE DESC
                """, (f"%#{tag}%", f"%{keyword}%", f"%{keyword}%"))
            elif tag:
                cursor.execute("""
                    SELECT ZUNIQUEIDENTIFIER, ZTITLE, ZTEXT, ZMODIFICATIONDATE 
                    FROM ZSFNOTE 
                    WHERE ZTEXT LIKE ? AND ZTRASHED = 0
                    ORDER BY ZMODIFICATIONDATE DESC
                """, (f"%#{tag}%",))
            elif keyword:
                cursor.execute("""
                    SELECT ZUNIQUEIDENTIFIER, ZTITLE, ZTEXT, ZMODIFICATIONDATE 
                    FROM ZSFNOTE 
                    WHERE (ZTEXT LIKE ? OR ZTITLE LIKE ?) AND ZTRASHED = 0
                    ORDER BY ZMODIFICATIONDATE DESC
                """, (f"%{keyword}%", f"%{keyword}%"))

            notes = cursor.fetchall()

        return self._format_notes(notes)

    def _format_notes(self, notes):
        """Format the database results into usable note objects"""
        if not notes:
            return []

        formatted_notes = []
        for note_id, title, content, timestamp in notes:
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

    def format_notes_for_chatgpt(self, notes, question):
        """Format notes and question for ChatGPT prompt"""
        combined_content = "\n\n===== NOTE SEPARATOR =====\n\n".join(
            [f"NOTE: {note['title']}\n\n{note['content']}" for note in notes]
        )

        return f"""Question: {question}

Document content:

{combined_content}

Please analyze the above document(s) and answer the question thoroughly."""


class LocalServer:
    """HTTP server to provide content to Tampermonkey and receive responses"""

    def __init__(self, prompt_content, port=8765):
        self.prompt_content = prompt_content
        self.port = port
        self.chatgpt_response = None
        self.response_received = False

    def start(self):
        handler = self._create_handler()

        with socketserver.TCPServer(("", self.port), handler) as httpd:
            print(f"\nServer started at http://localhost:{self.port}")
            print("Waiting for the Tampermonkey script to fetch the content...")
            print("Please navigate to https://chatgpt.com in your browser")
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

            # If we got a response, format and print it
            if self.response_received:
                print("\n" + "=" * 80)
                print("CHATGPT RESPONSE:")
                print("-" * 80)

                # Format and print the response
                if self.chatgpt_response:
                    formatted_response = self.format_chatgpt_response(self.chatgpt_response)
                    print(formatted_response)

                print("=" * 80)

    def format_chatgpt_response(self, response_text):
        """Format the ChatGPT response for better readability in the terminal."""
        if not response_text:
            return ""

        # Replace multiple consecutive newlines with a maximum of two
        formatted_text = re.sub(r'\n{3,}', '\n\n', response_text)

        # Handle the common "CHATGPT RESPONSE:" header pattern more cleanly
        formatted_text = re.sub(r'^-+\s*\nCHATGPT RESPONSE:\s*\n-+\s*\n', '', formatted_text)

        # Handle trailing separators
        formatted_text = re.sub(r'\n=+\s*$', '', formatted_text)

        return formatted_text

    def _create_handler(self):
        """Create and return the HTTP request handler class"""
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
    """Generate the Tampermonkey script for browser automation"""
    script_dir = Path(__file__).parent
    script_path = script_dir / "bear_to_chatgpt.user.js"

    script_content = """// ==UserScript==
// @name         Bear Notes to ChatGPT
// @namespace    http://tampermonkey.net/
// @version      1.0
// @description  Auto-paste Bear Notes, get ChatGPT response, and close tab
// @author       Generated Script
// @match        https://chatgpt.com/*
// @grant        GM_xmlhttpRequest
// @connect      localhost
// ==/UserScript==

(function() {
    'use strict';

    const PORT = {port};
    const SERVER_URL = `http://localhost:${PORT}/content`;
    const RESPONSE_URL = `http://localhost:${PORT}/response`;

    // Show status notifications
    const showStatus = (() => {{
        const el = document.createElement('div');
        Object.assign(el.style, {{
            position: 'fixed', top: '10px', left: '50%', transform: 'translateX(-50%)',
            zIndex: '10000', padding: '10px 15px', background: '#10a37f',
            borderRadius: '8px', boxShadow: '0 2px 10px rgba(0,0,0,0.2)',
            color: 'white', fontFamily: 'Arial', fontSize: '14px', fontWeight: 'bold'
        }});
        document.body.appendChild(el);

        return (msg, isError) => {{
            el.textContent = msg;
            el.style.background = isError ? '#e34234' : '#10a37f';
        }};
    }})();

    // Wait for ChatGPT to load
    const waitForChatGPT = () => new Promise(resolve => {{
        const interval = setInterval(() => {{
            if (document.querySelector('textarea[placeholder^="Send a message"]') || 
                document.querySelector('div[contenteditable="true"]')) {{
                clearInterval(interval);
                resolve();
            }}
        }}, 500);
    }});

    // Get content from local server
    const fetchContent = () => new Promise((resolve, reject) => {{
        GM_xmlhttpRequest({{
            method: 'GET',
            url: SERVER_URL,
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

    // Fill and submit content to ChatGPT
    const submitToChat = content => {{
        // Find the input field
        const selectors = [
            'textarea[placeholder^="Send a message"]',
            'div[contenteditable="true"]',
            'textarea.w-full'
        ];

        const input = selectors.map(s => document.querySelector(s)).find(el => el);
        if (!input) throw new Error('ChatGPT input not found');

        // Fill the input
        input.focus();
        if (input.tagName === 'TEXTAREA') {{
            input.value = content;
        }} else {{
            input.innerText = content;
        }}

        // Trigger input event to enable the send button
        input.dispatchEvent(new Event('input', {{ bubbles: true }}));

        // Try to find and click the send button (more reliable than Enter key)
        setTimeout(() => {{
            const sendButton = findSendButton();
            if (sendButton) {{
                sendButton.click();
            }} else {{
                // Fallback to Enter key
                input.dispatchEvent(new KeyboardEvent('keydown', {{
                    key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true
                }}));
            }}
        }}, 500);

        return input;
    }};

    // Find the send button using multiple strategies
    const findSendButton = () => {{
        const buttonSelectors = [
            'button[aria-label="Send message"]',
            'button[data-testid="send-button"]',
            'button.absolute.p-1.rounded-md',
            'button svg[data-testid="send-icon"]',
            'button.absolute.right-2',
            'button:has(svg)',
            'form button[type="submit"]'
        ];

        // Try each selector
        for (const selector of buttonSelectors) {{
            const elements = document.querySelectorAll(selector);
            for (const el of elements) {{
                if (el.tagName === 'BUTTON' &&
                    (el.textContent.trim() === '' || 
                     el.textContent.toLowerCase().includes('send') || 
                     el.getAttribute('aria-label')?.toLowerCase().includes('send'))) {{
                    return el;
                }}

                if (el.querySelector('svg')) {{
                    return el;
                }}
            }}
        }}

        // Try the last button in the form as fallback
        const form = document.querySelector('form');
        if (form) {{
            const buttons = form.querySelectorAll('button');
            if (buttons.length > 0) {{
                return buttons[buttons.length - 1];
            }}
        }}

        return null;
    }};

    // Check if ChatGPT is still generating a response
    const isThinking = () => {{
        return document.querySelector('.result-thinking') !== null ||
               document.querySelector('[role="progressbar"]') !== null ||
               document.querySelector('.animate-spin') !== null ||
               document.querySelector('[data-state="loading"]') !== null;
    }};

    // Get current response text from ChatGPT
    const getResponseText = () => {{
        const responses = document.querySelectorAll('[data-message-author-role="assistant"]');
        if (!responses.length) return '';
        return responses[responses.length - 1].textContent;
    }};

    // Wait for ChatGPT to finish responding
    const waitForResponse = () => new Promise(resolve => {{
        let started = false;
        let lastResponseText = '';
        let stableCount = 0;
        const MAX_WAIT_TIME = 300000; // 5 minutes
        const startTime = Date.now();

        const checkResponse = setInterval(() => {{
            // Check if maximum wait time exceeded
            if (Date.now() - startTime > MAX_WAIT_TIME) {{
                clearInterval(checkResponse);
                showStatus('Maximum wait time exceeded, capturing current response');
                setTimeout(resolve, 1000);
                return;
            }}

            // Check if response has started
            if (isThinking() || document.querySelectorAll('[data-message-author-role="assistant"]').length > 0) {{
                started = true;
                const currentResponseText = getResponseText();

                // Check if response has stabilized
                if (currentResponseText === lastResponseText) {{
                    stableCount++;
                    if (!isThinking() && stableCount >= 10) {{
                        clearInterval(checkResponse);
                        setTimeout(resolve, 2000);
                    }}
                }} else {{
                    stableCount = 0;
                    lastResponseText = currentResponseText;
                }}
            }}
        }}, 500);

        // Timeout if response hasn't started after 30 seconds
        setTimeout(() => {{
            if (!started) {{
                clearInterval(checkResponse);
                showStatus('Timeout waiting for response', true);
                resolve();
            }}
        }}, 30000);
    }});

    // Get the final response from ChatGPT
    const getResponse = () => {{
        const responses = document.querySelectorAll('[data-message-author-role="assistant"]');
        if (!responses.length) throw new Error('No ChatGPT response found');
        return responses[responses.length - 1].textContent;
    }};

    // Send response back to the local server
    const sendResponseToServer = response => new Promise((resolve, reject) => {{
        GM_xmlhttpRequest({{
            method: 'POST',
            url: RESPONSE_URL,
            data: JSON.stringify({{ response }}),
            headers: {{ 'Content-Type': 'application/json' }},
            onload: (response) => {{
                if (response.status === 200) resolve();
                else reject(`Server error: ${{response.status}}`);
            }},
            onerror: () => reject('Connection error')
        }});
    }});

    // Main workflow
    const run = async () => {{
        try {{
            await waitForChatGPT();
            showStatus('Fetching content from Bear Notes...');
            const content = await fetchContent();

            showStatus('Submitting to ChatGPT...');
            submitToChat(content);

            showStatus('Waiting for ChatGPT to respond...');
            await waitForResponse();

            showStatus('Capturing response...');
            const response = getResponse();

            showStatus('Sending response back to server...');
            await sendResponseToServer(response);

            showStatus('Done! Closing tab...');
            setTimeout(() => window.close(), 2000);
        }} catch (err) {{
            showStatus(`Error: ${{err.message || err}}`, true);
            console.error('Bear to ChatGPT error:', err);
        }}
    }};

    // Start the process
    run();
}})();""".format(port=port)

    with open(script_path, 'w') as f:
        f.write(script_content)

    print(f"\nTampermonkey script generated at: {script_path}")
    print("Please install this script in Tampermonkey for your browser.")

    return script_path


def main():
    parser = argparse.ArgumentParser(description="Send Bear notes to ChatGPT via Tampermonkey")

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
    parser.add_argument("--port", type=int, default=8765, help="Port for the local server")
    parser.add_argument("--gen-script", action="store_true", help="Generate Tampermonkey script and exit")

    args = parser.parse_args()

    # Generate Tampermonkey script if requested
    if args.gen_script:
        generate_tampermonkey_script(args.port)
        return

    # Validate arguments
    if not (args.tag or args.keyword or args.url):
        parser.error("At least one search option (--tag, --keyword, or --url) is required")

    if not args.list and not args.question:
        parser.error("--question is required unless --list is used")

    # Process notes
    processor = BearNotesProcessor()
    matching_notes = []

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
        else:
            # Use the simplified search function
            notes = processor.search_notes(tag=args.tag, keyword=args.keyword)
            matching_notes.extend(notes)

            if args.tag and args.keyword:
                print(f"Found {len(notes)} notes with tag #{args.tag} and keyword '{args.keyword}'")
            elif args.tag:
                print(f"Found {len(notes)} notes with tag #{args.tag}")
            elif args.keyword:
                print(f"Found {len(notes)} notes with keyword '{args.keyword}'")
    except Exception as e:
        print(f"Error: {e}")
        return

    if not matching_notes:
        print("No matching notes found.")
        return

    # Apply limit if provided
    original_count = len(matching_notes)
    if args.limit and args.limit > 0 and args.limit < original_count:
        matching_notes = matching_notes[:args.limit]
        print(f"\nLIMITED TO {args.limit} OF {original_count} NOTES\n")

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
    prompt = processor.format_notes_for_chatgpt(matching_notes, args.question)

    # Check if the Tampermonkey script exists, generate if not
    script_path = Path(__file__).parent / "bear-chatgpt.user.js"
    if not script_path.exists():
        print("\nTampermonkey script not found. Generating it now...")
        generate_tampermonkey_script(args.port)

    # Open ChatGPT in the browser
    print("\nOpening ChatGPT in your default browser...")
    webbrowser.open("https://chatgpt.com/")

    # Start the local server to provide the content
    server = LocalServer(prompt, port=args.port)
    print(f"\nStarting local server on port {args.port}...")
    print("The Tampermonkey script will automatically fetch, submit, and return the response.")
    server.start()


if __name__ == "__main__":
    main()