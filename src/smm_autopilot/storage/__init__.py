"""State storage — SQLite by default, optional Postgres.

Backs URL dedup and per-account scrape deltas (the ``Store``), plus a LangGraph
checkpointer factory.
"""

from .checkpoint import get_checkpointer
from .store import Store, filter_new_posts_by_delta

__all__ = ["Store", "filter_new_posts_by_delta", "get_checkpointer"]
