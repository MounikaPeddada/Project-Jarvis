import os
from dotenv import load_dotenv

# Load the .env file from the parent folder
load_dotenv()

# Grab the API key from the environment
api_key = os.getenv("API_KEY")

# Now use it in your AI requests
# Example: OpenRouter headers
headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}
