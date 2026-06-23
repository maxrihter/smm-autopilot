"""Content node: generate ready-to-shoot content briefs from the top trends."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from pydantic import BaseModel

from ...llm import LLMRole
from ...log import get_logger
from ...models.brief import Brief
from ...prompts import load_prompt
from ..serialize import brand_block, signals_summary

if TYPE_CHECKING:
    from ...config import Settings
    from ...llm import LLMRouter
    from ...models.state import PipelineState

logger = get_logger(__name__)

_TEMPERATURE = 0.6
_RETRY_HINT = (
    "You MUST return at least 2 briefs. Each needs title, format, topic_category, "
    "trend_reference, hook, body (the full post script), cta, and 3-5 hashtags."
)


class _BriefList(BaseModel):
    briefs: list[Brief]


async def content_node(
    state: PipelineState, *, settings: Settings, router: LLMRouter
) -> dict[str, object]:
    """Generate content briefs for the top trends."""
    trends = state.get("trends") or []
    if not trends:
        return {"briefs": []}

    n = settings.thresholds.briefs_count
    signals = signals_summary(
        trends[: max(5, n)], state.get("influencer_digest"), None, state.get("region_context")
    )
    user = (
        f"{brand_block(settings.brand)}\n\n"
        f"Produce {n} content briefs from the strongest trends.\n\n{signals}"
    )
    messages = [
        {"role": "system", "content": load_prompt("content_system")},
        {"role": "user", "content": user},
    ]
    try:
        result = cast(
            "_BriefList | None",
            await router.call_resilient(
                LLMRole.ANALYST,
                _BriefList,
                messages,
                nonempty=lambda r: bool(r.briefs),
                retry_hint=_RETRY_HINT,
                temperature=_TEMPERATURE,
                label="content",
            ),
        )
    except Exception:
        logger.exception("content_failed")
        return {"briefs": []}

    briefs = result.briefs if result else []
    briefs = [b for b in briefs if b.body.strip()]  # drop empty-body stubs
    for b in briefs:
        b.hashtags = b.hashtags[:5]  # trim to platform cap
    logger.info("content_complete", briefs=len(briefs))
    return {"briefs": briefs}
