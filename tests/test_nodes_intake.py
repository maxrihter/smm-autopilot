"""Intake nodes — filter empty-passthrough and web_context event/news resolution.

These run offline (no API keys): filter early-returns before any LLM call, and
web_context's news fetch is empty with no feeds configured.
"""

from __future__ import annotations

from datetime import date, timedelta

from smm_autopilot.config import EventConfig, default_settings
from smm_autopilot.engine.nodes.filter import filter_node
from smm_autopilot.engine.nodes.web_context import web_context_node
from smm_autopilot.llm import LLMRouter, default_llm_config


async def test_filter_empty_raw_is_empty_filter() -> None:
    out = await filter_node(
        {"dataset_ids": [], "run_id": "t", "raw_posts": []},  # type: ignore[typeddict-item]
        settings=default_settings(),
        router=LLMRouter(default_llm_config()),
    )
    assert out["pipeline_status"] == "empty_filter"


async def test_web_context_resolves_upcoming_event() -> None:
    today = date.today()
    soon = today + timedelta(days=5)
    settings = default_settings()
    settings.region.events = [EventConfig(name="Soon Day", month=soon.month, day=soon.day)]
    out = await web_context_node({"dataset_ids": [], "run_id": "t"}, settings=settings)  # type: ignore[arg-type]
    ctx = out["region_context"]
    assert "Soon Day" in [e.name for e in ctx.upcoming_events]  # type: ignore[attr-defined]


async def test_web_context_no_sources_is_empty() -> None:
    out = await web_context_node({"dataset_ids": [], "run_id": "t"}, settings=default_settings())  # type: ignore[arg-type]
    ctx = out["region_context"]
    assert ctx.news_headlines == []  # type: ignore[attr-defined]
    assert ctx.upcoming_events == []  # type: ignore[attr-defined]
