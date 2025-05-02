#!/usr/bin/env python3
"""
Bear Notes AI Integration - Docker API Service
"""

import os
import json
import requests
import datetime
import logging
from flask import Flask, render_template, request, jsonify, make_response
from flask_caching import Cache
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

app = Flask(__name__, static_url_path='/static', static_folder='static')

# Configure cache
cache_config = {
    "CACHE_TYPE": "SimpleCache",  # Simple in-memory cache
    "CACHE_DEFAULT_TIMEOUT": 300  # 5 minutes
}
cache = Cache(app, config=cache_config)

# Configure rate limiter
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)


def configure_logging():
    """Configure application logging"""
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    numeric_level = getattr(logging, log_level, logging.INFO)

    # Configure Flask logger
    app.logger.setLevel(numeric_level)

    # Add a formatter to the handler
    formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s in %(module)s: %(message)s'
    )
    for handler in app.logger.handlers:
        handler.setFormatter(formatter)


def get_llm_endpoint():
    """Returns the complete LLM API endpoint URL"""
    base_url = os.getenv("LLM_BASE_URL", "http://localhost:11434/api")
    return f"{base_url}/generate"  # For Ollama compatibility


def get_model_name():
    """Returns the model name to use for API requests"""
    # Model can be specified via env var, with a fallback to llama3
    model = os.getenv("LLM_MODEL_NAME", "llama3")
    app.logger.info(f"Using model: {model}")
    return model


def validate_environment():
    """Validates required environment variables and provides warnings"""
    llm_base_url = os.getenv("LLM_BASE_URL", "")
    llm_model_name = os.getenv("LLM_MODEL_NAME", "")

    if not llm_base_url:
        app.logger.warning("LLM_BASE_URL is not set. API calls will fail.")

    if not llm_model_name:
        app.logger.warning("LLM_MODEL_NAME is not set. Using default model.")

    return llm_base_url and llm_model_name


@app.route('/health')
def health_check():
    """Health check endpoint for container orchestration"""
    # Check if LLM API is accessible
    llm_status = "ok"
    try:
        # Simple check if the LLM endpoint is configured
        if not get_llm_endpoint():
            llm_status = "not_configured"
    except Exception as e:
        llm_status = "error"
        app.logger.error(f"Health check error: {e}")

    return jsonify({
        "status": "healthy",
        "llm_api": llm_status,
        "timestamp": datetime.datetime.now().isoformat()
    })


def validate_chat_request(data):
    """Validates and sanitizes chat API request data"""
    if not isinstance(data, dict):
        return False, "Invalid request format"

    message = data.get('message', '')
    if not message or not isinstance(message, str):
        return False, "Message is required and must be a string"

    if len(message) > 32000:  # Higher limit for note processing
        return False, "Message too long (max 32000 characters)"

    # Extract model if provided
    model = data.get('model')

    return True, (message, model)


@app.route('/api/chat', methods=['POST'])
@limiter.limit("10 per minute")
def chat_api():
    """Processes chat API requests"""
    data = request.json

    # Validate request
    valid, result = validate_chat_request(data)
    if not valid:
        return jsonify({'error': result}), 400

    message, custom_model = result

    # Special command for getting model info
    if message == "!modelinfo":
        return jsonify({'model': get_model_name()})

    # Call the LLM API
    try:
        # Use the custom model if provided, otherwise use default
        model_to_use = custom_model if custom_model else get_model_name()
        app.logger.info(f"Using model for request: {model_to_use}")
        response = call_llm_api(message, model_to_use)
        return jsonify({'response': response})
    except Exception as e:
        app.logger.error(f"Error calling LLM API: {e}")
        return jsonify({'error': 'Failed to get response from LLM'}), 500


@cache.memoize(timeout=300)
def call_llm_api(user_message, model_name=None):
    """Calls the LLM API and returns the response with caching"""
    # Use provided model or fall back to default
    model = model_name or get_model_name()

    # Format request based on Ollama API
    ollama_request = {
        "model": model,
        "prompt": user_message,
        "stream": False
    }

    headers = {"Content-Type": "application/json"}

    # Send request to LLM API
    app.logger.info(f"Sending request to LLM API: {get_llm_endpoint()} with model: {model}")
    response = requests.post(
        get_llm_endpoint(),
        headers=headers,
        json=ollama_request,
        timeout=180  # Even longer timeout for processing larger documents
    )

    # Check if the status code is not 200 OK
    if response.status_code != 200:
        raise Exception(f"API returned status code {response.status_code}: {response.text}")

    # Parse the response (format may vary based on the LLM service)
    api_response = response.json()

    # Extract response based on Ollama API format
    if "response" in api_response:
        return api_response["response"].strip()

    raise Exception("No valid response received from API")


@app.after_request
def add_security_headers(response):
    """Add security headers to response"""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'

    return response


if __name__ == '__main__':
    # Configure logging
    configure_logging()

    # Validate environment
    port = int(os.getenv("PORT", 8081))
    env_valid = validate_environment()

    if not env_valid:
        app.logger.warning("Environment not fully configured. Some features may not work.")

    app.logger.info(f"Server starting on http://localhost:{port}")
    app.logger.info(f"Using LLM endpoint: {get_llm_endpoint()}")
    app.logger.info(f"Using model: {get_model_name()}")

    app.run(host='0.0.0.0', port=port, debug=os.getenv("DEBUG", "false").lower() == "true")