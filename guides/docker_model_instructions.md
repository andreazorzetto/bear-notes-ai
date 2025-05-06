# Running Bear Notes AI with Docker Model Runner

This guide explains how to use Bear Notes AI with Docker Model Runner - a new feature in Docker Desktop 4.40+ that lets you run LLMs locally.

## Prerequisites

- **Docker Desktop 4.40+** on macOS with Apple Silicon
- Bear app installed on your Mac

## Quick Setup

1. Run the setup script to configure Docker Model Runner:

```bash
# Make the script executable
chmod +x setup-docker-model.sh

# Run with default model (small but fast)
./setup-docker-model.sh

# OR specify a more capable model
./setup-docker-model.sh ai/llama3.1:7b-instruct-Q5_K_M
```

2. Use the Docker Model Runner option in Bear Notes AI:

```bash
./bear_notes_ai.py --docker-model -m "ai/smollm2:360M-Q4_K_M" -t "research" -q "Summarize these notes"
```

## Available Models

Docker Model Runner provides several models out of the box:

- `ai/smollm2:360M-Q4_K_M` - Small and fast, good for simple queries
- `ai/llama3.1:7b-instruct-Q5_K_M` - Better for complex reasoning
- `ai/gemma3:2b-instruct-Q5_K_M` - Good balance of size and capability
- `ai/phi3:mini-128k-instruct-Q5_K_M` - Good for coding tasks

To see all available models:
```bash
docker model list
```

To pull a new model:
```bash
docker model pull ai/llama3.1:7b-instruct-Q5_K_M
```

## How It Works

Docker Model Runner is fundamentally different from other tools:

1. It's built into Docker Desktop and runs models natively (not in containers)
2. It provides an OpenAI-compatible API
3. It uses the same model distribution system as Docker containers

The Bear Notes AI script connects to Docker Model Runner's API endpoint at `http://model-runner.docker.internal/engines/v1` when running from within a container, or `http://localhost:12434/engines/v1` when running on the host.

## Troubleshooting

If you encounter issues:

1. **Verify Docker Desktop version**:
   ```bash
   docker version
   ```
   Make sure it's 4.40 or higher.

2. **Check Docker Model Runner is enabled**:
   ```bash
   docker desktop enable model-runner --tcp 12434
   ```

3. **Test the model directly**:
   ```bash
   docker model run ai/smollm2:360M-Q4_K_M "Hello!"
   ```

4. **Check API connectivity**:
   ```bash
   curl -X POST http://localhost:12434/engines/v1/completions \
     -H "Content-Type: application/json" \
     -d '{"model":"ai/smollm2:360M-Q4_K_M","prompt":"Hello world!","max_tokens":10}'
   ```

5. **Update Docker Desktop** if you continue to have issues.

## Additional Resources

- [Docker Model Runner Documentation](https://docs.docker.com/model-runner/)
- [Docker Hub AI Models](https://hub.docker.com/search?q=&type=model)
