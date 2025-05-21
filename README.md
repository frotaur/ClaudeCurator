# Claude Curator

A GitHub repository curator powered by Claude AI that automatically reviews and manages pull requests based on the repository guidelines.

## How It Works

1. When a pull request is opened, GitHub sends a webhook notification to this application
2. The application fetches the PR details and contents
3. Claude AI reviews the PR against the repository guidelines
4. Based on Claude's decision, the PR is either:
   - Approved and merged with an explanatory comment
   - Rejected with an explanatory comment and closed

## Setup Instructions

### Prerequisites

- GitHub repository
- GitHub personal access token with repo permissions
- Anthropic API key

### Environment Variables

Create a `.env` file with the following variables:

```
GITHUB_TOKEN=your_github_token
ANTHROPIC_API_KEY=your_anthropic_api_key
GITHUB_SECRET=your_webhook_secret
REPO_OWNER=github_username
REPO_NAME=repository_name
```

### Installation

1. Clone this repository
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Run the application:
   ```
   python app.py
   ```

### Setting Up GitHub Webhook

1. Go to your repository's Settings > Webhooks
2. Add a new webhook:
   - Payload URL: Your server's URL (e.g., `https://your-server.com/webhook`)
   - Content type: `application/json`
   - Secret: Same as GITHUB_SECRET
   - Events: Select "Pull requests"

## Deployment

This application can be deployed on:
- Heroku
- AWS Lambda + API Gateway
- Google Cloud Run
- Any server with Python installed

## License

MIT