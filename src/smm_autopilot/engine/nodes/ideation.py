"""Marketing ideation node: generate campaign/idea concepts from the signals."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from ...llm import LLMRole
from ...log import get_logger
from ...models.marketing_idea import MarketingIdeaSet
from ...prompts import load_prompt
from ..serialize import brand_block, signals_summary

if TYPE_CHECKING:
    from ...config import Settings
    from ...llm import LLMRouter
    from ...models.state import PipelineState

logger = get_logger(__name__)

_TEMPERATURE = 0.7
_RETRY_HINT = (
    "You MUST return at least 3 ideas. Each needs idea_type, topic_category, title, "
    "concept, hook, target_audience, based_on, why_now, 3-5 hashtags, cta, "
    "viral_score, effort, and priority."
)


async def marketing_ideation_node(
    state: PipelineState, *, settings: Settings, router: LLMRouter
) -> dict[str, object]:
    """Generate marketing ideas (carousels, stories, promos, collabs, campaigns)."""
    trends = state.get("trends") or []
    if not trends:
        return {"marketing_ideas": None}

    signals = signals_summary(
        trends,
        state.get("influencer_digest"),
        state.get("competitor_report"),
        state.get("region_context"),
    )
    action_plan = state.get("action_plan")
    extra = ""
    if action_plan and action_plan.recommendations:
        extra = "\n\n=== STRATEGIC ACTIONS ===\n" + "\n".join(
            f"- {r.title} ({r.category})" for r in action_plan.recommendations
        )
    user = f"{brand_block(settings.brand)}\n\n{signals}{extra}"
    messages = [
        {"role": "system", "content": load_prompt("marketing_ideation_system")},
        {"role": "user", "content": user},
    ]
    try:
        result = cast(
            "MarketingIdeaSet | None",
            await router.call_resilient(
                LLMRole.ANALYST,
                MarketingIdeaSet,
                messages,
                nonempty=lambda r: bool(r.ideas),
                retry_hint=_RETRY_HINT,
                temperature=_TEMPERATURE,
                label="ideation",
            ),
        )
    except Exception:
        logger.exception("marketing_ideation_failed")
        return {"marketing_ideas": None}

    if result is not None:
        result.ideas = [i for i in result.ideas if i.concept.strip()]  # drop empty stubs
        for i in result.ideas:
            i.viral_score = max(0.0, min(10.0, i.viral_score))  # clamp to 0-10
            i.suggested_hashtags = i.suggested_hashtags[:5]  # trim to platform cap
        logger.info("marketing_ideation_complete", ideas=len(result.ideas))
    return {"marketing_ideas": result}
