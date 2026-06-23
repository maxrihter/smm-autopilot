"""Cleanup node: end-of-run marker for Apify dataset hygiene.

``fetch_dataset`` deletes each Apify dataset right after a successful read (so
scraped data never lingers on Apify's servers), making this a belt-and-suspenders
terminal node that records completion.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...log import get_logger

if TYPE_CHECKING:
    from ...models.state import PipelineState

logger = get_logger(__name__)


async def cleanup_node(state: PipelineState) -> dict[str, object]:
    """Record run completion (datasets are already deleted at fetch time)."""
    logger.info("cleanup_done", datasets=len(state.get("dataset_ids") or []))
    return {"cleanup_done": True}
