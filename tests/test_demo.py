"""Demo mode runs the FULL pipeline end-to-end on fixtures, no API keys."""

from __future__ import annotations

from pathlib import Path

import pytest


async def test_demo_runs_end_to_end_without_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    # Prove no keys are needed — delete any that happen to be in the env.
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("APIFY_TOKEN", raising=False)

    from smm_autopilot.engine.demo import run_demo

    report = await run_demo()
    assert report is not None
    assert report.trends  # the analysis chain produced trends
    assert report.briefs  # content produced briefs
    assert all(b.approved for b in report.briefs)  # compliance approved them
    assert report.competitor_report is not None
    assert report.marketing_ideas is not None
    assert report.region_context is not None
    assert report.region_context.upcoming_events  # regional section renders
    # trends must have distinct scores (not byte-identical canned filler)
    scores = {t.trend_score_display for t in report.trends}
    assert len(scores) > 1
    assert (tmp_path / "output" / "demo.md").exists()
    assert (tmp_path / "output" / "demo.json").exists()
