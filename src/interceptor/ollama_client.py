"""Client for interacting with local/dockerized Ollama instance."""

import os
from typing import Any, Dict, List, Optional
import requests


class OllamaClient:
    """HTTP client for Ollama LLM runtime."""

    DEFAULT_BASE_URL = "http://localhost:11434"

    # Recommended lightweight models suitable for fast data analysis
    RECOMMENDED_MODELS = [
        "llama3.2:1b",
        "qwen2.5-coder:1.5b",
        "phi3:mini",
        "mistral",
    ]

    def __init__(self, base_url: Optional[str] = None) -> None:
        self.base_url = (base_url or os.getenv("OLLAMA_BASE_URL", self.DEFAULT_BASE_URL)).rstrip("/")

    def is_available(self) -> bool:
        """Check if Ollama service is reachable."""
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=3)
            return resp.status_code == 200
        except Exception:
            return False

    def list_models(self) -> List[str]:
        """List all downloaded models in Ollama."""
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                return [m["name"] for m in data.get("models", [])]
        except Exception:
            pass
        return []

    def pull_model(self, model_name: str) -> bool:
        """Pull/download a model from Ollama library."""
        try:
            resp = requests.post(
                f"{self.base_url}/api/pull",
                json={"name": model_name, "stream": False},
                timeout=300,
            )
            return resp.status_code == 200
        except Exception:
            return False

    def generate(
        self,
        model: str,
        prompt: str,
        system: Optional[str] = None,
        seed: Optional[int] = None,
        temperature: float = 0.0,
    ) -> str:
        """Generate response from an Ollama model."""
        options: Dict[str, Any] = {"temperature": temperature}
        if seed is not None:
            options["seed"] = seed

        payload: Dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": options,
        }
        if system:
            payload["system"] = system

        resp = requests.post(
            f"{self.base_url}/api/generate",
            json=payload,
            timeout=60,
        )
        if resp.status_code == 200:
            return resp.json().get("response", "").strip()
        raise RuntimeError(f"Ollama generation failed ({resp.status_code}): {resp.text}")
