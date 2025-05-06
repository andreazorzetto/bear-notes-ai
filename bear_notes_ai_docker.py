#!/usr/bin/env python3
"""
Bear Notes AI Integration - Process notes with Ollama, ChatGPT, or Docker Model Runner
Fixed version with working limit feature
"""

import sqlite3
import argparse
import os
import re
import time
import json
import urllib.parse
import requests
import subprocess
from math import ceil


class BearNotesAI:
    def __init__(self, use_chatgpt=False, use_docker_model=False, model_name="llama3", api_key=None,
                 ollama_host="http://localhost:11434", docker_model_endpoint=None):
        self.bear_db_path = os.path.expanduser(
            "~/Library/Group Containers/9K33E3U3T4.net.shinyfrog.bear/Application Data/database.sqlite"
        )
        self.use_chatgpt = use_chatgpt
        self.use_docker_model = use_docker_model
        self.model_name = model_name
        self.api_key = api_key
        self.ollama_host = ollama_host
        # Docker Model Runner endpoint (OpenAI compatible API)
        self.docker_model_endpoint = docker_model_endpoint or "http://model-runner.docker.internal/engines/v1"

    def check_bear_db_exists(self):
        return os.path.exists(self.bear_db_path)

    def get_note_by_id(self, note_id):
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
        if not callback_url.startswith("bear://"):
            raise ValueError("Invalid Bear callback URL format")

        match = re.search(r'id=([^&]+)', callback_url)
        if not match:
            raise ValueError("No note ID found in the callback URL")

        note_id = match.group(1)
        return urllib.parse.unquote(note_id)

    def search_notes_by_tag(self, tag):
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
        if not notes:
            return []

        formatted_notes = []
        for note_id, title, content, timestamp in notes:
            unix_timestamp = timestamp - 978307200
            date_modified = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(unix_timestamp))
            formatted_notes.append({
                'id': note_id,
                'title': title,
                'content': content,
                'date_modified': date_modified
            })
        return formatted_notes

    def process_notes_in_batches(self, notes, question, batch_size=5, delay_between_batches=1):
        """Process notes in batches to avoid API rate limits"""
        num_notes = len(notes)
        num_batches = ceil(num_notes / batch_size)

        all_results = []

        print(f"Processing {num_notes} notes in {num_batches} batches (batch size: {batch_size})")

        for batch_num in range(num_batches):
            start_idx = batch_num * batch_size
            end_idx = min((batch_num + 1) * batch_size, num_notes)
            current_batch = notes[start_idx:end_idx]

            print(f"\nProcessing batch {batch_num + 1}/{num_batches} ({len(current_batch)} notes)")
            print(f"Notes {start_idx + 1} to {end_idx} of {num_notes}")

            # Process the current batch
            batch_result = self.process_notes_together(current_batch, question)
            all_results.append(batch_result)

            # Display the result for this batch
            print("\nResult for current batch:")
            print("-" * 40)
            print(batch_result)
            print("-" * 40)

            # Add delay between batches to avoid rate limiting, except after the last batch
            if batch_num < num_batches - 1:
                print(f"Waiting {delay_between_batches} seconds before next batch...")
                time.sleep(delay_between_batches)

        # Combine all results
        if num_batches > 1:
            combined_result = "\n\n=== COMBINED RESULTS FROM ALL BATCHES ===\n\n"
            combined_result += "\n\n=== BATCH SEPARATOR ===\n\n".join(all_results)
            return combined_result
        else:
            return all_results[0]

    def process_notes_together(self, notes, question):
        # Combine all notes into one document
        combined_content = "\n\n===== NOTE SEPARATOR =====\n\n".join(
            [f"NOTE: {note['title']}\n\n{note['content']}" for note in notes]
        )

        if self.use_chatgpt:
            return self.ask_chatgpt(combined_content, question)
        elif self.use_docker_model:
            return self.ask_docker_model(combined_content, question)
        else:
            return self.ask_ollama_cli(combined_content, question)

    def ask_ollama_cli(self, content, question):
        prompt = f"Read ALL these documents together and answer: {question}\n\n{content}"
        cmd = ["ollama", "run", self.model_name, prompt]

        print("Working", end="", flush=True)

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        # Show progress while waiting
        while process.poll() is None:
            print(".", end="", flush=True)
            time.sleep(0.5)

        print()  # New line after progress dots

        stdout, stderr = process.communicate()
        if process.returncode == 0:
            return stdout
        else:
            return f"Error: {stderr}"

    def ask_chatgpt(self, content, question):
        if not self.api_key:
            return "Error: OpenAI API key is required for ChatGPT"

        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        data = {
            "model": "gpt-4o",
            "messages": [
                {"role": "system", "content": "You are a helpful assistant that answers questions about documents."},
                {"role": "user", "content": f"Document content:\n\n{content}\n\nQuestion: {question}"}
            ],
            "temperature": 0.7
        }

        print("Working", end="", flush=True)
        try:
            response = requests.post(url, headers=headers, json=data)
            print()  # New line after progress
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]
        except Exception as e:
            print()  # New line after progress
            return f"Error: {str(e)}"
        finally:
            print()  # Ensure new line

    def ask_docker_model(self, content, question):
        """Query Docker Model Runner using its OpenAI-compatible API"""
        prompt = f"Read ALL these documents together and answer: {question}\n\n{content}"

        # Format request for OpenAI-compatible API
        headers = {"Content-Type": "application/json"}
        data = {
            "model": self.model_name,
            "prompt": prompt,
            "max_tokens": 2048,
            "temperature": 0.7
        }

        print(f"Working with Docker Model Runner model: {self.model_name}", end="", flush=True)
        try:
            # Make the API call to Docker Model Runner's OpenAI-compatible endpoint
            response = requests.post(
                f"{self.docker_model_endpoint}/completions",
                headers=headers,
                json=data,
                timeout=180
            )
            print()  # New line after progress

            response.raise_for_status()
            result = response.json()

            # Extract the generated text from the OpenAI-compatible response
            if "choices" in result and len(result["choices"]) > 0:
                return result["choices"][0]["text"].strip()

            return "No valid response received from model"

        except requests.exceptions.RequestException as e:
            print()  # New line after progress
            return f"Error connecting to Docker Model Runner: {str(e)}"
        except Exception as e:
            print()  # New line after progress
            return f"Error: {str(e)}"
        finally:
            print()  # Ensure new line


