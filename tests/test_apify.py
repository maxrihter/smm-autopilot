"""Apify client — module imports cleanly and the retry predicate behaves.

The import assertion is a regression guard: the client previously imported
``ApifyApiError`` from the wrong (private) module path and failed to import at
all, which no test caught.
"""

from __future__ import annotations

from smm_autopilot.integrations import apify_client


def test_module_imports() -> None:
    assert callable(apify_client.fetch_dataset)
    assert callable(apify_client.run_actor)


def test_is_retryable_false_for_non_apify_error() -> None:
    assert apify_client._is_retryable(ValueError("boom")) is False
