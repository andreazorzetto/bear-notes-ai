#!/bin/bash
# Setup script for Docker Model Runner

# Default model if not specified
MODEL=${1:-"ai/smollm2:360M-Q4_K_M"}

# Check if Docker is installed and running
if ! command -v docker &> /dev/null; then
    echo "Docker is not installed. Please install Docker Desktop first."
    exit 1
fi

if ! docker info &> /dev/null; then
    echo "Docker is not running. Please start Docker Desktop first."
    exit 1
fi

# Check Docker version for Model Runner support
DOCKER_VERSION=$(docker version --format '{{.Server.Version}}')
if [[ "$DOCKER_VERSION" < "4.40" ]]; then
    echo "Error: Docker Desktop 4.40 or higher is required for Docker Model Runner."
    echo "Please update Docker Desktop to use this feature."
    exit 1
fi

# Check if running on Apple Silicon Mac
if [[ "$(uname)" != "Darwin" ]] || [[ "$(uname -m)" != "arm64" ]]; then
    echo "Warning: Docker Model Runner currently requires macOS with Apple Silicon."
    echo "Your system may not be able to run Docker Model Runner."
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo "Setting up Docker Model Runner with model: $MODEL"

# Enable Docker Model Runner TCP access if not already enabled
echo "Ensuring Docker Model Runner TCP access is enabled..."
docker desktop enable model-runner --tcp 12434 || true

# Pull the model
echo "Pulling model $MODEL..."
docker model pull $MODEL

# Test if the model can be executed
echo "Testing model..."
docker model run $MODEL "Hi, this is a test" > /dev/null

if [ $? -eq 0 ]; then
    echo -e "\nSetup complete!"
    echo "You can now use Docker Model Runner with Bear Notes AI:"
    echo "./bear_notes_ai.py --docker-model -m $MODEL -t \"tag\" -q \"Your question\""
    echo ""
    echo "Note: By default, Docker Model Runner is accessible at:"
    echo "  - Within containers: http://model-runner.docker.internal/engines/v1"
    echo "  - From host: http://localhost:12434/engines/v1"
else
    echo -e "\nSetup failed. Please check Docker Desktop logs or try a different model."
fi
