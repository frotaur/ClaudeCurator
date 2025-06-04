import os
import json
import requests
import hmac
import time
import hashlib
from flask import Flask, request, jsonify
from anthropic import Anthropic
from dotenv import load_dotenv
from pathlib import Path
# Load environment variables from .env file
load_dotenv()

curator_app = Flask(__name__)

# Configuration
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
GITHUB_SECRET = os.environ.get("GITHUB_SECRET")  # For webhook verification
REPO_OWNER = os.environ.get("REPO_OWNER")
REPO_NAME = os.environ.get("REPO_NAME")

# Initialize Anthropic client
client = Anthropic(api_key=ANTHROPIC_API_KEY)

# System prompt for Claude - more efficient as system prompts don't count toward token usage
system_prompt_file = Path("system_prompt.txt")
SYSTEM_PROMPT = None

if system_prompt_file.exists():
    with system_prompt_file.open("r") as f:
        SYSTEM_PROMPT = f.read().strip()
else:
    print("⚠️ WARNING: system_prompt.txt not found!")
    raise FileNotFoundError("Please create a system_prompt.txt file with the system prompt for Claude.")

@curator_app.route('/webhook', methods=['POST'])
def github_webhook():
    # Verify webhook signature
    if GITHUB_SECRET:
        signature = request.headers.get('X-Hub-Signature-256')
        verify_result = verify_signature(request.data, signature)
        print(f"Signature verification result: {verify_result}")
        
        # Uncomment for production:
        # if not verify_result:
        #     return jsonify({"error": "Invalid signature"}), 401
        
        # For testing - bypass verification:
        if not verify_result:
            print("⚠️ WARNING: Signature verification failed but proceeding anyway (testing mode)")
            
        # For debugging - print full request
        print(f"Headers: {dict(request.headers)}")
        print(f"Data: {request.data[:100]}...")  # Print first 100 chars

    # Parse the webhook payload
    event = request.headers.get('X-GitHub-Event')
    payload = request.json
    
    print(f"Received GitHub event: {event}")
    
    # Handle ping event (sent when webhook is first created)
    if event == 'ping':
        print('RECEIVED PING EVENT - Webhook configured successfully!')
        return jsonify({"status": "Webhook configured successfully"}), 200
    
    # Handle PR creation event
    if event == 'pull_request' and (payload['action'] == 'opened' or payload['action'] == 'reopened'):
        print('RECEIVED PR OPENED EVENT')
        pr_number = payload['pull_request']['number']
        pr_title = payload['pull_request']['title']
        pr_body = payload['pull_request']['body'] or ""
        pr_user = payload['pull_request']['user']['login']
        
        # Process the pull request
        process_pull_request(pr_number, pr_title, pr_body, pr_user, log=True)

        return jsonify({"status": "Processing PR"}), 200
    
    print(f"Received event: {event} with action: {payload.get('action', 'unknown')}")
    print("This event is not handled by the curator.")
    
    return jsonify({"status": "Event ignored"}), 200

def verify_signature(payload, signature):
    """Verify GitHub webhook signature"""
    if not signature:
        print("No signature provided")
        return False
    
    try:
        print(f"Received signature: {signature}")
        print(f"Secret being used: {GITHUB_SECRET[:5]}...")  # Print just first few chars for security
        
        sha_name, signature = signature.split('=')
        if sha_name != 'sha256':
            print(f"Invalid hash algorithm: {sha_name}")
            return False
        
        # GITHUB_SECRET needs to be encoded to bytes
        secret = GITHUB_SECRET.encode()
        # payload is already in bytes
        mac = hmac.new(secret, msg=payload, digestmod=hashlib.sha256)
        calculated_signature = mac.hexdigest()
        
        print(f"Calculated signature: {calculated_signature[:5]}...")  # Print just first few chars
        
        result = hmac.compare_digest(calculated_signature, signature)
        if not result:
            print("Signature verification failed - signatures don't match")
        return result
    except Exception as e:
        print(f"Error verifying signature: {e}")
        return False

