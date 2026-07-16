"""
OpenAI provider implementation.

Requires: OPENAI_API_KEY environment variable.
Install:   pip install openai
"""

from __future__ import annotations

import json
import os
from typing import Any

from ai_providers.base import BaseAIProvider


class OpenAIProvider(BaseAIProvider):
    """Calls the OpenAI Chat Completions API with JSON-mode output."""

    def __init__(self, model: str = "gpt-4o-mini") -> None:
        super().__init__(model=model)
        try:
            from openai import OpenAI  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "openai package is required. Install with: pip install openai"
            ) from exc
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY environment variable is not set.")
        self._client = OpenAI(api_key=api_key)

    def generate_structured(
        self,
        prompt: str,
        schema: dict[str, Any],
        *,
        system_prompt: str | None = None,
        temperature: float = 0.2,
    ) -> dict[str, Any]:
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content or ""
        try:
            result = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"OpenAI returned invalid JSON: {exc}\nRaw: {raw!r}") from exc
        return result