def main():
    parser = argparse.ArgumentParser(description="Process Bear notes with AI")

    # Search options
    search_group = parser.add_argument_group('Search Options')
    search_group.add_argument("-t", "--tag", help="Tag to search for")
    search_group.add_argument("-k", "--keyword", help="Keyword to search for")
    search_group.add_argument("-u", "--url", help="Bear callback URL")

    # AI options
    ai_group = parser.add_argument_group('AI Options')
    ai_type = ai_group.add_mutually_exclusive_group(required=True)
    ai_type.add_argument("--ollama", action="store_true", help="Use Ollama (local)")
    ai_type.add_argument("--chatgpt", action="store_true", help="Use ChatGPT API")
    ai_type.add_argument("--docker-model", action="store_true", help="Use Docker Model Runner")
    ai_group.add_argument("-m", "--model", default="llama3",
                          help="Model to use (works with Ollama and Docker Model Runner)")
    ai_group.add_argument("--host", default="http://localhost:12434/engines/v1", help="Ollama server URL")
    ai_group.add_argument("--docker-model-endpoint",
                          help="URL for Docker Model Runner API (default: http://model-runner.docker.internal/engines/v1)")
    ai_group.add_argument("--api-key", help="OpenAI API key for ChatGPT")
    ai_group.add_argument("-q", "--question", help="Question to ask about the note")

    # Batch processing options
    batch_group = parser.add_argument_group('Batch Processing Options')
    batch_group.add_argument("--batch-size", type=int,
                             help="Number of notes to process in each batch (default: process all together)")
    batch_group.add_argument("--batch-delay", type=int, default=1,
                             help="Delay in seconds between batches (default: 1)")
    batch_group.add_argument("--limit", type=int,
                             help="Limit total number of notes to process")

    # Other options
    parser.add_argument("-l", "--list", action="store_true", help="Just list matching notes")
    parser.add_argument("-y", "--yes", action="store_true", help="Process notes without confirmation")

    args = parser.parse_args()

    if not (args.tag or args.keyword or args.url):
        parser.error("At least one search option (--tag, --keyword, or --url) is required")

    if args.chatgpt and not args.api_key:
        parser.error("OpenAI API key is required when using ChatGPT")

    if not args.list and not args.question:
        parser.error("--question is required unless --list is used")

    processor = BearNotesAI(
        use_chatgpt=args.chatgpt,
        use_docker_model=args.docker_model,
        model_name=args.model,
        api_key=args.api_key,
        ollama_host=args.host,
        docker_model_endpoint=args.docker_model_endpoint
    )

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
            # Use combined tag and keyword search
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

    # CRITICAL FIX: Apply limit IMMEDIATELY after finding notes
    # Save original count before limiting
    original_count = len(matching_notes)

    # Check if limit is provided
    if args.limit:
        try:
            limit = int(args.limit)
            if limit <= 0:
                print("\nWarning: Invalid limit (must be positive). Processing all notes.")
            elif limit < original_count:
                # Actually limit the notes list
                matching_notes = matching_notes[:limit]
                print("\n" + "=" * 50)
                print(f"  LIMITED TO {limit} OF {original_count} NOTES")
                print("=" * 50 + "\n")
                # Don't need an else case - if limit >= original_count, do nothing
        except (ValueError, TypeError):
            print("\nWarning: Invalid limit value. Processing all notes.")

    # Display matching notes (after limiting)
    total_notes = len(matching_notes)  # This will be the limited count if limit was applied
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

    # Choose between batch processing or all at once
    ai_type = "ChatGPT" if args.chatgpt else "Docker Model Runner" if args.docker_model else f"Ollama ({args.model})"

    if args.batch_size is None:
        # Process all notes together by default
        print(f"\nProcessing all {total_notes} notes together")
        print(f"Asking {ai_type}: {args.question}")
        print("\nAI response:")
        print("-" * 40)

        response = processor.process_notes_together(matching_notes, args.question)
        print(response)
        print("-" * 40)
    else:
        # Process notes in batches only if batch-size is specified
        batch_size = args.batch_size
        print(f"\nProcessing {total_notes} notes in batches of {batch_size}")
        print(f"Asking {ai_type}: {args.question}")
        print(f"Using {args.batch_delay} second delay between batches")

        response = processor.process_notes_in_batches(
            matching_notes,
            args.question,
            batch_size=batch_size,
            delay_between_batches=args.batch_delay
        )


if __name__ == "__main__":
    main()