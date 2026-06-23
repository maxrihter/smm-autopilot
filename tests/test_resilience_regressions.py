"""Regression tests for the resilience + recompute hardening: router fallback/retry,
lenient schemas, metric re-attach by title, threshold guards, compliance id-matching,
and run-id sanitization."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import BaseModel

from smm_autopilot.config import Thresholds, default_settings
from smm_autopilot.engine.nodes.compliance import compliance_node
from smm_autopilot.engine.nodes.report import report_node
from smm_autopilot.engine.nodes.synthesis import _restore_metrics
from smm_autopilot.llm import LLMRole, LLMRouter, default_llm_config
from smm_autopilot.models import Brief, ComplianceResult, Trend


class _Out(BaseModel):
    items: list[str] = []


class _FakeChain:
    def __init__(self, sequence: list[object]) -> None:
        self._seq = list(sequence)
        self.calls = 0

    async def ainvoke(self, messages: object) -> object:
        out = self._seq[min(self.calls, len(self._seq) - 1)]
        self.calls += 1
        return out


async def test_call_resilient_retries_primary_without_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # the empty-result retry must fire on the PRIMARY even with no fallback.
    router = LLMRouter(default_llm_config())  # COMPLIANCE role has no fallback
    chain = _FakeChain([_Out(items=[]), _Out(items=["x"])])
    monkeypatch.setattr(router, "get_structured", lambda *a, **k: chain)
    res = await router.call_resilient(
        LLMRole.COMPLIANCE,
        _Out,
        [{"role": "user", "content": "x"}],
        nonempty=lambda r: bool(r.items),
        retry_hint="return at least one",
    )
    assert res is not None
    assert res.items == ["x"]
    assert chain.calls == 2  # primary + one hinted retry, no fallback involved


async def test_call_resilient_returns_none_when_all_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    router = LLMRouter(default_llm_config())
    chain = _FakeChain([_Out(items=[])])
    monkeypatch.setattr(router, "get_structured", lambda *a, **k: chain)
    res = await router.call_resilient(
        LLMRole.COMPLIANCE,
        _Out,
        [{"role": "user", "content": "x"}],
        nonempty=lambda r: bool(r.items),
    )
    assert res is None


def test_synthesis_restore_matches_by_title_not_index() -> None:
    # a reordered LLM response must not attach metrics to the wrong trend.
    orig_a = Trend(rank=1, title="A", description="da", post_count=5)
    orig_b = Trend(rank=2, title="B", description="db", post_count=9)
    enriched = [
        Trend(rank=1, title="B", description="new B", post_count=0),  # reordered: B first
        Trend(rank=2, title="A", description="new A", post_count=0),
    ]
    out = {t.title: t for t in _restore_metrics(enriched, [orig_a, orig_b])}
    assert out["A"].post_count == 5
    assert out["A"].description == "new A"
    assert out["B"].post_count == 9
    assert out["B"].description == "new B"


def test_zero_er_norm_ceiling_rejected() -> None:
    with pytest.raises(ValueError, match="must be > 0"):
        Thresholds(er_norm_ceiling=0.0)


def test_brief_accepts_short_body() -> None:  # lenient schema, no batch-killer
    Brief(title="t", body="short")  # must NOT raise


async def test_compliance_id_match_handles_title_collision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    briefs = [Brief(title="Same", body="a" * 10), Brief(title="Same", body="b" * 10)]

    class _CompOut(BaseModel):
        results: list[ComplianceResult] = []

    async def fake(*a: object, **k: object) -> _CompOut:
        return _CompOut(
            results=[
                ComplianceResult(item_title="b0", passed=True),
                ComplianceResult(item_title="b1", passed=False),
            ]
        )

    router = LLMRouter(default_llm_config())
    monkeypatch.setattr(router, "call_resilient", fake)
    res = await compliance_node(
        {"run_id": "t", "briefs": briefs}, settings=default_settings(), router=router
    )
    assert len(res["approved_briefs"]) == 1  # identical titles did NOT double-approve
    assert res["approved_briefs"][0] is briefs[0]
    assert res["rejected_briefs"] == ["Same"]


async def test_report_sanitizes_run_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    await report_node(
        {"run_id": "../evil", "trends": [], "briefs": []}, settings=default_settings()
    )
    assert not (tmp_path.parent / "evil.md").exists()  # did not escape output/
    assert list((tmp_path / "output").glob("*.md"))  # wrote safely inside output/
