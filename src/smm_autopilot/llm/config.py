"""LLM router configuration.

Populated from the ``llm:`` block of ``tenant.yaml`` or ``default_llm_config()`` for
the demo/tests. Three roles — filter / analyst / compliance — each map to a primary
provider with an optional fallback.
"""

from __future__ import annotations

import os
from typing import Literal

from pydantic import BaseModel

Provider = Literal["anthropic", "openai", "mistral", "google"]

# Default env var holding each provider's API key.
_DEFAULT_KEY_ENV: dict[str, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "google": "GOOGLE_API_KEY",
}


class ProviderConfig(BaseModel):
    """One provider+model endpoint for a pipeline role."""

    provider: Provider
    model: str
    api_key_env: str = ""  # defaults to the provider's standard env var
    base_url_env: str = "OPENAI_BASE_URL"  # only used by the openai-compatible provider
    max_tokens: int = 8192
    timeout: int = 120
    max_retries: int = 3

    def key_env(self) -> str:
        return self.api_key_env or _DEFAULT_KEY_ENV[self.provider]


class RoleConfig(BaseModel):
    """Primary + optional fallback provider for a single role."""

    primary: ProviderConfig
    fallback: ProviderConfig | None = None


class LLMConfig(BaseModel):
    """Role -> provider mapping for the three pipeline roles."""

    filter: RoleConfig
    analyst: RoleConfig
    compliance: RoleConfig


def default_llm_config() -> LLMConfig:
    """A runnable default (Anthropic-only) so the engine works with a single
    ``ANTHROPIC_API_KEY``.

    The shipped example tenant's ``llm:`` block shows how to mix providers
    and add fallbacks. An OpenAI-compatible analyst fallback is wired
    automatically when ``OPENAI_API_KEY`` is present (covers OpenAI / Ollama /
    imago.market).
    """
    sonnet = ProviderConfig(provider="anthropic", model="claude-sonnet-4-6")
    haiku = ProviderConfig(provider="anthropic", model="claude-haiku-4-5-20251001")
    openai_fallback = (
        ProviderConfig(provider="openai", model="gpt-4o-mini")
        if os.environ.get("OPENAI_API_KEY")
        else None
    )
    return LLMConfig(
        filter=RoleConfig(primary=haiku),
        analyst=RoleConfig(primary=sonnet, fallback=openai_fallback),
        compliance=RoleConfig(primary=sonnet),
    )
