import json, hashlib, hmac, time, requests
from anthropic import Anthropic
from flask import jsonify
from .utility import format_file_size
from pathlib import Path


class CuratorServer:
    def __init__(self, system_prompt, github_token, anthropic_api_key, github_secret, repo_owner, repo_name, log_dir=None, print_log=False):
        self.auth_headers = {"Authorization": f"token {github_token}"}
        self.client = Anthropic(api_key=anthropic_api_key)
        self.github_secret = github_secret
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.system_prompt = system_prompt

        self.repo_url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}"

        if log_dir:
            self.log_path = Path(log_dir) / 'curator_server_logs.txt'
            if not self.log_path.parent.exists():
                self.log_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            self.log_path=None
        
        self.print_log = print_log

    def verify_signature(self,payload, signature):
        """Verify GitHub webhook signature"""
        if not signature:
            self.log("No signature provided")
            return False
        
        try:
            self.log(f"Received signature: {signature}")
            self.log(f"Secret being used: {self.github_secret[:5]}...")  # self.log just first few chars to check

            sha_name, signature = signature.split('=')
            if sha_name != 'sha256':
                self.log(f"Invalid hash algorithm: {sha_name}")
                return False


            secret = self.github_secret.encode()
            # payload is already in bytes
            mac = hmac.new(secret, msg=payload, digestmod=hashlib.sha256)
            calculated_signature = mac.hexdigest()
            
            self.log(f"Calculated signature: {calculated_signature[:5]}...")  # self.log just first few chars
            
            result = hmac.compare_digest(calculated_signature, signature)
            if not result:
                self.log("Signature verification failed - signatures don't match")
            return result
    
        except Exception as e:
            self.log(f"Error verifying signature: {e}")
            return False

    def _check_mergeable(self, pr_number):
        """Check if a pull request is mergeable"""
        pr_detail_url = self.repo_url+f"/pulls/{pr_number}"
        
        self.log(f"Checking if PR #{pr_number} is auto-mergeable...")
        time.sleep(2)
        pr_response = requests.get(pr_detail_url, headers=self.auth_headers)
        if pr_response.status_code == 200:
            pr_data = pr_response.json()
            mergeable = pr_data.get('mergeable')
            mergeable_state = pr_data.get('mergeable_state')
            
            self.log(f"PR #{pr_number} mergeable status: {mergeable}, state: {mergeable_state}")
            
            # GitHub might not have computed mergeable status yet (null), try thrice
            count=0
            while(mergeable is None and mergeable_state == 'unknown' and count<3):
                self.log("Mergeable status not computed yet, waiting 5 seconds and trying again...")
                time.sleep(5)
                
                # Try again
                pr_response = requests.get(pr_detail_url, headers=self.auth_headers)
                if pr_response.status_code == 200:
                    pr_data = pr_response.json()
                    mergeable = pr_data.get('mergeable')
                    mergeable_state = pr_data.get('mergeable_state')
                    self.log(f"After retry - PR #{pr_number} mergeable status: {mergeable}, state: {mergeable_state}")
                count+=1

        return mergeable
    
    def process_pull_request(self, pr_number, pr_title, pr_body, pr_user, log=False, is_reopened=False):
        """Process a new or reopened pull request by sending it to Claude for review"""
        
        # First check if PR is auto-mergeable
        mergeable = self._check_mergeable(pr_number)

        # If GitHub says not mergeable, or unknown, reject the PR
        if mergeable!= True:
            rejection_message = """This pull request cannot be automatically merged due to conflicts with the base branch.

Please resolve the merge conflicts and reopen your pull request.

Note: This automatic rejection happens before content review. Once conflicts are resolved, feel free to reopen the PR for a full review.
"""
            self.log(f"Automatically rejecting PR #{pr_number} due to merge conflicts")
            self.reject_pull_request(pr_number, rejection_message)
            return
        
        # Continue with normal processing if PR is mergeable
        text_changes, image_changes, file_sizes = self.get_pr_changes(pr_number)
        
        MAX_FILE_SIZE = 2 * 1024 * 1024  # 2MB in bytes
        large_files = [f for f, size in file_sizes.items() if size > MAX_FILE_SIZE]
        
        if large_files:
            # Automatically reject PR containing files that are too large
            large_files_str = "\n".join([f"- {f} ({format_file_size(file_sizes[f])})" for f in large_files])
            rejection_message = f"This pull request has been automatically rejected because it contains files larger than 2MB.\nLarge files:\n{large_files_str}"

            self.log(f"Automatically rejecting PR #{pr_number} due to large files: {large_files}")
            self.reject_pull_request(pr_number, rejection_message)
            return
        
        # If all files are under the size limit, proceed with Claude review
        guidelines = self.get_repository_guidelines()
        
        # Build user prompt for Claude - contains the specific PR details
        base_prompt = f"""Repository Guidelines, contained in guidelines.md :
    "{guidelines}"

    Pull Request Details:
    Title: "{pr_title}"
    Submitted by: "{pr_user}"
    Description: <description_start>\n{pr_body}\n<description_end>"""
    
        # Add previous comments if this is a reopened PR
        if is_reopened:
            previous_comments = self.get_pr_comments(pr_number)
            base_prompt += f"""
    
    Previous Comments and Discussion:
    <previous_comments_start>\n{previous_comments}\n<previous_comments_end>"""
            
        base_prompt += "\n\n    Please review this pull request and decide if it should be accepted or rejected."
        
        changes_prompt = f"""Following are the changes made in this PR:
    <changes_start>\n{text_changes}\n<changes_end>"""

        images_prompt = self.build_image_prompt(image_changes) if image_changes else []
        
        user_prompt_content = []
        user_prompt_content.append({"type": "text", "text": base_prompt})
        if images_prompt:
            user_prompt_content.extend(images_prompt)
        user_prompt_content.append({"type": "text", "text": changes_prompt})
        # Send to Claude for review using system and user prompts
        response = self.client.messages.create(
            model="claude-3-7-sonnet-20250219",
            max_tokens=2000,
            system=self.system_prompt,
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
            self.log("❌ Error decoding Claude's response - falling back to raw text")
            claude_response = {'decision':False,'explanation': f'Curator failed to return parsable JSON, auto-rejected : {response.content[0].text}'}


        ## Logging....
        self.log(f"\n\n Processing PR #{pr_number}:\n")
        user_prompt = ""
        for prompt in user_prompt_content:
            if prompt['type'] == 'text':
                user_prompt += prompt['text'] + "\n\n"
            elif prompt['type'] == 'image':
                user_prompt += f"Image file: {prompt['source']['url']}\n\n"
            else:
                user_prompt += "Unknown content type" + "\n\n"
        self.log(user_prompt + "\n\n")
        self.log(f"Sending to Claude for review...\n")
        self.log(f"Claude's response:\n{claude_response}")

        # Parse Claude's decision
        decision = claude_response.get('decision', False)
        explanation = claude_response.get('explanation', 'No explanation provided.')

        # Take action on GitHub
        if decision:
            commit_title = claude_response.get('commit_title', None)
            commit_message = claude_response.get('commit_message', None)
            self.approve_pull_request(pr_number, explanation, commit_title, commit_message)
        else:
            self.reject_pull_request(pr_number, explanation)

    def reject_pull_request(self,pr_number, explanation):
        """Reject the pull request by adding a comment"""
        url = self.repo_url+f"/issues/{pr_number}/comments"
        data = {
            "body": f"❌ **PR Rejected by AI Curator** ❌\n\n{explanation}"
        }
        response = requests.post(url, headers=self.auth_headers, json=data)
        if response.status_code != 201:
            self.log(f"❌ Failed to add rejection comment to PR #{pr_number}. Status code: {response.status_code}")
            self.log(f"Error message: {response.text}")
        
        # Close the PR
        close_url = self.repo_url+f"/pulls/{pr_number}"
        close_data = {"state": "closed"}
        close_response = requests.patch(close_url, headers=self.auth_headers, json=close_data)

        if close_response.status_code != 200:
            self.log(f"❌ Failed to close PR #{pr_number}. Status code: {close_response.status_code}")
            self.log(f"Error message: {close_response.text}")
        else:
            self.log(f"✅ Successfully closed PR #{pr_number}")

    def approve_pull_request(self, pr_number, explanation, commit_title=None, commit_message=None):
        """Approve the pull request"""
        # Add comment
        comment_url = self.repo_url+f"/issues/{pr_number}/comments"
        comment_data = {
            "body": f"✅ **PR Approved by AI Curator** ✅\n\n{explanation}"
        }
        requests.post(comment_url, headers=self.auth_headers, json=comment_data)
        # Try to approve the PR (might fail if it's your own PR)
        review_url = self.repo_url+f"/pulls/{pr_number}/reviews"
        review_data = {
            "event": "APPROVE",
            "body": "Automatically approved by AI Curator"
        }
        approve_response = requests.post(review_url, headers=self.auth_headers, json=review_data)

        is_self_approval_error = False
        if approve_response.status_code == 200:
            self.log(f"✅ Successfully approved PR #{pr_number}")
        else:
            self.log(f"❌ Failed to approve PR #{pr_number}. Status code: {approve_response.status_code}")
            self.log(f"Error message: {approve_response.text}")
            
            # Check if it's the "can't approve your own PR" error
            try:
                error_data = approve_response.json()
                if "errors" in error_data and any("Can not approve your own pull request" in str(error) for error in error_data["errors"]):
                    self.log("ℹ️ This is your own PR - skipping approval but proceeding with merge")
                    is_self_approval_error = True
            except:
                pass
                
        if not is_self_approval_error and approve_response.status_code != 200:
            self.log("⚠️ Approval failed with an unexpected error - merge may also fail")
        
        
        # Merge the PR
        merge_url = self.repo_url+f"/pulls/{pr_number}/merge"
        merge_data = {
            "commit_title": commit_title or f"Merge PR #{pr_number}",
            "commit_message": commit_message or f"Automatically merged PR #{pr_number} by AI Curator",
            "merge_method": "merge"
        }
        self.log(f"Attempting to merge PR #{pr_number}...")
        merge_response = requests.put(merge_url, headers=self.auth_headers, json=merge_data)

        if merge_response.status_code == 200:
            self.log(f"✅ Successfully merged PR #{pr_number}")
        else:
            self.log(f"❌ Failed to merge PR #{pr_number}. Status code: {merge_response.status_code}")
            self.log(f"Error message: {merge_response.text}")
    
    def get_pr_changes(self,pr_number, only_diffs=True):
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
        url = self.repo_url+f"/pulls/{pr_number}/files"

        response = requests.get(url, headers=self.auth_headers)
        files_changed = response.json()
        
        changes_text = []
        changes_images = {} # Dictionary to track changed images
        file_sizes = {}  # Dictionary to track file sizes
        
        for file in files_changed:
            filename = file['filename']
            status = file['status']  # added, modified, removed
            self.log(f"Processing file: {filename} with status: {status}")
            self.log(f"File raw URL: {file.get('raw_url','unknown')}")
            self.log(f"File content url: {file['contents_url']}")
            # Get file content
            file_content_url = file['contents_url']
            file_content_response = requests.get(file_content_url, headers=self.auth_headers)
            
            download_url = None
            if file_content_response.status_code == 200:
                # get download url, and download the file
                download_url = file_content_response.json()['download_url']
                file_response = requests.get(download_url, headers=self.auth_headers)
            else:
                self.log(f"❌ Failed to fetch file content for {filename}. Status code: {file_content_response.status_code}")
                changes_text.append(f"File: {filename} ({status})\nUnable to fetch content.")
                continue
                
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
                    changes_images[filename] = download_url  # Store raw URL for images
                else:
                    # Try to decode as text, too many MIME types to check
                    try:
                        
                        if('patch' in file):
                            # If the file has a patch, include the changes
                            change_string = f"File: {filename} ({status})\n Changes made : ```\n{file.get('patch','')}\n```"
                            if(not only_diffs):
                                content = file_response.content.decode('utf-8')
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
                self.log(f"❌ Failed to fetch content for file: {filename}. Status code: {file_response.status_code}")
                changes_text.append(f"File: {filename} ({status})\nUnable to fetch content.")
        
        return "\n\n".join(changes_text), changes_images, file_sizes

    def get_repository_guidelines(self):
        """Fetch the current repository guidelines"""
        url = f"https://raw.githubusercontent.com/{self.repo_owner}/{self.repo_name}/main/guidelines.md"

        guideline_error = "Unable to fetch guidelines. They might have been deleted, or corrupted. Operate as if they are empty. Mention in the PR that the guidelines.md file should be created urgently."
        response = requests.get(url, headers=self.auth_headers)
        if response.status_code == 200:
            try:
                return response.content.decode('utf-8')
            except Exception as e:
                self.log(f"⚠️ WARNING: Failed to decode guidelines.md - {e}")
                return guideline_error
        else:
            return guideline_error

    def build_image_prompt(self, images_dictionary):
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

    def get_pr_comments(self, pr_number):
        """
        Fetch general comments from a pull request for context when reopened.
        
        Args:
            pr_number (int): The pull request number to fetch comments for.
            
        Returns:
            str: Formatted string containing all comments and their metadata.
        """
        comments_url = self.repo_url + f"/issues/{pr_number}/comments"
        comments_response = requests.get(comments_url, headers=self.auth_headers)
        
        if comments_response.status_code != 200:
            return "No previous comments found."
        
        comments = comments_response.json()
        if not comments:
            return "No previous comments found."
        
        formatted_comments = []
        for comment in comments:
            formatted_comments.append(f"Comment by {comment['user']['login']} at {comment['created_at']}:\n{comment['body']}")
        
        return "\n\n".join(formatted_comments)

    def handle_event(self, event, payload):
        """Handle a GitHub event"""
        if event == 'ping':
            self.log('RECEIVED PING EVENT - Webhook configured successfully!')
            return jsonify({"status": "Webhook configured successfully"}), 200
        
        # Handle PR creation event
        if event == 'pull_request' and payload['action'] == 'opened':
            self.log('RECEIVED PR OPENED EVENT')
            pr_number = payload['pull_request']['number']
            pr_title = payload['pull_request']['title']
            pr_body = payload['pull_request']['body'] or ""
            pr_user = payload['pull_request']['user']['login']
            
            # Process the pull request
            self.process_pull_request(pr_number, pr_title, pr_body, pr_user, log=True)

            return jsonify({"status": "Processing PR"}), 200
        if event == 'pull_request' and payload['action'] == 'reopened':
            self.log('RECEIVED PR REOPENED EVENT')
            pr_number = payload['pull_request']['number']
            pr_title = payload['pull_request']['title']
            pr_body = payload['pull_request']['body'] or ""
            pr_user = payload['pull_request']['user']['login']
            
            # Process the reopened pull request (includes comment history)
            self.process_pull_request(pr_number, pr_title, pr_body, pr_user, log=True, is_reopened=True)

            return jsonify({"status": "Processing reopened PR"}), 200
            
        self.log(f"Received event: {event} with action: {payload.get('action', 'unknown')}")
        self.log("This event is not handled by the curator.")
        
        return jsonify({"status": "Event ignored"}), 200

    def log(self, message):
        """Log a message to the log file if logging is enabled"""
        if self.log_path:
            with self.log_path.open("a") as f:
                f.write("------------------------------------------------------------------------\n")
                f.write(f"{message}\n")
    
        if self.print_log:
            print(message)
