"""LangGraph checkpointer factory."""

from __future__ import annotations


def get_checkpointer():
    """Return a LangGraph checkpointer.

    Defaults to an in-memory saver: the engine runs a pipeline end-to-end in a
    single invocation, so cross-restart checkpoint persistence isn't needed.
    (Durable dedup/delta state lives in the SQLite ``Store`` instead.)

    To make runs resumable across restarts, swap in langgraph's
    ``AsyncSqliteSaver`` or ``AsyncPostgresSaver`` here.
    """
    from langgraph.checkpoint.memory import MemorySaver

    return MemorySaver()
