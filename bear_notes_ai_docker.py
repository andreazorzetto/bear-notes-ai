#!/usr/bin/env python3
"""
Bear Notes AI Integration - Process notes with Ollama, ChatGPT, or Docker Model Runner
Enhanced version with incremental processing and token management
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
from typing import List, Dict, Any, Optional
import tiktoken
import concurrent.futures


class BearNotesAI:
    def __init__(self, use_chatgpt=False, use_docker_model=False, model_name="llama3", api_key=None,
                 ollama_host="http://localhost:11434", docker_model_endpoint=None,
                 max_tokens=4000, chunking_strategy="auto", overlap_tokens=100):
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

        # Token management parameters
        self.max_tokens = max_tokens
        self.chunking_strategy = chunking_strategy
        self.overlap_tokens = overlap_tokens

        # Initialize tokenizer based on model
        self.tokenizer = self._initialize_tokenizer()

        # Configure model-specific parameters
        self.model_params = self._get_model_params()

    def _initialize_tokenizer(self):
        """Initialize the appropriate tokenizer based on model"""
        try:
            if self.use_chatgpt:
                # For OpenAI models, use tiktoken
                if "gpt-4" in self.model_name:
                    return tiktoken.encoding_for_model("gpt-4")
                else:
                    return tiktoken.encoding_for_model("gpt-3.5-turbo")
            else:
                # For Ollama/other models, use a simpler approximation
                # This is a rough approximation for most models
                return SimpleTokenizer()
        except Exception as e:
            print(f"Warning: Couldn't initialize tokenizer: {e}")
            return SimpleTokenizer()

    def _get_model_params(self):
        """
        Get model parameters prioritizing user input and using
        very simple defaults for each model type with no API queries.
        """
        # If user specified max_tokens, always use that as context window
        if self.max_tokens > 0:
            context_window = self.max_tokens
            print(f"Using user-provided context window size: {context_window} tokens")
        else:
            # Use reasonable defaults based on model type
            if self.use_chatgpt:
                # For ChatGPT, use a large default without API query
                context_window = 128000  # Maximum possible
                print(f"Using maximum possible context window for ChatGPT initially")
                print(f"(Will adjust based on API errors if content is too large)")
            elif self.use_docker_model:
                # For Docker models, don't try to query - use a reasonable default
                context_window = 32000  # Reasonable default for most modern models
                print(f"Using default context window for Docker Model: {context_window} tokens")
                print(f"(Specify --max-tokens to override this value)")
            else:
                # For Ollama models, try to extract context info from model info
                context_window = self._extract_ollama_context_window()
                if not context_window:
                    context_window = 32000  # Reasonable default for most modern models
                    print(f"Using default context window for Ollama: {context_window} tokens")
                    print(f"(Specify --max-tokens to override this value)")

        # Calculate optimal parameters based on detected context window
        params = self._calculate_params_from_context_window(context_window)

        print(f"Model parameters for {self.model_name}:")
        print(f"- Context window: {params['context_window']} tokens")
        print(f"- Optimal chunk size: {params['optimal_chunk_size']} tokens")
        print(f"- Reserved for response: {params['response_tokens']} tokens")

        return params

    def _extract_ollama_context_window(self):
        """
        Extract context window from Ollama model info.
        Only makes a simple API request to Ollama and looks for context window.
        """
        try:
            # Try to get model info from Ollama
            response = requests.post(
                f"{self.ollama_host}/api/show",
                json={"name": self.model_name},
                timeout=5
            )

            if response.status_code == 200:
                model_info = response.json()

                # Look for context length in different places
                # First try to find it in model_info.model_info
                if "model_info" in model_info:
                    info = model_info["model_info"]
                    if "qwen2.context_length" in info:
                        return int(info["qwen2.context_length"])
                    elif "llama.context_length" in info:
                        return int(info["llama.context_length"])
                    elif "context_length" in info:
                        return int(info["context_length"])

                # Try other common locations
                if "context_length" in model_info:
                    return int(model_info["context_length"])
                elif "context_window" in model_info:
                    return int(model_info["context_window"])
                elif "parameters" in model_info:
                    params = model_info["parameters"]
                    if "context_length" in params:
                        return int(params["context_length"])
                    elif "context_window" in params:
                        return int(params["context_window"])

                # Look through details section
                if "details" in model_info:
                    details = model_info["details"]
                    if "context_length" in details:
                        return int(details["context_length"])
                    if "context_window" in details:
                        return int(details["context_window"])

                # Print model info for debugging
                print(f"Ollama API response: {json.dumps(model_info, indent=2)}")

                # Do a deep search through the JSON for any keys containing "context" and "length"
                def search_json(obj, context_keys=None):
                    if context_keys is None:
                        context_keys = []

                    if isinstance(obj, dict):
                        for k, v in obj.items():
                            if ("context" in k.lower() and "length" in k.lower()) or (
                                    "context" in k.lower() and "window" in k.lower()):
                                if isinstance(v, (int, float, str)) and str(v).isdigit():
                                    context_keys.append((k, int(v)))
                            elif isinstance(v, (dict, list)):
                                search_json(v, context_keys)
                    elif isinstance(obj, list):
                        for item in obj:
                            if isinstance(item, (dict, list)):
                                search_json(item, context_keys)

                    return context_keys

                # Search for any keys containing context information
                context_keys = search_json(model_info)
                if context_keys:
                    # Use the largest value found
                    largest_context = max(context_keys, key=lambda x: x[1])
                    print(f"Found context window information: {largest_context[0]} = {largest_context[1]}")
                    return largest_context[1]

        except Exception as e:
            print(f"Error querying Ollama API: {e}")

        return None

    def _calculate_params_from_context_window(self, context_window):
        """Calculate optimal chunk size and response tokens based on context window"""
        # General heuristics:
        # - Reserve 15-25% of context window for response
        # - Slightly more for smaller context windows, less for larger ones
        # - Optimal chunk size is context window minus response tokens minus some buffer

        if context_window <= 4000:
            # For small context windows, reserve 25%
            response_tokens = max(500, int(context_window * 0.25))
            buffer = 200  # Small buffer
        elif context_window <= 8000:
            # For medium context windows, reserve 20%
            response_tokens = max(800, int(context_window * 0.20))
            buffer = 400
        elif context_window <= 32000:
            # For large context windows, reserve 15%
            response_tokens = max(1500, int(context_window * 0.15))
            buffer = 800
        else:
            # For very large context windows, reserve 10%
            response_tokens = max(2000, int(context_window * 0.10))
            buffer = 1000

        # Calculate optimal chunk size
        optimal_chunk_size = context_window - response_tokens - buffer

        # Ensure minimum values
        response_tokens = max(500, response_tokens)
        optimal_chunk_size = max(1000, optimal_chunk_size)

        return {
            "context_window": context_window,
            "optimal_chunk_size": optimal_chunk_size,
            "response_tokens": response_tokens
        }

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

    def count_tokens(self, text):
        """Count tokens in the given text using the appropriate tokenizer"""
        if hasattr(self.tokenizer, "encode"):
            # For tiktoken
            return len(self.tokenizer.encode(text))
        else:
            # For SimpleTokenizer
            return self.tokenizer.count_tokens(text)

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
        """Process notes using the appropriate chunking strategy based on token count"""
        # Combine notes into one document
        combined_content = "\n\n===== NOTE SEPARATOR =====\n\n".join(
            [f"NOTE: {note['title']}\n\n{note['content']}" for note in notes]
        )

        # Count tokens in the combined content and question
        question_with_prefix = f"Read the following documents and answer: {question}"
        question_tokens = self.count_tokens(question_with_prefix)
        content_tokens = self.count_tokens(combined_content)

        total_tokens = question_tokens + content_tokens

        # For ChatGPT, we'll try the direct approach first, then handle errors
        if self.use_chatgpt:
            # Get context window from model parameters
            context_window = self.model_params["context_window"]
            reserved_response_tokens = self.model_params["response_tokens"]
            max_input_tokens = context_window - reserved_response_tokens

            print(f"\nToken analysis:")
            print(f"- Question tokens: {question_tokens}")
            print(f"- Content tokens: {content_tokens}")
            print(f"- Total tokens: {total_tokens}")
            print(f"- Available context window: {context_window}")
            print(f"- Max input tokens (after reserving {reserved_response_tokens} for response): {max_input_tokens}")

            # If content clearly exceeds the limit, warn the user before attempting
            if total_tokens > max_input_tokens and total_tokens > context_window:
                truncation_amount = total_tokens - max_input_tokens
                print(
                    f"\nWARNING: Content exceeds ChatGPT's {max_input_tokens} token limit by {truncation_amount} tokens")

                # Offer options upfront if we know it will fail
                if truncation_amount > 5000:  # Definitely too big to handle directly
                    return self._handle_token_limit_exceeded(combined_content, question, max_input_tokens)

            # Try direct processing first, even if it might be over the limit
            # The API will reject it if it's too large
            try:
                print("\nAttempting to process content directly with ChatGPT...")
                return self._process_content(combined_content, question)
            except Exception as e:
                error_msg = str(e).lower()
                # Check if the error is related to token limits
                if "token" in error_msg and ("exceed" in error_msg or "limit" in error_msg or "maximum" in error_msg):
                    print(f"\nError: Content exceeds ChatGPT's token limit. Error: {e}")
                    return self._handle_token_limit_exceeded(combined_content, question, max_input_tokens)
                else:
                    # For other errors, re-raise
                    raise
        else:
            # For non-ChatGPT models, use existing logic
            available_tokens = self.max_tokens if self.max_tokens > 0 else self.model_params["context_window"]
            reserved_response_tokens = self.model_params["response_tokens"]
            max_input_tokens = available_tokens - reserved_response_tokens

            print(f"\nToken analysis:")
            print(f"- Question tokens: {question_tokens}")
            print(f"- Content tokens: {content_tokens}")
            print(f"- Total tokens: {total_tokens}")
            print(f"- Available context window: {available_tokens}")
            print(f"- Max input tokens (after reserving {reserved_response_tokens} for response): {max_input_tokens}")

            # If content fits within token limit, process it directly
            if total_tokens <= max_input_tokens:
                print("\nContent fits within token limit - processing directly")
                return self._process_content(combined_content, question)

            # Otherwise, use chunking strategy
            print(f"\nContent exceeds token limit - using '{self.chunking_strategy}' chunking strategy")

            if self.chunking_strategy == "document":
                return self._process_with_document_chunking(notes, question)
            elif self.chunking_strategy == "token":
                return self._process_with_token_chunking(combined_content, question, max_input_tokens)
            elif self.chunking_strategy == "recursive":
                return self._process_with_recursive_summarization(notes, question)
            else:  # "auto" or any other value
                # Choose strategy based on content size
                if len(notes) > 10:
                    return self._process_with_document_chunking(notes, question)
                else:
                    return self._process_with_token_chunking(combined_content, question, max_input_tokens)

    def _handle_token_limit_exceeded(self, combined_content, question, max_input_tokens):
        """Handle the case where content exceeds token limits for ChatGPT"""
        print("\nOptions:")
        print("1. Proceed with truncation (will lose information from the end of the document)")
        print("2. Enable token chunking (processes document in parts)")

        choice = input("Enter choice (1/2) [2]: ") or "2"

        if choice == "1":
            # Truncate content to fit
            print("\nTruncating content to fit within token limit...")

            # Calculate how many tokens we need to keep
            question_tokens = self.count_tokens(f"Read the following documents and answer: {question}")
            available_content_tokens = max_input_tokens - question_tokens

            # Approximate token-based truncation
            truncated_content = self._truncate_to_token_limit(combined_content, available_content_tokens)
            print(f"Truncated content to approximately {self.count_tokens(truncated_content)} tokens")

            # Process truncated content
            return self._process_content(truncated_content, question)
        else:
            # Use token chunking
            print("\nUsing token chunking strategy...")
            return self._process_with_token_chunking(combined_content, question, max_input_tokens)

    def _truncate_to_token_limit(self, content, max_tokens):
        """Truncate content to approximately fit within token limit"""
        if self.count_tokens(content) <= max_tokens:
            return content

        # Simple truncation approach - split into lines and keep adding until limit
        lines = content.split('\n')
        truncated_lines = []
        current_tokens = 0

        for line in lines:
            line_tokens = self.count_tokens(line + '\n')
            if current_tokens + line_tokens > max_tokens:
                break
            truncated_lines.append(line)
            current_tokens += line_tokens

        truncated_content = '\n'.join(truncated_lines)

        # Add a note about truncation
        truncation_note = "\n\n[NOTE: Content has been truncated due to token limits]"
        truncated_content += truncation_note

        return truncated_content

    def _process_with_document_chunking(self, notes, question):
        """Process each document separately, then synthesize results"""
        print("\nProcessing each document separately and then synthesizing...")

        individual_results = []

        for i, note in enumerate(notes):
            print(f"\nProcessing note {i + 1}/{len(notes)}: {note['title']}")

            # Create prompt for this individual note
            individual_content = f"NOTE: {note['title']}\n\n{note['content']}"

            # Process the individual note with a slightly modified question
            individual_question = f"Extract key information from this document that's relevant to the following question: {question}"
            result = self._process_content(individual_content, individual_question)
            individual_results.append(result)

            # Add a short delay between processing notes to avoid rate limiting
            if i < len(notes) - 1:
                time.sleep(0.5)

        # Combine all individual results
        synthesis_content = "\n\n===== DOCUMENT SUMMARY SEPARATOR =====\n\n".join(
            [f"DOCUMENT {i + 1} - {notes[i]['title']}:\n\n{result}" for i, result in enumerate(individual_results)]
        )

        # Final synthesis with the original question
        synthesis_question = f"Based on these document summaries, answer the original question: {question}"
        final_result = self._process_content(synthesis_content, synthesis_question)

        return final_result

    def _process_with_token_chunking(self, content, question, max_input_tokens):
        """Process content in chunks based on token count with overlap"""
        print("\nProcessing content in chunks based on token count...")

        # Calculate tokens for question and instruction part
        question_prefix = f"Read this document chunk and extract key information relevant to the question: {question}\n\nDocument chunk:\n\n"
        question_tokens = self.count_tokens(question_prefix)

        # Calculate available tokens for content in each chunk
        available_chunk_tokens = max_input_tokens - question_tokens

        # Split content into chunks
        chunks = self._split_into_chunks(content, available_chunk_tokens)

        print(f"Split content into {len(chunks)} chunks")

        # Process each chunk
        chunk_results = []
        for i, chunk in enumerate(chunks):
            print(f"\nProcessing chunk {i + 1}/{len(chunks)} ({self.count_tokens(chunk)} tokens)")

            # For first chunk, mention it's the beginning
            if i == 0:
                chunk_prefix = "BEGINNING OF DOCUMENT: "
            # For last chunk, mention it's the end
            elif i == len(chunks) - 1:
                chunk_prefix = "END OF DOCUMENT: "
            else:
                chunk_prefix = f"DOCUMENT CHUNK {i + 1}: "

            chunk_content = chunk_prefix + chunk

            # For chunks, extract relevant information rather than answering directly
            chunk_question = f"Extract key information from this document chunk that's relevant to the question: {question}"
            result = self._process_content(chunk_content, chunk_question)
            chunk_results.append(result)

            # Add a short delay between processing chunks
            if i < len(chunks) - 1:
                time.sleep(0.5)

        # Combine chunk results
        synthesis_content = "\n\n===== CHUNK SUMMARY SEPARATOR =====\n\n".join(
            [f"CHUNK {i + 1}:\n\n{result}" for i, result in enumerate(chunk_results)]
        )

        # Final synthesis
        synthesis_question = f"Based on these document chunk summaries, answer the original question: {question}"
        final_result = self._process_content(synthesis_content, synthesis_question)

        return final_result

    def _split_into_chunks(self, content, max_chunk_tokens):
        """Split content into chunks based on token count with overlap"""
        chunks = []
        lines = content.split('\n')
        current_chunk = []
        current_token_count = 0

        for line in lines:
            line_tokens = self.count_tokens(line + '\n')

            # If adding this line would exceed the limit, finalize the current chunk
            if current_token_count + line_tokens > max_chunk_tokens and current_chunk:
                # Join current chunk and add to chunks list
                chunk_text = '\n'.join(current_chunk)
                chunks.append(chunk_text)

                # Start new chunk with overlap
                # Take the last few lines from the previous chunk for context
                overlap_lines = min(10, len(current_chunk))
                current_chunk = current_chunk[-overlap_lines:]
                current_token_count = self.count_tokens('\n'.join(current_chunk) + '\n')

            # Add the current line to the chunk
            current_chunk.append(line)
            current_token_count += line_tokens

        # Add the last chunk if it's not empty
        if current_chunk:
            chunks.append('\n'.join(current_chunk))

        return chunks

    def _process_with_recursive_summarization(self, notes, question):
        """Process large documents by recursively summarizing groups of documents"""
        print("\nUsing recursive summarization strategy for large content...")

        # If only a few notes, process them directly using token chunking
        if len(notes) <= 5:
            combined_content = "\n\n===== NOTE SEPARATOR =====\n\n".join(
                [f"NOTE: {note['title']}\n\n{note['content']}" for note in notes]
            )
            max_input_tokens = self.max_tokens - self.model_params["response_tokens"]
            return self._process_with_token_chunking(combined_content, question, max_input_tokens)

        # Otherwise, group notes and summarize each group
        group_size = max(2, len(notes) // 4)  # Aim for 4 groups, but at least 2 notes per group
        groups = [notes[i:i + group_size] for i in range(0, len(notes), group_size)]

        print(
            f"Recursive summarization: split {len(notes)} notes into {len(groups)} groups of ~{group_size} notes each")

        # Process each group
        group_results = []
        for i, group in enumerate(groups):
            print(f"\nProcessing group {i + 1}/{len(groups)} ({len(group)} notes)")

            # Recursively process each group
            if len(group) > 5:
                # If group is still large, recurse
                group_result = self._process_with_recursive_summarization(group, question)
            else:
                # Process smaller group directly
                combined_group_content = "\n\n===== NOTE SEPARATOR =====\n\n".join(
                    [f"NOTE: {note['title']}\n\n{note['content']}" for note in group]
                )
                group_question = f"Extract key information from these documents that's relevant to the question: {question}"
                group_result = self._process_content(combined_group_content, group_question)

            group_results.append(group_result)

            # Add delay between groups
            if i < len(groups) - 1:
                time.sleep(0.5)

        # Combine group results
        synthesis_content = "\n\n===== GROUP SUMMARY SEPARATOR =====\n\n".join(
            [f"GROUP {i + 1}:\n\n{result}" for i, result in enumerate(group_results)]
        )

        # Final synthesis
        synthesis_question = f"Based on these group summaries, answer the original question: {question}"
        final_result = self._process_content(synthesis_content, synthesis_question)

        return final_result

    def _process_content(self, content, question):
        """Process a single content chunk with the given question"""
        if self.use_chatgpt:
            return self.ask_chatgpt(content, question)
        elif self.use_docker_model:
            return self.ask_docker_model(content, question)
        else:
            return self.ask_ollama_cli(content, question)

    def ask_ollama_cli(self, content, question):
        """Send a query to Ollama CLI"""
        prompt = f"{question}\n\n{content}"
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
        """Send a query to ChatGPT API"""
        if not self.api_key:
            return "Error: OpenAI API key is required for ChatGPT"

        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        data = {
            "model": self.model_name or "gpt-4o",
            "messages": [
                {"role": "system", "content": "You are a helpful assistant that answers questions about documents."},
                {"role": "user", "content": f"Document content:\n\n{content}\n\nQuestion: {question}"}
            ],
            "temperature": 0.7,
            "max_tokens": self.model_params["response_tokens"]
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
        prompt = f"Read this document and answer: {question}\n\n{content}"

        # Format request for OpenAI-compatible API
        headers = {"Content-Type": "application/json"}
        data = {
            "model": self.model_name,
            "prompt": prompt,
            "max_tokens": self.model_params["response_tokens"],
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

    def process_notes_in_parallel(self, notes, question, max_workers=2):
        """Process notes in parallel using a ThreadPoolExecutor"""
        # Only use parallelization with multiple notes
        if len(notes) <= 1:
            return self.process_notes_together(notes, question)

        print(f"\nProcessing {len(notes)} notes in parallel with {max_workers} workers")

        # First, analyze if we should use document chunking
        if len(notes) > 4:
            # For many documents, use document chunking
            group_size = max(1, len(notes) // max_workers)
            groups = [notes[i:i + group_size] for i in range(0, len(notes), group_size)]

            print(f"Using document chunking with {len(groups)} groups")

            results = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Process each group in parallel
                futures = {
                    executor.submit(self.process_notes_together, group,
                                    f"Extract key information from these documents relevant to: {question}"): i
                    for i, group in enumerate(groups)
                }

                for future in concurrent.futures.as_completed(futures):
                    group_idx = futures[future]
                    try:
                        result = future.result()
                        results.append((group_idx, result))
                        print(f"Completed group {group_idx + 1}/{len(groups)}")
                    except Exception as e:
                        print(f"Error processing group {group_idx + 1}: {e}")
                        results.append((group_idx, f"Error: {str(e)}"))

            # Sort results by group index
            results.sort(key=lambda x: x[0])

            # Combine results
            combined_results = "\n\n===== GROUP SEPARATOR =====\n\n".join(
                [f"GROUP {idx + 1} ({len(groups[idx])} notes):\n\n{result}" for idx, result in results]
            )

            # Final synthesis
            synthesis_question = f"Based on these document group summaries, answer the original question: {question}"

            # Create special synthesizer object that uses recursive_summarization if needed
            return self._process_content(combined_results, synthesis_question)
        else:
            # For few documents, process each individually
            print(f"Processing {len(notes)} notes individually in parallel")

            results = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Process each note in parallel
                futures = {
                    executor.submit(self._process_content,
                                    f"NOTE: {note['title']}\n\n{note['content']}",
                                    f"Extract key information from this document relevant to: {question}"): i
                    for i, note in enumerate(notes)
                }

                for future in concurrent.futures.as_completed(futures):
                    note_idx = futures[future]
                    try:
                        result = future.result()
                        results.append((note_idx, result))
                        print(f"Completed note {note_idx + 1}/{len(notes)}: {notes[note_idx]['title']}")
                    except Exception as e:
                        print(f"Error processing note {note_idx + 1}: {e}")
                        results.append((note_idx, f"Error: {str(e)}"))

            # Sort results by note index
            results.sort(key=lambda x: x[0])

            # Combine results
            combined_results = "\n\n===== NOTE SUMMARY SEPARATOR =====\n\n".join(
                [f"NOTE SUMMARY {idx + 1} - {notes[idx]['title']}:\n\n{result}" for idx, result in results]
            )

            # Final synthesis
            synthesis_question = f"Based on these note summaries, answer the original question: {question}"
            return self._process_content(combined_results, synthesis_question)


class SimpleTokenizer:
    """Simple tokenizer that approximates token count based on whitespace and punctuation"""

    def count_tokens(self, text):
        """Approximate token count for text"""
        if not text:
            return 0

        # Simple tokenization rules
        # 1. Roughly 4 characters per token for English text
        # 2. Adjust for whitespace and punctuation

        # First, count words (roughly equivalent to tokens for many models)
        words = len(text.split())

        # Then adjust for special characters, numbers, etc.
        chars = len(text)

        # A rough estimate: mix of character count and word count
        token_estimate = words + chars // 8

        return token_estimate


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
    ai_group.add_argument("--host", default="http://localhost:11434", help="Ollama server URL")
    ai_group.add_argument("--docker-model-endpoint",
                          help="URL for Docker Model Runner API (default: http://model-runner.docker.internal/engines/v1)")
    ai_group.add_argument("--api-key", help="OpenAI API key for ChatGPT")
    ai_group.add_argument("-q", "--question", help="Question to ask about the note")

    # Token management options
    token_group = parser.add_argument_group('Token Management Options')
    token_group.add_argument("--max-tokens", type=int, default=0,
                             help="Maximum token limit for content (0 = use model default)")
    token_group.add_argument("--chunking-strategy", choices=['auto', 'document', 'token', 'recursive'],
                             default='auto', help="Strategy for chunking large content")
    token_group.add_argument("--overlap-tokens", type=int, default=100,
                             help="Overlap tokens between chunks when using token chunking")
    token_group.add_argument("--parallel", action="store_true",
                             help="Process notes in parallel when possible (for multiple notes)")
    token_group.add_argument("--max-workers", type=int, default=2,
                             help="Maximum number of worker threads for parallel processing")

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
    parser.add_argument("-v", "--verbose", action="store_true", help="Show verbose token information")
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
        docker_model_endpoint=args.docker_model_endpoint,
        max_tokens=args.max_tokens,
        chunking_strategy=args.chunking_strategy,
        overlap_tokens=args.overlap_tokens
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

    # Apply limit IMMEDIATELY after finding notes
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
        except (ValueError, TypeError):
            print("\nWarning: Invalid limit value. Processing all notes.")

    # Display matching notes (after limiting)
    total_notes = len(matching_notes)  # This will be the limited count if limit was applied
    print("\nMatching Notes:")
    for i, note in enumerate(matching_notes, 1):
        print(f"{i}. {note['title']} (Modified: {note['date_modified']})")
        if args.verbose:
            token_count = processor.count_tokens(note['content'])
            print(f"   - Estimated tokens: {token_count}")

    # Just list the notes if requested
    if args.list:
        return

    # Display token stats if verbose
    if args.verbose:
        all_content = "\n\n".join([note['content'] for note in matching_notes])
        total_tokens = processor.count_tokens(all_content)
        question_tokens = processor.count_tokens(args.question)
        print(f"\nTotal content tokens: {total_tokens}")
        print(f"Question tokens: {question_tokens}")
        print(f"Combined tokens: {total_tokens + question_tokens}")
        print(f"Model context window: {processor.model_params['context_window']}")
        print(f"Chunking strategy: {args.chunking_strategy}")

    # Ask for confirmation before processing
    if not args.yes:
        confirmation = input(f"\nFound {total_notes} matching notes. Process them? (y/n) [y]: ")
        if confirmation.lower() and confirmation.lower() != 'y':
            print("Operation cancelled.")
            return

    # Choose processing method
    ai_type = "ChatGPT" if args.chatgpt else "Docker Model Runner" if args.docker_model else f"Ollama ({args.model})"

    if args.parallel and total_notes > 1:
        # Use parallel processing
        print(f"\nProcessing {total_notes} notes in parallel with {args.max_workers} workers")
        print(f"Asking {ai_type}: {args.question}")
        print("\nAI response:")
        print("-" * 40)

        response = processor.process_notes_in_parallel(
            matching_notes,
            args.question,
            max_workers=args.max_workers
        )
        print(response)
        print("-" * 40)
    elif args.batch_size is not None:
        # Process notes in batches
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
        print(response)
    else:
        # Process all notes together by default
        print(f"\nProcessing all {total_notes} notes using {args.chunking_strategy} chunking strategy")
        print(f"Asking {ai_type}: {args.question}")
        print("\nAI response:")
        print("-" * 40)

        response = processor.process_notes_together(matching_notes, args.question)
        print(response)
        print("-" * 40)


if __name__ == "__main__":
    main()