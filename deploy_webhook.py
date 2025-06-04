#!/usr/bin/env python3
"""
Helper script to create a GitHub webhook for your repository
"""

import os
import argparse
import secrets
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def create_github_webhook(token, owner, repo, webhook_url, secret):
    """Create a GitHub webhook for the repository"""
    url = f"https://api.github.com/repos/{owner}/{repo}/hooks"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json"
    }
    data = {
        "name": "web",
        "active": True,
        "events": ["pull_request"],
        "config": {
            "url": webhook_url,
            "content_type": "json",
            "secret": secret,
            "insecure_ssl": "0"
        }
    }
    
    response = requests.post(url, headers=headers, json=data)
    
    if response.status_code == 201:
        print(f"✅ Webhook created successfully!")
        print(f"Webhook ID: {response.json()['id']}")
        return True
    else:
        print(f"❌ Failed to create webhook: {response.status_code}")
        print(response.json())
        return False

def generate_env_file(token, owner, repo, api_key, secret):
    """Generate a .env file with the provided values"""
    env_content = f"""GITHUB_TOKEN={token}
ANTHROPIC_API_KEY={api_key}
GITHUB_SECRET={secret}
REPO_OWNER={owner}
REPO_NAME={repo}
PORT=5000
"""
    
    with open(".env", "w") as f:
        f.write(env_content)
    
    print("✅ Created .env file with your configuration")

def main():
    parser = argparse.ArgumentParser(description="Set up a GitHub webhook for Claude Curator")
    parser.add_argument("--token", help="GitHub personal access token")
    parser.add_argument("--owner", help="GitHub repository owner")
    parser.add_argument("--repo", help="GitHub repository name")
    parser.add_argument("--webhook-url", help="URL where the webhook will be hosted")
    parser.add_argument("--api-key", help="Anthropic API key")
    
    args = parser.parse_args()
    
    # Use arguments or environment variables or prompt user
    github_token = args.token or os.environ.get("GITHUB_TOKEN") or input("GitHub token: ")
    repo_owner = args.owner or os.environ.get("REPO_OWNER") or input("Repository owner: ")
    repo_name = args.repo or os.environ.get("REPO_NAME") or input("Repository name: ")
    webhook_url = args.webhook_url or input("Webhook URL (e.g., https://your-server.com), /webhook will be added automatically: ")
    api_key = args.api_key or os.environ.get("ANTHROPIC_API_KEY") or input("Anthropic API key: ")
    
    webhook_url = webhook_url.rstrip("/") + "/webhook"  # Ensure the URL ends with /webhook
    # Generate a random webhook secret
    # webhook_secret = secrets.token_hex(20)
    webhook_secret = 'testsecret'
    
    # Create webhook
    if create_github_webhook(github_token, repo_owner, repo_name, webhook_url, webhook_secret):
        # Generate .env file
        generate_env_file(github_token, repo_owner, repo_name, api_key, webhook_secret)
        
        print("\n✨ Claude Curator setup complete! ✨")
        print(f"\nYour webhook secret: {webhook_secret}")
        print("This secret has been saved to your .env file.")
        print("\nNext steps:")
        print("1. Make sure your server is running at the webhook URL")
        print("2. Run 'python curator_server.py' to start the Flask server")
        print("3. Test it out by creating a pull request!")

if __name__ == "__main__":
    main()