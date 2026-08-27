"""Google Gemini Cloud API Client for ultra-fast data science agent reasoning."""

import os
import re
from typing import Any, Dict, List, Optional
import requests


class GeminiClient:
    """Client for Google Gemini models via official SDK or high-performance REST fallback."""

    DEFAULT_MODEL = "gemini-1.5-flash"

    AVAILABLE_MODELS = [
        "gemini-1.5-flash",
        "gemini-2.0-flash",
        "gemini-1.5-pro",
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
        """Generate response from Gemini model."""
        if not self.is_available():
            raise RuntimeError("GEMINI_API_KEY is not configured in .env")

        target_model = model or self.DEFAULT_MODEL
        # Normalize model string
        if not target_model.startswith("gemini-"):
            target_model = "gemini-1.5-flash"

        # Try google.genai SDK first
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=self.api_key)
            config = types.GenerateContentConfig(
                temperature=temperature,
                seed=seed,
                system_instruction=system_instruction,
            )
            response = client.models.generate_content(
                model=target_model,
                contents=prompt,
                config=config,
            )
            if response.text:
                return response.text.strip()
        except Exception:
            pass

        # High-performance Direct REST API Fallback
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{target_model}:generateContent?key={self.api_key}"
        headers = {"Content-Type": "application/json"}
        
        contents = [{"parts": [{"text": prompt}]}]
        body: Dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
            }
        }
        if seed is not None:
            body["generationConfig"]["seed"] = seed
        if system_instruction:
            body["systemInstruction"] = {"parts": [{"text": system_instruction}]}

        resp = requests.post(url, headers=headers, json=body, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            candidates = data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    return parts[0].get("text", "").strip()
            return ""
        else:
            raise RuntimeError(f"Gemini API error ({resp.status_code}): {resp.text}")
