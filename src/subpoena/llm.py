"""The only door a language model comes through.

Subpoena runs fully offline by default. A model is optional and is never on the
verdict path: it may help *read* a transcript, it never decides what is true.
"""

from __future__ import annotations

import os
from typing import Protocol

DEFAULT_MODEL = "claude-sonnet-5-5"


class LLMClient(Protocol):
    def complete(self, *, system: str, prompt: str, max_tokens: int = 1024) -> str: ...


class StaticLLM:
    """A canned model for tests and offline demos."""

    def __init__(self, reply: str) -> None:
        self._reply = reply
        self.prompts: list[str] = []

    def complete(self, *, system: str, prompt: str, max_tokens: int = 1024) -> str:
        self.prompts.append(prompt)
        return self._reply


class AnthropicLLM:  # pragma: no cover - needs network and credentials
    """Claude via the Anthropic SDK (``pip install subpoena-audit[llm]``)."""

    def __init__(self, model: str | None = None) -> None:
        try:
            import anthropic
        except ImportError as exc:
            raise RuntimeError("install the 'llm' extra to use a live model") from exc
        self._client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment
        self._model = model or os.environ.get("SUBPOENA_LLM_MODEL", DEFAULT_MODEL)

    def complete(self, *, system: str, prompt: str, max_tokens: int = 1024) -> str:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(block.text for block in response.content if block.type == "text")


def llm_from_env() -> LLMClient | None:
    """A live model only when explicitly enabled and credentialed; otherwise None."""
    if os.environ.get("SUBPOENA_LLM", "").lower() != "anthropic":
        return None
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    return AnthropicLLM()  # pragma: no cover
