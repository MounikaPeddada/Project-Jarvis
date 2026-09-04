import os
import time
import logging
from dotenv import load_dotenv
import google.genai as genai

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load API key
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise Exception("❌ GEMINI_API_KEY not found in .env file!")

genai.configure(api_key=api_key)

# Initialize client (singleton pattern)
_client = None

def get_client():
    """Get or create Gemini client (singleton)."""
    global _client
    if _client is None:
        try:
            _client = genai.Client(api_key=api_key)
            logger.info("✅ Gemini client initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Gemini client: {str(e)}")
            raise
    return _client

def call_gemini(prompt: str, max_retries: int = 3, timeout: float = 15.0) -> str:
    """
    Call Gemini API with automatic retry logic, timeout, and proper error handling.
    
    Args:
        prompt: The prompt to send to Gemini.
        max_retries: Number of retry attempts on failure.
        timeout: Maximum wait time for API response (in seconds).
    
    Returns:
        Gemini's response text.
    
    Raises:
        Exception: If all retries fail
    """
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("Prompt must be a non-empty string")
    
    client = get_client()
    
    for attempt in range(max_retries):
        try:
            start_time = time.time()
            
            logger.debug(f"API call attempt {attempt + 1}/{max_retries}")
            
            # Use new API with correct syntax
            response = client.models.generate_content(
                model="gemini-3.7-flash",
                contents=prompt,
                config={
                    "temperature": 0.7,
                    "max_output_tokens": 500,
                }
            )
            
            elapsed = time.time() - start_time
            logger.info(f"✅ API call successful in {elapsed:.2f}s")
            
            # Warn if slow
            if elapsed > timeout:
                logger.warning(f"⚠️ API response slow: {elapsed:.2f}s (timeout: {timeout}s)")
            
            return response.text
        
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"API error on attempt {attempt + 1}/{max_retries}: {str(e)} (took {elapsed:.2f}s)")
            
            if attempt < max_retries - 1:
                # Exponential backoff with max cap
                wait_time = min(2 ** attempt, 8)  # 1s, 2s, 4s, max 8s
                logger.info(f"Retrying in {wait_time}s...")
                time.sleep(wait_time)
                continue
            else:
                logger.critical(f"❌ API Error after {max_retries} attempts: {str(e)}")
                raise Exception(f"❌ Gemini API Error after {max_retries} attempts: {str(e)}")

def call_gemini_with_chat(system_prompt: str, user_message: str, max_retries: int = 3) -> str:
    """
    Call Gemini using Chat interface for multi-turn conversations.
    
    Args:
        system_prompt: System context/instructions
        user_message: User's message
        max_retries: Retry attempts
    
    Returns:
        Gemini's response text
    """
    if not isinstance(user_message, str) or not user_message.strip():
        raise ValueError("User message must be non-empty string")
    
    client = get_client()
    
    for attempt in range(max_retries):
        try:
            start_time = time.time()
            
            # Create chat session
            chat = client.chats.create(model="gemini-3.7-flash")
            
            # Send message
            response = chat.send_message(
                f"{system_prompt}\n\nUser: {user_message}",
                config={"max_output_tokens": 500}
            )
            
            elapsed = time.time() - start_time
            logger.info(f"✅ Chat call successful in {elapsed:.2f}s")
            
            return response.text
        
        except Exception as e:
            logger.error(f"Chat call failed on attempt {attempt + 1}/{max_retries}: {str(e)}")
            
            if attempt < max_retries - 1:
                wait_time = min(2 ** attempt, 8)
                logger.info(f"Retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                raise Exception(f"❌ Chat Error after {max_retries} attempts: {str(e)}")

if __name__ == "__main__":
    # Test the brain
    test_prompt = "What is 2+2?"
    try:
        result = call_gemini(test_prompt)
        logger.info(f"Test result: {result}")
    except Exception as e:
        logger.error(f"Test failed: {str(e)}")