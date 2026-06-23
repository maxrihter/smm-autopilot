"""Strategic planner node: turn the synthesized signals into an ActionPlan."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from ...llm import LLMRole
from ...log import get_logger
from ...models.action_plan import ActionPlan
from ...prompts import load_prompt
from ..serialize import brand_block, signals_summary

if TYPE_CHECKING:
    from ...config import Settings
    from ...llm import LLMRouter
    from ...models.state import PipelineState

logger = get_logger(__name__)

_TEMPERATURE = 0.5
_RETRY_HINT = (
    "You MUST return at least 3 recommendations. Each needs title, scenario "
    "(a full, executable plan), rationale, urgency, category, and inspired_by."
)


async def strategic_planner_node(
    state: PipelineState, *, settings: Settings, router: LLMRouter
) -> dict[str, object]:
    """Produce 5-7 actionable, on-brand strategic recommendations."""
    trends = state.get("trends") or []
    if not trends:
        return {"action_plan": None}

    signals = signals_summary(
        trends,
        state.get("influencer_digest"),
        state.get("competitor_report"),
        state.get("region_context"),
    )
    user = f"{brand_block(settings.brand)}\n\n{signals}"
    messages = [
        {"role": "system", "content": load_prompt("strategic_planner_system")},
        {"role": "user", "content": user},
    ]
    try:
        result = cast(
            "ActionPlan | None",
            await router.call_resilient(
                LLMRole.ANALYST,
                ActionPlan,
                messages,
                nonempty=lambda r: bool(r.recommendations),
                retry_hint=_RETRY_HINT,
                temperature=_TEMPERATURE,
                label="strategic",
            ),
        )
    except Exception:
        logger.exception("strategic_planner_failed")
        return {"action_plan": None}

    if result is not None:
        result.recommendations = [r for r in result.recommendations if r.scenario.strip()]
        logger.info("strategic_planner_complete", recommendations=len(result.recommendations))
    return {"action_plan": result}
