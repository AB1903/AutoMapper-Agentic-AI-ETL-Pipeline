"""
Wrapper around Ollama's local REST API.

  Docker containers reach it via host.docker.internal:11434
  If running outside Docker (local dev), use localhost:11434
"""

import logging
import os
from typing import Optional

import requests
import yaml

log = logging.getLogger(__name__)


def load_config(path: str = "config/config.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


class OllamaClient:
    """
    Simple wrapper around the Ollama REST API.
    Handles prompt sending, response parsing, and error recovery.
    """

    def __init__(self, config_path: str = "config/config.yaml"):
        cfg = load_config(config_path)

        # When running locally (not Docker), override to localhost
        host = os.getenv("OLLAMA_HOST", cfg["ollama"]["host"])

        self.base_url   = host.rstrip("/")
        self.model      = cfg["ollama"]["model"]
        self.temperature = cfg["ollama"]["temperature"]
        self.timeout    = cfg["ollama"]["timeout"]

        log.info("OllamaClient — model: %s | host: %s",
                 self.model, self.base_url)

    def generate(self, prompt: str,
                 system: Optional[str] = None,
                 temperature: Optional[float] = None) -> str:
        """
        Send a prompt to Ollama and return the response text.

        Args:
            prompt:      The user prompt
            system:      Optional system instruction
            temperature: Override default temperature

        Returns:
            Response text string from the model
        """
        payload = {
            "model":  self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature or self.temperature,
                "num_predict": 2048,
            }
        }

        if system:
            payload["system"] = system

        try:
            log.debug("Sending prompt to Ollama (%d chars)", len(prompt))
            response = requests.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=self.timeout
            )
            response.raise_for_status()
            result = response.json().get("response", "").strip()
            log.debug("Ollama response (%d chars)", len(result))
            return result

        except requests.exceptions.ConnectionError:
            raise ConnectionError(
                "Cannot reach Ollama. Make sure it is running:\n"
                "  ollama serve\n"
                "  ollama pull codellama:7b"
            )
        except requests.exceptions.Timeout:
            raise TimeoutError(
                f"Ollama did not respond within {self.timeout}s. "
                "Try a smaller model or reduce prompt size."
            )
        except Exception as e:
            log.error("Ollama error: %s", e)
            raise

    def is_available(self) -> bool:
        """Check if Ollama is running and model is loaded."""
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if resp.status_code != 200:
                return False
            models = [m["name"] for m in resp.json().get("models", [])]
            available = any(self.model.split(":")[0] in m for m in models)
            if not available:
                log.warning("Model %s not found. Run: ollama pull %s",
                            self.model, self.model)
            return available
        except Exception:
            return False

    def list_models(self) -> list:
        """Return list of locally available Ollama models."""
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=5)
            return [m["name"] for m in resp.json().get("models", [])]
        except Exception:
            return []
