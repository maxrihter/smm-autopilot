"""Generation + gate nodes — offline behavior (skip-on-empty, fail-closed
compliance, report writes the deliverable). No API keys: LLM calls aren't reached."""

from __future__ import annotations

from pathlib import Path

import pytest

from smm_autopilot.config import default_settings
from smm_autopilot.engine.nodes.cleanup import cleanup_node
from smm_autopilot.engine.nodes.compliance import compliance_node
from smm_autopilot.engine.nodes.content import content_node
from smm_autopilot.engine.nodes.ideation import marketing_ideation_node
from smm_autopilot.engine.nodes.report import report_node
from smm_autopilot.engine.nodes.strategic import strategic_planner_node
from smm_autopilot.engine.nodes.synthesis import synthesis_node
from smm_autopilot.llm import LLMRouter, default_llm_config


async def test_synthesis_skips_without_trends() -> None:
    out = await synthesis_node(
        {"dataset_ids": [], "run_id": "t"},  # type: ignore[arg-type]
        settings=default_settings(),
        router=LLMRouter(default_llm_config()),
    )
    assert out["trends"] == []


async def test_generation_nodes_skip_without_trends() -> None:
    s, r = default_settings(), LLMRouter(default_llm_config())
    base = {"dataset_ids": [], "run_id": "t", "trends": []}
    assert (await strategic_planner_node(base, settings=s, router=r))["action_plan"] is None  # type: ignore[arg-type]
    assert (await content_node(base, settings=s, router=r))["briefs"] == []  # type: ignore[arg-type]
    assert (await marketing_ideation_node(base, settings=s, router=r))["marketing_ideas"] is None  # type: ignore[arg-type]


async def test_compliance_empty_input_returns_empty() -> None:
    out = await compliance_node(
        {"dataset_ids": [], "run_id": "t"},  # type: ignore[arg-type]
        settings=default_settings(),
        router=LLMRouter(default_llm_config()),
    )
    assert out["approved_briefs"] == []
    assert out["rejected_briefs"] == []


async def test_cleanup_marks_done() -> None:
    out = await cleanup_node({"dataset_ids": ["a", "b"], "run_id": "t"})  # type: ignore[arg-type]
    assert out["cleanup_done"] is True


async def test_report_writes_markdown_and_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    out = await report_node(
        {"dataset_ids": [], "run_id": "demo-x", "trends": [], "briefs": []},  # type: ignore[arg-type]
        settings=default_settings("Barkwell"),
    )
    assert out["report"].run_id == "demo-x"  # type: ignore[attr-defined]
    assert (tmp_path / "output" / "demo-x.md").exists()
    assert (tmp_path / "output" / "demo-x.json").exists()
