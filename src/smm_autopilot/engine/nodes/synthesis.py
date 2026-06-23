"""Synthesis node: enrich trend descriptions with cross-signal context, then
re-rank deterministically.

The LLM only rewrites text (title/description/hook); every numeric metric is
restored from the trend analyzer's ground truth, so enrichment can't corrupt the
scores. Cross-signal boosts and the final ranking are computed in code.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from pydantic import BaseModel

from ...llm import LLMRole
from ...log import get_logger
from ...models.trend import Trend, TrendReport
from ...prompts import load_prompt
from ..ranking import apply_dual_ranking, classify_is_context, niche_keywords
from ..serialize import signals_summary

if TYPE_CHECKING:
    from ...config import Settings
    from ...llm import LLMRouter
    from ...models.state import PipelineState

logger = get_logger(__name__)

_TEMPERATURE = 0.4
_MAX_SIGNALS = 7  # 4 source types + 3 branches

# Fields owned by code (the trend analyzer) — restored after LLM text enrichment.
_CODE_FIELDS = (
    "engagement_rate",
    "engagement_norm",
    "reach_norm",
    "views_total",
    "likes_total",
    "cross_signal_count",
    "diversity_norm",
    "source_types",
    "example_posts",
    "post_count",
    "top_formats",
    "is_context",
)


class _TrendList(BaseModel):
    trends: list[Trend]


def _restore_metrics(enriched: list[Trend], originals: list[Trend]) -> list[Trend]:
    """Keep LLM text (title/description/hook); restore code-computed numbers.

    Matches enriched->original BY TITLE (the prompt keeps titles + example_posts
    fixed), never by position — so a reordered LLM response can't attach metrics to
    the wrong trend. Originals the LLM dropped or renamed are kept unchanged.
    """
    by_title = {o.title: o for o in originals}
    restored: list[Trend] = []
    used: set[str] = set()
    for e in enriched:
        orig = by_title.get(e.title)
        if orig is None or e.title in used:
            continue
        used.add(e.title)
        restored.append(e.model_copy(update={f: getattr(orig, f) for f in _CODE_FIELDS}))
    restored.extend(o for o in originals if o.title not in used)
    return restored


def _apply_cross_signal_boosts(trends: list[Trend], n_branches: int) -> list[Trend]:
    """Each available branch (+influencer/+competitor/+region) confirms trends."""
    if n_branches == 0:
        return trends
    return [
        t.model_copy(
            update={
                "branch_boost_count": n_branches,
                "diversity_norm": min(1.0, (t.cross_signal_count + n_branches) / _MAX_SIGNALS),
            }
        )
        for t in trends
    ]


async def synthesis_node(
    state: PipelineState, *, settings: Settings, router: LLMRouter
) -> dict[str, object]:
    """Enrich + re-rank trends using all available branch signals."""
    trend_report = state.get("trend_report")
    if trend_report is None or not trend_report.trends:
        return {"trends": []}

    influencer = state.get("influencer_digest")
    competitor = state.get("competitor_report")
    region = state.get("region_context")

    messages = [
        {"role": "system", "content": load_prompt("synthesis_system")},
        {
            "role": "user",
            "content": signals_summary(trend_report.trends, influencer, competitor, region),
        },
    ]
    try:
        result = cast(
            "_TrendList | None",
            await router.call_resilient(
                LLMRole.ANALYST,
                _TrendList,
                messages,
                nonempty=lambda r: bool(r.trends),
                temperature=_TEMPERATURE,
                label="synthesis",
            ),
        )
        enriched = (
            _restore_metrics(result.trends, trend_report.trends)
            if result
            else list(trend_report.trends)
        )
    except Exception:
        logger.exception("synthesis_failed")
        enriched = list(trend_report.trends)

    n_branches = sum(x is not None for x in (influencer, competitor, region))
    boosted = _apply_cross_signal_boosts(enriched, n_branches)

    temp = TrendReport(trends=boosted)
    classify_is_context(temp, niche_keywords(settings))
    apply_dual_ranking(temp, settings.thresholds.top_trends_count)
    logger.info("synthesis_complete", trends=len(temp.trends), branches=n_branches)
    return {"trends": temp.trends}
