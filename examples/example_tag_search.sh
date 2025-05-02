# examples/example_tag_search.sh
#!/bin/bash
# Example of searching notes by tag and processing with Ollama

../bear_notes_ai.py --ollama -t "research" -q "What are the key findings from my research?" -y

# examples/example_keyword_search.sh
#!/bin/bash
# Example of searching notes by keyword and processing with ChatGPT

../bear_notes_ai.py --chatgpt --api-key "your-openai-api-key" -k "meeting notes" -q "Summarize all action items from these meetings" -y

# examples/example_url_search.sh
#!/bin/bash
# Example of processing a specific note via Bear URL

../bear_notes_ai.py --ollama -u "bear://x-callback-url/open-note?id=your-note-id-here" -q "Give me a summary of the main points" -y