def process_pull_request(pr_number, pr_title, pr_body, pr_user, log=False):
    """Process a new pull request by sending it to Claude for review"""
    # First check if PR is auto-mergeable
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    pr_detail_url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/pulls/{pr_number}"
    
    print(f"Checking if PR #{pr_number} is auto-mergeable...")
    time.sleep(1) # Small delay to help github figure out if the PR is mergeable
    pr_response = requests.get(pr_detail_url, headers=headers)
    
    if pr_response.status_code == 200:
        pr_data = pr_response.json()
        mergeable = pr_data.get('mergeable')
        mergeable_state = pr_data.get('mergeable_state')
        
        print(f"PR #{pr_number} mergeable status: {mergeable}, state: {mergeable_state}")
        
        # GitHub might not have computed mergeable status yet (null)
        if mergeable is None and mergeable_state == 'unknown':
            print("Mergeable status not computed yet, waiting 5 seconds and trying again...")
            time.sleep(5)
            
            # Try again
            pr_response = requests.get(pr_detail_url, headers=headers)
            if pr_response.status_code == 200:
                pr_data = pr_response.json()
                mergeable = pr_data.get('mergeable')
                mergeable_state = pr_data.get('mergeable_state')
                print(f"After retry - PR #{pr_number} mergeable status: {mergeable}, state: {mergeable_state}")
        
        # If GitHub explicitly says it's not mergeable
        if mergeable is False:
            rejection_message = """This pull request cannot be automatically merged due to conflicts with the base branch.

Please resolve the merge conflicts and reopen your pull request.

Note: This automatic rejection happens before content review. Once conflicts are resolved, feel free to reopen the PR for a full review.
"""
            print(f"Automatically rejecting PR #{pr_number} due to merge conflicts")
            reject_pull_request(pr_number, rejection_message)
            return
    
    # Continue with normal processing if PR is mergeable or we couldn't determine
    # Get PR details including changed files
    text_changes, image_changes, file_sizes = get_pr_changes(pr_number)
    
    # Check if any files are over the size limit (2MB = 2*1024*1024 bytes)
    MAX_FILE_SIZE = 2 * 1024 * 1024  # 2MB in bytes
    large_files = [f for f, size in file_sizes.items() if size > MAX_FILE_SIZE]
    
    if large_files:
        # Automatically reject PR containing files that are too large
        large_files_str = "\n".join([f"- {f} ({format_file_size(file_sizes[f])})" for f in large_files])
        rejection_message = f"This pull request has been automatically rejected because it contains files larger than 2MB.\nLarge files:\n{large_files_str}"

        print(f"Automatically rejecting PR #{pr_number} due to large files: {large_files}")
        reject_pull_request(pr_number, rejection_message)
        return
    
    # If all files are under the size limit, proceed with Claude review
    guidelines = get_repository_guidelines()
    
    # Build user prompt for Claude - contains the specific PR details
    base_prompt = f"""Repository Guidelines, contained in guidelines.md :
"{guidelines}"

Pull Request Details:
Title: "{pr_title}"
Submitted by: "{pr_user}"
Description: <description_start>\n{pr_body}\n<description_end>

Please review this pull request and decide if it should be accepted or rejected."""
    
    changes_prompt = f"""Following are the changes made in this PR:
<changes_start>\n{text_changes}\n<changes_end>"""

    images_prompt = build_image_prompt(image_changes) if image_changes else []
    
    user_prompt_content = []
    user_prompt_content.append({"type": "text", "text": base_prompt})
    if images_prompt:
        user_prompt_content.extend(images_prompt)
    user_prompt_content.append({"type": "text", "text": changes_prompt})
    # Send to Claude for review using system and user prompts
    response = client.messages.create(
        model="claude-3-7-sonnet-20250219",
        max_tokens=1000,
        system=SYSTEM_PROMPT,
        messages=[
            {"role": "user", 
             "content": user_prompt_content
            },
            {"role": "assistant", "content": "{"}
        ]
    )

    try:
        claude_response = json.loads("{"+response.content[0].text)
    except json.JSONDecodeError:
        print("❌ Error decoding Claude's response - falling back to raw text")
        claude_response = {'decision':False,'explanation': f'Curator failed to return parsable JSON, auto-rejected : {response.content[0].text}'}

    if(log):
        filepath = Path("logs.txt")
        with filepath.open("a") as log_file:
            log_file.write(f"\n\n Processing PR #{pr_number}:\n")
            user_prompt = ""
            for prompt in user_prompt_content:
                if prompt['type'] == 'text':
                    user_prompt += prompt['text'] + "\n\n"
                elif prompt['type'] == 'image':
                    user_prompt += f"Image file: {prompt['source']['url']}\n\n"
                else:
                    user_prompt += "Unknown content type" + "\n\n"
            log_file.write(user_prompt + "\n\n")
            log_file.write(f"Sending to Claude for review...\n")
            log_file.write(f"Claude's response:\n{claude_response}\n")

    print(f"Claude's response: {claude_response}")
    # Parse Claude's decision
    decision = claude_response.get('decision', False)
    explanation = claude_response.get('explanation', 'No explanation provided.')

    # Take action on GitHub
    if decision:
        commit_title = claude_response.get('commit_title', None)
        commit_message = claude_response.get('commit_message', None)
        approve_pull_request(pr_number, explanation, commit_title, commit_message)
    else:
        reject_pull_request(pr_number, explanation)

