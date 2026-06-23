"""SQLite-backed durable state: URL dedup + per-account scrape deltas.

A single local file (default ``data/state.db``). Operations are tiny and
synchronous — fine to call from async nodes.
Pass ``":memory:"`` for an ephemeral store (used by the demo and tests).
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from ..log import get_logger

logger = get_logger(__name__)

_DEDUP_TTL_DAYS = 7
_TS_FMT = "%Y-%m-%d %H:%M:%S"
# Stay under SQLite's pre-3.32 SQLITE_MAX_VARIABLE_NUMBER (999) so large dedup /
# delta lookups never raise "too many SQL variables" on older bundled libsqlite.
_SQL_VARS_PER_QUERY = 900


def _chunks(seq: list[str], size: int) -> list[list[str]]:
    return [seq[i : i + size] for i in range(0, len(seq), size)]


class Store:
    """Durable dedup + delta state on SQLite."""

    def __init__(self, db_path: str | Path = "data/state.db") -> None:
        self._path = str(db_path)
        if self._path != ":memory:":
            Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.execute("PRAGMA busy_timeout=5000")  # wait out a concurrent writer
        if self._path != ":memory:":
            self._conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS seen_urls (
                url TEXT PRIMARY KEY,
                seen_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_seen_urls_at ON seen_urls(seen_at);
            CREATE TABLE IF NOT EXISTS account_scrape_state (
                account_url TEXT PRIMARY KEY,
                last_post_id TEXT,
                posts_seen INTEGER NOT NULL DEFAULT 0,
                last_scraped_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            """
        )
        self._conn.commit()

    # ------------------------------------------------------------------ dedup
    def filter_new_urls(self, urls: list[str]) -> list[str]:
        """Return only the URLs not already in ``seen_urls``."""
        if not urls:
            return []
        existing: set[str] = set()
        for batch in _chunks(urls, _SQL_VARS_PER_QUERY):
            placeholders = ",".join("?" * len(batch))
            rows = self._conn.execute(
                f"SELECT url FROM seen_urls WHERE url IN ({placeholders})", batch
            ).fetchall()
            existing.update(r[0] for r in rows)
        new_urls = [u for u in urls if u not in existing]
        logger.info("dedup_filter", total=len(urls), existing=len(existing), new=len(new_urls))
        return new_urls

    def mark_urls_seen(self, urls: list[str]) -> None:
        """Record URLs as seen (ignoring duplicates)."""
        if not urls:
            return
        self._conn.executemany(
            "INSERT OR IGNORE INTO seen_urls (url) VALUES (?)", [(u,) for u in urls]
        )
        self._conn.commit()
        logger.info("dedup_mark", count=len(urls))

    def purge_old_urls(self, ttl_days: int = _DEDUP_TTL_DAYS) -> int:
        """Delete dedup entries older than ``ttl_days``. Returns rows deleted."""
        cutoff = (datetime.now(tz=UTC) - timedelta(days=ttl_days)).strftime(_TS_FMT)
        cur = self._conn.execute("DELETE FROM seen_urls WHERE seen_at < ?", (cutoff,))
        self._conn.commit()
        logger.info("dedup_purge", deleted=cur.rowcount)
        return cur.rowcount

    # ------------------------------------------------------------------ delta
    def get_last_scraped(self, account_urls: list[str]) -> dict[str, datetime]:
        """Return ``{account_url: last_scraped_at}`` for known accounts (UTC-aware)."""
        if not account_urls:
            return {}
        result: dict[str, datetime] = {}
        for batch in _chunks(account_urls, _SQL_VARS_PER_QUERY):
            placeholders = ",".join("?" * len(batch))
            rows = self._conn.execute(
                f"SELECT account_url, last_scraped_at FROM account_scrape_state "
                f"WHERE account_url IN ({placeholders})",
                batch,
            ).fetchall()
            for url, ts in rows:
                try:
                    dt = datetime.fromisoformat(ts)
                except (ValueError, TypeError):
                    continue
                result[url] = dt if dt.tzinfo else dt.replace(tzinfo=UTC)
        return result

    def update_scrape_state(self, updates: list[tuple[str, str, int]]) -> None:
        """Upsert scrape state for accounts: ``(account_url, last_post_id, posts_seen)``."""
        if not updates:
            return
        now = datetime.now(tz=UTC).strftime(_TS_FMT)
        for account_url, last_post_id, posts_seen in updates:
            self._conn.execute(
                """
                INSERT INTO account_scrape_state
                    (account_url, last_post_id, posts_seen, last_scraped_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(account_url) DO UPDATE SET
                    last_post_id = excluded.last_post_id,
                    last_scraped_at = excluded.last_scraped_at,
                    posts_seen = account_scrape_state.posts_seen + excluded.posts_seen
                """,
                (account_url, last_post_id, posts_seen, now),
            )
        self._conn.commit()
        logger.info("delta_update", accounts=len(updates))

    def close(self) -> None:
        self._conn.close()


def filter_new_posts_by_delta(
    posts: list[dict],
    account_url: str,
    last_scraped: dict[str, datetime],
) -> list[dict]:
    """Keep only raw Apify posts newer than this account's last scrape.

    Returns all posts if the account hasn't been scraped before. Pure CPU,
    intentionally synchronous. Unparseable timestamps are kept (the normalizer
    handles them downstream).
    """
    cutoff = last_scraped.get(account_url)
    if cutoff is None:
        return posts

    new_posts: list[dict] = []
    for post in posts:
        ts_raw = post.get("timestamp", "")
        try:
            ts = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=UTC)
            if ts > cutoff:
                new_posts.append(post)
        except (ValueError, AttributeError, TypeError):
            new_posts.append(post)

    logger.info(
        "delta_filter",
        account=account_url,
        total=len(posts),
        new=len(new_posts),
        cutoff=cutoff.isoformat(),
    )
    return new_posts
