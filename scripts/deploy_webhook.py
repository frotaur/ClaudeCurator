"""
Helper script to create a GitHub webhook for your repository, and to setup the .env file with necessary configurations.
"""

import os
import argparse
import secrets
import requests
from dotenv import load_dotenv

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

def generate_env_file(token, owner, repo, webhook_url, api_key, secret, port):
    """Generate a .env file with the provided values"""
    env_content = f"""GITHUB_TOKEN={token}
ANTHROPIC_API_KEY={api_key}
GITHUB_SECRET={secret}
REPO_OWNER={owner}
REPO_NAME={repo}
WEBHOOK_URL={webhook_url}
PORT={port}
"""
    
    with open(".env", "w") as f:
        f.write(env_content)
    
    print("✅ Created .env file with your configuration")

def main():
    parser = argparse.ArgumentParser(description="Set up Claude Curator .env and associated GitHub webhook. You can also modify the .env manually, and this script will only ask for missing values. See .env.example")
    
    # Use arguments or environment variables or prompt user
    github_token = os.environ.get("GITHUB_TOKEN") or input("Curator's GitHub access token: ")
    repo_owner = os.environ.get("REPO_OWNER") or input("Repository owner: ")
    repo_name = os.environ.get("REPO_NAME") or input("Repository name: ")
    webhook_url = os.environ.get("WEBHOOK_URL") or input("Webhook URL (e.g., https://your-server.com), /webhook will be added automatically: ")
    api_key = os.environ.get("ANTHROPIC_API_KEY") or input("Anthropic API key: ")
    webhook_secret = os.environ.get("GITHUB_SECRET") or input("Webhook secret (leave blank to generate a random one): ")
    server_port = os.environ.get("PORT") or input("Server port (default 2718): ") or "2718"

    if(not webhook_url.endswith("webhook")):
        webhook_url = webhook_url.rstrip("/") + "/webhook"  # Ensure the URL ends with /webhook
    # Generate a random webhook secret
    if(webhook_secret == ""):
        webhook_secret = secrets.token_hex(20)

    if create_github_webhook(github_token, repo_owner, repo_name, webhook_url, webhook_secret):
        generate_env_file(github_token, repo_owner, repo_name, webhook_url, api_key, webhook_secret, server_port)

        print("\n✨ Claude Curator setup complete! ✨")
        print(f"\nYour webhook secret: {webhook_secret}")
        print("This secret has been saved to your .env file.")
        print("\nNext steps:")
        print("1. Run 'run-server -p' to start the Curator server")
        print("2. Make sure your server is accessible at the webhook URL you provided")
        print("3. Test it out by creating a pull request!")
    else:
        print("❌ Webhook creation failed. Ensure that your GitHub token has permission to create webhooks in the repository.")
        print("Alternatively, create the webhook manually!")

if __name__ == "__main__":
    main()