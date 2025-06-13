#!/usr/bin/env python3
"""
Main entry point for the ClaudeCurator server package.
This can be used as a console script entry point.
"""
import os
import sys
from pathlib import Path
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from .curator_server import CuratorServer


def main():
    """Main entry point for the curator server"""
    # Load environment variables from .env file
    load_dotenv()

    curator_app = Flask(__name__)

    # Configuration
    GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
    GITHUB_SECRET = os.environ.get("GITHUB_SECRET")  # For webhook verification
    REPO_OWNER = os.environ.get("REPO_OWNER")
    REPO_NAME = os.environ.get("REPO_NAME")

    # System prompt for Claude - more efficient as system prompts don't count toward token usage
    system_prompt_file = Path("system_prompt.txt")
    SYSTEM_PROMPT = None

    if system_prompt_file.exists():
        with system_prompt_file.open("r") as f:
            SYSTEM_PROMPT = f.read().strip()
    else:
        print("⚠️ WARNING: system_prompt.txt not found!")
        raise FileNotFoundError("Please create a system_prompt.txt file with the system prompt for Claude.")

    server = CuratorServer(system_prompt=SYSTEM_PROMPT,
                           github_token=GITHUB_TOKEN,
                           anthropic_api_key=ANTHROPIC_API_KEY,
                           repo_owner=REPO_OWNER,
                           repo_name=REPO_NAME,
                           github_secret=GITHUB_SECRET)

    @curator_app.route('/webhook', methods=['POST'])
    def github_webhook():
        signature = request.headers.get('X-Hub-Signature-256')
        verify_result = server.verify_signature(request.data, signature)
        
        if not verify_result:
            return jsonify({"error": "Invalid signature"}), 401

        # Parse the webhook payload
        event = request.headers.get('X-GitHub-Event')
        payload = request.json
        
        # Let the server handle and return the response
        return server.handle_event(event, payload)

    curator_app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))


if __name__ == '__main__':
    main()