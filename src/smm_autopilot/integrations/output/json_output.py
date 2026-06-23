"""Render the pipeline Report as structured JSON."""

from __future__ import annotations

from ...models import Report


def render_json(report: Report) -> str:
    """Serialize the full report to indented JSON."""
    return report.model_dump_json(indent=2)
