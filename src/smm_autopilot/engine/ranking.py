"""Trend classification + dual ranking — shared by the trend and synthesis nodes.

Niche-relevant trends are ranked first, then general-context ones, capped at the
configured ``top_trends_count``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..config import Settings
    from ..models.trend import TrendReport


def niche_keywords(settings: Settings) -> set[str]:
    """The tenant's niche keywords (L1+L2+L3), lowercased."""
    return {
        kw.lower()
        for kw in (
            *settings.niche.keywords_l1,
            *settings.niche.keywords_l2,
            *settings.niche.keywords_l3,
        )
    }


def classify_is_context(report: TrendReport, keywords: set[str]) -> None:
    """Mark each trend niche-relevant (is_context=False) or general (True)."""
    for trend in report.trends:
        if not keywords:
            trend.is_context = False
            continue
        combined = f"{trend.title.lower()} {trend.description.lower()}"
        trend.is_context = not any(kw in combined for kw in keywords)


def apply_dual_ranking(report: TrendReport, total: int) -> None:
    """Rank niche-relevant trends first, then general-context, capped at ``total``."""
    if total <= 0:
        report.trends = []
        return
    max_context = max(1, total // 3)
    max_niche = max(0, total - max_context)
    niche = sorted(
        (t for t in report.trends if not t.is_context), key=lambda t: t.trend_score, reverse=True
    )
    context = sorted(
        (t for t in report.trends if t.is_context), key=lambda t: t.trend_score, reverse=True
    )
    selected = niche[:max_niche]
    selected += context[: total - len(selected)]
    if len(selected) < total:  # backfill from leftover niche
        selected += niche[max_niche : max_niche + (total - len(selected))]
    for i, trend in enumerate(selected, start=1):
        trend.rank = i
    report.trends = selected
