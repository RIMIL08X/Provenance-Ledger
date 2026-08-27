"""Google Gemini Cloud API Client with rate-limit resiliency and smart model fallbacks."""

import os
import re
from typing import Any, Dict, List, Optional
import requests


class GeminiClient:
    """Client for Google Gemini models with intelligent multi-model fallbacks."""

    DEFAULT_MODEL = "gemini-3.6-flash"

    AVAILABLE_MODELS = [
        "gemini-3.6-flash",
        "gemini-flash-latest",
        "gemini-2.5-flash-lite",
        "gemini-pro-latest",
    ]

    def __init__(self, api_key: Optional[str] = None) -> None:
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")

    def is_available(self) -> bool:
        """Check if Gemini API key is configured."""
        return bool(self.api_key and len(self.api_key) > 5)

    def generate(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.0,
        seed: Optional[int] = None,
    ) -> str:
        """Generate response from Gemini model with multi-model fallback chain."""
        if not self.is_available():
            raise RuntimeError("GEMINI_API_KEY is not configured in .env")

        candidate_models = []
        if model and model in self.AVAILABLE_MODELS:
            candidate_models.append(model)
        for m in self.AVAILABLE_MODELS:
            if m not in candidate_models:
                candidate_models.append(m)

        from google import genai
        from google.genai import types

        client = genai.Client(api_key=self.api_key)

        last_err = None
        for candidate in candidate_models:
            try:
                config = types.GenerateContentConfig(
                    temperature=temperature,
                    seed=seed,
                    system_instruction=system_instruction,
                )
                response = client.models.generate_content(
                    model=candidate,
                    contents=prompt,
                    config=config,
                )
                if response and response.text:
                    return response.text.strip()
            except Exception as e:
                last_err = e
                # Continue down fallback chain on 429, 404, or 503
                continue

        if last_err:
            raise RuntimeError(f"Gemini API failure across models: {str(last_err)}")
        return ""
