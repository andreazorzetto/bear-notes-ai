# Bear Notes AI Integration

<img src="bear-ai-logo.png" alt="Bear AI Logo" width="150"/>


Your Bear notes are now searchable via AI. Finally put those 237 half-written thoughts to good use.

## What It Does

- Unleashes AI on your hoarded Bear notes collection
- Works with Ollama (free/slow), ChatGPT (expensive/fast), or Docker Model Runner
- Filters by tags (#obsession), keywords ("todo"), or direct URLs
- Batch processing for when you've gone note-crazy

## Requirements

- macOS (your $2000 PDF reader with Bear app installed)
- Python 3.6+ (the world's slowest programming language that somehow runs everything)
- Choose your AI poison: Ollama, OpenAI API credits, or Docker Model Runner

## Setup

```bash
git clone https://github.com/yourusername/bear-notes-ai.git
cd bear-notes-ai
pip install -r requirements.txt
chmod +x bear_notes_ai.py
```

## Usage Examples

```bash
# Free AI (Ollama)
./bear_notes_ai.py --ollama -t "projectnotes" -q "What deadlines did I ignore?"

# Expensive AI (GPT-4o)
./bear_notes_ai.py --chatgpt --api-key "sk-yourwalletisempty" -k "meeting" -q "Summarize those meetings I pretended to attend"

# Docker AI (local)
./bear_notes_ai.py --docker-model -m "ai/llama3.1:7b-instruct-Q5_K_M" -t "research" -q "What did I discover?"
```

## Core Options

- Search: `-t/--tag`, `-k/--keyword`, `-u/--url`  
- AI: `--ollama`, `--chatgpt`, `--docker-model`
- Processing: `--limit N`, `--batch-size N`, `--batch-delay N`

## Advanced Features

- `--limit 10`: Process only the 10 most recent notes (for the chronically verbose)
- `--batch-size 5`: Process notes in batches to avoid API rate limits or thermal throttling
- `-l/--list`: Preview matching notes without wasting tokens
- `-y/--yes`: Skip confirmation for the dangerously confident

## Future Development

- Bulk modification capabilities (for when AI decides your notes need a complete rewrite)
- More AI models support (because choice paralysis is the true mark of a modern app)
- Deeper Bear integration (we're going hibernating with this bear)

## Setup Guides

- ChatGPT: See `chatgpt_setup_guide.md` (requires credit card and soul)
- Ollama: Install from [ollama.ai](https://ollama.ai), run `ollama pull llama3`, done
- Docker Model Runner: Run `./docker_model_setup.sh` (requires Docker Desktop 4.40+)

## Support The Developer

<a href="https://www.paypal.com/donate/?business=vim-double6e@icloud.com&no_recurring=0&item_name=Support+Bear+Notes+AI+Development&currency_code=USD">
  <img src="https://img.shields.io/badge/PayPal-Buy%20me%20coffee%20to%20maintain%20my%20caffeine%20hallucinations-blue?style=for-the-badge&logo=paypal" alt="Donate with PayPal" />
</a>

*Because building AI tools for note hoarders doesn't pay for itself. Or at all.*

## License

GPL v3 - See LICENSE file for details, or don't, we're not lawyers.