"""
Anthropic (Claude) provider implementation.

Requires: ANTHROPIC_API_KEY environment variable.
Install:   pip install anthropic
"""

from __future__ import annotations

import json
import os
from typing import Any

from ai_providers.base import BaseAIProvider


class AnthropicProvider(BaseAIProvider):
    """Calls the Anthropic Messages API, requesting JSON output."""

    # Prefix added to every prompt to reliably elicit JSON output from Claude.
    _JSON_INSTRUCTION = (
        "\n\nRespond ONLY with valid JSON matching the requested schema. "
        "Do not include any prose, markdown fences, or explanation."
    )

    def __init__(self, model: str = "claude-haiku-3-5") -> None:
        super().__init__(model=model)
        try:
            import anthropic  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "anthropic package is required. Install with: pip install anthropic"
            ) from exc
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY environment variable is not set.")
        self._client = anthropic.Anthropic(api_key=api_key)

    def generate_structured(
        self,
        prompt: str,
        schema: dict[str, Any],
        *,
        system_prompt: str | None = None,
        temperature: float = 0.2,
    ) -> dict[str, Any]:
        system = (system_prompt or "") + self._JSON_INSTRUCTION
        response = self._client.messages.create(
            model=self.model,
            max_tokens=4096,
            temperature=temperature,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text if response.content else ""
        # Strip accidental markdown fences
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
                f"Anthropic returned invalid JSON: {exc}\nRaw: {raw!r}"
            ) from exc
        return result
