# Claude Curator

A simple repository curator, that queries Claude to decide whether to merge or not incoming PR's, given a 'guidelines.md' file. If you are looking to interact with a curated repository, you should [go here](https://github.com/frotaur/AICurated). For a more in depth explanation, [check out this post on my website](https://vassi.life/projects/claudecurator)

This has clearly less capability than other AI agent that can contribute/maintain repositories, and uses nothing fancy like MCP and agentic capabilities. The difference (and main idea) with this project, is that the 'guidelines.md' file is itself contained in the repository that is being maintained. As such, it may generate interesting situations, as you can gaslight the curator to change its own guidelines... My hope is that it can produce some interesting interactions with people trying to hack/protect the guidelines. As such, the limited context the curator has to work with to accept/refuse PRs can be considered a feature!

## Quick Start

1. **Install dependencies:**
Using pip :
```bash
pip install -e .
```

Using uv : 
```bash
uv sync
```

This will install the package, and install three scripts `deploy-webhook`, `run-gunicron` and `run-server`.

2. **Set up environment variables:**
For a guided setup of the necessary environment variables, run :
```bash
deploy-webhook
```
This will prompt you to give the require variables, and then setup the github webhook to allow the curator to run. Note that the provided `GITHUB_TOKEN` will be used by the curator to merge/reject pull requests, and the messages it writes will appear as coming from the account who owns `GITHUB_TOKEN`. For the webhook to be automatically created, 'GITHUB_TOKEN' must have webhook creation privilegies. Otherwise, see the **Deploy webhook** section. 

You can also do this manually. First, create a `.env` file with:

```
GITHUB_TOKEN=your_github_personal_access_token
ANTHROPIC_API_KEY=your_anthropic_api_key
REPO_NAME=curated_repository_name
REPO_OWNER=username_of_owner_of_curated_repository
GITHUB_SECRET=your_webhook_secret
WEBHOOK_URL=public_url_where_the_server_is_exposed  # Optional, only if you want to create it with 'deploy-webhook'
PORT=port_where_curator_server_will_run
```

3. **Create repository guidelines:**
Add a `guidelines.md` file to your repository's main branch with your contribution rules. We provide and example `example_guidelines.md`, but feel free to make it as you like!

4. **Deploy webhook (optional helper):**
Either deploy the webhook with the provided script, or you can deploy manually on the repository settings on github. Note that for the deploy-webhook script to work, the provided `GITHUB_TOKEN` needs to have the correct privilegies.
   ```bash
   deploy-webhook --url https://your-server.com/webhook
   ```

5. **Run the server:**
```bash
run-server --log-dir ./logs --print-log  # Custom log directory and console output
```

This will start the curator server, that will handle the PR when it receives webhook events. Note that the server is run locally, so it is your job to expose it to the internet in whichever way you prefer to connect it to github. You can use `ngrok`, for example.

The optional parameters provide a folder where to store the server logs (provide `''` to not save logs), and if the second one is included the logs will also be printed on the console.

`run-server` runs the server in 'development mode'. To run it in 'production mode' (whatever that changes, I really have no idea beyond several workers, but here we use anyway one worker because the PR should be sequential, anyway) with gunicorn, you can instead do :

```bash
run-gunicorn --log-dir ./logs --print-log # Custom log directory and console output
```

## How the Curator Works
- Listens for GitHub webhook events on `/webhook` endpoint
- Only does something if it receives as 'PR opened' or 'PR reopened' event.
- Fetches PR content and repository guidelines
- Uses Claude to review PRs against your guidelines
- Note that the review is not 'agentic', Claude can access only the content of the PR.
- Automatically approves and merges PRs or rejects non-compliant ones, with a nice explanation
- Handles both images and text, but not more.

Note that the PR reviews/merges will come from the user who owns the provided `GITHUB_TOKEN`. Ideally, I would make it a github app, and I'll consider this in the future.

### Webhook Setup

Either use the helper script or manually create a webhook:
- URL: `https://your-server.com/webhook`
- Content type: `application/json`
- Secret: Same as `GITHUB_SECRET`
- Events: Pull requests

## Repository Structure

- `src/curator_server/`: Server logic
- `scripts/`: CLI tools for running the server and deploying the webhook
- `example_guidelines.md`: Example repository guidelines
- The system prompt which is used is located in `src/curator_server/system_prompt.txt`. This could be changed, but it is entangled with how the server works. However, if you want to include some guidelines that can't be changed, it should be done in the system prompt.

## License
MIT
