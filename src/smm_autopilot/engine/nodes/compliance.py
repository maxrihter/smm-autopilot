"""Compliance node: the safety/brand gate.

Reviews every generated brief and idea against the tenant's safety + brand rules
and returns one verdict per item. Items that pass are marked approved; the rest
are tracked as rejected. Fails CLOSED — if the gate can't run, nothing is
auto-approved (a content item only ships once it has explicitly passed).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from pydantic import BaseModel

from ...llm import LLMRole
from ...log import get_logger
from ...models.compliance import ComplianceResult
from ...prompts import load_prompt
from ..serialize import brand_block

if TYPE_CHECKING:
    from ...config import Settings
    from ...llm import LLMRouter
    from ...models.brief import Brief
    from ...models.marketing_idea import MarketingIdea
    from ...models.state import PipelineState

logger = get_logger(__name__)


class _ComplianceOutput(BaseModel):
    results: list[ComplianceResult]


def _build_items(briefs: list[Brief], ideas: list[MarketingIdea]) -> str:
    blocks: list[str] = []
    for idx, b in enumerate(briefs):
        blocks.append(
            f"id: b{idx}\ntitle: {b.title}\nformat: {b.format}\nhook: {b.hook}\n"
            f"body: {b.body}\ncta: {b.cta}\nhashtags: {', '.join(b.hashtags)}"
        )
    for idx, i in enumerate(ideas):
        blocks.append(
            f"id: i{idx}\ntitle: {i.title}\ntype: {i.idea_type}\nconcept: {i.concept}\ncta: {i.cta}"
        )
    return "\n\n---\n\n".join(blocks)


async def compliance_node(
    state: PipelineState, *, settings: Settings, router: LLMRouter
) -> dict[str, object]:
    """Gate briefs + ideas; mark approved, track rejected."""
    briefs: list[Brief] = state.get("briefs") or []
    ideas_set = state.get("marketing_ideas")
    ideas: list[MarketingIdea] = ideas_set.ideas if ideas_set else []

    if not briefs and not ideas:
        return {
            "approved_briefs": [],
            "compliance_results": [],
            "rejected_briefs": [],
            "rejected_ideas": [],
        }

    user = (
        f"{brand_block(settings.brand)}\n\n"
        "Review each item below. Return exactly one result per item. Set `item_title` "
        "to the item's `id` (e.g. b0, i2) copied EXACTLY, plus passed (bool), checks "
        "(per-rule bools), and a one-sentence suggestion if it fails.\n\n"
        f"{_build_items(briefs, ideas)}"
    )
    messages = [
        {"role": "system", "content": load_prompt("compliance_system")},
        {"role": "user", "content": user},
    ]
    try:
        result = cast(
            "_ComplianceOutput | None",
            await router.call_resilient(
                LLMRole.COMPLIANCE,
                _ComplianceOutput,
                messages,
                nonempty=lambda r: bool(r.results),
                temperature=0.0,
                label="compliance",
            ),
        )
    except Exception:
        logger.exception("compliance_failed")
        result = None

    if result is None:
        logger.warning("compliance_unavailable_failing_closed")
        return {
            "briefs": briefs,
            "approved_briefs": [],
            "compliance_results": [],
            "rejected_briefs": [b.title for b in briefs],
            "rejected_ideas": [i.title for i in ideas],
        }

    # Match verdicts to items by stable id (b0/i1...), not title — avoids
    # collisions and title-drift; brief and idea id namespaces stay separate.
    passed = {r.item_title.strip() for r in result.results if r.passed}
    id_to_title = {f"b{idx}": b.title for idx, b in enumerate(briefs)}
    id_to_title.update({f"i{idx}": i.title for idx, i in enumerate(ideas)})
    for r in result.results:  # restore human titles for the deliverable
        r.item_title = id_to_title.get(r.item_title.strip(), r.item_title)

    approved_briefs = [b for idx, b in enumerate(briefs) if f"b{idx}" in passed]
    for b in approved_briefs:
        b.approved = True
    rejected_briefs = [b.title for idx, b in enumerate(briefs) if f"b{idx}" not in passed]
    rejected_ideas = [i.title for idx, i in enumerate(ideas) if f"i{idx}" not in passed]
    logger.info(
        "compliance_complete",
        approved=len(approved_briefs),
        rejected_briefs=len(rejected_briefs),
        rejected_ideas=len(rejected_ideas),
    )
    return {
        # Re-write the briefs channel explicitly (approved flags set in place) so the
        # report's view is well-defined under any checkpointer — not reference-aliased.
        "briefs": briefs,
        "approved_briefs": approved_briefs,
        "compliance_results": result.results,
        "rejected_briefs": rejected_briefs,
        "rejected_ideas": rejected_ideas,
    }
