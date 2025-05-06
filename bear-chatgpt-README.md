# Bear Notes to ChatGPT Integration

This tool allows you to send Bear notes directly to ChatGPT and capture the response, all through a seamless integration using a Python script and a Firefox Tampermonkey script.

## Features

- Search Bear notes by tag, keyword, or direct URL
- Send notes directly to ChatGPT web interface
- Auto-submit the query to ChatGPT
- Capture ChatGPT's response back to your terminal
- Option to save responses to a file

## Requirements

- Python 3.6+
- Firefox browser
- Tampermonkey browser extension
- Bear Notes (macOS only, as it requires access to the Bear database)

## Installation

1. **Save the Python Script**:
   - Save `bear_to_chatgpt.py` to your preferred location
   - Make it executable: `chmod +x bear_to_chatgpt.py`

2. **Generate the Tampermonkey Script**:
   ```
   ./bear_to_chatgpt.py --gen-script
   ```

3. **Install the Tampermonkey Script**:
   - Install the Tampermonkey extension in Firefox
   - Open Tampermonkey dashboard
   - Create a new script
   - Copy and paste the content from `bear_to_chatgpt.user.js`
   - Save the script

## Usage

### Basic Usage

```
./bear_to_chatgpt.py -t programming -q "What are the key concepts in these notes?"
```

This will:
1. Search for Bear notes with the tag "programming"
2. Format them with your question
3. Start a local server
4. Open ChatGPT in your browser
5. (You'll click the "Fetch & Paste Bear Notes" button that appears)
6. ChatGPT will automatically receive the content and respond
7. (You'll click the "Capture ChatGPT Response" button)
8. The response will appear in your terminal
9. You'll be asked if you want to save it to a file

### Advanced Options

```
./bear_to_chatgpt.py -t programming -k "python" -q "Summarize these notes" --limit 5
```

This searches for notes with both tag "programming" and keyword "python", limiting to 5 notes.

### Command Line Options

- `-t, --tag`: Search for notes with this tag
- `-k, --keyword`: Search for notes containing this keyword
- `-u, --url`: Use a specific Bear note URL (format: bear://x-callback-url/open-note?id=NOTE-ID)
- `-q, --question`: Question to ask ChatGPT about the notes
- `-l, --list`: Just list matching notes without processing
- `--limit N`: Limit to N most recent notes
- `-y, --yes`: Process notes without confirmation
- `--port`: Set custom port for local server (default: 8765)
- `--gen-script`: Generate Tampermonkey script and exit
- `--debug`: Show additional debug information

## How It Works

1. The Python script searches the Bear Notes database for matching notes
2. It starts a small local HTTP server to serve the formatted content
3. The script opens ChatGPT in your browser
4. The Tampermonkey script adds UI buttons to ChatGPT's interface
5. When you click "Fetch & Paste Bear Notes", it retrieves content from the local server
6. The content is automatically submitted to ChatGPT
7. When ChatGPT finishes responding, the "Capture Response" button appears
8. Clicking it sends the response back to your terminal
9. The server automatically closes, displaying the response

## Troubleshooting

- **Script won't run**: Ensure Python 3.6+ is installed and the script is executable
- **Bear database not found**: Make sure Bear is installed and you've used it before
- **Tampermonkey button not appearing**: Refresh the ChatGPT page and check if Tampermonkey is enabled
- **Response capture fails**: Try clicking the button again after ensuring ChatGPT has completely finished its response

## License

This project is released under the MIT License.
