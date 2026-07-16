"""
Google Gemini provider implementation.

Requires: GOOGLE_API_KEY environment variable.
Install:   pip install google-generativeai
"""

from __future__ import annotations

import json
import os
from typing import Any

from ai_providers.base import BaseAIProvider


class GeminiProvider(BaseAIProvider):
    """Calls the Google Generative AI (Gemini) API with JSON output."""

    _JSON_INSTRUCTION = (
        "\n\nRespond ONLY with valid JSON matching the requested schema. "
        "Do not include any prose, markdown fences, or explanation."
    )

    def __init__(self, model: str = "gemini-1.5-flash") -> None:
        super().__init__(model=model)
        try:
            import google.generativeai as genai  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "google-generativeai package is required. "
                "Install with: pip install google-generativeai"
            ) from exc
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError("GOOGLE_API_KEY environment variable is not set.")
        genai.configure(api_key=api_key)
        self._genai = genai
        self._model_name = model

    def generate_structured(
        self,
        prompt: str,
        schema: dict[str, Any],
        *,
        system_prompt: str | None = None,
        temperature: float = 0.2,
    ) -> dict[str, Any]:
        import google.generativeai as genai  # type: ignore[import]

        system = (system_prompt or "") + self._JSON_INSTRUCTION
        model = genai.GenerativeModel(
            model_name=self._model_name,
            system_instruction=system,
            generation_config=genai.GenerationConfig(
                temperature=temperature,
                response_mime_type="application/json",
            ),
        )
        response = model.generate_content(prompt)
        raw = response.text or ""
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```", 2)[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.rsplit("```", 1)[0].strip()
        try:
            result = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Gemini returned invalid JSON: {exc}\nRaw: {raw!r}"
            ) from exc
        return result
