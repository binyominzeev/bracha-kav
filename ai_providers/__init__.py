"""
AI provider package.

Usage:
    from ai_providers import get_provider
    provider = get_provider()           # reads PROVIDER / MODEL from env
    result = provider.generate_structured(prompt, schema)
"""

from ai_providers.base import BaseAIProvider
from ai_providers.factory import get_provider

__all__ = ["BaseAIProvider", "get_provider"]
