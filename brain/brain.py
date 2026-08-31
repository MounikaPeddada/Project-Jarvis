import os
from dotenv import load_dotenv
from google import genai

# Load environment variables from the .env file
load_dotenv()

# Retrieve the Gemini API key from the environment
api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    raise ValueError("GEMINI_API_KEY not found. Please set it in your .env file.")

# Initialize the Gemini client
client = genai.Client(api_key=api_key)

def ask_jarvis(prompt, enable_web_search=False):
    """
    Sends a prompt to Jarvis via Gemini API.
    
    Args:
        prompt (str): The question or command to ask Jarvis
        enable_web_search (bool): Whether to enable web search (future feature)
    
    Returns:
        str: Jarvis's response
    """
    try:
        response = client.models.generate_content(
            model="models/gemini-3.6-flash",  # Latest available model
            contents=prompt,
            config={
                "temperature": 0.7,
                "max_output_tokens": 1000,
            }
        )
        return response.text
    except Exception as e:
        return f"An error occurred: {str(e)}"

def main():
    """Main function to test Jarvis."""
    print("=" * 60)
    print("🤖 JARVIS - AI Assistant")
    print("=" * 60)
    
    # Test 1: Simple greeting
    question1 = "Hello, who are you and what can you do?"
    print(f"\n🧠 Question: {question1}")
    print("-" * 60)
    response1 = ask_jarvis(question1)
    print(f"🤖 Jarvis says: {response1}")
    
    # Test 2: Another question
    question2 = "What is machine learning in simple terms?"
    print(f"\n🧠 Question: {question2}")
    print("-" * 60)
    response2 = ask_jarvis(question2)
    print(f"🤖 Jarvis says: {response2}")
    
    print("\n" + "=" * 60)

if __name__ == "__main__":
    main()