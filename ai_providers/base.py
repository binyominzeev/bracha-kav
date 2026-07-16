"""
Abstract base interface for AI providers.

Every provider must implement generate_structured(), which sends a prompt
and returns a validated dict conforming to the given JSON schema.
"""

from __future__ import annotations

import abc
from typing import Any


class BaseAIProvider(abc.ABC):
    """Thin adapter interface over different LLM APIs."""

    def __init__(self, model: str) -> None:
        self.model = model

    @abc.abstractmethod
    def generate_structured(
        self,
        prompt: str,
        schema: dict[str, Any],
        *,
        system_prompt: str | None = None,
        temperature: float = 0.2,
    ) -> dict[str, Any]:
        """
        Send *prompt* to the LLM and return a dict validated against *schema*.

        Parameters
        ----------
        prompt:
            The user-facing prompt (may include inline source material).
        schema:
            A JSON Schema dict describing the expected response structure.
        system_prompt:
            Optional system/instruction message prepended to the conversation.
        temperature:
            Sampling temperature — keep low for structured extraction tasks.

        Returns
        -------
        dict
            The parsed and schema-validated response from the model.

        Raises
        ------
        ValueError
            If the model response cannot be parsed or fails schema validation.
        RuntimeError
            On unrecoverable API errors.
        """

    @property
    def provider_name(self) -> str:
        """Human-readable provider name, e.g. 'openai'."""
        return type(self).__name__.replace("Provider", "").lower()
