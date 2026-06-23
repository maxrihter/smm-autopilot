"""Output adapters — Markdown + JSON rendering of a Report."""

from __future__ import annotations

import json

from smm_autopilot.integrations.output import render_json, render_markdown
from smm_autopilot.models import Brief, Report, Trend


def _sample_report() -> Report:
    return Report(
        run_id="demo-1",
        total_posts_scraped=120,
        total_posts_filtered=80,
        trends=[
            Trend(
                rank=1,
                title="Fresh-food unboxing",
                description="Creators filming the first-bowl reaction drive saves.",
                post_count=12,
                engagement_norm=0.8,
                reach_norm=0.6,
                diversity_norm=0.5,
                engagement_rate=0.052,
                views_total=45000,
                top_formats=["Reel"],
            )
        ],
        briefs=[
            Brief(
                title="First bowl reaction",
                topic_category="product",
                trend_reference="Fresh-food unboxing",
                hook="Her face when the bowl hits the floor.",
                body="x" * 450,
                cta="Try the sampler box",
                hashtags=["dogfood", "freshdogfood", "puppylove"],
            )
        ],
    )


def test_render_markdown_has_sections() -> None:
    md = render_markdown(_sample_report(), title="Barkwell — Growth Report")
    assert "# Barkwell — Growth Report" in md
    assert "## 📈 Trends" in md
    assert "Fresh-food unboxing" in md
    assert "## ✍️ Content briefs" in md
    assert md.endswith("\n")


def test_render_json_is_valid() -> None:
    payload = render_json(_sample_report())
    data = json.loads(payload)
    assert data["run_id"] == "demo-1"
    assert data["trends"][0]["rank"] == 1
