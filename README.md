# Bear Notes AI Integration

<img src="bear-ai-logo.png" alt="Bear AI Logo" width="150"/>

Your Bear notes are now searchable via AI. Finally put those 237 half-written thoughts to good use.

## What It Does

- Unleashes AI on your hoarded Bear notes collection
- Works with Ollama (free/slow), ChatGPT (expensive/fast), or Docker Model Runner
- Filters by tags (#obsession), keywords ("todo"), or direct URLs
- Batch processing for when you've gone note-crazy
- Smart token management with chunking strategies for large documents
- Parallel processing for multiple notes

## Requirements

- macOS
- Python 3.6+
- Ollama, OpenAI API credits, or Docker Model Runner

## Setup

```bash
git clone https://github.com/andreazorzetto/bear-notes-ai.git
cd bear-notes-ai
pip install -r requirements.txt
chmod +x bear_notes_ai_docker.py
```

## Usage Examples

```bash
# Ollama with default model
./bear_notes_ai_docker.py --ollama -t "projectnotes" -q "What deadlines did I ignore?"

# Ollama with specific model
./bear_notes_ai_docker.py --ollama -m "llama3:latest" -k "meeting" -q "Summarize these meeting notes"

# GPT-4o
./bear_notes_ai_docker.py --chatgpt --api-key "sk-yourwalletisempty" -k "meeting" -q "Summarize those meetings zoom transcribed for me"

# Docker Model
./bear_notes_ai_docker.py --docker-model -m "deepseek-r1:latest" -t "research" -q "What did I discover?"
```

## Core Options

- Search: `-t/--tag`, `-k/--keyword`, `-u/--url`  
- AI: `--ollama`, `--chatgpt`, `--docker-model`
- Model: `-m/--model` (default: "llama3" for Ollama, "gpt-4o" for ChatGPT)

## Advanced Features

- `--limit 10`: Process only the 10 most recent notes
- `--batch-size 5`: Process notes in batches to avoid API rate limits
- `--parallel`: Enable parallel processing for multiple notes
- `--max-workers 4`: Set the number of parallel workers (default: 2)
- `--max-tokens 8000`: Override default context window size
- `--chunking-strategy`: Choose chunking strategy for large content (auto, document, token, recursive)
- `-l/--list`: Preview matching notes without wasting tokens
- `-v/--verbose`: Show detailed token information
- `-y/--yes`: Skip confirmation

## Token Management

The script automatically handles large documents by:

- Detecting context window sizes from models
- Calculating optimal chunk sizes
- Reserving appropriate tokens for responses
- Processing content using different strategies based on size

## Future Development

- Bulk modification capabilities (for when AI decides your notes need a complete rewrite)
- UI(?)
  
## Setup Guides

- ChatGPT: See `chatgpt_setup_guide.md` (requires credit card)
- Ollama: Install from [ollama.ai](https://ollama.ai), run `ollama pull llama3`, done
- Docker Model Runner: Run `./docker_model_setup.sh` (requires Docker Desktop 4.40+)

## Support The Developer

<a href="https://www.paypal.com/donate/?business=vim-double6e@icloud.com&no_recurring=0&item_name=Support+Bear+Notes+AI+Development&currency_code=USD">
  <img src="https://img.shields.io/badge/PayPal-Buy%20me%20coffee%20to%20maintain%20my%20caffeine%20hallucinations-blue?style=for-the-badge&logo=paypal" alt="Donate with PayPal" />
</a>

*Because building AI tools for note hoarders doesn't pay for itself. Or at all.*

## License

GPL v3 - See LICENSE file for details, or don't, we're not lawyers.