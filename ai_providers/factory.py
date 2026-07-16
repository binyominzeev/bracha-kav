"""
Factory function that instantiates the configured AI provider.

The provider and model are read from environment variables:
    PROVIDER  — one of: openai | anthropic | gemini  (default: openai)
    MODEL     — provider-specific model name
                defaults per provider:
                  openai:    gpt-4o-mini
                  anthropic: claude-haiku-3-5
                  gemini:    gemini-1.5-flash
"""

from __future__ import annotations

import os

from ai_providers.base import BaseAIProvider

_DEFAULTS: dict[str, str] = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-haiku-3-5",
    "gemini": "gemini-1.5-flash",
}


def get_provider() -> BaseAIProvider:
    """Return an initialised provider based on PROVIDER / MODEL env vars."""
    provider_name = os.getenv("PROVIDER", "openai").lower().strip()
    model = os.getenv("MODEL", _DEFAULTS.get(provider_name, "gpt-4o-mini"))

    if provider_name == "openai":
        from ai_providers.openai_provider import OpenAIProvider
        return OpenAIProvider(model=model)
    elif provider_name == "anthropic":
        from ai_providers.anthropic_provider import AnthropicProvider
        return AnthropicProvider(model=model)
    elif provider_name == "gemini":
        from ai_providers.gemini_provider import GeminiProvider
        return GeminiProvider(model=model)
    else:
        raise ValueError(
            f"Unknown PROVIDER={provider_name!r}. "
            "Supported values: openai, anthropic, gemini"
        )
