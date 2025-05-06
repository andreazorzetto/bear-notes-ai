# Bear Notes to ChatGPT

Send Bear notes to ChatGPT and get responses automatically in your terminal.

## Quick Start

1. Save both scripts (`bear-chatgpt.py` and `bear-chatgpt.user.js`)
2. Install the user script in Firefox Tampermonkey
3. Run: `python bear-chatgpt.py -t yourtag -q "Your question"`

## Requirements

- Python 3.6+
- Firefox with Tampermonkey
- Bear Notes (macOS)

## Key Commands

```bash
# Generate userscript
python bear-chatgpt.py --gen-script

# Search by tag
python bear-chatgpt.py -t programming -q "Summarize these notes"

# Search by keyword
python bear-chatgpt.py -k python -q "Extract key concepts"

# Direct Bear note URL
python bear-chatgpt.py -u "bear://x-callback-url/open-note?id=NOTE-ID" -q "Question"

# List matching notes without processing
python bear-chatgpt.py -t programming -l

# Limit results
python bear-chatgpt.py -t programming -q "Question" --limit 3

# Skip confirmation
python bear-chatgpt.py -t programming -q "Question" -y
```

## How It Works

1. Python script finds matching Bear notes
2. A local server starts to serve the content
3. ChatGPT opens in Firefox
4. Tampermonkey script:
   - Fetches note content
   - Sends to ChatGPT
   - Waits for response
   - Returns response to terminal
   - Closes tab

## Troubleshooting

- Script not working? Regenerate userscript: `python bear-chatgpt.py --gen-script`
- ChatGPT UI changed? Update the userscript selectors for inputs and buttons
- No response? Check the wait time in the userscript

Licensed under GPLv3