def build_image_prompt(images_dictionary):
    """
        Build a prompt for Claude with the changed images.

        Args:
            images_dictionary (dict): A dictionary mapping image filenames to their raw URLs.

        Returns:
            list: A list of prompts for Claude, each containing an image and its filename, to be sent sequentially.
    """
    if not images_dictionary:
        raise ValueError("No images found in the PR changes.")
    prompts = []
    for filename, raw_url in images_dictionary.items():
        prompts.append({"type": "text", "text": f"Image file: {filename}"})
        prompts.append({"type": "image", "source": {"type": "url","url": raw_url}})

    return prompts

def get_repository_guidelines():
    """Fetch the current repository guidelines"""
    url = f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/main/guidelines.md"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    
    guideline_error = "Unable to fetch guidelines. They might have been deleted, or corrupted. Operate as if they are empty."
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        try:
            return response.content.decode('utf-8')
        except Exception as e:
            print(f"⚠️ WARNING: Failed to decode guidelines.md - {e}")
            return guideline_error
    else:
        return guideline_error

def format_file_size(size_in_bytes):
    """Helper function to format file size in human-readable format"""
    if size_in_bytes < 1024:
        return f"{size_in_bytes} bytes"
    elif size_in_bytes < 1024 * 1024:
        return f"{size_in_bytes / 1024:.1f} KB"
    else:
        return f"{size_in_bytes / (1024 * 1024):.1f} MB"

