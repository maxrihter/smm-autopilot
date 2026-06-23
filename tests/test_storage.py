"""Storage layer — dedup + delta on an in-memory SQLite store (no keys, no I/O)."""

from __future__ import annotations

from datetime import UTC, datetime

from smm_autopilot.storage import Store, filter_new_posts_by_delta


def test_dedup_filters_seen_urls() -> None:
    store = Store(":memory:")
    urls = ["https://a", "https://b", "https://c"]
    assert store.filter_new_urls(urls) == urls  # nothing seen yet
    store.mark_urls_seen(["https://a", "https://b"])
    assert store.filter_new_urls(urls) == ["https://c"]
    store.close()


def test_dedup_handles_large_batches() -> None:
    # Exceeds SQLite's pre-3.32 999-variable cap — exercises the IN-list chunking.
    store = Store(":memory:")
    urls = [f"https://x/{i}" for i in range(2500)]
    assert store.filter_new_urls(urls) == urls
    store.mark_urls_seen(urls[:1000])
    assert len(store.filter_new_urls(urls)) == 1500
    store.close()


def test_delta_state_roundtrip() -> None:
    store = Store(":memory:")
    assert store.get_last_scraped(["acct"]) == {}
    store.update_scrape_state([("acct", "post123", 5)])
    last = store.get_last_scraped(["acct"])
    assert "acct" in last
    assert last["acct"].tzinfo is not None
    store.close()


def test_filter_new_posts_by_delta_keeps_newer() -> None:
    cutoff = datetime(2026, 1, 1, tzinfo=UTC)
    posts = [
        {"id": "old", "timestamp": "2025-12-01T00:00:00Z"},
        {"id": "new", "timestamp": "2026-02-01T00:00:00Z"},
        {"id": "unparseable", "timestamp": "not-a-date"},
    ]
    kept = filter_new_posts_by_delta(posts, "acct", {"acct": cutoff})
    ids = {p["id"] for p in kept}
    assert "new" in ids
    assert "old" not in ids
    assert "unparseable" in ids  # kept — normalizer handles it


def test_filter_new_posts_by_delta_passthrough_when_unknown() -> None:
    posts = [{"id": "x", "timestamp": "2026-02-01T00:00:00Z"}]
    assert filter_new_posts_by_delta(posts, "unknown", {}) == posts
