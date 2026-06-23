"""Report node: assemble the Report and render the deliverable (Markdown + JSON)."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import TYPE_CHECKING

from ...integrations.output import render_json, render_markdown
from ...log import get_logger
from ...models.report import Report

if TYPE_CHECKING:
    from ...config import Settings
    from ...models.state import PipelineState

logger = get_logger(__name__)

_OUTPUT_DIR = Path("output")


def _write_outputs(report: Report, title: str) -> None:
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    # Sanitize run_id before it touches the filesystem (no path traversal/clobber-escape).
    safe_id = re.sub(r"[^A-Za-z0-9_-]", "_", report.run_id)[:64] or "report"
    md_path = _OUTPUT_DIR / f"{safe_id}.md"
    json_path = _OUTPUT_DIR / f"{safe_id}.json"
    md_path.write_text(render_markdown(report, title=title), encoding="utf-8")
    json_path.write_text(render_json(report), encoding="utf-8")


async def report_node(state: PipelineState, *, settings: Settings) -> dict[str, object]:
    """Assemble the final Report and write Markdown + JSON to ``output/``."""
    report = Report(
        run_id=state["run_id"],
        trends=state.get("trends") or [],
        briefs=state.get("briefs") or [],
        total_posts_scraped=len(state.get("raw_posts") or []),
        total_posts_filtered=len(state.get("filtered_posts") or []),
        trend_report=state.get("trend_report"),
        influencer_digest=state.get("influencer_digest"),
        competitor_report=state.get("competitor_report"),
        region_context=state.get("region_context"),
        action_plan=state.get("action_plan"),
        marketing_ideas=state.get("marketing_ideas"),
        compliance_results=state.get("compliance_results") or [],
        rejected_briefs=state.get("rejected_briefs") or [],
        rejected_ideas=state.get("rejected_ideas") or [],
    )

    title = f"{settings.brand.name} — Growth Report"
    await asyncio.to_thread(_write_outputs, report, title)

    logger.info(
        "report_written",
        run_id=report.run_id,
        trends=len(report.trends),
        briefs=len(report.briefs),
        output_dir=str(_OUTPUT_DIR),
    )
    return {"report": report}