def get_pr_changes(pr_number, only_diffs=True):
    """
        Get the changes made in the pull request. Separates images from text-like files,
        to be able to send them to Claude separately. For now, just reads the name of 
        the other files and reports them with size and name.

        Args:
            pr_number (int): The pull request number to fetch changes for.
            only_diffs (bool): If True, only displays diffs. Otherwise, displays the full changed file.

        Returns:
            str, dict, dict: text changes, changed images, and file sizes.
    """
    # Get the list of files changed
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/pulls/{pr_number}/files"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    
    response = requests.get(url, headers=headers)
    files_changed = response.json()
    
    changes_text = []
    changes_images = {} # Dictionary to track changed images
    file_sizes = {}  # Dictionary to track file sizes
    
    for file in files_changed:
        filename = file['filename']
        status = file['status']  # added, modified, removed
        
        # Get file content
        file_url = file['raw_url']
        file_response = requests.get(file_url, headers=headers)
        
        if file_response.status_code == 200:
            # Store file size for size checks
            content_type = file_response.headers.get('Content-Type', '')
            content_length = file_response.headers.get('content-length')
            if content_length:
                    file_size = int(content_length)
            else:
                file_size = len(file_response.content)
                
            file_sizes[filename] = file_size
            
            if(status == 'renamed' or status == 'copied'):
                # If it has been renamed or copied, mention the previous filename
                # then continue as usual
                previous_filename = file.get('previous_filename', 'unknown')
                changes_text.append(f"File: {previous_filename} -> {filename} ({status})")
            
            if content_type.startswith('image/'):
                size_str = format_file_size(file_size)
                changes_text.append(f"File: {filename} ({status})\n[Image file - {size_str}]")
                changes_images[filename] = file['raw_url']  # Store raw URL for images
            else:
                # Try to decode as text, too many MIME types to check
                try:
                    content = file_response.content.decode('utf-8')
                    if('patch' in file):
                        # If the file has a patch, include the changes
                        change_string = f"File: {filename} ({status})\n Changes made : ```\n{file.get('patch','')}\n```"
                        if(not only_diffs):
                            change_string += f"\n\nFull content:\n```{content}```"
                    changes_text.append(change_string)
                except UnicodeDecodeError:
                    # If decoding fails, it's probably binary even if not on our list
                    size_str = format_file_size(file_size)
                    changes_text.append(f"File: {filename} ({status})\n[Binary file - {size_str} - content not displayed]")
                except Exception as e:
                    # Handle any other errors
                    changes_text.append(f"File: {filename} ({status})\nError reading file: {str(e)}")
        else:
            changes_text.append(f"File: {filename} ({status})\nUnable to fetch content.")
    
    return "\n\n".join(changes_text), changes_images, file_sizes

def approve_pull_request(pr_number, explanation, commit_title=None, commit_message=None):
    """Approve the pull request"""
    # Add comment
    comment_url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/issues/{pr_number}/comments"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    comment_data = {
        "body": f"✅ **PR Approved by AI Curator** ✅\n\n{explanation}"
    }
    requests.post(comment_url, headers=headers, json=comment_data)
    # Try to approve the PR (might fail if it's your own PR)
    review_url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/pulls/{pr_number}/reviews"
    review_data = {
        "event": "APPROVE",
        "body": "Automatically approved by AI Curator"
    }
    approve_response = requests.post(review_url, headers=headers, json=review_data)
    
    is_self_approval_error = False
    if approve_response.status_code == 200:
        print(f"✅ Successfully approved PR #{pr_number}")
    else:
        print(f"❌ Failed to approve PR #{pr_number}. Status code: {approve_response.status_code}")
        print(f"Error message: {approve_response.text}")
        
        # Check if it's the "can't approve your own PR" error
        try:
            error_data = approve_response.json()
            if "errors" in error_data and any("Can not approve your own pull request" in str(error) for error in error_data["errors"]):
                print("ℹ️ This is your own PR - skipping approval but proceeding with merge")
                is_self_approval_error = True
        except:
            pass
            
    if not is_self_approval_error and approve_response.status_code != 200:
        print("⚠️ Approval failed with an unexpected error - merge may also fail")
    
    
    # Merge the PR
    merge_url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/pulls/{pr_number}/merge"
    merge_data = {
        "commit_title": commit_title or f"Merge PR #{pr_number}: {pr_title}",
        "commit_message": commit_message or f"Automatically merged PR #{pr_number} by AI Curator",
        "merge_method": "merge"
    }
    print(f"Attempting to merge PR #{pr_number}...")
    merge_response = requests.put(merge_url, headers=headers, json=merge_data)
    
    if merge_response.status_code == 200:
        print(f"✅ Successfully merged PR #{pr_number}")
    else:
        print(f"❌ Failed to merge PR #{pr_number}. Status code: {merge_response.status_code}")
        print(f"Error message: {merge_response.text}")

def reject_pull_request(pr_number, explanation):
    """Reject the pull request by adding a comment"""
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/issues/{pr_number}/comments"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    data = {
        "body": f"❌ **PR Rejected by AI Curator** ❌\n\n{explanation}"
    }
    requests.post(url, headers=headers, json=data)
    
    # Close the PR
    close_url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/pulls/{pr_number}"
    close_data = {"state": "closed"}
    requests.patch(close_url, headers=headers, json=close_data)

if __name__ == '__main__':
    curator_app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))