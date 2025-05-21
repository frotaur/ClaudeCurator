import os
import json
from anthropic import Anthropic
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Test function to simulate Claude's review process
def test_claude_review():
    """Test Claude's ability to review a PR based on guidelines"""
    # Get API key
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY not found in environment variables")
        return
    
    # Initialize Anthropic client
    client = Anthropic(api_key=api_key)
    
    # Load guidelines
    try:
        with open("example_guidelines.md", "r") as f:
            guidelines = f.read()
    except FileNotFoundError:
        print("Error: guidelines.md not found")
        return
    
    # System prompt
    system_prompt = """You are the curator of a GitHub repository. Your job is to review pull requests and decide if they should be accepted or rejected based on the repository guidelines.

Your tasks for each PR:
1. Review if the contribution complies with the repository guidelines
2. Decide whether to accept or reject the pull request
3. Provide a detailed, helpful explanation for your decision

Format your response exactly as follows:

DECISION: [ACCEPT/REJECT]

EXPLANATION:
[Your detailed explanation here]

Your tone should be friendly but firm. Remember that the guidelines are the source of truth for what belongs in this repository."""
    
    # Test cases
    test_cases = [
        {
            "title": "Add blue whale facts",
            "user": "whale_lover",
            "description": "Adding some interesting facts about blue whales",
            "changes": "File: blue_whale_facts.md (added)\n```\n# Blue Whale Facts\n\n- Blue whales are the largest animals ever known to have lived on Earth\n- They can grow up to 100 feet long and weigh up to 200 tons\n- Their hearts are the size of a small car\n- Despite their massive size, they feed almost exclusively on tiny krill\n```"
        },
        {
            "title": "Add cat pictures",
            "user": "cat_fan",
            "description": "Cats are better than whales!",
            "changes": "File: cute_cats.md (added)\n```\n# Cute Cat Pictures\n\nHere are links to some cute cat pictures!\n\n- [Cat 1](https://example.com/cat1.jpg)\n- [Cat 2](https://example.com/cat2.jpg)\n- [Cat 3](https://example.com/cat3.jpg)\n```"
        },
        {
            "title": "Update guidelines to include dolphins",
            "user": "marine_biologist",
            "description": "Expanding the scope to include dolphins, which are closely related to whales",
            "changes": "File: guidelines.md (modified)\n@@ -3,7 +3,7 @@\n \n Welcome to the Whale Repository! 🐋\n \n-This repository is dedicated to all things whale-related. Everyone is welcome to contribute, as long as contributions follow these guidelines:\n+This repository is dedicated to all things whale and dolphin-related. Everyone is welcome to contribute, as long as contributions follow these guidelines:\n \n ## Content Requirements\n- All contributions must be whale-related"
        }
    ]
    
    # Note: these test cases are designed for whale-themed guidelines
    # If you've changed your guidelines, you may want to update these test cases
    print("Note: Test cases are designed for the initial whale-themed repository.")
    print("If you've changed your guidelines, consider updating the test cases in this file.\n")
    
    # Run tests
    for i, test in enumerate(test_cases):
        print(f"\n--- Test Case {i+1}: {test['title']} ---\n")
        
        # Construct user prompt
        user_prompt = f"""Repository Guidelines:
{guidelines}

Pull Request Details:
Title: {test['title']}
Submitted by: {test['user']}
Description: {test['description']}

Changes:
{test['changes']}

Please review this pull request and decide if it should be accepted or rejected."""
        
        # Get Claude's response
        try:
            response = client.messages.create(
                model="claude-3-7-sonnet-20250219",
                max_tokens=1000,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": user_prompt}
                ]
            )
            
            print(response.content[0].text)
            
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    test_claude_review()