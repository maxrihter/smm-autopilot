"""LangGraph wiring: bind the 13 nodes to their dependencies and compile the graph.

Topology (a sequential analysis chain to stay gentle on LLM rate limits):

    ingestion -> filter -> [empty -> cleanup
                            | web_context -> influencer -> competitor -> trend
                              -> synthesis -> strategic -> {ideation, content}
                              -> barrier -> compliance -> report -> cleanup -> END]
"""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING

from langgraph.graph import END, StateGraph

from ..log import get_logger
from ..models.state import PipelineState
from .nodes.cleanup import cleanup_node
from .nodes.competitor import competitor_analyzer_node
from .nodes.compliance import compliance_node
from .nodes.content import content_node
from .nodes.filter import filter_node
from .nodes.ideation import marketing_ideation_node
from .nodes.influencer import influencer_analyzer_node
from .nodes.ingestion import ingestion_node
from .nodes.report import report_node
from .nodes.strategic import strategic_planner_node
from .nodes.synthesis import synthesis_node
from .nodes.trend import trend_analyzer_node
from .nodes.web_context import web_context_node

if TYPE_CHECKING:
    from langgraph.checkpoint.base import BaseCheckpointSaver
    from langgraph.graph.state import CompiledStateGraph

    from ..config import Settings
    from ..llm import LLMRouter
    from ..storage import Store

logger = get_logger(__name__)

_ABORT_STATUSES = frozenset({"empty_filter"})


def _after_filter(state: PipelineState) -> str:
    """Route to cleanup on an abort status (so Apify datasets are still purged)."""
    if state.get("pipeline_status", "") in _ABORT_STATUSES:
        logger.warning("pipeline_aborted", reason=state.get("pipeline_status"))
        return "cleanup"
    return "web_context"


async def _content_barrier(state: PipelineState) -> dict[str, object]:
    """Fan-in barrier so compliance runs exactly once after ideation AND content."""
    return {}


def build_graph(
    settings: Settings,
    router: LLMRouter,
    store: Store,
    checkpointer: BaseCheckpointSaver | None = None,
) -> CompiledStateGraph:
    """Build and compile the pipeline graph with all dependencies bound."""
    builder: StateGraph = StateGraph(PipelineState)

    builder.add_node("ingestion", partial(ingestion_node, settings=settings, store=store))
    builder.add_node("filter", partial(filter_node, settings=settings, router=router))
    builder.add_node("web_context", partial(web_context_node, settings=settings))
    builder.add_node(
        "influencer_analyzer", partial(influencer_analyzer_node, settings=settings, router=router)
    )
    builder.add_node(
        "competitor_analyzer", partial(competitor_analyzer_node, settings=settings, router=router)
    )
    builder.add_node(
        "trend_analyzer", partial(trend_analyzer_node, settings=settings, router=router)
    )
    builder.add_node("synthesis", partial(synthesis_node, settings=settings, router=router))
    builder.add_node(
        "strategic_planner", partial(strategic_planner_node, settings=settings, router=router)
    )
    builder.add_node(
        "marketing_ideation", partial(marketing_ideation_node, settings=settings, router=router)
    )
    builder.add_node("content", partial(content_node, settings=settings, router=router))
    builder.add_node("content_barrier", _content_barrier)
    builder.add_node("compliance", partial(compliance_node, settings=settings, router=router))
    builder.add_node("report", partial(report_node, settings=settings))
    builder.add_node("cleanup", cleanup_node)

    builder.set_entry_point("ingestion")
    builder.add_edge("ingestion", "filter")
    builder.add_conditional_edges("filter", _after_filter, ["web_context", "cleanup"])
    builder.add_edge("web_context", "influencer_analyzer")
    builder.add_edge("influencer_analyzer", "competitor_analyzer")
    builder.add_edge("competitor_analyzer", "trend_analyzer")
    builder.add_edge("trend_analyzer", "synthesis")
    builder.add_edge("synthesis", "strategic_planner")
    builder.add_edge("strategic_planner", "marketing_ideation")
    builder.add_edge("strategic_planner", "content")
    builder.add_edge("marketing_ideation", "content_barrier")
    builder.add_edge("content", "content_barrier")
    builder.add_edge("content_barrier", "compliance")
    builder.add_edge("compliance", "report")
    builder.add_edge("report", "cleanup")
    builder.add_edge("cleanup", END)

    return builder.compile(checkpointer=checkpointer)
