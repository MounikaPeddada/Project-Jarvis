import os
import time
import logging
import requests
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
CONNECT_TIMEOUT = 3                                   # offline server fails in 3s
READ_TIMEOUT = float(os.getenv("OLLAMA_TIMEOUT", "120"))  # first call loads the model


class BrainOfflineError(RuntimeError):
    """Raised when the local Ollama server or model is unavailable."""


def check_server() -> None:
    """Raise a clear error if Ollama is down or the model isn't installed."""
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=CONNECT_TIMEOUT)
        r.raise_for_status()
    except requests.exceptions.RequestException as e:
        raise BrainOfflineError(
            f"Ollama is not running at {OLLAMA_URL}. Start it with `ollama serve`."
        ) from e
    installed = [m["name"] for m in r.json().get("models", [])]
    if MODEL not in installed and f"{MODEL}:latest" not in installed:
        raise BrainOfflineError(f"Model '{MODEL}' not installed. Run: ollama pull {MODEL}")


def call_llm(prompt: str, system: str | None = None,
             temperature: float = 0.2, max_tokens: int = 300) -> str:
    """Send one prompt to the local Ollama model and return the reply text."""
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("Prompt must be a non-empty string")

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": MODEL,
        "messages": messages,
        "stream": False,
        "keep_alive": "30m",              # keep the model in VRAM between commands
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
            "num_ctx": 4096,
        },
    }

    start = time.time()
    try:
        r = requests.post(f"{OLLAMA_URL}/api/chat", json=payload,
                          timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))
    except requests.exceptions.ConnectionError as e:
        raise BrainOfflineError(
            f"Ollama is not running at {OLLAMA_URL}. Start it with `ollama serve`."
        ) from e
    except requests.exceptions.Timeout as e:
        raise BrainOfflineError(f"Ollama did not answer within {READ_TIMEOUT:.0f}s.") from e

    if r.status_code == 404:
        raise BrainOfflineError(f"Model '{MODEL}' not found. Run: ollama pull {MODEL}")
    if r.status_code >= 400:
        raise RuntimeError(f"Ollama error {r.status_code}: {r.text[:200]}")

    text = r.json()["message"]["content"].strip()
    logger.info(f"Local LLM replied in {time.time() - start:.2f}s")
    return text


def warm_up() -> None:
    """
    Load the model into VRAM now so the first user command isn't slow.
    Sends a tiny prompt (max 1 token) just to force Ollama to load the model.
    """
    try:
        logger.info("🔥 Warming up the local model (loading into VRAM)...")
        start = time.time()
        call_llm("hi", max_tokens=1)
        logger.info(f"✅ Model warmed up in {time.time() - start:.2f}s and ready!")
    except Exception as e:
        logger.warning(f"⚠️ Warm-up failed: {e}")


# Backward compatibility: agent.py still imports call_gemini
call_gemini = call_llm


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    check_server()
    print("Testing model...")
    print(call_llm("What is 2+2? Answer in one word."))