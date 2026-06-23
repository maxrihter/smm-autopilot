"""LLM router — config + resilience logic (no real provider clients built)."""

from __future__ import annotations

import pytest

from smm_autopilot.llm import LLMRole, LLMRouter, default_llm_config, is_transient_error
from smm_autopilot.models import Trend


def test_default_config_has_all_roles() -> None:
    cfg = default_llm_config()
    assert cfg.filter.primary.provider == "anthropic"
    assert cfg.analyst.primary.model
    assert cfg.compliance.primary.provider == "anthropic"


def test_router_missing_fallback_raises() -> None:
    router = LLMRouter(default_llm_config())
    # compliance has no fallback configured -> requesting one is an error
    with pytest.raises(ValueError, match="no fallback"):
        router.get_structured(LLMRole.COMPLIANCE, Trend, fallback=True)


def test_is_transient_error_detects_transient() -> None:
    assert is_transient_error(RuntimeError("Rate limit exceeded (429)"))
    assert is_transient_error(TimeoutError("read timeout while calling model"))
    assert is_transient_error(RuntimeError("anthropic overloaded_error, retry later"))


def test_is_transient_error_ignores_real_bugs() -> None:
    assert not is_transient_error(ValueError("schema validation failed"))
    assert not is_transient_error(KeyError("missing field"))
    # Regression: the substring trap — these must NOT be read as transient.
    assert not is_transient_error(ValueError("field 'timeout' must be positive"))
    assert not is_transient_error(RuntimeError("error code 429 is reserved"))
