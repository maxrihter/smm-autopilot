"""Graph wiring — the graph compiles with all nodes, and live-scrape guards on token."""

from __future__ import annotations

from pathlib import Path

import pytest

from smm_autopilot.config import default_settings
from smm_autopilot.engine.graph import build_graph
from smm_autopilot.engine.scrape import collect_datasets
from smm_autopilot.llm import LLMRouter, default_llm_config
from smm_autopilot.storage import Store

_EXPECTED_NODES = {
    "ingestion",
    "filter",
    "web_context",
    "influencer_analyzer",
    "competitor_analyzer",
    "trend_analyzer",
    "synthesis",
    "strategic_planner",
    "marketing_ideation",
    "content",
    "compliance",
    "report",
    "cleanup",
}


def test_build_graph_compiles_with_all_nodes() -> None:
    store = Store(":memory:")
    graph = build_graph(default_settings(), LLMRouter(default_llm_config()), store)
    nodes = set(graph.get_graph().nodes)
    assert _EXPECTED_NODES <= nodes
    store.close()


async def test_collect_datasets_requires_token() -> None:
    # No APIFY_TOKEN configured → a live run must fail clearly, not silently no-op.
    with pytest.raises(RuntimeError, match="APIFY_TOKEN"):
        await collect_datasets(default_settings())


def test_username_strips_query_and_path() -> None:
    # natural copy-paste URLs (trailing ?query) must not become bogus handles.
    from smm_autopilot.config import AccountEntry
    from smm_autopilot.engine.scrape import _username

    def u(url: str) -> str:
        return _username(AccountEntry(name="x", instagram_url=url))

    assert u("https://www.instagram.com/foo/") == "foo"
    assert u("https://instagram.com/foo/?hl=en") == "foo"
    assert u("https://www.instagram.com/@bar") == "bar"
    assert u("https://www.instagram.com/") == ""  # dropped by the empty filter


def test_cli_run_missing_config_exits_cleanly(tmp_path: Path) -> None:
    # the documented `run` must not dump a raw traceback on a missing config.
    from typer.testing import CliRunner

    from smm_autopilot.cli import app

    result = CliRunner().invoke(app, ["run", "--config", str(tmp_path / "nope.yaml")])
    assert result.exit_code == 1
    assert "Config not found" in result.output
