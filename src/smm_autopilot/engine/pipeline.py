"""End-to-end pipeline entrypoint: build dependencies, invoke the graph."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from ..llm import LLMRouter
from ..log import get_logger
from ..storage import Store, get_checkpointer
from .graph import build_graph

if TYPE_CHECKING:
    from ..config import Settings
    from ..models.report import Report

logger = get_logger(__name__)


async def run_pipeline(
    settings: Settings,
    *,
    dataset_ids: list[str],
    source_map: dict[str, str] | None = None,
    run_id: str | None = None,
    store: Store | None = None,
    router: LLMRouter | None = None,
) -> Report | None:
    """Run the full pipeline over the given Apify dataset ids; return the Report
    (or ``None`` if the run aborted before producing one)."""
    run_id = run_id or uuid.uuid4().hex[:12]
    owns_store = store is None
    store = store or Store()
    try:
        router = router or LLMRouter(settings.llm)
        graph = build_graph(settings, router, store, get_checkpointer())
        state: dict[str, object] = {"dataset_ids": dataset_ids, "run_id": run_id}
        if source_map is not None:
            state["source_map"] = source_map
        logger.info("pipeline_start", run_id=run_id, datasets=len(dataset_ids))
        result = await graph.ainvoke(state, config={"configurable": {"thread_id": run_id}})
        return result.get("report")
    finally:
        if owns_store:
            store.close()
