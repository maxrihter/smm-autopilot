"""Filter node: keep only relevant, non-spam posts (LLM relevance gate).

A cost/relevance gate, not a safety gate — when in doubt it keeps the post and
lets downstream stages decide. A cheap engagement pre-filter trims obvious
low-signal posts before any LLM call.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential

from ...llm import LLMRole
from ...log import get_logger
from ...prompts import load_prompt

if TYPE_CHECKING:
    from ...config import Settings
    from ...llm import LLMRouter
    from ...models.post import Post
    from ...models.state import PipelineState

logger = get_logger(__name__)

_BATCH_SIZE = 15
_EVENT_HORIZON_DAYS = 21


class _PostClassification(BaseModel):
    post_id: str
    relevant: bool
    reason: str = ""


class _FilterOutput(BaseModel):
    results: list[_PostClassification]


def _seasonal_context(settings: Settings) -> str:
    """A short date/season block injected into the filter prompt."""
    today = datetime.now(tz=UTC).date()
    lines = [f"Current date: {today.isoformat()}."]
    soon: list[str] = []
    for ev in settings.region.events:
        days = (ev.next_occurrence(today) - today).days
        if days <= _EVENT_HORIZON_DAYS:
            soon.append(f"{ev.name} (in {days}d)")
    if soon:
        lines.append(
            "Upcoming events: " + ", ".join(soon) + ". Related posts are more likely relevant."
        )
    return "\n".join(lines)


@retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=2, min=4, max=30), reraise=True)
async def _classify_batch(
    posts: list[Post], system_prompt: str, router: LLMRouter
) -> list[_PostClassification]:
    chain = router.get_structured(LLMRole.FILTER, _FilterOutput)
    batch_text = "\n\n".join(
        f"post_id: {p.id}\ncaption: {p.caption or ''}\n"
        f"views: {p.videoPlayCount}\nlikes: {p.likesCount}\ncomments: {p.commentsCount}"
        for p in posts
    )
    result: _FilterOutput | None = await chain.ainvoke(  # type: ignore[attr-defined]
        [{"role": "system", "content": system_prompt}, {"role": "user", "content": batch_text}]
    )
    # On a parse miss, pass posts through as relevant (this is a relevance gate,
    # not a safety gate) and let downstream stages decide.
    if result is None or not result.results:
        logger.warning("filter_batch_passthrough", batch_size=len(posts))
        return [
            _PostClassification(post_id=p.id, relevant=True, reason="passthrough") for p in posts
        ]
    return result.results


async def filter_node(
    state: PipelineState, *, settings: Settings, router: LLMRouter
) -> dict[str, object]:
    """Filter ``raw_posts`` down to relevant, non-spam posts."""
    all_raw: list[Post] = state.get("raw_posts") or []
    if not all_raw:
        return {"filtered_posts": [], "pipeline_status": "empty_filter"}

    # Competitor posts bypass the filter — analyzed separately.
    non_competitor = [p for p in all_raw if p.source != "competitor"]

    # Source-aware engagement pre-filter (Reels by views, others by likes).
    posts_to_filter: list[Post] = []
    for p in non_competitor:
        min_views, min_likes = settings.thresholds.engagement_floor(p.source)
        passed = (
            p.videoPlayCount >= min_views if p.videoPlayCount > 0 else p.likesCount >= min_likes
        )
        if passed:
            posts_to_filter.append(p)

    if not posts_to_filter:
        return {"filtered_posts": [], "pipeline_status": "empty_filter"}

    system_prompt = f"## CONTEXT\n{_seasonal_context(settings)}\n\n{load_prompt('filter_system')}"
    batches = [
        posts_to_filter[i : i + _BATCH_SIZE] for i in range(0, len(posts_to_filter), _BATCH_SIZE)
    ]
    results = await asyncio.gather(
        *[_classify_batch(b, system_prompt, router) for b in batches],
        return_exceptions=True,
    )

    # Fail-open (matches the parse-miss passthrough): a batch that exhausts its
    # retries keeps its posts as relevant rather than killing the whole node.
    relevant_ids: set[str] = set()
    for batch, res in zip(batches, results, strict=True):
        if isinstance(res, BaseException):
            logger.warning("filter_batch_failed_passthrough", error=str(res)[:150])
            relevant_ids.update(p.id for p in batch)
        else:
            relevant_ids.update(c.post_id for c in res if c.relevant)
    filtered = [p for p in posts_to_filter if p.id in relevant_ids]

    cap = settings.thresholds.max_posts_after_filter
    if len(filtered) > cap:
        filtered.sort(key=lambda p: (p.videoPlayCount or 0) + (p.likesCount or 0), reverse=True)
        filtered = filtered[:cap]

    logger.info(
        "filter_complete", raw=len(all_raw), candidates=len(posts_to_filter), filtered=len(filtered)
    )
    if not filtered:
        return {"filtered_posts": [], "pipeline_status": "empty_filter"}
    return {"filtered_posts": filtered}
